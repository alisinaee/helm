"""Flow 2: a human clicks Stop in the GUI. The agent's Edit is denied, the roadmap reads stay allowed, Resume from the
GUI lets the same call through again, and an agent shell cannot resume, change a limit or override."""

import os
import unittest

from tests.integration.harness import stack


class StopFlowTests(unittest.TestCase):
    def test_gui_stop_denies_edits_and_resume_allows_them_again(self):
        sandbox, server = stack(self)
        self.assertIsNone(sandbox.hook("Edit", {"file_path": "docs/tasks.json"}))

        stopped = server.cmd("control.stop", {})
        self.assertTrue(stopped["ok"])
        self.assertTrue(os.path.exists(sandbox.sentinel))

        for tool, tool_input in (("Edit", {"file_path": "x.md"}), ("Write", {"file_path": "y.md"}),
                                 ("Bash", {"command": "npm test"}), ("Agent", {"prompt": "work"})):
            reply = sandbox.hook(tool, tool_input)
            self.assertIsNotNone(reply, tool)
            self.assertEqual(reply["hookSpecificOutput"]["permissionDecision"], "deny")
            self.assertIn("stopped by user", reply["hookSpecificOutput"]["permissionDecisionReason"])

        for command in ("roadmap status", "roadmap inbox", "roadmap ask list", "roadmap rules show"):
            self.assertIsNone(sandbox.hook("Bash", {"command": command}), command)
            proc = sandbox.cli(command.split()[1:], agent=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)

        self.assertIsNone(sandbox.hook("Read", {"file_path": "docs/tasks.json"}))

        resumed = server.cmd("control.resume", {})
        self.assertTrue(resumed["ok"])
        self.assertFalse(os.path.exists(sandbox.sentinel))
        self.assertIsNone(sandbox.hook("Edit", {"file_path": "x.md"}))

    def test_an_agent_shell_cannot_resume_change_a_limit_or_override(self):
        sandbox, server = stack(self)
        server.cmd("control.stop", {})
        for args in (["resume"], ["override", "--hours", "1"], ["limit", "set", "--scope", "global",
                                                              "--window", "day", "--pct", "10"]):
            proc = sandbox.cli(args, agent=True)
            self.assertEqual(proc.returncode, 4, (args, proc.stderr))
            self.assertIn("next: ", proc.stderr, args)  # one line: "roadmap: <why>. next: <command>"
        self.assertTrue(os.path.exists(sandbox.sentinel))

        proc = sandbox.cli(["resume"])  # the same command from a human shell is allowed
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse(os.path.exists(sandbox.sentinel))

    def test_the_gui_resume_is_not_refused_as_an_agent(self):
        sandbox, server = stack(self)
        server.cmd("control.stop", {})
        self.assertEqual(server.cmd("control.resume", {})["ok"], True)


if __name__ == "__main__":
    unittest.main()
