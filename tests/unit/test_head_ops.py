"""HEAD-SPEC H4: the head ops through commands.run. Log, triage, set, bind, unbind, split, merge, convert, review, accept,
forget, and undo. Accept, review and forget are the person's only: refused for an agent, the phone and a non-TTY shell.
Runs in a temp ROADMAP_HOME with a copy of the fixture project."""

import contextlib
import datetime
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from roadmap.errors import RoadmapError
from roadmap.services import agentguard, commands, hooks, tasks
from roadmap.services import head as store
from roadmap.store import config as config_store
from tests.api.support import FIXTURE, PROJECT_ID
from tests.unit.test_control_support import ControlCase, read_json, write_json


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


class VerifiedOpsGapTests(HeadOpsCase):
    """Test gaps confirmed in docs/reviews/agy-head-testgaps-ops.md (rows for roadmap/services/headops.py)."""

    def bind(self, eid, refs):
        return self.op("head.bind", {"id": eid, "refs": refs})

    def test_log_with_blank_text_is_a_usage_error(self):
        with self.assertRaises(RoadmapError) as raised:
            self.op("head.log", {"text": "   "})
        self.assertEqual(raised.exception.code, "usage")

    def test_log_with_refs_binds_them_and_undo_declines_and_unbinds(self):
        result = self.op("head.log", {"text": "rename the export", "refs": ["task:P1.1"]})
        eid = result["data"]["id"]
        self.assertEqual(result["data"]["bound"], ["task:P1.1"])
        self.assertIn("task:P1.1", self.row(eid)["links"])
        self.undo(result)
        self.assertEqual(self.row(eid)["status"], "declined")
        self.assertEqual(self.row(eid)["links"], [])

    def test_log_while_spooled_has_no_id_and_binds_nothing(self):
        spooled = {"id": None, "status": "spooled", "kind": "ask?", "sum": "anything here", "len": 13}
        with mock.patch.object(store, "capture", return_value=spooled):
            result = self.op("head.log", {"text": "anything here", "refs": ["task:P1.1"]})
        self.assertIsNone(result["data"]["id"])
        self.assertEqual(result["data"]["bound"], [])

    def test_triage_with_empty_summary_is_a_usage_error(self):
        eid = self.log()
        with self.assertRaises(RoadmapError) as raised:
            self.op("head.triage", {"id": eid, "kind": "bug", "sum": ""})
        self.assertEqual(raised.exception.code, "usage")

    def test_triage_refuses_a_seventh_link(self):
        eid = self.log()
        self.bind(eid, ["task:P1.%d" % n for n in range(1, 7)])
        with self.assertRaises(RoadmapError) as raised:
            self.op("head.triage", {"id": eid, "kind": "bug", "sum": "Map broken", "refs": ["task:P2.1"]})
        self.assertEqual(raised.exception.code, "usage")

    def test_triage_stores_an_explicit_status(self):
        eid = self.log()
        self.op("head.triage", {"id": eid, "kind": "bug", "sum": "Map broken", "status": "needs-you"})
        self.assertEqual(self.row(eid)["status"], "needs-you")

    def test_set_with_no_field_is_a_usage_error(self):
        eid = self.log()
        with self.assertRaises(RoadmapError) as raised:
            self.op("head.set", {"id": eid})
        self.assertEqual(raised.exception.code, "usage")

    def test_set_note_only_is_recorded_and_leaves_status_alone(self):
        eid = self.log()
        result = self.op("head.set", {"id": eid, "note": "checked with the owner"})
        self.assertEqual(result["data"]["changed"], ["note"])
        self.assertEqual(self.row(eid)["status"], "new")
        self.assertEqual(store._records(self.data_dir)[-1].get("note"), "checked with the owner")

    def test_bind_with_no_refs_is_a_usage_error(self):
        eid = self.log()
        with self.assertRaises(RoadmapError) as raised:
            self.op("head.bind", {"id": eid, "refs": []})
        self.assertEqual(raised.exception.code, "usage")

    def test_bind_of_an_existing_ref_binds_nothing_new(self):
        eid = self.log()
        self.bind(eid, ["task:P1.1"])
        result = self.bind(eid, ["task:P1.1"])
        self.assertEqual(result["data"]["bound"], [])

    def test_undo_of_unbind_restores_the_removed_link(self):
        eid = self.log()
        self.bind(eid, ["task:P1.1"])
        result = self.op("head.unbind", {"id": eid, "refs": ["task:P1.1"]})
        self.assertEqual(self.row(eid)["links"], [])
        self.undo(result)
        self.assertEqual(self.row(eid)["links"], ["task:P1.1"])

    def test_split_needs_exactly_two_non_empty_summaries(self):
        eid = self.log()
        for sums in (["only one"], ["one two", ""], ["a b", "c d", "e f"]):
            with self.assertRaises(RoadmapError) as raised:
                self.op("head.split", {"id": eid, "sums": sums})
            self.assertEqual(raised.exception.code, "usage", sums)

    def test_split_of_a_merged_entry_is_refused(self):
        first = self.log("first ask")
        second = self.log("second ask")
        self.op("head.merge", {"id": second, "into": first})
        with self.assertRaises(RoadmapError) as raised:
            self.op("head.split", {"id": second, "sums": ["part one", "part two"]})
        self.assertEqual(raised.exception.code, "usage")

    def test_merge_into_a_missing_entry_is_not_found(self):
        eid = self.log()
        with self.assertRaises(RoadmapError) as raised:
            self.op("head.merge", {"id": eid, "into": "H4242"})
        self.assertEqual(raised.exception.code, "not_found")

    def test_convert_rejects_a_bad_target_or_phase(self):
        eid = self.log("add a sync badge")
        with self.assertRaises(RoadmapError) as bad_target:
            self.op("head.convert", {"id": eid, "target": "epic"})
        self.assertEqual(bad_target.exception.code, "usage")
        with self.assertRaises(RoadmapError) as bad_phase:
            self.op("head.convert", {"id": eid, "target": "task", "phase": "bad phase!"})
        self.assertEqual(bad_phase.exception.code, "usage")

    def test_convert_to_a_task_in_an_existing_phase_binds_the_new_task(self):
        eid = self.log("add a sync badge")
        ref = self.op("head.convert", {"id": eid, "target": "task", "phase": "P1"})["data"]["ref"]
        self.assertTrue(ref.startswith("task:P1."), ref)
        self.assertIn(ref, self.row(eid)["links"])

    def test_convert_is_refused_when_the_entry_already_holds_six_links(self):
        eid = self.log("add dark mode")
        self.bind(eid, ["task:P1.%d" % n for n in range(1, 7)])
        with self.assertRaises(RoadmapError) as raised:
            self.op("head.convert", {"id": eid, "target": "backlog"})
        self.assertEqual(raised.exception.code, "usage")

    def test_undo_of_accept_restores_the_previous_status(self):
        eid = self.log()
        result = self.person_op("head.accept", {"id": eid})
        self.assertEqual(self.row(eid)["status"], "done")
        self.undo(result)
        self.assertEqual(self.row(eid)["status"], "new")


class HookGapTests(ControlCase):
    """Hook-level gaps from docs/reviews/agy-head-testgaps-ops.md: the UserPromptSubmit capture in
    roadmap/services/hooks.py. Runs in the ControlCase temp ROADMAP_HOME, never the real home or port 8780."""

    MOMENT = datetime.datetime(2026, 10, 15, 9, 30, tzinfo=datetime.timezone.utc)
    SECRET = "sk-abcdef1234567890XYZ"

    def setUp(self):
        super().setUp()
        path = os.path.join(self.docs, "roadmap.config.json")
        data = read_json(path)
        data["headCapture"] = True
        write_json(path, data)
        self.head_file = os.path.join(self.docs, "head.jsonl")
        self.text_file = os.path.join(self.docs, "head-text.jsonl")

    def prompt(self, text):
        payload = {"hook_event_name": "UserPromptSubmit", "cwd": self.project, "session_id": "sess-1",
                   "prompt": text, "permission_mode": "default"}
        return hooks.run_hook(json.dumps(payload), now=self.MOMENT.timestamp())

    def records(self, path):
        with open(path, encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]

    def test_slash_command_with_arguments_is_an_entry_not_a_session_start(self):
        self.prompt("/head brief")  # two words: an ack-length prompt, nothing is written
        self.assertFalse(os.path.exists(self.head_file))
        self.prompt("/head brief for the board now")
        self.assertEqual([r["t"] for r in self.records(self.head_file)], ["e"])

    def test_hook_cuts_the_verbatim_text_at_8000_and_strips_control_characters(self):
        self.prompt("\x07" + "please fix the broken export button " * 300)
        stored = [r for r in self.records(self.text_file) if r.get("id") == "H1"][-1]["text"]
        self.assertEqual(len(stored), 8000)
        self.assertNotIn("\x07", stored)

    def test_the_summary_in_head_jsonl_carries_the_masked_secret(self):
        self.prompt("fix the export, the key is " + self.SECRET + " and mail a@b.com about it")
        entry = [r for r in self.records(self.head_file) if r.get("t") == "e"][0]
        self.assertNotIn(self.SECRET, entry["sum"])
        self.assertNotIn("a@b.com", entry["sum"])
        self.assertIn("[secret]", entry["sum"])


if __name__ == "__main__":
    unittest.main()
