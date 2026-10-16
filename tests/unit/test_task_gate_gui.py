"""The unapproved-phase gate on the GUI/API task status path (R9.24, Q24).

The CLI `task start` refuses a task in a phase whose approved flag is explicitly false (WP62b, tasks.start_refusal).
The GUI Start button sends task.status with status partial through the command layer, so the same rule must apply
there: refused with exit 4, nothing written, no activity line. Other statuses and approved or old phases are unchanged.
Runs in a temp ROADMAP_HOME through the command layer only."""

import json
import os

from roadmap.errors import EXIT_CONFLICT, RoadmapError
from tests.unit.test_cmd_support import CmdCase


class GuiStartGateTests(CmdCase):
    def set_p1_approved(self, value):
        path = os.path.join(self.data, "tasks.json")
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        for phase in doc["phases"]:
            if phase["id"] == "P1":
                if value is None:
                    phase.pop("approved", None)
                else:
                    phase["approved"] = value
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)

    def status_of(self, tid):
        for task in self.read_json("tasks.json")["tasks"]:
            if task["id"] == tid:
                return task["status"]
        return None

    def test_gui_start_in_unapproved_phase_is_refused_and_writes_nothing(self):
        self.set_p1_approved(False)
        before = self.read_json("tasks.json")
        with self.assertRaises(RoadmapError) as ctx:
            self.op("task.status", {"id": "P1.1", "status": "partial"})
        self.assertEqual(ctx.exception.code, "conflict")
        self.assertEqual(ctx.exception.exit, EXIT_CONFLICT)
        self.assertIn("phase P1 is not approved", ctx.exception.message)
        self.assertEqual(self.read_json("tasks.json"), before)
        self.assertEqual(self.read_lines("activity.jsonl"), [])

    def test_refusal_is_the_same_message_as_the_cli_rule(self):
        self.set_p1_approved(False)
        with self.assertRaises(RoadmapError) as gui:
            self.op("task.status", {"id": "P1.1", "status": "partial"})
        with self.assertRaises(RoadmapError) as cli:
            self.op("task.status", {"id": "P1.2", "status": "partial"})
        self.assertEqual(gui.exception.message, cli.exception.message)
        self.assertEqual(gui.exception.next, cli.exception.next)

    def test_gui_start_in_approved_phase_still_works(self):
        self.set_p1_approved(True)
        reply = self.op("task.status", {"id": "P1.1", "status": "partial"})
        self.assertTrue(reply["ok"])
        self.assertEqual(self.status_of("P1.1"), "partial")

    def test_gui_start_in_phase_without_the_key_still_works(self):
        self.set_p1_approved(None)
        reply = self.op("task.status", {"id": "P1.1", "status": "partial"})
        self.assertTrue(reply["ok"])
        self.assertEqual(self.status_of("P1.1"), "partial")

    def test_non_start_status_in_unapproved_phase_is_not_gated(self):
        self.set_p1_approved(False)
        reply = self.op("task.status", {"id": "P1.1", "status": "hold"})
        self.assertTrue(reply["ok"])
        self.assertEqual(self.status_of("P1.1"), "hold")
