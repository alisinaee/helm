"""Work M5 CLI: `roadmap work list|show|add|set|link|accept|reopen` and `roadmap head next` through cli.main. Every line
is at most 15, the ok/next grammar holds, accept and reopen are the person's only (a non-TTY shell is refused), and
the head next lines are runnable commands. Runs in a temp ROADMAP_HOME with a copy of the fixture project."""

import contextlib
import io
import os
import shutil
import tempfile
import unittest
from unittest import mock

from roadmap.cli import main
from roadmap.errors import EXIT_CONFLICT, EXIT_OK, EXIT_USAGE
from roadmap.services import agentguard, tasks
from roadmap.store import config as config_store
from tests.api.support import FIXTURE, PROJECT_ID


def _not_tty():
    stream = mock.Mock()
    stream.isatty.return_value = False
    return stream


@contextlib.contextmanager
def person():
    """The person's own terminal: agentguard.person_context says yes (the TTY proof itself is tested in agentguard)."""
    with mock.patch.object(agentguard, "person_context", return_value=True):
        yield


def _run(argv):
    """Run the CLI in-process as a non-TTY shell: (exit code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with mock.patch("sys.stdin", _not_tty()), mock.patch.object(agentguard, "agent_marked", return_value=False), \
            contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv + ["--project", PROJECT_ID])
    return code, out.getvalue(), err.getvalue()


class WorkCliCase(unittest.TestCase):
    def setUp(self):
        env = mock.patch.dict(os.environ, {})
        env.start()
        self.addCleanup(env.stop)
        self.tmp = tempfile.mkdtemp(prefix="rb-work-cli-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        os.environ["ROADMAP_HOME"] = os.path.join(self.tmp, "home")
        os.environ.pop("CLAUDECODE", None)
        root = os.path.join(self.tmp, "split_net")
        shutil.copytree(FIXTURE, os.path.join(root, "docs"))
        config_store.add_project("split-net", root, project_id=PROJECT_ID)
        self.data_dir = tasks.resolve(PROJECT_ID)[1]
        self.task_id = tasks.load(self.data_dir)["tasks"][0]["id"]

    def add(self, title="Ship the map", **extra):
        argv = ["work", "add", title]
        for key, value in extra.items():
            argv += ["--" + key, value]
        code, out, _ = _run(argv)
        self.assertEqual(code, EXIT_OK)
        return out.split()[1]


class WorkListShowTests(WorkCliCase):
    def test_empty_list_says_ok_and_points_at_add(self):
        code, out, _ = _run(["work", "list"])
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(out, 'ok no Work items. next: roadmap work add "<title>"\n')

    def test_add_then_list_one_line_per_item(self):
        code, out, _ = _run(["work", "add", "Ship the map", "--outcome", "the map opens"])
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(out, "ok W1 added. next: roadmap work show W1\n")
        code, out, _ = _run(["work", "list"])
        lines = out.splitlines()
        self.assertRegex(lines[0], r"^W1 +Todo +P2 +0/0 Ship the map$")
        self.assertEqual(lines[-1], "next: roadmap work show W1")

    def test_list_caps_at_fifteen_lines(self):
        for n in range(17):
            self.add("Item %d" % n)
        code, out, _ = _run(["work", "list"])
        self.assertEqual(code, EXIT_OK)
        lines = out.splitlines()
        self.assertLessEqual(len(lines), 15)
        self.assertIn("more (roadmap work list)", out)
        self.assertEqual(lines[-1], "next: roadmap work show W1")

    def test_show_lists_outcome_and_linked_agent_tasks(self):
        wid = self.add("Ship the map", outcome="the map opens")
        _run(["work", "link", self.task_id, wid])
        code, out, _ = _run(["work", "show", wid])
        self.assertEqual(code, EXIT_OK)
        lines = out.splitlines()
        state = tasks.get(self.data_dir, self.task_id)["status"]
        self.assertRegex(lines[0], r"^W1 +\S+ +P2 +[01]/1 Ship the map$")
        self.assertEqual(lines[1], "  outcome: the map opens")
        self.assertEqual(lines[2], "  %s %s" % (self.task_id, state))
        self.assertLessEqual(len(lines), 15)

    def test_show_unknown_id_is_not_found_with_next(self):
        code, _, err = _run(["work", "show", "W99"])
        self.assertNotEqual(code, EXIT_OK)
        self.assertIn("no Work item W99", err)
        self.assertIn("next:", err)


class WorkWriteTests(WorkCliCase):
    def test_wording_lint_refuses_a_file_name_before_any_write(self):
        code, _, err = _run(["work", "add", "Fix roadmap/cmd.py"])
        self.assertEqual(code, EXIT_USAGE)
        self.assertIn("plain words", err)
        self.assertEqual(_run(["work", "list"])[1], 'ok no Work items. next: roadmap work add "<title>"\n')

    def test_bad_prio_is_a_usage_error(self):
        code, _, err = _run(["work", "add", "Ship it", "--prio", "P9"])
        self.assertEqual(code, EXIT_USAGE)
        self.assertIn("P0-P3", err)

    def test_set_changes_title_and_prio(self):
        wid = self.add("Ship the map")
        code, out, _ = _run(["work", "set", wid, "--title", "Open the map", "--prio", "P1"])
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(out, "ok W1 changed. next: roadmap work show W1\n")
        self.assertRegex(_run(["work", "list"])[1], r"W1 +Todo +P1 +0/0 Open the map")

    def test_set_with_nothing_to_change_is_refused(self):
        wid = self.add()
        code, _, err = _run(["work", "set", wid])
        self.assertEqual(code, EXIT_USAGE)
        self.assertIn("nothing to set", err)

    def test_link_binds_an_agent_task_and_unknown_task_is_refused(self):
        wid = self.add()
        code, out, _ = _run(["work", "link", self.task_id, wid])
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(out, "ok %s -> W1 linked. next: roadmap work show W1\n" % self.task_id)
        code, _, err = _run(["work", "link", "R99.9", wid])
        self.assertNotEqual(code, EXIT_OK)
        self.assertIn("next:", err)

    def test_accept_from_a_plain_shell_is_refused_for_the_person(self):
        wid = self.add()
        code, _, err = _run(["work", "accept", wid])
        self.assertEqual(code, EXIT_CONFLICT)
        self.assertIn("is for the person", err)

    def test_the_persons_terminal_accepts_then_reopens(self):
        wid = self.add()
        with person():
            code, out, _ = _run(["work", "accept", wid])
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(out, "ok W1 Done. next: roadmap work list\n")
        with person():
            code, out, _ = _run(["work", "reopen", wid])
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(out, "ok W1 reopened. next: roadmap work show W1\n")

    def test_json_envelope_carries_the_op_data(self):
        code, out, _ = _run(["work", "add", "Ship the map", "--json"])
        self.assertEqual(code, EXIT_OK)
        self.assertIn('"ok": true', out)
        self.assertIn('"id": "W1"', out)


class HeadNextTests(WorkCliCase):
    def test_head_next_lists_runnable_ops_ending_with_the_brief(self):
        code, out, _ = _run(["head", "next"])
        self.assertEqual(code, EXIT_OK)
        lines = out.splitlines()
        self.assertEqual(lines[0], "ok 1 runnable. next: roadmap head brief")
        self.assertEqual(lines[-1], "roadmap head brief")
        self.assertLessEqual(len(lines), 15)

    def test_head_next_lines_have_no_placeholders(self):
        _run(["head", "log", "make the map open in a new tab", "--kind", "ask"])
        code, out, _ = _run(["head", "next"])
        self.assertEqual(code, EXIT_OK)
        self.assertIn("roadmap head show H1", out)
        self.assertNotIn("<", out)
        self.assertNotIn(">", out)


if __name__ == "__main__":
    unittest.main()
