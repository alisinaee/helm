"""Tests for the task, plan and status commands (WP16.2): output line budgets, dry runs write nothing, a second import
prints '0 changed', unknown ids and invalid input exit with a next: line, --json envelopes, and reads never change a
file. Everything runs in a temp ROADMAP_HOME with a temp project."""

import io
import json
import os
from unittest import mock

from roadmap.core import planfmt
from tests.unit.test_project_support import ProjectCase, run_cli

EXAMPLE = """P M1 todo | Foundations
T M1.1 todo 20 haiku/low | Scaffold repo, CI and lint
T M1.2 todo 40 sonnet/medium c:sonnet/8 | Data model and storage layer
T M1.3 todo 5 haiku/low ! | Create hosting account and API key # needs your login
T M1.4 todo 80 opus/high c:opus/15 | Sync engine design and spike
T M1.5 todo 10 haiku/low | README quick start
"""


class TaskCmdCase(ProjectCase):
    def setUp(self):
        super().setUp()
        self.init_and_add()
        self.tasks_file = os.path.join(self.data, "tasks.json")
        self.jobs_file = os.path.join(self.data, "jobs.json")
        self.initial = self.raw(self.tasks_file)  # init leaves an empty tasks.json behind

    def cli(self, argv, stdin=None):
        """Run the CLI with --project demo; stdin text is fed through a patched sys.stdin."""
        argv = list(argv) + ["--project", "demo"]
        if stdin is None:
            return run_cli(argv)
        with mock.patch("sys.stdin", io.StringIO(stdin)):
            return run_cli(argv)

    def raw(self, path):
        if not os.path.exists(path):
            return None
        with open(path, "rb") as fh:
            return fh.read()

    def import_example(self):
        code, out, err = self.cli(["plan", "import", "-"], stdin=EXAMPLE)
        self.assertEqual(code, 0, err)
        return out

    def add_many_tasks(self, count):
        lines = ["P P1 todo | Bulk"]
        lines += ["T P1.%d todo 1 haiku/low | task %d" % (n, n) for n in range(1, count + 1)]
        code, _, err = self.cli(["plan", "import", "-"], stdin="\n".join(lines) + "\n")
        self.assertEqual(code, 0, err)


class PlanTemplateTests(TaskCmdCase):
    def test_template_fits_in_fifteen_lines(self):
        code, out, _ = run_cli(["plan", "template"])
        self.assertEqual(code, 0)
        self.assertLessEqual(len(out.splitlines()), 15)
        self.assertIn("P M1 todo | Foundations", out)

    def test_template_json_envelope(self):
        code, out, _ = run_cli(["plan", "template", "--json"])
        body = json.loads(out)
        self.assertTrue(body["ok"])
        self.assertIn("P <id> <status> | <name>", body["data"]["text"])


class PlanImportTests(TaskCmdCase):
    def test_dry_run_reports_would_and_writes_nothing(self):
        code, out, err = self.cli(["plan", "import", "-", "--dry-run"], stdin=EXAMPLE)
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "would: +P1 +T5 (no write)")
        self.assertEqual(self.raw(self.tasks_file), self.initial)

    def test_dry_run_does_not_change_an_existing_file(self):
        self.import_example()
        before = self.raw(self.tasks_file)
        code, out, _ = self.cli(["plan", "import", "-", "--dry-run"],
                                stdin=EXAMPLE.replace("todo 20", "done 20"))
        self.assertEqual(code, 0)
        self.assertIn("~T1", out)
        self.assertIn("M1.1 status todo→done", out)
        self.assertEqual(self.raw(self.tasks_file), before)

    def test_real_import_then_second_import_is_zero_changed(self):
        out = self.import_example()
        self.assertEqual(out.strip(), "wrote: +P1 +T5")
        before = self.raw(self.tasks_file)
        code, out, _ = self.cli(["plan", "import", "-"], stdin=EXAMPLE)
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "0 changed")
        self.assertEqual(self.raw(self.tasks_file), before)

    def test_import_from_markdown_reads_the_roadmap_plan_block(self):
        path = os.path.join(self.tmp, "note.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("# Plan\n\n```text\nT X9.9 nope\n```\n\n```roadmap-plan\n" + EXAMPLE + "```\n")
        code, out, err = self.cli(["plan", "import", path])
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "wrote: +P1 +T5")

    def test_invalid_plan_writes_nothing_and_exits_five_with_next(self):
        bad = EXAMPLE + "T M1.9 nope 1 haiku/low | bad status\nP M2 maybe | x\n"
        code, out, err = self.cli(["plan", "import", "-"], stdin=bad)
        self.assertEqual(code, 5)
        self.assertEqual(self.raw(self.tasks_file), self.initial)
        lines = err.splitlines()
        self.assertLessEqual(len(lines), 6)
        self.assertTrue(lines[0].startswith("roadmap: line 7:"))
        self.assertEqual(lines[-1], "next: roadmap plan import - --dry-run")

    def test_missing_phase_exits_three_with_next(self):
        code, _, err = self.cli(["plan", "import", "-"], stdin="T Z9.1 todo 1 haiku/low | orphan\n")
        self.assertEqual(code, 3)
        self.assertIn("next: roadmap status", err)
        self.assertEqual(self.raw(self.tasks_file), self.initial)

    def test_import_json_envelope_carries_summary(self):
        code, out, _ = self.cli(["plan", "import", "-", "--dry-run", "--json"], stdin=EXAMPLE)
        body = json.loads(out)
        self.assertEqual(code, 0)
        self.assertTrue(body["ok"])
        self.assertEqual(body["data"]["summary"], "would: +P1 +T5 (no write)")
        self.assertTrue(body["data"]["dry_run"])


class PlanExportTests(TaskCmdCase):
    def test_export_round_trips_through_the_parser(self):
        self.import_example()
        code, out, _ = self.cli(["plan", "export"])
        self.assertEqual(code, 0)
        records, errors = planfmt.parse_plan(out)
        self.assertEqual(errors, [])
        self.assertEqual(len(records), 6)

    def test_export_one_line_per_record_and_phase_filter(self):
        self.import_example()
        self.add_many_tasks(2)
        code, out, _ = self.cli(["plan", "export", "--phase", "M1"])
        self.assertEqual(code, 0)
        self.assertEqual(len(out.splitlines()), 6)
        self.assertTrue(out.splitlines()[0].startswith("P M1 "))

    def test_export_unknown_phase_exits_three(self):
        code, _, err = self.cli(["plan", "export", "--phase", "P9"])
        self.assertEqual(code, 3)
        self.assertIn("next: roadmap status", err)


class TaskChangeTests(TaskCmdCase):
    def setUp(self):
        super().setUp()
        self.import_example()

    def test_done_prints_one_line_per_id_and_stores_tokens(self):
        code, out, err = self.cli(["task", "done", "M1.1", "M1.2", "--tokens", "18", "--note", "wired"])
        self.assertEqual(code, 0, err)
        self.assertEqual(out.splitlines(), ["M1.1 done", "M1.2 done"])
        with open(self.tasks_file, encoding="utf-8") as fh:
            doc = json.load(fh)
        first = [t for t in doc["tasks"] if t["id"] == "M1.1"][0]
        self.assertEqual(first["status"], "done")
        self.assertEqual(first["tokensK"], 18)
        self.assertEqual(first["note"], "wired")

    def test_start_and_hold_set_partial_and_hold(self):
        code, out, _ = self.cli(["task", "start", "M1.1"])
        self.assertEqual(out.strip(), "M1.1 partial")
        code, out, _ = self.cli(["task", "hold", "M1.5"])
        self.assertEqual(out.strip(), "M1.5 hold")

    def test_unknown_id_exits_three_with_exact_next_line(self):
        code, _, err = self.cli(["task", "done", "P9.9"])
        self.assertEqual(code, 3)
        self.assertEqual(err, "roadmap: no task P9.9. next: roadmap task list --phase P9\n")

    def test_unknown_id_in_bulk_set_exits_three_and_writes_nothing(self):
        before = self.raw(self.tasks_file)
        code, _, err = self.cli(["task", "set", "-"], stdin="M9.1 status=done\n")
        self.assertEqual(code, 3)
        self.assertIn("next: roadmap task list --phase M9", err)
        self.assertEqual(self.raw(self.tasks_file), before)

    def test_bulk_set_from_stdin_and_one_line_summary(self):
        code, out, err = self.cli(["task", "set", "-"], stdin="M1.1 status=done tokensK=18\n")
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "wrote: ~P1 ~T1")
        self.assertEqual(len(out.splitlines()), 1)

    def test_bulk_set_dry_run_lists_field_diffs_and_writes_nothing(self):
        before = self.raw(self.tasks_file)
        code, out, _ = self.cli(["task", "set", "-", "--dry-run"], stdin="M1.1 status=done\n")
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines()[0], "would: ~P1 ~T1 (no write)")
        self.assertIn("~ M1.1 status todo→done", out.splitlines())
        self.assertEqual(self.raw(self.tasks_file), before)

    def test_bulk_set_bad_line_exits_five_and_writes_nothing(self):
        before = self.raw(self.tasks_file)
        code, _, err = self.cli(["task", "set", "-"], stdin="M1.1 status=finished\n")
        self.assertEqual(code, 5)
        self.assertLessEqual(len(err.splitlines()), 6)
        self.assertTrue(err.splitlines()[-1].startswith("next: roadmap task set - --dry-run"))
        self.assertEqual(self.raw(self.tasks_file), before)

    def test_non_whole_tokens_is_rejected_before_any_write(self):
        before = self.raw(self.tasks_file)
        code, _, err = self.cli(["task", "done", "M1.1", "--tokens", "1.5"])
        self.assertEqual(code, 5)
        self.assertEqual(self.raw(self.tasks_file), before)

    def test_task_change_json_envelope(self):
        code, out, _ = self.cli(["task", "done", "M1.1", "--json"])
        body = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual(body["data"], {"ids": ["M1.1"], "status": "done"})

    def test_error_json_carries_error_next(self):
        code, out, _ = self.cli(["task", "show", "P9.9", "--json"])
        body = json.loads(out)
        self.assertEqual(code, 3)
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"]["next"], "roadmap task list --phase P9")


class TaskReadTests(TaskCmdCase):
    def setUp(self):
        super().setUp()
        self.import_example()

    def test_show_is_one_plan_line(self):
        code, out, _ = self.cli(["task", "show", "M1.3"])
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(), [
            "T M1.3 todo 5 haiku/low ! | Create hosting account and API key # needs your login"])

    def test_list_default_limit_is_twenty_lines(self):
        self.add_many_tasks(25)
        code, out, _ = self.cli(["task", "list"])
        self.assertEqual(code, 0)
        self.assertEqual(len(out.splitlines()), 20)

    def test_list_filters_by_needs_you_and_phase(self):
        code, out, _ = self.cli(["task", "list", "--needs-you", "--phase", "M1"])
        self.assertEqual(len(out.splitlines()), 1)
        self.assertIn("M1.3", out)

    def test_list_with_no_match_says_so(self):
        code, out, _ = self.cli(["task", "list", "--status", "done"])
        self.assertEqual(out.strip(), "no tasks")

    def test_list_bad_status_is_usage_error(self):
        code, _, err = self.cli(["task", "list", "--status", "finished"])
        self.assertEqual(code, 2)
        self.assertIn("status 'finished' is not valid", err)

    def test_reads_never_modify_files(self):
        self.cli(["job", "start", "Scaffold", "haiku", "M1.1"])
        before = (self.raw(self.tasks_file), self.raw(self.jobs_file))
        for argv in (["task", "show", "M1.1"], ["task", "list"], ["plan", "export"], ["status"],
                     ["task", "list", "--json"]):
            code, _, err = self.cli(argv)
            self.assertEqual(code, 0, err)
        self.assertEqual(run_cli(["plan", "template"])[0], 0)
        self.assertEqual((self.raw(self.tasks_file), self.raw(self.jobs_file)), before)


class StatusTests(TaskCmdCase):
    def setUp(self):
        super().setUp()
        self.import_example()

    def test_status_within_budget(self):
        self.cli(["job", "start", "Scaffold", "haiku", "M1.1"])
        code, out, err = self.cli(["status"])
        self.assertEqual(code, 0, err)
        self.assertLessEqual(len(out.splitlines()), 8)
        self.assertLessEqual(len(out), 700)
        self.assertIn("running 1", out)
        self.assertIn("run: j1 haiku M1.1", out)

    def test_status_json_envelope(self):
        code, out, _ = self.cli(["status", "--json"])
        body = json.loads(out)
        self.assertEqual(code, 0)
        self.assertTrue(body["data"]["lines"][0].startswith("demo  updated"))
