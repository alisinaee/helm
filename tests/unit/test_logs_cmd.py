"""Tests for `roadmap logs` (R7.16 step 3): the default view, filters, summary, marks, status switch, the --json
envelope, and the core.write and hook.event emitters. Every test uses its own state directory."""

import contextlib
import io
import json
import time
import shutil
import tempfile
import unittest

from roadmap import log
from roadmap.cli import main
from roadmap.commands import hook as hook_cmd
from roadmap.services import commands


def run(argv):
    out = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


class LogsCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="rb-logscmd-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        log.set_state_dir(self.tmp)
        self.addCleanup(log.set_state_dir, None)

    def write(self, lvl, ev, msg="boom", sid="aaaa1111", route="#/tasks", ref=None, data=None):
        self.assertTrue(log.debug_event("ui", lvl, ev, msg=msg, route=route, ref=ref, sid=sid, data=data))


class DefaultViewTests(LogsCase):
    def test_empty_log_prints_one_hint_line(self):
        code, out, _ = run(["logs"])
        self.assertEqual(code, 0)
        lines = out.strip().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertIn("next:", lines[0])

    def test_empty_and_off_hints_to_enable(self):
        log.set_enabled(False)
        code, out, _ = run(["logs"])
        self.assertEqual(code, 0)
        self.assertEqual(len(out.strip().splitlines()), 1)
        self.assertIn("roadmap logs status --on", out)

    def test_shows_only_warn_and_error_with_next_line(self):
        self.write("INFO", "ui.load", msg="quiet")
        self.write("WARN", "ui.api", msg="slow call")
        self.write("ERROR", "ui.error", msg="bad thing", ref="rb:p/task/P1")
        code, out, _ = run(["logs"])
        self.assertEqual(code, 0)
        lines = out.strip().splitlines()
        self.assertNotIn("quiet", out)
        self.assertEqual(len(lines), 3)
        self.assertIn("ui.api", lines[0])
        self.assertIn("rb:p/task/P1", lines[1])
        self.assertTrue(lines[-1].startswith("next:"))

    def test_line_has_clock_src_ev_route_ref_msg(self):
        self.write("ERROR", "ui.error", msg="bad thing", ref="rb:p/task/P1")
        _, out, _ = run(["logs"])
        first = out.splitlines()[0].split()
        self.assertRegex(first[0], r"^\d\d:\d\d:\d\d$")
        self.assertEqual(first[1:4], ["ui", "ui.error", "#/tasks"])
        self.assertEqual(first[4], "rb:p/task/P1")
        self.assertIn("bad thing", out)

    def test_limit_is_capped_at_100(self):
        for n in range(120):
            self.write("WARN", "ui.api", msg="w%d" % n)
        _, out, _ = run(["logs", "--limit", "500"])
        self.assertEqual(len(out.strip().splitlines()) - 1, 100)
        _, out, _ = run(["logs"])
        self.assertEqual(len(out.strip().splitlines()) - 1, 20)

    def test_json_envelope(self):
        self.write("ERROR", "ui.error", msg="bad")
        code, out, _ = run(["logs", "--json"])
        body = json.loads(out)
        self.assertEqual(code, 0)
        self.assertTrue(body["ok"])
        self.assertEqual(body["data"]["events"][0]["ev"], "ui.error")
        self.assertEqual(body["data"]["count"], 1)


class FilterTests(LogsCase):
    def test_ev_src_and_session_filters(self):
        self.write("ERROR", "ui.error", msg="from ui", sid="aaaa1111")
        self.assertTrue(log.debug_event("core", "WARN", "core.write", msg="from core", sid="core-9"))
        _, out, _ = run(["logs", "--src", "core"])
        self.assertIn("from core", out)
        self.assertNotIn("from ui", out)
        _, out, _ = run(["logs", "--ev", "ui.error"])
        self.assertIn("from ui", out)
        self.assertNotIn("from core", out)
        _, out, _ = run(["logs", "--session", "aaaa1111"])
        self.assertIn("from ui", out)
        self.assertNotIn("from core", out)

    def test_session_last_is_the_newest_session(self):
        self.write("ERROR", "ui.error", msg="older", sid="old00001")
        self.write("ERROR", "ui.error", msg="newest", sid="new00002")
        _, out, _ = run(["logs", "--session", "last"])
        self.assertIn("newest", out)
        self.assertNotIn("older", out)

    def test_ref_filter(self):
        self.write("ERROR", "ui.error", msg="one", ref="rb:p/task/P1")
        self.write("ERROR", "ui.error", msg="two", ref="rb:p/task/P2")
        _, out, _ = run(["logs", "--ref", "rb:p/task/P2"])
        self.assertIn("two", out)
        self.assertNotIn("one", out)

    def test_level_widens_the_floor(self):
        self.write("INFO", "ui.load", msg="info line")
        _, out, _ = run(["logs", "--level", "INFO"])
        self.assertIn("info line", out)

    def test_bad_since_is_a_usage_error(self):
        code, _, err = run(["logs", "--since", "soon"])
        self.assertEqual(code, 2)
        self.assertIn("--since", err)

    def test_since_keeps_recent_events(self):
        self.write("ERROR", "ui.error", msg="fresh")
        _, out, _ = run(["logs", "--since", "10m"])
        self.assertIn("fresh", out)


class SummaryMarksStatusTests(LogsCase):
    def test_summary_is_short_and_counts(self):
        for n in range(3):
            self.write("ERROR", "ui.error", msg="same")
        self.write("WARN", "ui.api", msg="slow")
        self.write("INFO", "ui.mark", msg="note", route="#/x", ref="rb:p/task/P1")
        code, out, _ = run(["logs", "summary"])
        lines = out.strip().splitlines()
        self.assertEqual(code, 0)
        self.assertLessEqual(len(lines), 15)
        self.assertIn("by ev:", out)
        self.assertIn("3x ui.error same", out)
        self.assertIn("sessions: 1", out)
        self.assertTrue(lines[-1].startswith("next:"))

    def test_marks_newest_first_with_route_and_ref(self):
        self.write("INFO", "ui.mark", msg="first note", route="#/a", ref="rb:p/task/P1")
        self.write("INFO", "ui.mark", msg="second note", route="#/b", ref="rb:p/task/P2")
        _, out, _ = run(["logs", "marks"])
        lines = out.strip().splitlines()
        self.assertIn("second note", lines[0])
        self.assertIn("#/b", lines[0])
        self.assertIn("rb:p/task/P2", lines[0])
        self.assertIn("first note", lines[1])
        self.assertTrue(lines[-1].startswith("next:"))

    def test_marks_none_is_one_line(self):
        code, out, _ = run(["logs", "marks"])
        self.assertEqual(code, 0)
        self.assertEqual(len(out.strip().splitlines()), 1)

    def test_status_switch_and_report(self):
        code, out, _ = run(["logs", "status", "--off"])
        self.assertEqual(code, 0)
        self.assertIn("logs: off", out)
        self.assertFalse(log.enabled())
        code, out, _ = run(["logs", "status", "--on"])
        self.assertIn("logs: on", out)
        self.assertTrue(log.enabled())
        self.assertLessEqual(len(out.strip().splitlines()), 15)
        code, out, _ = run(["logs", "status", "--json"])
        self.assertTrue(json.loads(out)["data"]["enabled"])

    def test_status_on_and_off_together_is_refused(self):
        code, _, _ = run(["logs", "status", "--on", "--off"])
        self.assertEqual(code, 2)


class CoreWriteEmitterTests(LogsCase):
    def test_write_op_logs_keys_not_values(self):
        commands._log_write("task.status", {"id": "P1.2", "status": "secret-value"}, "ok")
        events = log.read_events(ev="core.write")
        self.assertEqual(len(events), 1)
        data = events[0]["data"]
        self.assertEqual(data["op"], "task.status")
        self.assertEqual(data["keys"], "id,status")
        self.assertEqual(data["code"], "ok")
        self.assertNotIn("secret-value", json.dumps(events[0]))
        self.assertNotIn("P1.2", json.dumps(events[0]))

    def test_error_code_is_warn(self):
        commands._log_write("task.status", {"id": "P1"}, "not_found")
        events = log.read_events(ev="core.write", level_min="WARN")
        self.assertEqual(events[-1]["data"]["code"], "not_found")
        self.assertEqual(events[-1]["lvl"], "WARN")

    def test_emitter_never_raises(self):
        commands._log_write("task.status", object(), "ok")
        commands._log_write(None, None, None)


class HookEmitterTests(LogsCase):
    def test_deny_is_warn_with_decision_and_ms(self):
        raw = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Bash"})
        reply = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny"}}
        hook_cmd._log_event(raw, reply, started=time.monotonic())
        events = log.read_events(ev="hook.event")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["lvl"], "WARN")
        self.assertEqual(events[0]["data"]["decision"], "deny")
        self.assertEqual(events[0]["data"]["hook"], "PreToolUse")
        self.assertIn("ms", events[0]["data"])
        self.assertEqual(events[0]["sid"], "hook")

    def test_allow_is_debug_and_skipped_when_budget_low(self):
        raw = json.dumps({"hook_event_name": "PostToolUse"})
        hook_cmd._log_event(raw, None, started=time.monotonic())
        self.assertEqual(log.read_events(ev="hook.event"), [])  # DEBUG is off by default
        log.set_debug(True)
        hook_cmd._log_event(raw, None, started=time.monotonic())
        self.assertEqual(log.read_events(ev="hook.event")[-1]["data"]["decision"], "allow")
        hook_cmd._log_event(raw, None, started=time.monotonic() - 5)
        self.assertEqual(len(log.read_events(ev="hook.event")), 1)

    def test_bad_stdin_never_raises(self):
        hook_cmd._log_event("not json", None, started=time.monotonic())


if __name__ == "__main__":
    unittest.main()


class SessionLastFilterTests(LogsCase):
    def test_session_last_follows_the_level_filter(self):
        self.write("WARN", "ui.error", msg="old warning", sid="old00001")
        self.write("INFO", "ui.action", msg="newest info", sid="new00002")
        _, out, _ = run(["logs", "--session", "last", "--level", "WARN"])
        self.assertIn("old warning", out)
        self.assertNotIn("newest info", out)
