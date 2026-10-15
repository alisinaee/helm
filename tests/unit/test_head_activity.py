"""HEAD-SPEC section 5 and 10: head ledger events are visible elsewhere. Every public head op writes one activity line
(through commands.run). An entry that becomes needs-you, or a head-done entry that waits for the person's Review past
head.staleMin, raises the existing notification (services/notify.notify_dir). No test runs osascript: notify_dir is
patched, and the test runner guard in notify keeps the real call a no-op anyway. Runs in a temp ROADMAP_HOME."""

import datetime
import os
import shutil
import tempfile
import unittest
from unittest import mock

from roadmap.services import activity, commands, headops, notify, tasks
from roadmap.services import head as store
from roadmap.store import config as config_store
from tests.api.support import FIXTURE, PROJECT_ID
from tests.unit import test_head_ops as ops


class HeadActivityBase(unittest.TestCase):
    """A temp ROADMAP_HOME with a copy of the fixture project (the same setup as test_head_ops, without its tests)."""

    def setUp(self):
        env = mock.patch.dict(os.environ, {})
        env.start()
        self.addCleanup(env.stop)
        self.tmp = tempfile.mkdtemp(prefix="rb-head-activity-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        os.environ["ROADMAP_HOME"] = os.path.join(self.tmp, "home")
        os.environ.pop("CLAUDECODE", None)
        root = os.path.join(self.tmp, "split_net")
        shutil.copytree(FIXTURE, os.path.join(root, "docs"))
        config_store.add_project("split-net", root, project_id=PROJECT_ID)
        self.data_dir = tasks.resolve(PROJECT_ID)[1]

    def op(self, name, args=None, source="cli"):
        with commands.context(source, PROJECT_ID), mock.patch("sys.stdin", ops._not_tty()), \
                mock.patch("sys.stdout", ops._not_tty()):
            return commands.run(name, args or {}, source, self.data_dir)

    def person_op(self, name, args=None):
        with commands.context("gui", PROJECT_ID), ops.agentguard.browser_proven(True):
            return commands.run(name, args or {}, "gui", self.data_dir)

    def row(self, eid):
        for item in store.rows(self.data_dir):
            if item["id"] == eid:
                return item
        self.fail("no row " + eid)

    def log(self, text="rename the export and fix the import"):
        return self.op("head.log", {"text": text})["data"]["id"]


class HeadActivityTests(HeadActivityBase):
    def later(self, hours):
        return datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=hours)

    def run_at(self, name, args, moment):
        with commands.context("cli", PROJECT_ID), mock.patch("sys.stdin", ops._not_tty()), \
                mock.patch("sys.stdout", ops._not_tty()):
            return commands.run(name, args, "cli", self.data_dir, now=moment)

    def lines(self):
        return activity.recent(self.data_dir, 100)

    def test_each_head_op_writes_one_activity_line(self):
        eid = self.log("add a map view")
        self.op("head.triage", {"id": eid, "kind": "bug", "sum": "Map broken"})
        self.op("head.set", {"id": eid, "status": "needs-you"})
        self.op("head.set", {"id": eid, "status": "declined"})
        ops = [line["op"] for line in self.lines()]
        self.assertEqual(ops, ["head.log", "head.triage", "head.set", "head.set"])
        self.assertIn(eid + " set status", self.lines()[-1]["sum"])

    def test_activity_line_names_the_entry_and_undo_is_recorded(self):
        result = self.op("head.log", {"text": "ship the export"})
        line = self.lines()[-1]
        self.assertTrue(line["sum"].startswith("H1 ask"))
        self.assertIn("logged", line["sum"])
        self.assertTrue(line["undo"])
        self.assertEqual(line["id"], result["activity"])

    def test_needs_you_raises_the_existing_notification(self):
        eid = self.log()
        with mock.patch.object(notify, "notify_dir") as notify_dir:
            self.op("head.set", {"id": eid, "status": "needs-you"})
        self.assertEqual(notify_dir.call_count, 1)
        args = notify_dir.call_args[0]
        self.assertEqual(args[1], headops.NEEDS_YOU_KIND)
        self.assertEqual(args[2], "Head needs you")
        self.assertEqual(args[0], self.data_dir)

    def test_convert_to_rule_raises_needs_you_once(self):
        eid = self.log("never log passwords")
        with mock.patch.object(notify, "notify_dir") as notify_dir:
            self.op("head.convert", {"id": eid, "target": "rule"})
            self.op("head.log", {"text": "another note"})
        kinds = [call[0][1] for call in notify_dir.call_args_list]
        self.assertEqual(kinds, [headops.NEEDS_YOU_KIND])

    def test_already_needs_you_is_not_notified_again(self):
        eid = self.log()
        self.op("head.set", {"id": eid, "status": "needs-you"})
        with mock.patch.object(notify, "notify_dir") as notify_dir:
            self.op("head.set", {"id": eid, "note": "still waiting"})
        notify_dir.assert_not_called()

    def test_head_done_waiting_past_stale_time_raises_review_notice(self):
        eid = self.log()
        self.op("head.set", {"id": eid, "status": "done"})
        with mock.patch.object(notify, "notify_dir") as notify_dir:
            self.run_at("head.log", {"text": "second ask"}, self.later(1))
            notify_dir.assert_not_called()
            self.run_at("head.log", {"text": "third ask"}, self.later(3))
        kinds = [call[0][1] for call in notify_dir.call_args_list]
        self.assertEqual(kinds, [headops.REVIEW_KIND])

    def test_person_confirmed_done_is_not_awaiting_review(self):
        eid = self.log()
        self.op("head.set", {"id": eid, "status": "done"})
        with ops.person_at_terminal():
            self.person_op("head.review", {"id": eid, "action": "confirm"})
        with mock.patch.object(notify, "notify_dir") as notify_dir:
            self.run_at("head.log", {"text": "later"}, self.later(5))
        notify_dir.assert_not_called()

    def test_stale_time_comes_from_config(self):
        eid = self.log()
        self.op("head.set", {"id": eid, "status": "done"})
        with mock.patch.object(headops.config, "load", return_value={"head": {"staleMin": 10}}), \
                mock.patch.object(notify, "notify_dir") as notify_dir:
            self.run_at("head.log", {"text": "later"}, self.later(5 / 60.0))
            notify_dir.assert_not_called()
            self.run_at("head.log", {"text": "later again"}, self.later(11 / 60.0))
        self.assertEqual([c[0][1] for c in notify_dir.call_args_list], [headops.REVIEW_KIND])

    def test_bad_stale_config_falls_back_to_default(self):
        for value in (None, "soon", 0, -5, True):
            with mock.patch.object(headops.config, "load", return_value={"head": {"staleMin": value}}):
                self.assertEqual(headops._stale_min(), headops.STALE_MIN_DEFAULT)

    def test_notice_failure_never_fails_the_op(self):
        eid = self.log()
        with mock.patch.object(notify, "notify_dir", side_effect=RuntimeError("boom")):
            got = self.op("head.set", {"id": eid, "status": "needs-you"})
        self.assertTrue(got["ok"])
        self.assertEqual(self.row(eid)["status"], "needs-you")

    def test_no_real_osascript_under_tests(self):
        eid = self.log()
        with mock.patch("roadmap.services.notify.subprocess.run") as run:
            self.op("head.set", {"id": eid, "status": "needs-you"})
        run.assert_not_called()

