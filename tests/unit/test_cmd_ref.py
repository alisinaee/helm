"""The ref command on the CLI: a task, a feature, a phase, an orphan task, an issue and a sub resolve in one call; an
unknown ref and an unknown project exit with a next: line; --json prints the same as the text."""

import json
import os

from tests.unit.test_cmd_support import CmdCase
from tests.unit.test_project_support import run_cli


class RefCommandTests(CmdCase):
    def setUp(self):
        super().setUp()
        code, _, err = self.cli(["feature", "add", "Planner filters", "--phase", "P1"])
        assert code == 0, err
        code, _, err = self.cli(["feature", "link", "F1", "P1.1"])
        assert code == 0, err
        code, _, err = self.cli(["subtask", "add", "P1.1", "write the filter"])
        assert code == 0, err

    def ref(self, text, *extra):
        """The ref command has no --project: a ref names its project, so run it without the demo flag."""
        return run_cli(["ref", text] + list(extra))

    def test_task_record_in_one_call(self):
        code, out, err = self.ref("rb:demo/task/P1.1")
        self.assertEqual(code, 0, err)
        lines = out.splitlines()
        self.assertEqual(lines[0], "ref: rb:demo/task/P1.1")
        self.assertIn("title: First task", lines)
        self.assertIn("feature: F1", out)
        self.assertIn("orphan: no", out)
        self.assertEqual(lines[-1], "next: roadmap task show P1.1")
        self.assertLessEqual(len(lines), 10)

    def test_orphan_task_is_flagged(self):
        code, out, err = self.ref("rb:demo/task/P1.2")
        self.assertEqual(code, 0, err)
        self.assertIn("orphan: yes", out)

    def test_feature_phase_sub_and_project_records(self):
        code, out, err = self.ref("rb:demo/feature/F1")
        self.assertEqual(code, 0, err)
        self.assertIn("title: Planner filters", out)
        self.assertIn("next: roadmap feature show F1", out)
        code, out, err = self.ref("rb:demo/phase/P1")
        self.assertEqual(code, 0, err)
        self.assertIn("title: Engine", out)
        self.assertIn("next: roadmap plan view", out)
        code, out, err = self.ref("rb:demo/sub/P1.1.s1")
        self.assertEqual(code, 0, err)
        self.assertIn("title: write the filter", out)
        code, out, err = self.ref("rb:demo")
        self.assertEqual(code, 0, err)
        self.assertIn("next: roadmap project show demo", out)

    def test_issue_record_and_unknown_issue(self):
        self.cli(["issue", "new", "Login fails", "--kind", "bug", "--task", "P1.1"])
        code, out, err = self.ref("rb:demo/issue/I1")
        self.assertEqual(code, 0, err)
        self.assertIn("title: Login fails", out)
        self.assertIn("next: roadmap issue show I1", out)
        code, _, err = self.ref("rb:demo/issue/I9")
        self.assertEqual(code, 2)
        self.assertIn("unknown ref: rb:demo/issue/I9", err)
        self.assertIn("next:", err)

    def test_unknown_task_is_an_unknown_ref_with_exit_2(self):
        code, _, err = self.ref("rb:demo/task/P9.9")
        self.assertEqual(code, 2)
        self.assertIn("unknown ref", err)
        self.assertIn("next: roadmap status", err)

    def test_malformed_ref_is_an_unknown_ref_with_exit_2(self):
        code, _, err = self.ref("task P1.1")
        self.assertEqual(code, 2)
        self.assertIn("unknown ref", err)

    def test_unknown_project_lists_the_project_command(self):
        code, _, err = self.ref("rb:nope/task/P1.1")
        self.assertEqual(code, 3)
        self.assertIn("no registered project with id 'nope'", err)
        self.assertIn("next: roadmap project list", err)

    def test_json_is_the_same_record_as_one_object(self):
        code, out, err = self.ref("rb:demo/task/P1.1", "--json")
        self.assertEqual(code, 0, err)
        body = json.loads(out)
        self.assertIs(body["ok"], True)
        data = body["data"]
        self.assertEqual(data["ref"], "rb:demo/task/P1.1")
        self.assertEqual(data["title"], "First task")
        self.assertEqual(data["feature"], "F1")
        self.assertEqual(data["next"], "roadmap task show P1.1")

    def test_no_output_names_an_absolute_path(self):
        for text in ("rb:demo/task/P1.1", "rb:demo/phase/P1", "rb:demo/feature/F1", "rb:demo"):
            with self.subTest(ref=text):
                _, out, _ = self.ref(text)
                self.assertNotIn(self.folder, out)
                self.assertNotIn("/Users/", out)
                self.assertNotIn(os.sep + "tmp", out)

    def test_research_note_is_found_by_its_number(self):
        notes = os.path.join(self.data, "research")
        os.makedirs(notes, exist_ok=True)
        with open(os.path.join(notes, "01-first-look.md"), "w", encoding="utf-8") as fh:
            fh.write("# first look\n")
        code, out, err = self.ref("rb:demo/research/01")
        self.assertEqual(code, 0, err)
        self.assertIn("file: research/01-first-look.md", out)
        code, _, _ = self.ref("rb:demo/research/02")
        self.assertEqual(code, 2)
