"""Gap tests for the task.rename op (roadmap/services/commands.py): title edge cases, undo rules for each source,
the undo file cap, the activity line fields, and the argument checks. Built on the RenameCase fixture (a copy of the
split-net fixture in a temp ROADMAP_HOME). Nothing is notified or launched; the op only writes under the temp folder."""

import datetime
import os
import unittest
from unittest import mock

from roadmap.errors import EXIT_NOT_FOUND, RoadmapError
from roadmap.services import commands, records
from roadmap.store import jsonl
from tests.api.support import PROJECT_ID
from tests.unit.test_task_rename import RenameCase as BaseRenameCase


class RenameCase(BaseRenameCase):
    def line_of(self, activity_id):
        return [line for line in self.activity() if line["id"] == activity_id][0]


class TitleRules(RenameCase):
    def test_padded_120_characters_is_allowed_and_padded_121_is_refused(self):
        self.run_op("task.rename", {"id": "P1.1", "title": "  " + "x" * 120 + "  "})
        self.assertEqual(self.title_of("P1.1"), "x" * 120)
        with self.assertRaises(RoadmapError) as ctx:
            self.run_op("task.rename", {"id": "P1.1", "title": " " + "x" * 121 + " "})
        self.assertEqual(ctx.exception.code, "usage")
        self.assertIn("121", str(ctx.exception))

    def test_a_single_character_title_is_allowed(self):
        self.run_op("task.rename", {"id": "P1.1", "title": "x"})
        self.assertEqual(self.title_of("P1.1"), "x")

    def test_nul_cr_vt_ff_c1_and_escape_characters_are_refused_and_log_nothing(self):
        before = len(self.activity())
        for bad in ("nul\x00x", "cr\rx", "vt\x0bx", "ff\x0cx", "c1\u0085x", "c1\u009fx", "esc\x1bx"):
            with self.subTest(bad=bad), self.assertRaises(RoadmapError) as ctx:
                self.run_op("task.rename", {"id": "P1.1", "title": bad})
            self.assertEqual(ctx.exception.code, "usage")
        self.assertEqual(len(self.activity()), before)

    def test_a_zero_width_space_is_not_a_control_character_and_is_kept(self):
        self.run_op("task.rename", {"id": "P1.1", "title": "a​b"})
        self.assertEqual(self.title_of("P1.1"), "a​b")


class UndoRules(RenameCase):
    def test_a_second_undo_of_the_same_rename_conflicts(self):
        old = self.title_of("P1.1")
        reply = self.run_op("task.rename", {"id": "P1.1", "title": "Temporary"})
        self.run_op("undo", {"activity": reply["activity"]})
        with self.assertRaises(RoadmapError) as ctx:
            self.run_op("undo", {"activity": reply["activity"]})
        self.assertEqual(ctx.exception.code, "conflict")
        self.assertIn("already undone", str(ctx.exception))
        self.assertEqual(self.title_of("P1.1"), old)

    def test_the_undo_record_and_the_undo_reply_have_the_documented_shape(self):
        old = self.title_of("P1.1")
        reply = self.run_op("task.rename", {"id": "P1.1", "title": "Shape it"})
        entries, _ = jsonl.read_objects(records.file_of(self.data_dir, commands.UNDO_FILE))
        mine = [e for e in entries if e.get("activity") == reply["activity"]]
        self.assertEqual(len(mine), 1)
        self.assertEqual(mine[0]["op"], "task.rename")
        self.assertEqual(mine[0]["args"], {"id": "P1.1", "title": old})
        self.assertEqual(mine[0]["sum"], "P1.1 title='Shape it'")
        self.assertIn("at", mine[0])
        undone = self.run_op("undo", {"activity": reply["activity"]})
        self.assertEqual(undone["data"], {"undone": reply["activity"], "op": "task.rename",
                                          "sum": "P1.1 title='Shape it'"})

    def test_a_gui_rename_cannot_be_undone_by_the_phone(self):
        reply = self.run_op("task.rename", {"id": "P1.1", "title": "From gui"}, source="gui")
        with self.assertRaises(RoadmapError) as ctx:
            self.run_op("undo", {"activity": reply["activity"]}, source="phone")
        self.assertEqual(ctx.exception.code, "forbidden")
        self.assertEqual(self.title_of("P1.1"), "From gui")

    def test_the_phone_may_undo_its_own_rename(self):
        old = self.title_of("P1.1")
        reply = self.run_op("task.rename", {"id": "P1.1", "title": "From phone"}, source="phone")
        self.run_op("undo", {"activity": reply["activity"]}, source="phone")
        self.assertEqual(self.title_of("P1.1"), old)

    def test_an_identical_title_logs_undo_false_and_has_nothing_to_undo(self):
        current = self.title_of("P1.1")
        reply = self.run_op("task.rename", {"id": "P1.1", "title": current})
        self.assertFalse(reply["undo"])
        line = self.line_of(reply["activity"])
        self.assertFalse(line["undo"])
        with self.assertRaises(RoadmapError) as ctx:
            self.run_op("undo", {"activity": reply["activity"]})
        self.assertEqual(ctx.exception.code, "not_found")

    def test_undo_of_a_task_that_is_gone_fails_logs_undo_failed_and_raises(self):
        reply = self.run_op("task.rename", {"id": "P1.1", "title": "Gone soon"})
        gone = RoadmapError("not_found", "task P1.1 not found", EXIT_NOT_FOUND)
        with mock.patch.object(commands.tasks, "get", side_effect=gone), \
                self.assertRaises(RoadmapError) as ctx:
            self.run_op("undo", {"activity": reply["activity"]})
        self.assertEqual(ctx.exception.code, "not_found")
        entries, _ = jsonl.read_objects(records.file_of(self.data_dir, commands.UNDO_FILE))
        self.assertIn({"undoFailed": reply["activity"], "at": entries[-1]["at"]}, entries)

    def test_the_undo_file_keeps_only_the_newest_entries(self):
        with mock.patch.object(commands, "UNDO_KEEP", 2):
            ids = [self.run_op("task.rename", {"id": "P1.1", "title": "T%d" % n})["activity"] for n in range(3)]
        entries, _ = jsonl.read_objects(records.file_of(self.data_dir, commands.UNDO_FILE))
        self.assertEqual([e["activity"] for e in entries], ids[1:])


class Sources(RenameCase):
    def test_an_agent_may_rename_and_the_line_says_agent(self):
        reply = self.run_op("task.rename", {"id": "P1.1", "title": "By agent"}, source="agent")
        self.assertTrue(reply["ok"])
        self.assertEqual(self.title_of("P1.1"), "By agent")
        self.assertEqual(self.line_of(reply["activity"])["src"], "agent")

    def test_a_cli_rename_is_logged_as_cli(self):
        reply = self.run_op("task.rename", {"id": "P1.1", "title": "By cli"}, source="cli")
        self.assertEqual(self.line_of(reply["activity"])["src"], "cli")

    def test_an_unknown_source_is_refused(self):
        with self.assertRaises(RoadmapError) as ctx:
            self.run_op("task.rename", {"id": "P1.1", "title": "Fine"}, source="invalid")
        self.assertEqual(ctx.exception.code, "usage")
        self.assertIn("source 'invalid' is not valid", str(ctx.exception))

    def test_write_under_claudecode_logs_the_rename_as_agent(self):
        os.environ["CLAUDECODE"] = "1"
        reply = commands.write(PROJECT_ID, "task.rename", {"id": "P1.1", "title": "Via write"}, "roadmap status")
        self.assertEqual(self.line_of(reply["activity"])["src"], "agent")
        self.assertEqual(self.title_of("P1.1"), "Via write")


class Arguments(RenameCase):
    def test_args_must_be_an_object(self):
        with self.assertRaises(RoadmapError) as ctx:
            commands.run("task.rename", "string", "gui", self.data_dir)
        self.assertEqual(ctx.exception.code, "usage")
        self.assertEqual(str(ctx.exception), "args must be an object")

    def test_a_missing_id_is_refused_with_roadmap_status_next(self):
        with self.assertRaises(RoadmapError) as ctx:
            self.run_op("task.rename", {"title": "Fine"})
        self.assertEqual(ctx.exception.code, "usage")
        self.assertEqual(ctx.exception.next, "roadmap status")

    def test_an_empty_title_is_reported_before_an_unknown_id(self):
        with self.assertRaises(RoadmapError) as ctx:
            self.run_op("task.rename", {"id": "P99.99", "title": ""})
        self.assertEqual(ctx.exception.code, "usage")
        self.assertIn("title is empty", str(ctx.exception))
        self.assertEqual(ctx.exception.next, "roadmap task list --phase P99")

    def test_an_unknown_id_writes_no_activity_line(self):
        before = len(self.activity())
        with self.assertRaises(RoadmapError) as ctx:
            self.run_op("task.rename", {"id": "P99.99", "title": "Fine"})
        self.assertEqual(ctx.exception.code, "not_found")
        self.assertEqual(len(self.activity()), before)

    def test_the_activity_line_has_the_documented_fields(self):
        reply = self.run_op("task.rename", {"id": "P1.1", "title": "Fields"})
        line = self.line_of(reply["activity"])
        self.assertEqual(line["op"], "task.rename")
        self.assertEqual(line["src"], "gui")
        self.assertEqual(line["sum"], "P1.1 title=Fields")
        self.assertTrue(line["undo"])

    def test_the_injected_now_is_the_activity_time(self):
        when = datetime.datetime(2026, 1, 2, 3, 4, 5, tzinfo=datetime.timezone.utc)
        with commands.context("gui", PROJECT_ID):
            reply = commands.run("task.rename", {"id": "P1.1", "title": "Timed"}, "gui", self.data_dir, now=when)
        self.assertEqual(self.line_of(reply["activity"])["at"], records.now_iso(when))


if __name__ == "__main__":
    unittest.main()
