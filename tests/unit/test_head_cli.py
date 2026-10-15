"""HEAD-SPEC H5: the `roadmap head` commands (roadmap/commands/head.py) through cli.main. The ok/next grammar, the list
columns, the one-call triage, claim and brief, review (the person's only: a non-TTY shell is refused), and the status
line. Runs in a temp ROADMAP_HOME with a copy of the fixture project."""

import argparse
import contextlib
import io
import json
import os
import re
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
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

    def _doc(self, name, text):
        path = os.path.join(self.tmp, "split_net", name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def test_import_grammar_and_idempotence(self):
        path = self._doc("notes.md", "# Notes\n\n## 2\n1. Always use the staging host\n2. Please check the audit?\n\n"
                                     "## 3\n- Not imported here\n")
        code, out, _ = _run(["head", "import", "--doc", path, "--section", "2"])
        self.assertEqual(code, 0)
        self.assertEqual(out, "ok import 2 logged, 0 skipped. next: roadmap head list\n")
        self.assertEqual(len(store.rows(self.data_dir)), 2)
        code, out, _ = _run(["head", "import", "--doc", path, "--section", "2,2b"])
        self.assertIn("ok import 0 logged, 2 skipped. next: roadmap head list", out)
        self.assertEqual(len(store.rows(self.data_dir)), 2)

    def test_import_whole_file_when_no_section(self):
        path = self._doc("all.md", "## 2\n- first item\n## 3\n- second item\n")
        code, out, _ = _run(["head", "import", "--doc", path])
        self.assertIn("ok import 2 logged, 0 skipped.", out)

    def test_import_refuses_paths_outside_the_project(self):
        outside = os.path.join(self.tmp, "outside.md")
        with open(outside, "w", encoding="utf-8") as fh:
            fh.write("## 2\n- secret-ish item\n")
        code, _, err = _run(["head", "import", "--doc", outside])
        self.assertEqual(code, 2)
        self.assertIn("inside the project folder", err)
        self.assertEqual(store.rows(self.data_dir), [])

    def test_import_missing_doc_is_not_found(self):
        code, _, err = _run(["head", "import", "--doc", os.path.join(self.tmp, "split_net", "none.md")])
        self.assertNotEqual(code, 0)
        self.assertIn("no doc at", err)

    def test_status_line_only_with_entries(self):
        project = tasks.resolve(PROJECT_ID)[0]
        self.assertIsNone(head_cmd.status_line(project, self.data_dir))
        self.log("an open ask")
        line = head_cmd.status_line(project, self.data_dir)
        self.assertTrue(line.startswith("head: 1 open"))


class HeadAutopilotCli(unittest.TestCase):
    """HEAD-SPEC section 11: head brief --gate, head brief --done, head pause and head resume."""

    def setUp(self):
        HeadCliCase.setUp(self)
        self.log = lambda text, kind="ask", extra=(): HeadCliCase.log(self, text, kind, extra)
        patcher = mock.patch.object(head_cmd.hooks, "_git_counts", return_value=(2, None))
        patcher.start()
        self.addCleanup(patcher.stop)

    def _gate_out(self):
        code, out, _ = _run(["head", "brief", "--gate"])
        self.assertEqual(code, 0)
        return out.strip().split("\n")

    def test_gate_nothing_pending(self):
        patcher = mock.patch.object(head_cmd.hooks, "_git_counts", return_value=(0, 0))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.assertEqual(self._gate_out(), ["ok nothing pending"])

    def test_gate_lists_asks_then_work_as_continue_lines(self):
        self.log("first open ask")
        self.log("second open ask")
        lines = self._gate_out()
        self.assertLessEqual(len(lines), head_cmd.GATE_LINES)
        self.assertTrue(lines[0].startswith("continue: H1 unanswered "))
        self.assertTrue(lines[1].startswith("continue: H2 unanswered "))
        self.assertIn("continue: 2 uncommitted files", lines)
        self.assertTrue(all(line.startswith("continue: ") for line in lines))

    def test_gate_caps_at_five_lines(self):
        for n in range(7):
            self.log("ask number %d" % n)
        self.assertEqual(len(self._gate_out()), head_cmd.GATE_LINES)

    def test_pause_silences_and_resume_restores(self):
        self.log("an open ask")
        code, out, _ = _run(["head", "pause"])
        self.assertEqual(code, 0)
        self.assertIn("ok head paused", out)
        self.assertTrue(os.path.exists(os.path.join(self.data_dir, store.GATE_PAUSE_FILE)))
        self.assertEqual(self._gate_out(), ["ok nothing pending"])
        code, out, _ = _run(["head", "resume"])
        self.assertIn("ok head resumed. next: roadmap head brief --gate", out)
        self.assertFalse(os.path.exists(os.path.join(self.data_dir, store.GATE_PAUSE_FILE)))
        self.assertTrue(self._gate_out()[0].startswith("continue: H1 "))

    def test_resume_when_not_paused_says_so(self):
        code, out, _ = _run(["head", "resume"])
        self.assertEqual(code, 0)
        self.assertIn("ok head was not paused", out)

    def test_gate_config_switch_off_is_silent(self):
        self.log("an open ask")
        with open(os.path.join(self.data_dir, "roadmap.config.json"), "w", encoding="utf-8") as fh:
            fh.write('{"head": {"gate": false}}')
        self.assertEqual(self._gate_out(), ["ok nothing pending"])

    def test_done_checklist_has_the_section_11_steps(self):
        code, out, _ = _run(["head", "brief", "--done"])
        self.assertEqual(code, 0)
        lines = out.strip().split("\n")
        self.assertLessEqual(len(lines), 15)
        for word in ("verify the diff", "--tokens", "commit", "push", "next wave", "cursor or agy audit", "head set"):
            self.assertTrue(any(word in line for line in lines), word)
        self.assertEqual(lines[-1], "next: roadmap head brief --gate")


class HeadCliGaps(HeadCliCase):
    """Edge cases from docs/reviews/agy-head-testgaps-cli.md that the CLI tests did not cover."""

    def test_log_reports_a_spooled_capture(self):
        with mock.patch.object(head_cmd, "_write", return_value={"data": {"id": None, "kind": "ask"}}):
            code, out, _ = _run(["head", "log", "a spooled ask"])
        self.assertEqual(code, 0)
        self.assertEqual(out, "ok logged, numbered after the next head write (spooled). next: roadmap head list\n")

    def test_triage_status_flag_is_applied(self):
        self.log("make the map open in a new tab")
        code, out, _ = _run(["head", "t", "H1", "bug", "map tab", "--status", "declined"])
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("ok H1 bug declined"), out)
        self.assertEqual(store.rows(self.data_dir)[0]["status"], "declined")

    def test_bind_of_an_existing_link_says_nothing_new(self):
        self.log("some ask")
        _run(["head", "bind", "H1", "task:R1.1"])
        code, out, _ = _run(["head", "bind", "H1", "task:R1.1"])
        self.assertEqual(code, 0)
        self.assertEqual(out, "ok H1 bound nothing new. next: roadmap head list\n")

    def test_unbind_of_an_absent_link_says_nothing(self):
        self.log("some ask")
        code, out, _ = _run(["head", "unbind", "H1", "task:R9.9"])
        self.assertEqual(code, 0)
        self.assertEqual(out, "ok H1 unbound nothing. next: roadmap head list\n")

    def test_convert_to_task_prints_the_new_ref(self):
        self.log("make the map open in a new tab")
        code, out, _ = _run(["head", "convert", "H1", "task"])
        self.assertEqual(code, 0)
        self.assertRegex(out, r"^ok H1 -> \S+\. next: roadmap head list\n$")

    def test_review_reopen_writes_the_decision(self):
        self.log("a done ask")
        _run(["head", "set", "H1", "status=done"])
        args = argparse.Namespace(project=PROJECT_ID, id="H1", decision="reopen", json=False)
        out = io.StringIO()
        with mock.patch.object(head_cmd, "_write", return_value={"data": {}}) as write, \
                contextlib.redirect_stdout(out):
            head_cmd._review(args)
        self.assertEqual(out.getvalue(), "ok H1 reopened. next: roadmap head list\n")
        self.assertEqual(write.call_args[0][1:], ("head.review", {"id": "H1", "action": "reopen"}))

    def test_review_with_nothing_waiting(self):
        self.log("an open ask")
        code, out, _ = _run(["head", "review"])
        self.assertEqual(code, 0)
        self.assertEqual(out, "nothing to review\nnext: roadmap head list\n")

    def test_show_entry_without_verbatim_text(self):
        self.log("an ask")
        with mock.patch.object(store, "text_of", return_value=None):
            code, out, _ = _run(["head", "show", "H1"])
        self.assertEqual(code, 0)
        self.assertEqual(out.split("\n")[1], "text: (none)")

    def test_show_unknown_entry_is_a_usage_error(self):
        code, _, err = _run(["head", "show", "H9"])
        self.assertEqual(code, 2)
        self.assertIn("no head entry H9", err)

    def test_list_rejects_a_zero_count(self):
        code, _, err = _run(["head", "list", "--n", "0"])
        self.assertEqual(code, 2)
        self.assertIn("--n must be at least 1", err)

    def test_list_kind_filter_with_no_match(self):
        self.log("an ask")
        code, out, _ = _run(["head", "list", "--kind", "rule"])
        self.assertEqual(code, 0)
        self.assertEqual(out.split("\n")[0], "no entries match (open)")

    def test_claim_lists_asks_carried_from_an_earlier_session(self):
        earlier = datetime.now(timezone.utc) - timedelta(hours=1)
        store.capture(self.data_dir, "an ask carried over", session_id="old-session", now=earlier)
        code, out, _ = _run(["head", "claim", "--model", "Sonnet 5.5"])
        self.assertEqual(code, 0)
        lines = out.rstrip("\n").split("\n")
        self.assertTrue(lines[0].startswith("  H1 ask "), out)
        self.assertEqual(lines[-1], "ok claim Sonnet 5.5, 1 carried. next: roadmap head brief")

    def test_triage_list_shows_a_duplicate_suggestion(self):
        self.log("make the map open in a new tab")
        self.log("make the map open in a new tab")
        _, out, _ = _run(["head", "triage"])
        self.assertIn(" dup H1 ", out)

    def test_import_json_envelope(self):
        path = self._doc("json.md", "## 2\n- first json item\n")
        code, out, _ = _run(["head", "import", "--doc", path, "--json"])
        self.assertEqual(code, 0)
        data = json.loads(out)["data"]
        self.assertEqual(data["logged"], ["H1"])
        self.assertEqual(data["skipped"], 0)
        self.assertEqual(len(data["items"]), 1)


class HeadGateCliGaps(HeadCliCase):
    """The autopilot read (head brief --gate) with a stop state and an unreadable usage file."""

    def setUp(self):
        HeadCliCase.setUp(self)
        patcher = mock.patch.object(head_cmd.hooks, "_git_counts", return_value=(2, None))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_stop_in_the_control_state_silences_the_gate(self):
        self.log("an open ask")
        with mock.patch.object(head_cmd.control, "read_state", return_value={"stop": True}):
            _, out, _ = _run(["head", "brief", "--gate"])
        self.assertEqual(out, "ok nothing pending\n")

    def test_usage_file_from_a_newer_build_is_ignored_by_the_gate(self):
        self.log("an open ask")
        newer = os.path.join(self.tmp, "usage.json")
        with open(newer, "w", encoding="utf-8") as fh:
            json.dump({"schemaVersion": 999, "fiveHourPercent": 99}, fh)
        with mock.patch.object(head_cmd.paths, "usage_file", return_value=newer):
            code, out, _ = _run(["head", "brief", "--gate"])
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("continue: H1 unanswered "), out)


if __name__ == "__main__":
    unittest.main()
