"""Guard gap tests (agy batch 3, verdicts in docs/reviews/agy-verify-3.md): agent markers, person context, and the
feature accept and restore refusals.

Each test injects its own environ dict (agentguard's os is swapped for a namespace, so the real environment is never
read or changed) and its own TTY or pipe streams (sys.stdin and sys.stdout). Nothing launches, nothing uses the
network, and the in-process commands run under the temp ROADMAP_HOME that CmdCase sets up.
"""

import contextlib
import io
import sys
import types
import unittest
from unittest import mock

from roadmap.errors import EXIT_CONFLICT, RoadmapError
from roadmap.services import agentguard, commands, featops, features
from tests.unit.test_cmd_support import CmdCase


class Tty(object):
    def isatty(self):
        return True


class Pipe(object):
    def isatty(self):
        return False


class Raises(object):
    """A stream whose isatty probe fails (a closed or broken stream)."""

    def __init__(self, exc):
        self.exc = exc

    def isatty(self):
        raise self.exc


class TtyText(io.StringIO):
    def isatty(self):
        return True


class PipeText(io.StringIO):
    def isatty(self):
        return False


@contextlib.contextmanager
def environ(values):
    """Let agentguard see only this dict as os.environ, for this block."""
    with mock.patch.object(agentguard, "os", types.SimpleNamespace(environ=dict(values))):
        yield


@contextlib.contextmanager
def streams(stdin, stdout):
    with mock.patch.object(sys, "stdin", stdin), mock.patch.object(sys, "stdout", stdout):
        yield


@contextlib.contextmanager
def browser_click():
    with agentguard.browser_proven(True):
        yield


class AgentMarkerRules(unittest.TestCase):
    def test_no_argument_reads_the_agent_environment(self):
        with environ({"CLAUDECODE": "1"}):
            self.assertTrue(agentguard.agent_marked())
        with environ({"PATH": "/bin"}):
            self.assertFalse(agentguard.agent_marked())

    def test_a_whitespace_only_marker_is_not_a_marker(self):
        self.assertFalse(agentguard.agent_marked({"CLAUDECODE": "   "}))

    def test_an_empty_environment_is_not_marked(self):
        self.assertFalse(agentguard.agent_marked({}))

    def test_benign_variables_are_not_markers(self):
        self.assertFalse(agentguard.agent_marked({"PATH": "/bin", "USER": "dev"}))

    def test_a_bare_prefix_is_a_marker(self):
        self.assertTrue(agentguard.agent_marked({"AGY_": "1"}))
        self.assertTrue(agentguard.agent_marked({"CODEX_": "1"}))

    def test_a_name_without_the_trailing_underscore_is_not_a_marker(self):
        self.assertFalse(agentguard.agent_marked({"CURSOR": "1"}))
        self.assertFalse(agentguard.agent_marked({"CODEX": "1"}))

    def test_a_non_string_value_still_counts(self):
        self.assertTrue(agentguard.agent_marked({"CLAUDECODE": 123}))


class PersonContextGaps(unittest.TestCase):
    def test_a_pipe_stdin_with_a_tty_stdout_is_not_the_person(self):
        self.assertFalse(agentguard.person_context("cli", {}, Pipe(), Tty()))

    def test_a_stream_whose_probe_raises_is_not_a_tty(self):
        for exc in (ValueError("closed file"), OSError("bad file descriptor")):
            self.assertFalse(agentguard.person_context("cli", {}, Raises(exc), Tty()), repr(exc))
            self.assertFalse(agentguard.person_context("cli", {}, Tty(), Raises(exc)), repr(exc))

    def test_a_stream_without_isatty_is_not_a_tty(self):
        self.assertFalse(agentguard.person_context("cli", {}, object(), Tty()))
        self.assertFalse(agentguard.person_context("cli", {}, Tty(), object()))

    def test_the_default_streams_are_sys_stdin_and_stdout(self):
        with streams(Tty(), Tty()):
            self.assertTrue(agentguard.person_context("cli", {}))
        with streams(Pipe(), Tty()):
            self.assertFalse(agentguard.person_context("cli", {}))

    def test_a_default_environment_is_read_from_the_agent_environment(self):
        with streams(Tty(), Tty()):
            with environ({"CLAUDECODE": "1"}):
                self.assertFalse(agentguard.person_context("cli"))
            with environ({}):
                self.assertTrue(agentguard.person_context("cli"))

    def test_a_proven_click_is_the_person_even_with_an_agent_marker(self):
        with browser_click():
            self.assertTrue(agentguard.person_context("gui", {"CLAUDECODE": "1"}))

    def test_the_proof_ends_with_its_block(self):
        with browser_click():
            self.assertTrue(agentguard.person_context("gui", {}))
        self.assertFalse(agentguard.person_context("gui", {}))

    def test_an_explicitly_unproven_gui_call_is_not_the_person(self):
        with agentguard.browser_proven(False):
            self.assertFalse(agentguard.person_context("gui", {}))

    def test_a_missing_or_unknown_source_is_not_the_person(self):
        for source in (None, "", "cron", "system"):
            self.assertFalse(agentguard.person_context(source, {}, Tty(), Tty()), repr(source))

    def test_a_whitespace_marker_does_not_block_a_terminal(self):
        self.assertTrue(agentguard.person_context("cli", {"CLAUDECODE": "   "}, Tty(), Tty()))


class AcceptGaps(CmdCase):
    def setUp(self):
        super().setUp()
        self.op("feature.add", {"title": "Visual", "acc": "reads at 375 px", "prio": 2, "phase": None,
                                "parent": None})

    def person_accepts(self):
        with streams(TtyText(), TtyText()), environ({}):
            return self.op("feature.accept", {"id": "F1", "on": True, "confirm": True})

    def accepted(self, fid="F1"):
        return next(f for f in features.load_doc(self.data)["features"] if f["id"] == fid)["accepted"]

    def assert_refused(self, ctx):
        self.assertEqual(ctx.exception.code, "agent_refused")
        self.assertEqual(ctx.exception.exit, EXIT_CONFLICT)
        self.assertEqual(ctx.exception.next, "ask the person")

    def test_an_agent_source_accept_is_refused(self):
        with self.assertRaises(RoadmapError) as ctx:
            commands.run("feature.accept", {"id": "F1", "on": True, "confirm": True}, "agent", self.data)
        self.assert_refused(ctx)
        self.assertIsNone(self.accepted())

    def test_a_phone_source_accept_is_refused(self):
        with self.assertRaises(RoadmapError) as ctx:
            commands.run("feature.accept", {"id": "F1", "on": True, "confirm": True}, "phone", self.data)
        self.assert_refused(ctx)
        self.assertIsNone(self.accepted())

    def test_clearing_an_acceptance_from_a_bare_cli_is_refused(self):
        self.person_accepts()
        with streams(PipeText(), PipeText()), environ({}):
            with self.assertRaises(RoadmapError) as ctx:
                self.op("feature.accept", {"id": "F1", "on": False})
        self.assert_refused(ctx)
        self.assertIsNotNone(self.accepted())

    def test_clearing_an_acceptance_from_an_agent_is_refused(self):
        self.person_accepts()
        with self.assertRaises(RoadmapError) as ctx:
            commands.run("feature.accept", {"id": "F1", "on": False}, "agent", self.data)
        self.assert_refused(ctx)
        self.assertIsNotNone(self.accepted())

    def test_an_agent_undo_of_a_clearance_is_refused_and_the_clear_stands(self):
        self.person_accepts()
        with streams(TtyText(), TtyText()), environ({}):
            cleared = self.op("feature.accept", {"id": "F1", "on": False})
        with self.assertRaises(RoadmapError) as ctx:
            commands.run("undo", {"activity": cleared["activity"]}, "agent", self.data)
        self.assert_refused(ctx)
        self.assertIsNone(self.accepted())

    def test_a_terminal_marked_by_claudecode_or_codex_home_is_refused(self):
        for key, value in (("CLAUDECODE", "1"), ("CODEX_HOME", "/x")):
            with streams(TtyText(), TtyText()), environ({key: value}):
                with self.assertRaises(RoadmapError) as ctx:
                    self.op("feature.accept", {"id": "F1", "on": True, "confirm": True})
            self.assert_refused(ctx)
        self.assertIsNone(self.accepted())

    def test_a_bad_accept_date_is_a_usage_error(self):
        with self.assertRaises(RoadmapError) as ctx:
            featops._check_accept({"id": "F1", "date": "bad-date"})
        self.assertEqual(ctx.exception.code, "usage")

    def test_a_bad_feature_id_is_a_usage_error(self):
        for bad in ("FX", "F100"):
            with self.assertRaises(RoadmapError) as ctx:
                featops._check_accept({"id": bad})
            self.assertEqual(ctx.exception.code, "usage", bad)


class RestoreGaps(CmdCase):
    def setUp(self):
        super().setUp()
        self.op("feature.add", {"title": "Visual", "acc": "reads at 375 px", "prio": 2, "phase": None,
                                "parent": None})

    def accepted_then_removed(self):
        """Accept F1 as the person, then remove it. Returns (accepted date, activity id of the removal)."""
        with streams(TtyText(), TtyText()), environ({}):
            accepted = self.op("feature.accept", {"id": "F1", "on": True, "confirm": True})
        removed = self.op("feature.rm", {"id": "F1"})
        return accepted["data"]["accepted"], removed["activity"]

    def ids(self):
        return [f["id"] for f in features.load_doc(self.data)["features"]]

    def test_a_bare_cli_undo_cannot_restore_an_accepted_feature(self):
        _, removal = self.accepted_then_removed()
        with streams(PipeText(), PipeText()), environ({}):
            with self.assertRaises(RoadmapError) as ctx:
                self.op("undo", {"activity": removal})
        self.assertEqual(ctx.exception.code, "agent_refused")
        self.assertEqual(ctx.exception.exit, EXIT_CONFLICT)
        self.assertEqual(self.ids(), [])

    def test_a_terminal_with_an_agent_marker_cannot_restore_an_accepted_feature(self):
        _, removal = self.accepted_then_removed()
        with streams(TtyText(), TtyText()), environ({"AGY_SESSION": "1"}):
            with self.assertRaises(RoadmapError) as ctx:
                self.op("undo", {"activity": removal})
        self.assertEqual(ctx.exception.code, "agent_refused")
        self.assertEqual(self.ids(), [])

    def test_an_unproven_gui_undo_cannot_restore_an_accepted_feature(self):
        _, removal = self.accepted_then_removed()
        with environ({}):
            with self.assertRaises(RoadmapError) as ctx:
                commands.run("undo", {"activity": removal}, "gui", self.data)
        self.assertEqual(ctx.exception.code, "agent_refused")
        self.assertEqual(self.ids(), [])

    def test_a_proven_browser_click_restores_with_the_accepted_date_intact(self):
        date, removal = self.accepted_then_removed()
        with browser_click(), environ({}):
            commands.run("undo", {"activity": removal}, "gui", self.data)
        self.assertEqual(self.ids(), ["F1"])
        self.assertEqual(next(f for f in features.load_doc(self.data)["features"])["accepted"], date)

    def test_a_restore_record_needs_a_dict_feature(self):
        for args in ({"feature": "F1"}, {}):
            with self.assertRaises(RoadmapError) as ctx:
                featops._check_restore(args)
            self.assertEqual(ctx.exception.code, "usage", repr(args))
            self.assertEqual(ctx.exception.message, "feature restore needs a feature record")

    def test_a_restore_record_needs_a_valid_feature_id(self):
        with self.assertRaises(RoadmapError) as ctx:
            featops._check_restore({"feature": {"id": "123"}})
        self.assertEqual(ctx.exception.code, "usage")

    def test_a_restore_record_with_no_accepted_date_keeps_it_unset(self):
        clean = featops._check_restore({"feature": {"id": "F1", "accepted": None}})
        self.assertIsNone(clean["feature"]["accepted"])


if __name__ == "__main__":
    unittest.main()
