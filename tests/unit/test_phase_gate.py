"""Tests for the phase approval gate and the research status line (WP62b).

A phase whose approved flag is explicitly false refuses `task start` (exit 4, nothing written). Phases without the key
(old projects) behave as before. `status` gets one extra line for the research notes and the unapproved phases.
Everything runs in a temp ROADMAP_HOME and a temp project folder, through the CLI."""

import json
import os

from tests.unit.test_project_support import ProjectCase, read_text, run_cli, write_json

REFUSAL = ("roadmap: phase P1 is not approved. next: ask the person to approve it "
           "(GUI Roadmap > Approve, or roadmap phase approve P1)\n")


def phases_doc(p1_approved=None):
    """A tasks.json with phase P1 (approved as given: False, True, or missing when None) and P2 without the key."""
    p1 = {"id": "P1", "name": "Phase 1", "status": "todo"}
    if p1_approved is not None:
        p1["approved"] = p1_approved
    return {"schemaVersion": 1, "updated": "2026-10-13", "phases": [p1, {"id": "P2", "name": "Phase 2",
                                                                          "status": "todo"}],
            "tasks": [{"id": "P1.1", "title": "First", "status": "todo", "phase": "P1"},
                      {"id": "P1.2", "title": "Second", "status": "todo", "phase": "P1"},
                      {"id": "P2.1", "title": "Third", "status": "todo", "phase": "P2"}]}


class PhaseGateCase(ProjectCase):
    def setUp(self):
        super().setUp()
        self.init_and_add()
        self.tasks_path = os.path.join(self.data, "tasks.json")

    def write_plan(self, p1_approved=None):
        write_json(self.tasks_path, phases_doc(p1_approved))

    def cli(self, argv):
        return run_cli(list(argv) + ["--project", "demo"])

    def status_of(self, tid):
        with open(self.tasks_path, encoding="utf-8") as fh:
            for task in json.load(fh)["tasks"]:
                if task["id"] == tid:
                    return task["status"]
        return None


class StartRefusalTests(PhaseGateCase):
    def test_start_is_refused_in_an_unapproved_phase_with_exit_4_and_hint(self):
        self.write_plan(p1_approved=False)
        before = read_text(self.tasks_path)
        code, _, err = self.cli(["task", "start", "P1.1"])
        self.assertEqual(code, 4)
        self.assertEqual(err, REFUSAL)
        self.assertEqual(read_text(self.tasks_path), before)

    def test_refused_start_leaves_the_task_todo(self):
        self.write_plan(p1_approved=False)
        self.cli(["task", "start", "P1.1"])
        self.assertEqual(self.status_of("P1.1"), "todo")

    def test_one_refused_id_refuses_the_whole_call(self):
        self.write_plan(p1_approved=False)
        code, _, _ = self.cli(["task", "start", "P2.1", "P1.1"])
        self.assertEqual(code, 4)
        self.assertEqual(self.status_of("P2.1"), "todo")

    def test_unknown_id_is_still_not_found(self):
        self.write_plan(p1_approved=False)
        code, _, _ = self.cli(["task", "start", "P9.9"])
        self.assertEqual(code, 3)

    def test_done_and_hold_are_not_gated(self):
        self.write_plan(p1_approved=False)
        code, _, err = self.cli(["task", "hold", "P1.1"])
        self.assertEqual(code, 0, err)
        code, _, err = self.cli(["task", "done", "P1.2"])
        self.assertEqual(code, 0, err)


class ApprovedPhaseTests(PhaseGateCase):
    def test_approved_phase_starts(self):
        self.write_plan(p1_approved=True)
        code, out, err = self.cli(["task", "start", "P1.1"])
        self.assertEqual(code, 0, err)
        self.assertIn("P1.1 partial", out)
        self.assertEqual(self.status_of("P1.1"), "partial")

    def test_other_phase_without_the_key_starts(self):
        self.write_plan(p1_approved=False)
        code, _, err = self.cli(["task", "start", "P2.1"])
        self.assertEqual(code, 0, err)
        self.assertEqual(self.status_of("P2.1"), "partial")

    def test_approving_then_starting_works_after_the_flag_changes(self):
        self.write_plan(p1_approved=False)
        self.assertEqual(self.cli(["task", "start", "P1.1"])[0], 4)
        self.write_plan(p1_approved=True)
        code, _, err = self.cli(["task", "start", "P1.1"])
        self.assertEqual(code, 0, err)


class OldProjectTests(PhaseGateCase):
    def test_phases_without_the_key_behave_as_before(self):
        self.write_plan(p1_approved=None)
        code, _, err = self.cli(["task", "start", "P1.1"])
        self.assertEqual(code, 0, err)
        self.assertEqual(self.status_of("P1.1"), "partial")

    def test_old_project_status_has_no_gate_line(self):
        self.write_plan(p1_approved=None)
        code, out, _ = self.cli(["status"])
        self.assertEqual(code, 0)
        self.assertFalse(any("approved" in line or line.startswith("research ") for line in out.splitlines()), out)


class StatusGateLineTests(PhaseGateCase):
    def add_research(self, notes):
        """notes: list of (number, slug, has_finding). Writes the note files and INDEX.md lines."""
        folder = os.path.join(self.data, "research")
        os.makedirs(folder, exist_ok=True)
        index = "# Research index\n\n"
        for number, slug, has_finding in notes:
            with open(os.path.join(folder, "%02d-%s.md" % (number, slug)), "w", encoding="utf-8") as fh:
                fh.write("# Research\n")
            finding = "Found it." if has_finding else "(no finding yet)"
            index += "- %02d %s — Title — %s\n" % (number, slug, finding)
        with open(os.path.join(folder, "INDEX.md"), "w", encoding="utf-8") as fh:
            fh.write(index)

    def status_lines(self):
        code, out, err = self.cli(["status"])
        self.assertEqual(code, 0, err)
        return out.splitlines()

    def test_research_and_unapproved_phase_share_one_line(self):
        self.write_plan(p1_approved=False)
        self.add_research([(1, "scope", False), (2, "market", True)])
        lines = self.status_lines()
        gate = [line for line in lines if line.startswith("research ")]
        self.assertEqual(gate, ["research 1/2 open, phase P1 not approved"])

    def test_only_the_unapproved_phase_when_there_is_no_research_folder(self):
        self.write_plan(p1_approved=False)
        self.assertIn("phase P1 not approved", self.status_lines())

    def test_only_research_when_every_phase_is_approved(self):
        self.write_plan(p1_approved=True)
        self.add_research([(1, "scope", False)])
        self.assertIn("research 1/1 open", self.status_lines())

    def test_several_unapproved_phases_name_the_first_and_count_the_rest(self):
        doc = phases_doc(p1_approved=False)
        doc["phases"][1]["approved"] = False
        write_json(self.tasks_path, doc)
        self.assertIn("phase P1 not approved (+1)", self.status_lines())

    def test_status_stays_within_the_line_and_character_budget(self):
        self.write_plan(p1_approved=False)
        self.add_research([(1, "scope", False), (2, "market", False), (3, "stack", True)])
        self.op_issue()
        lines = self.status_lines()
        self.assertLessEqual(len(lines), 8)
        self.assertLessEqual(len("\n".join(lines)), 700)
        self.assertIn("research 2/3 open, phase P1 not approved", lines)

    def op_issue(self):
        """One open issue, so the issues line is present and the budget is tight."""
        from roadmap.services import commands
        commands.run("issue.new", {"title": "Login fails on Safari", "kind": "blocker", "sev": 1},
                     "cli", self.data)
