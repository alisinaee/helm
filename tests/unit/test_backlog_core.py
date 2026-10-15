"""R7.22 step 1: the backlog task status in the core (parsers, mdtables, planfmt, guide) and the CLI commands
`task backlog|promote`, `backlog add` and the start guard. Counts and progress are step 2/3 and are not tested here."""

import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from roadmap.cli import main
from roadmap.core import guide, mdtables, parsers, planfmt
from roadmap.errors import EXIT_CONFLICT
from roadmap.services import tasks
from roadmap.store import config as config_store
from tests.api.support import FIXTURE, PROJECT_ID


def run(argv):
    """Run the CLI in-process and return (exit code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


class ParserTests(unittest.TestCase):
    def test_task_may_be_backlog_and_phase_reads_it_as_todo(self):
        text = json.dumps({"updated": "", "phases": [{"id": "P1", "name": "A", "status": "backlog"}],
                           "tasks": [{"id": "P1.1", "phase": "P1", "title": "x", "status": "backlog"}]})
        data, errors = parsers.parse_tasks(text)
        self.assertEqual(errors, [])
        self.assertEqual(data["tasks"][0]["state"], "backlog")
        self.assertEqual(data["phases"][0]["state"], "todo")

    def test_unknown_task_status_still_reads_as_todo(self):
        text = json.dumps({"updated": "", "phases": [], "tasks": [{"id": "P1.1", "phase": "P1", "status": "soon"}]})
        data, _ = parsers.parse_tasks(text)
        self.assertEqual(data["tasks"][0]["state"], "todo")

    def test_deferred_is_still_its_own_state(self):
        text = json.dumps({"updated": "", "phases": [], "tasks": [{"id": "P1.1", "phase": "P1", "status": "hold",
                                                                   "note": "Deferred until v2"}]})
        data, _ = parsers.parse_tasks(text)
        self.assertEqual(data["tasks"][0]["state"], "deferred")


class PlanFormatTests(unittest.TestCase):
    def test_task_line_accepts_backlog(self):
        records, errors = planfmt.parse_plan("P BL - | Backlog\nT BL.1 backlog 0 haiku/low | An idea")
        self.assertEqual(errors, [])
        self.assertEqual(records[1]["status"], "backlog")

    def test_phase_line_refuses_backlog(self):
        records, errors = planfmt.parse_plan("P P1 backlog | Foundations")
        self.assertEqual(records, [])
        self.assertIn("status 'backlog' is not valid", errors[0])
        self.assertNotIn("backlog", planfmt.PHASE_STATUSES)

    def test_backlog_task_round_trips(self):
        text = "P BL - | Backlog\nT BL.1 backlog 0 haiku/low | An idea # note"
        records, _ = planfmt.parse_plan(text)
        line = planfmt.format_task(dict(id="BL.1", status="backlog", tokensK=0, model="haiku", thinking="low",
                                        title="An idea"))
        self.assertTrue(line.startswith("T BL.1 backlog 0 haiku/low"))
        again, errors = planfmt.parse_plan(line + " | An idea")
        self.assertEqual(errors, [])
        self.assertEqual(again[0]["status"], "backlog")
        self.assertEqual(records[1]["id"], "BL.1")

    def test_set_line_accepts_backlog_status(self):
        rec, problem = planfmt.parse_set_line("P1.1 status=backlog")
        self.assertIsNone(problem)
        self.assertEqual(rec["fields"], {"status": "backlog"})

    def test_guide_names_backlog(self):
        self.assertTrue(any("backlog" in line for line in guide.lines()))
        self.assertLessEqual(len(guide.lines()), guide.GUIDE_MAX_LINES)


class MarkdownTests(unittest.TestCase):
    def test_backlog_emoji_and_word_classify(self):
        self.assertEqual(mdtables.classify("💡"), "backlog")
        self.assertEqual(mdtables.classify("Backlog"), "backlog")
        self.assertEqual(mdtables.classify("⬜ todo"), "todo")


class BacklogCliTests(unittest.TestCase):
    def setUp(self):
        env = mock.patch.dict(os.environ, {})
        env.start()
        self.addCleanup(env.stop)
        self.tmp = tempfile.mkdtemp(prefix="rb-backlog-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        os.environ["ROADMAP_HOME"] = os.path.join(self.tmp, "home")
        os.environ.pop("CLAUDECODE", None)
        root = os.path.join(self.tmp, "split_net")
        shutil.copytree(FIXTURE, os.path.join(root, "docs"))
        config_store.add_project("split-net", root, project_id=PROJECT_ID)
        self.data_dir = tasks.resolve(PROJECT_ID)[1]

    def status_of(self, tid):
        return tasks.get(self.data_dir, tid)["status"]

    def test_add_without_phase_creates_reserved_phase_and_numbers_tasks(self):
        code, out, _ = run(["backlog", "add", "Faster export", "--project", PROJECT_ID])
        self.assertEqual(code, 0)
        self.assertIn("T BL.1 added (backlog)", out)
        self.assertIn("next: roadmap task promote BL.1", out)
        doc = tasks.load(self.data_dir)
        self.assertEqual([p["id"] for p in doc["phases"]][-1], "BL")
        self.assertEqual(self.status_of("BL.1"), "backlog")
        code, out, _ = run(["backlog", "add", "Second idea", "--project", PROJECT_ID])
        self.assertIn("T BL.2 added", out)

    def test_add_to_given_phase_and_the_list_filter(self):
        phase = tasks.load(self.data_dir)["phases"][0]["id"]
        code, out, _ = run(["backlog", "add", "Idea here", "--phase", phase, "--project", PROJECT_ID])
        self.assertEqual(code, 0)
        tid = out.split()[1]
        self.assertTrue(tid.startswith(phase + "."))
        code, out, _ = run(["task", "list", "--status", "backlog", "--project", PROJECT_ID])
        self.assertIn(tid, out)

    def test_add_refuses_empty_and_long_titles(self):
        code, _, err = run(["backlog", "add", "   ", "--project", PROJECT_ID])
        self.assertNotEqual(code, 0)
        code, _, err = run(["backlog", "add", "x" * (parsers.TITLE_MAX + 1), "--project", PROJECT_ID])
        self.assertNotEqual(code, 0)
        self.assertIn("up to", err)

    def test_promote_and_demote_move_between_backlog_and_todo(self):
        run(["backlog", "add", "Idea", "--project", PROJECT_ID])
        code, out, _ = run(["task", "promote", "BL.1", "--project", PROJECT_ID])
        self.assertEqual(code, 0)
        self.assertIn("ok BL.1 -> todo. next: roadmap task start BL.1", out)
        self.assertEqual(self.status_of("BL.1"), "todo")
        code, out, _ = run(["task", "backlog", "BL.1", "--project", PROJECT_ID])
        self.assertIn("ok BL.1 -> backlog. next: roadmap task promote BL.1", out)
        self.assertEqual(self.status_of("BL.1"), "backlog")

    def test_promote_of_a_task_not_in_backlog_is_a_conflict(self):
        code, _, err = run(["task", "promote", "P1.1", "--project", PROJECT_ID])
        self.assertEqual(code, EXIT_CONFLICT)
        self.assertIn("P1.1 is not backlog", err)

    def test_agent_shell_cannot_promote_or_demote(self):
        run(["backlog", "add", "Idea", "--project", PROJECT_ID])
        with mock.patch.dict(os.environ, {"CLAUDECODE": "1"}):
            code, _, err = run(["task", "promote", "BL.1", "--project", PROJECT_ID])
            self.assertEqual(code, EXIT_CONFLICT)
            self.assertIn('roadmap ask', err)
            code, _, _ = run(["task", "backlog", "P1.1", "--project", PROJECT_ID])
            self.assertEqual(code, EXIT_CONFLICT)
            code, out, _ = run(["backlog", "add", "Agent idea", "--project", PROJECT_ID])
            self.assertEqual(code, 0)  # agents may add to the backlog
        self.assertEqual(self.status_of("BL.1"), "backlog")

    def test_start_of_a_backlog_task_is_refused_for_everyone(self):
        run(["backlog", "add", "Idea", "--project", PROJECT_ID])
        code, _, err = run(["task", "start", "BL.1", "--project", PROJECT_ID])
        self.assertEqual(code, EXIT_CONFLICT)
        self.assertIn("BL.1 is backlog", err)
        self.assertIn("roadmap task promote BL.1", err)
        self.assertEqual(self.status_of("BL.1"), "backlog")

    def test_bulk_set_cannot_start_a_backlog_task_or_promote_from_an_agent(self):
        run(["backlog", "add", "Idea", "--project", PROJECT_ID])
        with mock.patch("sys.stdin", io.StringIO("BL.1 status=partial\n")):
            code, _, _ = run(["task", "set", "--project", PROJECT_ID])
        self.assertNotEqual(code, 0)
        self.assertEqual(self.status_of("BL.1"), "backlog")
        with mock.patch.dict(os.environ, {"CLAUDECODE": "1"}), \
                mock.patch("sys.stdin", io.StringIO("BL.1 status=todo\n")):
            code, _, _ = run(["task", "set", "--project", PROJECT_ID])
        self.assertEqual(code, EXIT_CONFLICT)
        self.assertEqual(self.status_of("BL.1"), "backlog")


if __name__ == "__main__":
    unittest.main()
