"""HEAD-SPEC H5: the `roadmap head` commands (roadmap/commands/head.py) through cli.main. The ok/next grammar, the list
columns, the one-call triage, claim and brief, review (the person's only: a non-TTY shell is refused), and the status
line. Runs in a temp ROADMAP_HOME with a copy of the fixture project."""

import contextlib
import io
import os
import re
import shutil
import tempfile
import unittest
from unittest import mock

from roadmap.cli import main
from roadmap.commands import head as head_cmd
from roadmap.services import tasks
from roadmap.services import head as store
from roadmap.store import config as config_store
from tests.api.support import FIXTURE, PROJECT_ID

LIST_RE = re.compile(r"^H\d+ +\S+ +\S+ +(\d+[mhd]|-) +\S* *.*$")


def _not_tty():
    stream = mock.Mock()
    stream.isatty.return_value = False
    return stream


def _run(argv):
    """Run the CLI in-process as a non-TTY shell: (exit code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with mock.patch("sys.stdin", _not_tty()), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv + ["--project", PROJECT_ID])
    return code, out.getvalue(), err.getvalue()


class HeadCliCase(unittest.TestCase):
    def setUp(self):
        env = mock.patch.dict(os.environ, {})
        env.start()
        self.addCleanup(env.stop)
        self.tmp = tempfile.mkdtemp(prefix="rb-head-cli-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        os.environ["ROADMAP_HOME"] = os.path.join(self.tmp, "home")
        os.environ.pop("CLAUDECODE", None)
        root = os.path.join(self.tmp, "split_net")
        shutil.copytree(FIXTURE, os.path.join(root, "docs"))
        config_store.add_project("split-net", root, project_id=PROJECT_ID)
        self.data_dir = tasks.resolve(PROJECT_ID)[1]

    def log(self, text, kind="ask", extra=()):
        code, out, _ = _run(["head", "log", text, "--kind", kind] + list(extra))
        self.assertEqual(code, 0)
        return re.match(r"^ok (H\d+) ", out).group(1)

    def test_log_grammar_ok_then_next(self):
        code, out, _ = _run(["head", "log", "make the map open in a new tab", "--kind", "ask"])
        self.assertEqual(code, 0)
        self.assertRegex(out, r"^ok H1 ask new\. next: roadmap head t H1 \.\.\n$")

    def test_log_with_bind_is_bound(self):
        code, out, _ = _run(["head", "log", "split the head section", "--kind", "ask", "--bind", "task:R1.1"])
        self.assertEqual(code, 0)
        self.assertIn("ok H1 ask bound. next: roadmap head list", out)

    def test_triage_one_call(self):
        self.log("make the map open in a new tab")
        code, out, _ = _run(["head", "t", "H1", "bug", "make map open in new tab", "task:R1.1"])
        self.assertEqual(code, 0)
        self.assertIn("ok H1 bug bound task:R1.1. next: roadmap head list", out)
        rows = store.rows(self.data_dir)
        self.assertEqual(rows[0]["kind"], "bug")
        self.assertEqual(rows[0]["links"], ["task:R1.1"])

    def test_list_columns_and_filters(self):
        self.log("first ask here", extra=["--bind", "task:R1.1"])
        self.log("second ask here")
        _run(["head", "set", "H2", "status=declined"])
        code, out, _ = _run(["head", "list"])
        self.assertEqual(code, 0)
        lines = out.strip().split("\n")
        self.assertEqual(len(lines), 2)  # one entry plus the next line
        self.assertRegex(lines[0], LIST_RE)
        self.assertTrue(lines[0].startswith("H1 "))
        self.assertIn("ask", lines[0])
        self.assertIn("bound", lines[0])
        self.assertIn("R1.1", lines[0])
        self.assertTrue(lines[-1].startswith("next: "))
        _, out_all, _ = _run(["head", "list", "--all"])
        self.assertIn("H2 ", out_all)
        _, out_q, _ = _run(["head", "list", "--all", "--q", "second"])
        self.assertIn("H2 ", out_q)
        self.assertNotIn("H1 ", out_q)

    def test_show_lines_and_history(self):
        self.log("make the map open in a new tab", extra=["--bind", "task:R1.1"])
        code, out, _ = _run(["head", "show", "H1"])
        self.assertEqual(code, 0)
        lines = out.strip().split("\n")
        self.assertLessEqual(len(lines), head_cmd.SHOW_MAX)
        self.assertRegex(lines[0], r"^H1 +ask ")
        self.assertIn("text: make the map open in a new tab", lines[1])
        self.assertTrue(any(line.startswith("links: task:R1.1") for line in lines))
        self.assertTrue(any(line.startswith("history:") for line in lines))

    def test_set_bind_unbind_and_errors(self):
        self.log("some ask")
        code, out, _ = _run(["head", "set", "H1", "status=declined", "note=dropped"])
        self.assertEqual(code, 0)
        self.assertIn("ok H1 set status, note. next:", out)
        code, out, _ = _run(["head", "bind", "H1", "task:R2.2"])
        self.assertIn("ok H1 bound task:R2.2", out)
        code, out, _ = _run(["head", "unbind", "H1", "task:R2.2"])
        self.assertIn("ok H1 unbound task:R2.2", out)
        code, _, err = _run(["head", "set", "H1", "bogus"])
        self.assertEqual(code, 2)
        self.assertIn("set takes key=value pairs", err)
        self.assertIn("next:", err)

    def test_split_and_merge(self):
        self.log("two things in one message")
        code, out, _ = _run(["head", "split", "H1", "first thing", "second thing"])
        self.assertIn("ok H1 split into H2, H3. next:", out)
        self.log("first thing again")
        code, out, _ = _run(["head", "merge", "H4", "--into", "H2"])
        self.assertIn("ok H4 merged into H2", out)

    def test_convert_rule_sets_needs_you(self):
        self.log("always use dark mode", kind="rule")
        code, out, _ = _run(["head", "convert", "H1", "rule"])
        self.assertEqual(code, 0)
        self.assertIn("H1 needs-you: add to rules.txt?", out)

    def test_brief_and_claim(self):
        self.log("an open ask")
        code, out, _ = _run(["head", "claim", "--model", "Opus 5.5", "--acct", "B"])
        self.assertEqual(code, 0)
        self.assertIn("ok claim Opus 5.5, 0 carried. next: roadmap head brief", out)
        code, out, _ = _run(["head", "brief"])
        lines = out.strip().split("\n")
        self.assertLessEqual(len(lines), store.BRIEF_MAX_LINES)
        self.assertTrue(lines[0].startswith("head: 1 open"))
        code, out, _ = _run(["head", "brief", "--md"])
        self.assertTrue(out.startswith("**head: "))

    def test_claim_needs_model(self):
        code, _, err = _run(["head", "claim"])
        self.assertEqual(code, 2)
        self.assertIn("--model", err)

    def test_triage_list_shows_untriaged(self):
        self.log("an untriaged ask")
        code, out, _ = _run(["head", "triage"])
        self.assertEqual(code, 0)
        self.assertRegex(out, r'^H1 ask \| "an untriaged ask"\n')
        self.assertIn("next: roadmap head t H1", out)

    def test_review_lists_done_then_refuses_person_actions(self):
        self.log("a done ask")
        _run(["head", "set", "H1", "status=done"])
        code, out, _ = _run(["head", "review"])
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("H1 "))
        self.assertIn("next: roadmap head review H1 confirm|reopen", out)
        code, _, err = _run(["head", "review", "H1", "confirm"])
        self.assertNotEqual(code, 0)
        self.assertIn("ask the person", err)
        code, _, err = _run(["head", "accept", "H1"])
        self.assertNotEqual(code, 0)
        self.assertIn("ask the person", err)
        code, _, err = _run(["head", "forget", "H1"])
        self.assertNotEqual(code, 0)

    def test_review_needs_a_decision(self):
        self.log("a done ask")
        code, _, err = _run(["head", "review", "H1"])
        self.assertEqual(code, 2)
        self.assertIn("needs confirm or reopen", err)

    def test_status_line_only_with_entries(self):
        project = tasks.resolve(PROJECT_ID)[0]
        self.assertIsNone(head_cmd.status_line(project, self.data_dir))
        self.log("an open ask")
        line = head_cmd.status_line(project, self.data_dir)
        self.assertTrue(line.startswith("head: 1 open"))


if __name__ == "__main__":
    unittest.main()
