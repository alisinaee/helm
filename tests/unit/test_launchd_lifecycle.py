"""Tests for the launchd lifecycle: the exact launchctl argv for install, uninstall, start, stop, restart and status,
status parsing, the launchd log truncation, the log tail and follow, and the service command envelope."""

import os
import unittest
from unittest import mock

from roadmap.errors import EXIT_EXTERNAL, EXIT_NOT_FOUND, RoadmapError
from roadmap.services import launchd
from tests.unit.test_launchd_support import SAMPLE_PRINT, FakeRunner, LaunchdCase, answer_for, envelope, run_cli

NOT_LOADED = {"rc": 113, "err": "Could not find service"}
LOADED = {"rc": 0, "out": SAMPLE_PRINT}


def lc(print_answer, **others):
    """Answer launchctl print with print_answer; every other launchctl subcommand succeeds unless named in others."""

    def handler(argv):
        if argv[0] != "launchctl":
            return (1, "", "unexpected tool " + argv[0])
        if argv[1] == "print":
            return (print_answer["rc"], print_answer.get("out", ""), print_answer.get("err", ""))
        spec = others.get(argv[1], {})
        return (spec.get("rc", 0), spec.get("out", ""), spec.get("err", ""))

    return handler


class InstallTests(LaunchdCase):
    def test_install_bootouts_then_bootstraps_the_plist(self):
        fake = FakeRunner()
        path = launchd.install(python="/usr/bin/python3", runner=fake, logs_dir=self.logs)
        self.assertEqual(fake.calls, [
            ["launchctl", "bootout", self.target()],
            ["launchctl", "bootstrap", self.domain(), path],
        ])

    def test_bootstrap_failure_is_external_exit_6_with_the_launchctl_line(self):
        fake = FakeRunner(answer_for(launchctl={"rc": 5, "err": "Bootstrap failed: 5: Input/output error\nmore"}))
        with self.assertRaises(RoadmapError) as ctx:
            launchd.install(python="/usr/bin/python3", runner=fake, logs_dir=self.logs)
        self.assertEqual(ctx.exception.exit, EXIT_EXTERNAL)
        self.assertEqual(ctx.exception.code, "external")
        self.assertEqual(ctx.exception.message, "launchctl bootstrap failed: Bootstrap failed: 5: Input/output error")

    def test_uninstall_bootouts_then_removes_only_the_plist(self):
        launchd.install(python="/usr/bin/python3", runner=FakeRunner(), logs_dir=self.logs)
        log_file = os.path.join(self.logs, "server.log")
        os.makedirs(self.logs, exist_ok=True)
        with open(log_file, "w", encoding="utf-8") as fh:
            fh.write("kept\n")
        fake = FakeRunner()
        self.assertTrue(launchd.uninstall(runner=fake))
        self.assertEqual(fake.calls, [["launchctl", "bootout", self.target()]])
        self.assertFalse(os.path.exists(launchd.plist_path()))
        self.assertTrue(os.path.exists(log_file))

    def test_uninstall_without_a_plist_returns_false(self):
        fake = FakeRunner(answer_for(launchctl=NOT_LOADED))
        self.assertFalse(launchd.uninstall(runner=fake))
        self.assertEqual(fake.calls, [["launchctl", "bootout", self.target()]])


class LifecycleTests(LaunchdCase):
    def setUp(self):
        super().setUp()
        launchd.install(python="/usr/bin/python3", runner=FakeRunner(), logs_dir=self.logs)

    def test_start_loads_the_plist_when_not_loaded(self):
        fake = FakeRunner(lc(NOT_LOADED))
        launchd.start(runner=fake)
        self.assertEqual(fake.calls, [
            ["launchctl", "print", self.target()],
            ["launchctl", "bootstrap", self.domain(), launchd.plist_path()],
        ])

    def test_start_kickstarts_when_loaded(self):
        fake = FakeRunner(lc(LOADED))
        launchd.start(runner=fake)
        self.assertEqual(fake.calls, [["launchctl", "print", self.target()], ["launchctl", "kickstart", self.target()]])

    def test_start_without_a_plist_is_not_found_exit_3(self):
        os.remove(launchd.plist_path())
        fake = FakeRunner(answer_for(launchctl=NOT_LOADED))
        with self.assertRaises(RoadmapError) as ctx:
            launchd.start(runner=fake)
        self.assertEqual(ctx.exception.exit, EXIT_NOT_FOUND)
        self.assertEqual(fake.calls, [["launchctl", "print", self.target()]])

    def test_stop_bootouts_and_an_unloaded_job_is_not_an_error(self):
        fake = FakeRunner(lc(NOT_LOADED, bootout=NOT_LOADED))
        launchd.stop(runner=fake)
        self.assertEqual(fake.calls, [["launchctl", "bootout", self.target()]])
        self.assertTrue(os.path.exists(launchd.plist_path()))

    def test_stop_real_failure_is_external(self):
        fake = FakeRunner(lc(LOADED, bootout={"rc": 5, "err": "Operation not permitted"}))
        with self.assertRaises(RoadmapError) as ctx:
            launchd.stop(runner=fake)
        self.assertEqual(ctx.exception.exit, EXIT_EXTERNAL)

    def test_restart_when_loaded_uses_kickstart_k(self):
        fake = FakeRunner(lc(LOADED))
        launchd.restart(runner=fake)
        self.assertEqual(fake.calls, [["launchctl", "print", self.target()],
                                      ["launchctl", "kickstart", "-k", self.target()]])

    def test_restart_when_not_loaded_bootstraps(self):
        fake = FakeRunner(lc(NOT_LOADED))
        launchd.restart(runner=fake)
        self.assertEqual(fake.calls[-1], ["launchctl", "bootstrap", self.domain(), launchd.plist_path()])

    def test_target_is_the_gui_domain_of_this_user(self):
        self.assertEqual(self.target(), "gui/%d/com.roadmap-board.agent" % os.getuid())


class StatusTests(LaunchdCase):
    def test_parse_print_reads_state_pid_exit_and_runs(self):
        fields = launchd.parse_print(SAMPLE_PRINT)
        self.assertEqual(fields["state"], "running")
        self.assertEqual(fields["pid"], 4242)
        self.assertEqual(fields["lastExitCode"], "0")
        self.assertEqual(fields["runs"], 3)
        self.assertEqual(fields["path"], "/Users/test/Library/LaunchAgents/com.roadmap-board.agent.plist")

    def test_parse_print_missing_fields_are_none(self):
        fields = launchd.parse_print("gui/501/x = {\n}\n")
        self.assertIsNone(fields["state"])
        self.assertIsNone(fields["pid"])

    def test_status_when_loaded(self):
        fake = FakeRunner(answer_for(launchctl=LOADED))
        info = launchd.status(runner=fake)
        self.assertIs(info["loaded"], True)
        self.assertEqual((info["state"], info["pid"], info["lastExitCode"]), ("running", 4242, "0"))
        self.assertEqual(fake.calls, [["launchctl", "print", self.target()]])  # read-only

    def test_status_when_not_loaded_and_plist_missing(self):
        info = launchd.status(runner=FakeRunner(answer_for(launchctl=NOT_LOADED)))
        self.assertIs(info["loaded"], False)
        self.assertIs(info["plistInstalled"], False)
        self.assertIsNone(info["pid"])

    def test_listener_on_parses_lsof_and_none_when_free(self):
        busy = FakeRunner(answer_for(lsof={"out": "p777\ncPython\n"}))
        self.assertEqual(launchd.listener_on(8765, runner=busy), {"pid": 777, "name": "Python"})
        self.assertEqual(busy.calls[0][:3], ["lsof", "-nP", "-iTCP:8765"])
        free = FakeRunner(answer_for(lsof={"rc": 1, "out": ""}))
        self.assertIsNone(launchd.listener_on(8765, runner=free))


class LogHelperTests(LaunchdCase):
    def setUp(self):
        super().setUp()
        os.makedirs(self.logs, exist_ok=True)

    def write(self, name, size):
        path = os.path.join(self.logs, name)
        with open(path, "wb") as fh:
            fh.write(b"x" * size)
        return path

    def test_launchd_out_above_5_mb_is_truncated_at_serve_start(self):
        big = self.write("launchd.out", launchd.LAUNCHD_MAX_BYTES + 1)
        cut = launchd.prepare_launchd_logs(logs_dir=self.logs)
        self.assertEqual(cut, ["launchd.out"])
        self.assertEqual(os.path.getsize(big), 0)

    def test_exactly_5_mb_and_small_files_are_kept(self):
        exact = self.write("launchd.out", launchd.LAUNCHD_MAX_BYTES)
        small = self.write("launchd.err", 10)
        self.assertEqual(launchd.prepare_launchd_logs(logs_dir=self.logs), [])
        self.assertEqual(os.path.getsize(exact), launchd.LAUNCHD_MAX_BYTES)
        self.assertEqual(os.path.getsize(small), 10)

    def test_truncate_large_on_a_missing_file_is_false(self):
        self.assertFalse(launchd.truncate_large(os.path.join(self.logs, "nope.err")))

    def test_tail_lines_gives_the_last_hundred(self):
        path = os.path.join(self.logs, "server.log")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("".join("line %d\n" % n for n in range(150)))
        lines = launchd.tail_lines(path, 100)
        self.assertEqual(len(lines), 100)
        self.assertEqual(lines[0], "line 50")
        self.assertEqual(launchd.tail_lines(os.path.join(self.logs, "missing.log")), [])

    def test_follow_emits_only_new_complete_lines(self):
        path = os.path.join(self.logs, "server.log")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("old\n")
        state = {"n": 0}

        def append(text):
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(text)

        def sleep(_):
            state["n"] += 1
            if state["n"] == 1:
                append("new1\npart")
            elif state["n"] == 2:
                append("ial\n")

        out = []
        launchd.follow(path, out.append, lambda: state["n"] >= 3, sleep=sleep, poll_s=0)
        self.assertEqual(out, ["new1", "partial"])


class ServiceCommandTests(LaunchdCase):
    def test_status_json_envelope_when_not_loaded(self):
        self.use_runner(FakeRunner(answer_for(launchctl=NOT_LOADED)))
        code, body = envelope(["service", "status"])
        self.assertEqual(code, 0)
        self.assertIs(body["ok"], True)
        self.assertIs(body["data"]["loaded"], False)

    def test_install_json_then_status_with_fake_launchctl(self):
        fake = self.use_runner(FakeRunner(answer_for(launchctl=LOADED)))
        code, body = envelope(["service", "install"])
        self.assertEqual(code, 0, body)
        self.assertEqual(body["data"]["plist"], launchd.plist_path())
        self.assertIs(body["data"]["loaded"], True)
        self.assertEqual(fake.calls[0], ["launchctl", "bootout", self.target()])
        self.assertEqual(fake.calls[1][:3], ["launchctl", "bootstrap", self.domain()])

    def test_start_failure_is_exit_6_in_the_envelope(self):
        self.use_runner(FakeRunner(answer_for(launchctl={"rc": 5, "err": "boom"})))
        os.makedirs(self.agents, exist_ok=True)
        with open(launchd.plist_path(), "w", encoding="utf-8") as fh:
            fh.write("<plist/>")
        code, body = envelope(["service", "start"])
        self.assertEqual(code, 6)
        self.assertEqual(body["error"]["code"], "external")

    def test_logs_json_returns_the_tail_of_server_log(self):
        os.makedirs(self.logs, exist_ok=True)
        with open(os.path.join(self.logs, "server.log"), "w", encoding="utf-8") as fh:
            fh.write("first\nsecond\n")
        code, body = envelope(["service", "logs"])
        self.assertEqual(code, 0)
        self.assertEqual(body["data"]["lines"], ["first", "second"])

    def test_logs_follow_stops_quietly_on_ctrl_c(self):
        with mock.patch.object(launchd, "follow", side_effect=KeyboardInterrupt):
            code, _, _ = run_cli(["service", "logs", "-f"])
        self.assertEqual(code, 0)

    def test_uninstall_plain_output(self):
        self.use_runner(FakeRunner(answer_for(launchctl=NOT_LOADED)))
        code, out, _ = run_cli(["service", "uninstall"])
        self.assertEqual(code, 0)
        self.assertIn("nothing to remove", out)


if __name__ == "__main__":
    unittest.main()
