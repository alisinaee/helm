"""Tests for the plist: the rendered keys, XML escaping, the 0644 mode, and plutil -lint on a temp file."""

import os
import plistlib
import stat
import unittest

from roadmap.services import launchd
from tests.unit.test_launchd_support import FakeRunner, LaunchdCase


class PlistContentTests(LaunchdCase):
    def render(self, repo="/Users/test/Works/roadmap-board"):
        text = launchd.render_plist(python="/usr/bin/python3", repo=repo, logs_dir="/Users/test/Logs/rb")
        return plistlib.loads(text.encode("utf-8"))

    def test_keys_match_the_agreed_agent_definition(self):
        data = self.render()
        self.assertEqual(data["Label"], "com.roadmap-board.agent")
        self.assertEqual(data["ProgramArguments"], ["/usr/bin/python3", "-m", "roadmap", "serve"])
        self.assertEqual(data["EnvironmentVariables"], {"PYTHONPATH": "/Users/test/Works/roadmap-board"})
        self.assertEqual(data["WorkingDirectory"], "/Users/test/Works/roadmap-board")
        self.assertIs(data["RunAtLoad"], True)
        self.assertIs(data["KeepAlive"], True)
        self.assertEqual(data["ThrottleInterval"], 10)
        self.assertEqual(data["ProcessType"], "Interactive")
        self.assertEqual(data["LimitLoadToSessionType"], "Aqua")

    def test_launchd_output_files_are_in_the_logs_folder(self):
        data = self.render()
        self.assertEqual(data["StandardOutPath"], "/Users/test/Logs/rb/launchd.out")
        self.assertEqual(data["StandardErrorPath"], "/Users/test/Logs/rb/launchd.err")

    def test_values_are_xml_escaped(self):
        repo = "/Users/test/a&b<c>d"
        data = self.render(repo=repo)
        self.assertEqual(data["WorkingDirectory"], repo)
        self.assertEqual(data["EnvironmentVariables"]["PYTHONPATH"], repo)

    def test_install_writes_the_plist_with_mode_0644_in_the_agents_folder(self):
        fake = self.use_runner(FakeRunner())
        path = launchd.install(python="/usr/bin/python3", logs_dir=self.logs)
        self.assertEqual(path, os.path.join(self.agents, "com.roadmap-board.agent.plist"))
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o644)
        with open(path, "rb") as fh:
            self.assertEqual(plistlib.loads(fh.read())["Label"], "com.roadmap-board.agent")
        self.assertTrue(fake.calls)  # the fake, not launchctl, handled the lifecycle calls


@unittest.skipUnless(os.path.exists("/usr/bin/plutil"), "plutil is only on macOS")
class PlutilLintTests(LaunchdCase):
    """plutil runs only on plists written into the test's temp folder."""

    def test_rendered_plist_lints_ok(self):
        path = os.path.join(self.tmp, "good.plist")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(launchd.render_plist(python="/usr/bin/python3", repo=self.tmp, logs_dir=self.logs))
        ok, message = launchd.lint_plist(path, runner=launchd._default_runner)
        self.assertTrue(ok, message)

    def test_broken_plist_fails_lint(self):
        path = os.path.join(self.tmp, "bad.plist")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("<plist><dict><key>Label</key></dict>")
        ok, _ = launchd.lint_plist(path, runner=launchd._default_runner)
        self.assertFalse(ok)


class LintWithFakeRunnerTests(unittest.TestCase):
    def test_lint_reports_failure_text_from_the_runner(self):
        fake = FakeRunner(lambda argv: (1, "", "Property List error: bad token"))
        ok, message = launchd.lint_plist("/tmp/x/anything.plist", runner=fake)
        self.assertFalse(ok)
        self.assertEqual(message, "Property List error: bad token")
        self.assertEqual(fake.calls, [["/usr/bin/plutil", "-lint", "/tmp/x/anything.plist"]])


if __name__ == "__main__":
    unittest.main()
