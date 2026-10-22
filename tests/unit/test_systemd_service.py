"""Tests for the systemd --user backend: the rendered unit (env lines only when set), install and uninstall argv and
files, the lifecycle calls, `systemctl show` parsing for active and inactive units, the stale check, and the service
command's backend choice (systemd on Linux, launchd on macOS). Every systemctl call goes through a fake runner and
HOME is a temp folder, so nothing touches the real user units."""

import os
import stat
import sys
import time
import unittest
from unittest import mock

from roadmap.errors import EXIT_EXTERNAL, EXIT_NOT_FOUND, RoadmapError
from roadmap.services import launchd, systemd
from roadmap.commands import service as service_cmd
from tests.unit.test_launchd_support import FakeRunner, answer_for, envelope
from tests.unit.test_store_support import HomeCase

SHOW_ACTIVE = "ActiveState=active\nMainPID=4242\nExecMainStatus=0\nLoadState=loaded\n"
SHOW_INACTIVE = "ActiveState=inactive\nMainPID=0\nExecMainStatus=0\nLoadState=loaded\n"
SHOW_ARGV = ["systemctl", "--user", "show", "helm.service", "-p", "ActiveState,MainPID,ExecMainStatus,LoadState"]
ENV_KEYS = ("ROADMAP_BIND_HOST", "ROADMAP_PUBLIC_HOST", "ROADMAP_HOME")


def _without_roadmap_env():
    """A patch of os.environ that drops the ROADMAP_* variables, so the host's own settings never leak into renders."""
    return mock.patch.dict(os.environ, {key: "" for key in ENV_KEYS}, clear=False)


class UnitCase(HomeCase):
    """HomeCase (temp HOME and ROADMAP_HOME) with no ROADMAP_* host variables set."""

    def setUp(self):
        super().setUp()
        env = _without_roadmap_env()
        env.start()
        self.addCleanup(env.stop)
        for key in ENV_KEYS:
            os.environ.pop(key, None)

    def fake(self, handler=None):
        """A fake systemctl runner; also installed as the systemd RUNNER for the rest of the test."""
        fake = FakeRunner(handler)
        patcher = mock.patch.object(systemd, "RUNNER", fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        return fake


class RenderTests(UnitCase):
    def test_unit_has_the_fixed_sections_and_no_optional_env_lines(self):
        text = systemd.render_unit(repo="/opt/helm", env={})
        lines = text.splitlines()
        self.assertIn("[Unit]", lines)
        self.assertIn("Description=Helm dashboard", lines)
        self.assertIn("After=network-online.target", lines)
        self.assertIn("WorkingDirectory=/opt/helm", lines)
        self.assertIn("Environment=PYTHONUNBUFFERED=1", lines)
        self.assertIn("ExecStart=/opt/helm/bin/roadmap serve --no-phone", lines)
        self.assertIn("Restart=on-failure", lines)
        self.assertIn("RestartSec=5", lines)
        self.assertIn("WantedBy=default.target", lines)
        self.assertEqual([line for line in lines if line.startswith("Environment=ROADMAP_")], [])

    def test_env_lines_appear_only_for_variables_that_are_set(self):
        text = systemd.render_unit(repo="/opt/helm", env={"ROADMAP_BIND_HOST": "0.0.0.0", "OTHER": "x"})
        lines = text.splitlines()
        self.assertIn("Environment=ROADMAP_BIND_HOST=0.0.0.0", lines)
        self.assertNotIn("Environment=ROADMAP_PUBLIC_HOST=", "\n".join(lines))
        self.assertNotIn("Environment=ROADMAP_HOME=", "\n".join(lines))
        self.assertNotIn("Environment=OTHER=x", lines)

    def test_all_three_env_lines_when_all_are_set(self):
        env = {"ROADMAP_BIND_HOST": "127.0.0.1", "ROADMAP_PUBLIC_HOST": "helm.mjplabs.ir",
               "ROADMAP_HOME": "/srv/helm"}
        lines = systemd.render_unit(repo="/opt/helm", env=env).splitlines()
        self.assertIn("Environment=ROADMAP_BIND_HOST=127.0.0.1", lines)
        self.assertIn("Environment=ROADMAP_PUBLIC_HOST=helm.mjplabs.ir", lines)
        self.assertIn("Environment=ROADMAP_HOME=/srv/helm", lines)

    def test_a_value_with_spaces_is_quoted_and_percent_is_escaped(self):
        lines = systemd.render_unit(repo="/opt/my helm", env={"ROADMAP_HOME": "/srv/a b%c"}).splitlines()
        self.assertIn('Environment="ROADMAP_HOME=/srv/a b%%c"', lines)
        self.assertIn('ExecStart="/opt/my helm/bin/roadmap" serve --no-phone', lines)

    def test_env_defaults_to_os_environ(self):
        with mock.patch.dict(os.environ, {"ROADMAP_BIND_HOST": "10.0.0.5"}):
            text = systemd.render_unit(repo="/opt/helm")
        self.assertIn("Environment=ROADMAP_BIND_HOST=10.0.0.5", text.splitlines())


class InstallTests(UnitCase):
    def test_install_writes_the_unit_then_reloads_and_enables_now(self):
        fake = self.fake()
        path = systemd.install(runner=fake)
        self.assertEqual(path, systemd.plist_path())
        self.assertEqual(path, os.path.join(os.path.expanduser("~"), ".config", "systemd", "user", "helm.service"))
        self.assertEqual(fake.calls, [
            ["systemctl", "--user", "daemon-reload"],
            ["systemctl", "--user", "enable", "--now", "helm.service"],
        ])
        with open(path, "r", encoding="utf-8") as fh:
            self.assertIn("ExecStart=", fh.read())
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o644)

    def test_install_writes_the_env_line_when_the_variable_is_set(self):
        with mock.patch.dict(os.environ, {"ROADMAP_BIND_HOST": "0.0.0.0"}):
            systemd.install(runner=self.fake())
        with open(systemd.plist_path(), "r", encoding="utf-8") as fh:
            self.assertIn("Environment=ROADMAP_BIND_HOST=0.0.0.0", fh.read().splitlines())

    def test_enable_failure_is_an_external_error(self):
        fake = self.fake(answer_for(systemctl={"rc": 1, "err": "Failed to enable unit\nmore"}))
        with self.assertRaises(RoadmapError) as ctx:
            systemd.install(runner=fake)
        self.assertEqual(ctx.exception.code, "external")
        self.assertEqual(ctx.exception.exit, EXIT_EXTERNAL)


class UninstallTests(UnitCase):
    def test_uninstall_disables_removes_the_file_and_reloads(self):
        os.makedirs(os.path.dirname(systemd.plist_path()), exist_ok=True)
        with open(systemd.plist_path(), "w", encoding="utf-8") as fh:
            fh.write("[Unit]\n")
        fake = self.fake()
        self.assertIs(systemd.uninstall(runner=fake), True)
        self.assertFalse(os.path.exists(systemd.plist_path()))
        self.assertEqual(fake.calls, [
            ["systemctl", "--user", "disable", "--now", "helm.service"],
            ["systemctl", "--user", "daemon-reload"],
        ])

    def test_uninstall_without_a_file_is_quiet(self):
        def handler(argv):
            if "disable" in argv:
                return (1, "", "Unit helm.service does not exist")
            return (0, "", "")

        fake = self.fake(handler)
        self.assertIs(systemd.uninstall(runner=fake), False)
        self.assertEqual(fake.calls[-1], ["systemctl", "--user", "daemon-reload"])

    def test_a_disable_failure_keeps_the_file(self):
        os.makedirs(os.path.dirname(systemd.plist_path()), exist_ok=True)
        with open(systemd.plist_path(), "w", encoding="utf-8") as fh:
            fh.write("[Unit]\n")
        fake = self.fake(answer_for(systemctl={"rc": 1, "err": "boom"}))
        with self.assertRaises(RoadmapError):
            systemd.uninstall(runner=fake)
        self.assertTrue(os.path.exists(systemd.plist_path()))


class LifecycleTests(UnitCase):
    def _install_file(self):
        os.makedirs(os.path.dirname(systemd.plist_path()), exist_ok=True)
        with open(systemd.plist_path(), "w", encoding="utf-8") as fh:
            fh.write("[Unit]\n")

    def test_start_stop_restart_argv(self):
        self._install_file()
        fake = self.fake()
        systemd.start(runner=fake)
        systemd.stop(runner=fake)
        systemd.restart(runner=fake)
        self.assertEqual(fake.calls, [
            ["systemctl", "--user", "start", "helm.service"],
            ["systemctl", "--user", "stop", "helm.service"],
            ["systemctl", "--user", "restart", "helm.service"],
        ])

    def test_start_and_restart_need_the_unit_file(self):
        fake = self.fake()
        for call in (systemd.start, systemd.restart):
            with self.assertRaises(RoadmapError) as ctx:
                call(runner=fake)
            self.assertEqual(ctx.exception.code, "not_found")
            self.assertEqual(ctx.exception.exit, EXIT_NOT_FOUND)
        self.assertEqual(fake.calls, [])

    def test_stop_of_an_unknown_unit_is_not_an_error(self):
        fake = self.fake(answer_for(systemctl={"rc": 5, "err": "not loaded"}))
        systemd.stop(runner=fake)

    def test_start_failure_is_an_error(self):
        self._install_file()
        fake = self.fake(answer_for(systemctl={"rc": 1, "err": "Job failed"}))
        with self.assertRaises(RoadmapError):
            systemd.start(runner=fake)


class StatusTests(UnitCase):
    def test_active_unit_reports_loaded_state_and_pid(self):
        fake = self.fake(answer_for(systemctl={"rc": 0, "out": SHOW_ACTIVE}))
        info = systemd.status(runner=fake)
        self.assertEqual(fake.calls, [SHOW_ARGV])
        self.assertEqual(info["label"], "helm.service")
        self.assertEqual(info["plist"], systemd.plist_path())
        self.assertIs(info["plistInstalled"], False)
        self.assertIs(info["loaded"], True)
        self.assertEqual(info["state"], "active")
        self.assertEqual(info["pid"], 4242)
        self.assertEqual(info["lastExitCode"], "0")
        self.assertIsNone(info["runs"])

    def test_inactive_unit_is_not_loaded_and_has_no_pid(self):
        fake = self.fake(answer_for(systemctl={"rc": 0, "out": SHOW_INACTIVE}))
        info = systemd.status(runner=fake)
        self.assertIs(info["loaded"], False)
        self.assertEqual(info["state"], "inactive")
        self.assertIsNone(info["pid"])

    def test_failed_show_gives_not_loaded(self):
        fake = self.fake(answer_for(systemctl={"rc": 1, "err": "no bus"}))
        info = systemd.status(runner=fake)
        self.assertIs(info["loaded"], False)
        self.assertIsNone(info["state"])

    def test_parse_show_reads_key_value_lines(self):
        fields = systemd.parse_show("ActiveState=active\nnot a pair\nMainPID=7\n")
        self.assertEqual(fields, {"ActiveState": "active", "MainPID": "7"})


class StaleTests(UnitCase):
    def _repo_with_web_file(self, mtime):
        repo = os.path.join(self.tmp, "repo")
        os.makedirs(os.path.join(repo, "web"))
        path = os.path.join(repo, "web", "app.js")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("x\n")
        os.utime(path, (mtime, mtime))
        return repo

    def _runner(self, started_at):
        stamp = time.strftime("%a %b %d %H:%M:%S %Y", time.localtime(started_at))

        def handler(argv):
            if argv[0] == "ps":
                return (0, stamp + "\n", "")
            return (0, SHOW_ACTIVE, "") if argv[:3] == ["systemctl", "--user", "show"] else (1, "", "unexpected")

        return self.fake(handler)

    def test_stale_when_a_watched_file_is_newer_than_the_process(self):
        repo = self._repo_with_web_file(mtime=2000)
        result = systemd.stale(runner=self._runner(started_at=1000), repo=repo)
        self.assertIs(result["stale"], True)
        self.assertEqual(result["pid"], 4242)

    def test_not_stale_when_the_process_started_after_the_change(self):
        repo = self._repo_with_web_file(mtime=2000)
        result = systemd.stale(runner=self._runner(started_at=3000), repo=repo)
        self.assertIs(result["stale"], False)

    def test_not_loaded_is_never_stale(self):
        fake = self.fake(answer_for(systemctl={"rc": 0, "out": SHOW_INACTIVE}))
        self.assertIs(systemd.stale(runner=fake, repo=self.tmp)["stale"], False)


class CommandBackendTests(UnitCase):
    def test_linux_uses_systemd_and_darwin_uses_launchd(self):
        with mock.patch.object(sys, "platform", "linux"):
            self.assertIs(service_cmd.backend(), systemd)
        with mock.patch.object(sys, "platform", "darwin"):
            self.assertIs(service_cmd.backend(), launchd)

    def test_status_on_linux_goes_through_systemctl_show(self):
        fake = self.fake(answer_for(systemctl={"rc": 0, "out": SHOW_INACTIVE}))
        with mock.patch.object(sys, "platform", "linux"):
            code, body = envelope(["service", "status"])
        self.assertEqual(code, 0)
        self.assertIs(body["data"]["loaded"], False)
        self.assertEqual(fake.calls, [SHOW_ARGV])

    def test_install_on_linux_writes_the_unit_and_enables_it(self):
        fake = self.fake(answer_for(systemctl={"rc": 0, "out": SHOW_ACTIVE}))
        with mock.patch.object(sys, "platform", "linux"):
            code, body = envelope(["service", "install"])
        self.assertEqual(code, 0, body)
        self.assertEqual(body["data"]["plist"], systemd.plist_path())
        self.assertIs(body["data"]["loaded"], True)
        self.assertEqual(fake.calls[0], ["systemctl", "--user", "daemon-reload"])
        self.assertEqual(fake.calls[1], ["systemctl", "--user", "enable", "--now", "helm.service"])


if __name__ == "__main__":
    unittest.main()
