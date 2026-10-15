"""HEAD-SPEC H4: the head ops through commands.run. Log, triage, set, bind, unbind, split, merge, convert, review, accept,
forget, and undo. Accept, review and forget are the person's only: refused for an agent, the phone and a non-TTY shell.
Runs in a temp ROADMAP_HOME with a copy of the fixture project."""

import contextlib
import os
import shutil
import tempfile
import unittest
from unittest import mock

from roadmap.errors import RoadmapError
from roadmap.services import agentguard, commands, tasks
from roadmap.services import head as store
from roadmap.store import config as config_store
from tests.api.support import FIXTURE, PROJECT_ID


def _tty():
    stream = mock.Mock()
    stream.isatty.return_value = True
    return stream


def _not_tty():
    stream = mock.Mock()
    stream.isatty.return_value = False
    return stream


@contextlib.contextmanager
def person_at_terminal():
    """An interactive terminal with no agent marker: the person's own CLI shell."""
    with mock.patch("sys.stdin", _tty()), mock.patch("sys.stdout", _tty()), \
            mock.patch.object(agentguard, "agent_marked", return_value=False):
        yield


class HeadOpsCase(unittest.TestCase):
    def setUp(self):
        env = mock.patch.dict(os.environ, {})
        env.start()
        self.addCleanup(env.stop)
        self.tmp = tempfile.mkdtemp(prefix="rb-head-ops-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        os.environ["ROADMAP_HOME"] = os.path.join(self.tmp, "home")
        os.environ.pop("CLAUDECODE", None)
        root = os.path.join(self.tmp, "split_net")
        shutil.copytree(FIXTURE, os.path.join(root, "docs"))
        config_store.add_project("split-net", root, project_id=PROJECT_ID)
        self.data_dir = tasks.resolve(PROJECT_ID)[1]

    def op(self, name, args=None, source="cli"):
        with commands.context(source, PROJECT_ID), mock.patch("sys.stdin", _not_tty()), \
                mock.patch("sys.stdout", _not_tty()):
            return commands.run(name, args or {}, source, self.data_dir)

    def person_op(self, name, args=None):
        """The person's browser click (gui with the same-origin proof)."""
        with commands.context("gui", PROJECT_ID), agentguard.browser_proven(True):
            return commands.run(name, args or {}, "gui", self.data_dir)

    def undo(self, result):
        return commands.run("undo", {"activity": result["activity"]}, "cli", self.data_dir)

    def row(self, eid):
        for item in store.rows(self.data_dir):
            if item["id"] == eid:
                return item
        self.fail("no row " + eid)

    def log(self, text="rename the export and fix the import"):
        return self.op("head.log", {"text": text})["data"]["id"]

    def test_log_numbers_the_entry_and_redacts_the_text(self):
        got = self.op("head.log", {"text": "use key sk-ant-abcdefghijklmnop1234 and mail a@b.com"})
        self.assertEqual(got["data"]["id"], "H1")
        verbatim = store.text_of(self.data_dir, "H1")
        self.assertNotIn("sk-ant", verbatim)
        self.assertNotIn("a@b.com", verbatim)

    def test_undo_of_log_declines_the_entry(self):
        result = self.op("head.log", {"text": "add a map view"})
        self.undo(result)
        self.assertEqual(self.row("H1")["status"], "declined")

    def test_triage_sets_kind_summary_and_links_and_undo_restores_them(self):
        eid = self.log("add a map view on mobile")
        before = self.row(eid)
        result = self.op("head.triage", {"id": eid, "kind": "bug", "sum": "Map broken on mobile",
                                         "refs": ["task:P1.1"]})
        after = self.row(eid)
        self.assertEqual((after["kind"], after["sum"], after["links"]),
                         ("bug", "Map broken on mobile", ["task:P1.1"]))
        self.undo(result)
        restored = self.row(eid)
        self.assertEqual(restored["links"], [])
        self.assertEqual(restored["sum"], before["sum"])
        self.assertEqual(restored["kind"], "ask")

    def test_triage_needs_a_valid_kind(self):
        eid = self.log()
        with self.assertRaises(RoadmapError) as ctx:
            self.op("head.triage", {"id": eid, "kind": "nonsense", "sum": "x"})
        self.assertEqual(ctx.exception.code, "usage")

    def test_bind_refuses_a_seventh_link_and_unbind_frees_one(self):
        eid = self.log()
        refs = ["task:P1.%d" % n for n in range(1, 7)]
        self.op("head.bind", {"id": eid, "refs": refs})
        self.assertEqual(len(self.row(eid)["links"]), 6)
        with self.assertRaises(RoadmapError) as ctx:
            self.op("head.bind", {"id": eid, "refs": ["task:P2.1"]})
        self.assertEqual(ctx.exception.code, "usage")
        self.op("head.unbind", {"id": eid, "refs": ["task:P1.1"]})
        self.op("head.bind", {"id": eid, "refs": ["task:P2.1"]})
        self.assertIn("task:P2.1", self.row(eid)["links"])

    def test_bad_link_ref_is_a_usage_error(self):
        eid = self.log()
        with self.assertRaises(RoadmapError) as ctx:
            self.op("head.bind", {"id": eid, "refs": ["nothing-here"]})
        self.assertEqual(ctx.exception.code, "usage")

    def test_split_makes_two_entries_from_the_first_and_undo_restores(self):
        eid = self.log()
        result = self.op("head.split", {"id": eid, "sums": ["Rename export", "Fix import"]})
        ids = result["data"]["into"]
        self.assertEqual(len(ids), 2)
        self.assertEqual(self.row(eid)["status"], "merged")
        self.assertEqual([self.row(i)["from"] for i in ids], [eid, eid])
        self.undo(result)
        self.assertEqual(self.row(eid)["status"], "new")
        self.assertEqual([self.row(i)["status"] for i in ids], ["declined", "declined"])

    def test_merge_marks_the_entry_merged_into_another(self):
        first = self.log("first ask")
        second = self.log("second ask")
        result = self.op("head.merge", {"id": second, "into": first})
        self.assertEqual(self.row(second)["status"], "merged")
        self.assertEqual(self.row(second)["into"], first)
        self.undo(result)
        self.assertEqual(self.row(second)["status"], "new")

    def test_merge_into_itself_is_refused(self):
        eid = self.log()
        with self.assertRaises(RoadmapError) as ctx:
            self.op("head.merge", {"id": eid, "into": eid})
        self.assertEqual(ctx.exception.code, "usage")

    def test_convert_backlog_adds_a_backlog_task_and_binds_it(self):
        eid = self.log("add dark mode")
        got = self.op("head.convert", {"id": eid, "target": "backlog"})["data"]["ref"]
        self.assertTrue(got.startswith("backlog:BL."))
        task_id = got.split(":", 1)[1]
        doc = tasks.load(self.data_dir)
        self.assertIn(task_id, [t.get("id") for t in doc["tasks"] if isinstance(t, dict)])
        self.assertIn(got, self.row(eid)["links"])

    def test_convert_issue_opens_an_issue_and_binds_it(self):
        eid = self.log("export crashes on empty files")
        got = self.op("head.convert", {"id": eid, "target": "issue", "kind": "bug"})["data"]["ref"]
        self.assertTrue(got.startswith("issue:"))
        self.assertIn(got, self.row(eid)["links"])

    def test_convert_task_to_a_missing_phase_is_refused(self):
        eid = self.log("a task")
        with self.assertRaises(RoadmapError) as ctx:
            self.op("head.convert", {"id": eid, "target": "task", "phase": "ZZ9"})
        self.assertEqual(ctx.exception.code, "usage")

    def test_convert_rule_sets_needs_you_and_undo_restores(self):
        eid = self.log("always run the tests before push")
        result = self.op("head.convert", {"id": eid, "target": "rule"})
        self.assertEqual(self.row(eid)["status"], "needs-you")
        self.undo(result)
        self.assertEqual(self.row(eid)["status"], "new")

    def test_head_may_set_done_by_itself(self):
        eid = self.log()
        self.op("head.set", {"id": eid, "status": "done"})
        self.assertEqual(self.row(eid)["status"], "done")

    def test_review_is_the_persons_only_and_can_reopen(self):
        eid = self.log()
        self.op("head.set", {"id": eid, "status": "done"})
        with self.assertRaises(RoadmapError) as ctx:
            self.op("head.review", {"id": eid, "action": "confirm"})
        self.assertEqual(ctx.exception.code, "agent_refused")
        self.person_op("head.review", {"id": eid, "action": "confirm"})
        self.assertEqual(self.row(eid)["status"], "done")
        self.person_op("head.review", {"id": eid, "action": "reopen"})
        self.assertEqual(self.row(eid)["status"], "new")

    def test_review_action_must_be_confirm_or_reopen(self):
        eid = self.log()
        with self.assertRaises(RoadmapError) as ctx:
            self.person_op("head.review", {"id": eid, "action": "maybe"})
        self.assertEqual(ctx.exception.code, "usage")

    def test_accept_is_refused_for_an_agent_the_phone_and_a_script(self):
        eid = self.log()
        with mock.patch.dict(os.environ, {"CLAUDECODE": "1"}):
            with self.assertRaises(RoadmapError) as agent:
                self.op("head.accept", {"id": eid})
        self.assertEqual(agent.exception.code, "agent_refused")
        with self.assertRaises(RoadmapError) as phone:
            self.op("head.accept", {"id": eid}, source="phone")
        self.assertEqual(phone.exception.code, "agent_refused")
        with self.assertRaises(RoadmapError) as script:
            self.op("head.accept", {"id": eid}, source="cli")
        self.assertEqual(script.exception.code, "agent_refused")
        self.assertEqual(self.row(eid)["status"], "new")

    def test_accept_by_the_person_at_a_terminal_marks_done(self):
        eid = self.log()
        with person_at_terminal(), commands.context("cli", PROJECT_ID):
            commands.run("head.accept", {"id": eid}, "cli", self.data_dir)
        self.assertEqual(self.row(eid)["status"], "done")

    def test_forget_is_refused_for_an_agent_and_blanks_the_verbatim_when_the_person_asks(self):
        eid = self.log("keep this secret thing private")
        with mock.patch.dict(os.environ, {"CLAUDECODE": "1"}):
            with self.assertRaises(RoadmapError) as agent:
                self.op("head.forget", {"id": eid})
        self.assertEqual(agent.exception.code, "agent_refused")
        self.assertIn("private", store.text_of(self.data_dir, eid))
        self.person_op("head.forget", {"id": eid})
        self.assertEqual(store.text_of(self.data_dir, eid), "")
        self.assertEqual(self.row(eid)["sum"], "keep this secret thing private")

    def test_restore_is_internal_and_not_callable(self):
        with self.assertRaises(RoadmapError) as ctx:
            self.op("head.restore", {"steps": [{"id": "H1"}]})
        self.assertEqual(ctx.exception.code, "usage")

    def test_bad_ids_and_statuses_are_usage_errors(self):
        with self.assertRaises(RoadmapError) as bad_id:
            self.op("head.set", {"id": "X1", "status": "done"})
        self.assertEqual(bad_id.exception.code, "usage")
        eid = self.log()
        with self.assertRaises(RoadmapError) as bad_status:
            self.op("head.set", {"id": eid, "status": "bogus"})
        self.assertEqual(bad_status.exception.code, "usage")

    def test_unknown_entry_is_not_found(self):
        with self.assertRaises(RoadmapError) as ctx:
            self.op("head.set", {"id": "H4242", "status": "done"})
        self.assertEqual(ctx.exception.code, "not_found")


if __name__ == "__main__":
    unittest.main()
