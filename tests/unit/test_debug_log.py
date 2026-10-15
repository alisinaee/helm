"""Tests for the debug event log writer in roadmap/log.py: caps, redaction, rotation boundary, symlink refusal,
corrupt-line tolerance, concurrent appends, the disabled switch, unknown names, and no exception escaping."""

import datetime
import json
import os
import shutil
import stat
import tempfile
import threading
import unittest
from unittest import mock

from roadmap import log

DEBUG_NAME_1 = "debug.jsonl.1"


class DebugCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="rb-debuglog-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        log.set_state_dir(self.tmp)
        self.addCleanup(log.set_state_dir, None)

    def logs(self, name=log.DEBUG_FILE):
        return os.path.join(self.tmp, "logs", name)

    def lines(self, name=log.DEBUG_FILE):
        with open(self.logs(name), "r", encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]

    def emit(self, ev="ui.action", msg="m", **kw):
        return log.debug_event(kw.pop("src", "ui"), kw.pop("lvl", "INFO"), ev, msg=msg, **kw)


class WriterTests(DebugCase):
    def test_writes_one_json_line_with_the_spec_fields(self):
        ok = log.debug_event("ui", "INFO", "ui.action", msg="clicked", route="#/tasks?x=1", ref="rb:p/task/1",
                             sid="abcd1234", data={"kind": "task"})
        self.assertTrue(ok)
        (rec,) = self.lines()
        self.assertEqual(set(rec), {"ts", "sid", "src", "lvl", "ev", "route", "ref", "msg", "data"})
        self.assertEqual((rec["src"], rec["lvl"], rec["ev"]), ("ui", "INFO", "ui.action"))
        self.assertEqual(rec["route"], "#/tasks")
        self.assertEqual(rec["ref"], "rb:p/task/1")
        self.assertEqual(rec["data"], {"kind": "task"})
        datetime.datetime.fromisoformat(rec["ts"])

    def test_file_is_owner_only_and_dir_is_0700(self):
        self.emit()
        self.assertEqual(stat.S_IMODE(os.stat(self.logs()).st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(os.stat(os.path.dirname(self.logs())).st_mode), 0o700)

    def test_core_sid_defaults_to_pid(self):
        self.assertTrue(log.debug_event("core", "WARN", "core.guard", msg="csrf"))
        self.assertEqual(self.lines()[0]["sid"], "core-%d" % os.getpid())

    def test_unknown_event_and_source_are_dropped_silently(self):
        self.assertFalse(log.debug_event("ui", "INFO", "ui.bogus", msg="x"))
        self.assertFalse(log.debug_event("nope", "INFO", "ui.action", msg="x"))
        self.assertFalse(os.path.exists(self.logs()))

    def test_debug_level_is_off_by_default(self):
        self.assertFalse(log.debug_event("ui", "DEBUG", "ui.action", msg="x"))
        self.assertFalse(os.path.exists(self.logs()))
        self.assertTrue(log.set_debug(True))
        self.assertTrue(log.debug_event("ui", "DEBUG", "ui.action", msg="x"))

    def test_unknown_level_is_written_as_info(self):
        self.assertTrue(log.debug_event("ui", "LOUD", "ui.action", msg="x"))
        self.assertEqual(self.lines()[0]["lvl"], "INFO")


class CapTests(DebugCase):
    def test_field_caps(self):
        self.emit(msg="m" * 1000, route="/" + "r" * 500, ref="rb:" + "f" * 500, sid="s" * 100)
        rec = self.lines()[0]
        self.assertEqual(len(rec["msg"]), 300)
        self.assertTrue(rec["msg"].endswith("…"))
        self.assertLessEqual(len(rec["route"]), 120)
        self.assertLessEqual(len(rec["ref"]), 120)
        self.assertLessEqual(len(rec["sid"]), 32)

    def test_data_caps_keys_and_items(self):
        self.emit(data={"k%d" % i: 1 for i in range(30)})
        self.assertEqual(len(self.lines()[0]["data"]), 20)
        self.emit(data={"items": list(range(30))})
        self.assertEqual(len(self.lines()[1]["data"]["items"]), 10)

    def test_data_strings_are_capped_at_200(self):
        self.emit(data={"s": "v" * 500})
        self.assertEqual(len(self.lines()[0]["data"]["s"]), 200)

    def test_data_over_one_kilobyte_is_cut(self):
        nested = {"a%d" % i: {"b%d" % j: "x" * 200 for j in range(3)} for i in range(6)}
        self.emit(data=nested)
        rec = self.lines()[0]
        self.assertEqual(rec.get("data"), {"cut": True})

    def test_stack_keeps_twelve_frames(self):
        stack = "\n".join("frame %d" % i for i in range(50))
        self.emit(ev="ui.error", data={"stack": stack})
        kept = self.lines()[0]["data"]["stack"]
        self.assertEqual(len(kept.splitlines()), 12)
        self.assertLessEqual(len(kept), 1500)

    def test_circular_data_is_depth_limited(self):
        loop = {}
        loop["self"] = loop
        self.assertTrue(self.emit(data=loop))
        self.assertIn("self", self.lines()[0]["data"])


class RedactionTests(DebugCase):
    def test_secrets_tokens_and_query_strings_are_removed(self):
        home = os.path.expanduser("~")
        self.emit(msg="Bearer abc.def sk-ant-XYZ123 k=secretvalue in %s/Works/x.py" % home,
                  route="/api/v1/tasks?token=TOKEN123", ref="rb:p/task/1?t=QQ",
                  data={"token": "t1", "cookie": "c1", "csrf": "x1", "authorization": "y1", "value": "form text",
                        "kind": "task", "password": "pw1", "clipboard": "clip1"})
        with open(self.logs(), encoding="utf-8") as fh:
            raw = fh.read()
        for leaked in ("abc.def", "XYZ123", "secretvalue", "TOKEN123", "QQ", "form text", "pw1", "clip1", home):
            self.assertNotIn(leaked, raw)
        rec = self.lines()[0]
        self.assertEqual(rec["data"], {"kind": "task"})
        self.assertEqual(rec["route"], "/api/v1/tasks")
        self.assertIn("~/Works/x.py", rec["msg"])

    def test_absolute_paths_outside_home_keep_only_the_last_segment(self):
        self.emit(msg="failed at /etc/secret/hosts")
        msg = self.lines()[0]["msg"]
        self.assertNotIn("/etc/", msg)
        self.assertIn("hosts", msg)


class RotationTests(DebugCase):
    def test_rotation_happens_exactly_at_the_limit(self):
        self.emit(msg="one")
        one = os.path.getsize(self.logs())
        with mock.patch.object(log, "DEBUG_MAX_BYTES", 2 * one):
            self.emit(msg="one")  # 2 lines = limit exactly: no rotation
            self.assertFalse(os.path.exists(self.logs(DEBUG_NAME_1)))
            self.assertEqual(os.path.getsize(self.logs()), 2 * one)
            self.emit(msg="one")  # would pass the limit: rotate first
            self.assertTrue(os.path.exists(self.logs(DEBUG_NAME_1)))
            self.assertEqual(os.path.getsize(self.logs()), one)
            self.assertEqual(os.path.getsize(self.logs(DEBUG_NAME_1)), 2 * one)

    def test_only_three_backups_are_kept(self):
        with mock.patch.object(log, "DEBUG_MAX_BYTES", 400):
            for i in range(60):
                self.emit(msg="line %d" % i)
        self.assertTrue(os.path.exists(self.logs("debug.jsonl.3")))
        self.assertFalse(os.path.exists(self.logs("debug.jsonl.4")))
        total = sum(os.path.getsize(self.logs(n)) for n in ("debug.jsonl", "debug.jsonl.1", "debug.jsonl.2",
                                                             "debug.jsonl.3"))
        self.assertLessEqual(total, 4 * 400)
        self.assertEqual(stat.S_IMODE(os.stat(self.logs("debug.jsonl.3")).st_mode), 0o600)

    def test_default_caps_match_the_spec(self):
        self.assertEqual(log.DEBUG_MAX_BYTES, 5 * 1024 * 1024)
        self.assertEqual(log.DEBUG_BACKUPS, 3)
        self.assertEqual(log.DEBUG_CAP_BYTES, 20 * 1024 * 1024)


class SymlinkTests(DebugCase):
    def setUp(self):
        super().setUp()
        self.outside = tempfile.mkdtemp(prefix="rb-outside-")
        self.addCleanup(shutil.rmtree, self.outside, True)
        self.target = os.path.join(self.outside, "keep.txt")
        with open(self.target, "w", encoding="utf-8") as fh:
            fh.write("keep")

    def read_target(self):
        with open(self.target, encoding="utf-8") as fh:
            return fh.read()

    def test_symlinked_log_file_is_refused(self):
        os.makedirs(os.path.join(self.tmp, "logs"))
        os.symlink(self.target, self.logs())
        self.assertFalse(self.emit())
        self.assertEqual(self.read_target(), "keep")

    def test_symlinked_logs_dir_is_refused(self):
        os.symlink(self.outside, os.path.join(self.tmp, "logs"))
        self.assertFalse(self.emit())
        self.assertEqual(os.listdir(self.outside), ["keep.txt"])

    def test_symlinked_backup_blocks_rotation(self):
        self.emit(msg="one")
        one = os.path.getsize(self.logs())
        os.symlink(self.target, self.logs(log.DEBUG_FILE + ".1"))
        with mock.patch.object(log, "DEBUG_MAX_BYTES", one):
            self.assertFalse(self.emit(msg="two"))
        self.assertEqual(self.read_target(), "keep")


class ReadTests(DebugCase):
    def test_corrupt_lines_are_skipped(self):
        self.emit(msg="good 1")
        with open(self.logs(), "ab") as fh:
            fh.write(b"not json at all\n[1, 2]\n\xff\xfe garbage\n{\"no_ev\": 1}\n{\"ts\": \"x\", \"ev\": \"y\"\n")
        self.emit(msg="good 2")
        got = log.read_events()
        self.assertEqual([r["msg"] for r in got], ["good 1", "good 2"])

    def test_filters_and_limit(self):
        self.emit(ev="ui.action", msg="a", src="ui", ref="rb:p/task/1", sid="s1")
        self.emit(ev="ui.error", msg="b", src="ui", lvl="ERROR", sid="s1")
        log.debug_event("core", "WARN", "core.guard", msg="c", sid="s2")
        self.assertEqual([r["msg"] for r in log.read_events(src="core")], ["c"])
        self.assertEqual([r["msg"] for r in log.read_events(ev="ui.error")], ["b"])
        self.assertEqual([r["msg"] for r in log.read_events(ref="rb:p/task/1")], ["a"])
        self.assertEqual([r["msg"] for r in log.read_events(session="s2")], ["c"])
        self.assertEqual([r["msg"] for r in log.read_events(level_min="WARN")], ["b", "c"])
        self.assertEqual([r["msg"] for r in log.read_events(limit=2)], ["b", "c"])
        self.assertEqual(len(log.read_events(since=datetime.datetime.now() - datetime.timedelta(hours=1))), 3)
        self.assertEqual(log.read_events(since=datetime.datetime.now() + datetime.timedelta(hours=1)), [])

    def test_read_across_rotated_files_is_oldest_first(self):
        with mock.patch.object(log, "DEBUG_MAX_BYTES", 500):
            for i in range(20):
                self.emit(msg="m%02d" % i)
        msgs = [r["msg"] for r in log.read_events()]
        self.assertEqual(msgs, sorted(msgs))
        self.assertEqual(msgs[-1], "m19")

    def test_status_reports_files_and_caps(self):
        self.emit(msg="x")
        status = log.log_status()
        self.assertTrue(status["enabled"])
        self.assertEqual(status["files"]["debug.jsonl"], os.path.getsize(self.logs()))
        self.assertEqual(status["cap_bytes"], 20 * 1024 * 1024)
        self.assertNotIn(self.tmp, status["dir"])


class SwitchTests(DebugCase):
    def test_default_is_on(self):
        self.assertTrue(log.enabled())

    def test_disabled_switch_writes_nothing(self):
        self.assertTrue(log.set_enabled(False))
        self.assertFalse(log.enabled())
        self.assertFalse(self.emit())
        self.assertFalse(os.path.exists(self.logs()))
        self.assertTrue(log.set_enabled(True))
        self.assertTrue(self.emit())

    def test_corrupt_settings_file_falls_back_to_defaults(self):
        with open(os.path.join(self.tmp, log.SETTINGS_FILE), "w", encoding="utf-8") as fh:
            fh.write("{broken")
        self.assertTrue(log.enabled())
        self.assertFalse(log.debug_enabled())

    def test_settings_file_is_owner_only(self):
        log.set_enabled(False)
        path = os.path.join(self.tmp, log.SETTINGS_FILE)
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)


class ConcurrencyTests(DebugCase):
    def run_threads(self, count, per_thread):
        def worker(n):
            for i in range(per_thread):
                log.debug_event("ui", "INFO", "ui.action", msg="t%d-%d" % (n, i), sid="thread%d" % n)

        threads = [threading.Thread(target=worker, args=(n,)) for n in range(count)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

    def test_concurrent_appends_keep_every_line_whole(self):
        self.run_threads(8, 100)
        recs = self.lines()
        self.assertEqual(len(recs), 800)
        self.assertEqual(len({r["msg"] for r in recs}), 800)

    def test_concurrent_appends_with_rotation_leave_no_broken_line(self):
        with mock.patch.object(log, "DEBUG_MAX_BYTES", 6000):
            self.run_threads(8, 100)
        for name in ("debug.jsonl", "debug.jsonl.1", "debug.jsonl.2", "debug.jsonl.3"):
            if os.path.exists(self.logs(name)):
                self.assertLessEqual(os.path.getsize(self.logs(name)), 6000)
                self.lines(name)  # every line parses


class FailOpenTests(DebugCase):
    def test_no_exception_escapes(self):
        class Boom:
            def __str__(self):
                raise RuntimeError("boom")

        self.assertIsInstance(self.emit(data={"x": Boom()}), bool)
        self.assertIsInstance(log.debug_event(None, None, None), bool)
        self.assertIsInstance(log.debug_event("ui", "INFO", ["unhashable"]), bool)
        self.assertFalse(log.debug_event("ui", "INFO", "ui.action", msg=Boom()))

    def test_os_failure_gives_false(self):
        with mock.patch.object(log.os, "write", side_effect=OSError("disk full")):
            self.assertFalse(self.emit())
        self.assertEqual(log.read_events(), [])

    def test_read_failure_gives_empty_list_or_error_status(self):
        with mock.patch.object(log, "_read_paths", side_effect=RuntimeError("x")):
            self.assertEqual(log.read_events(), [])
        with mock.patch.object(log, "_read_settings", side_effect=RuntimeError("x")):
            self.assertEqual(log.log_status(), {"error": True})


if __name__ == "__main__":
    unittest.main()
