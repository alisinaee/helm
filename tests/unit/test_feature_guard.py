"""R3.3a: only the person accepts a feature (review findings 1, 3, 9, 13).

The person is a browser click with the same-origin proof (source gui, proven on the thread), or an interactive
terminal (both stdin and stdout are TTYs) with no agent marker in the environment. Agents, the phone and a bare non-TTY
cli shell (Cursor, agy, scripts) are refused. Restore never sets an accepted date for a non-person call, validates
the date, and checks the phase exists. Runs in-process under a temp ROADMAP_HOME; the environment and streams are
patched and restored after each test.
"""

import contextlib
import os
import sys
import unittest
from unittest import mock

from roadmap.errors import RoadmapError
from roadmap.services import agentguard, commands, featops, features
from tests.unit.test_cmd_support import CmdCase

MARKER_PREFIXES = ("CLAUDE_CODE_", "CURSOR_", "AGY_", "ANTIGRAVITY_", "CODEX_")


class Tty(object):
    def isatty(self):
        return True


class Pipe(object):
    def isatty(self):
        return False


@contextlib.contextmanager
def person_tty():
    """An interactive terminal with no agent marker: the person typing in a shell. The TTY probe answers yes, so
    the in-process CLI (whose stdout is a StringIO) is seen as a terminal."""
    with mock.patch.dict(os.environ, {}):
        for key in list(os.environ):
            if key == "CLAUDECODE" or key.startswith(MARKER_PREFIXES):
                del os.environ[key]
        with mock.patch.object(agentguard, "_isatty", return_value=True):
            yield


@contextlib.contextmanager
def browser_click():
    """A browser click that passed the same-origin proof on this thread."""
    with agentguard.browser_proven(True):
        yield


class PersonContextRules(unittest.TestCase):
    def test_a_bare_non_tty_cli_is_not_the_person(self):
        self.assertFalse(agentguard.person_context("cli", {}, Pipe(), Pipe()))
        self.assertFalse(agentguard.person_context("cli", {}, Tty(), Pipe()))
        self.assertFalse(agentguard.person_context("cli", {}, None, None))

    def test_an_interactive_tty_with_no_marker_is_the_person(self):
        self.assertTrue(agentguard.person_context("cli", {}, Tty(), Tty()))
        self.assertTrue(agentguard.person_context("cli", {"CLAUDECODE": ""}, Tty(), Tty()))

    def test_any_agent_marker_makes_a_tty_not_the_person(self):
        for env in ({"CLAUDECODE": "1"}, {"CLAUDE_CODE_ENTRYPOINT": "cli"}, {"CURSOR_TRACE_ID": "x"},
                    {"AGY_SESSION": "1"}, {"ANTIGRAVITY_RUN": "1"}, {"CODEX_HOME": "/x"}):
            self.assertFalse(agentguard.person_context("cli", env, Tty(), Tty()), env)

    def test_agent_phone_and_unproven_gui_are_never_the_person(self):
        self.assertFalse(agentguard.person_context("agent", {}, Tty(), Tty()))
        self.assertFalse(agentguard.person_context("phone", {}, Tty(), Tty()))
        self.assertFalse(agentguard.person_context("gui", {}, Tty(), Tty()))
        with browser_click():
            self.assertTrue(agentguard.person_context("gui", {}))


class FeatureGuardCase(CmdCase):
    def setUp(self):
        super().setUp()
        env = mock.patch.dict(os.environ, {})
        env.start()
        self.addCleanup(env.stop)
        for key in list(os.environ):
            if key == "CLAUDECODE" or key.startswith(MARKER_PREFIXES):
                del os.environ[key]

    def add(self, title="Visual"):
        return commands.run("feature.add", {"title": title, "acc": "reads at 375 px", "prio": 2, "phase": None,
                                            "parent": None}, "cli", self.data)

    def run_as(self, name, args, source="cli"):
        return commands.run(name, args, source, self.data)

    def accepted(self, fid="F1"):
        return next(f for f in features.load_doc(self.data)["features"] if f["id"] == fid)["accepted"]


class AcceptIsPersonOnly(FeatureGuardCase):
    def test_a_bare_cli_shell_is_refused_and_nothing_is_written(self):
        self.add()
        with self.assertRaises(RoadmapError) as ctx:
            self.run_as("feature.accept", {"id": "F1", "on": True, "confirm": True})
        self.assertEqual((ctx.exception.code, ctx.exception.next), ("agent_refused", "ask the person"))
        self.assertIsNone(self.accepted())

    def test_a_cursor_or_agy_marked_tty_is_refused(self):
        self.add()
        for key in ("CURSOR_TRACE_ID", "AGY_SESSION"):
            with person_tty(), mock.patch.dict(os.environ, {key: "1"}):
                with self.assertRaises(RoadmapError) as ctx:
                    self.run_as("feature.accept", {"id": "F1", "on": True, "confirm": True})
                self.assertEqual(ctx.exception.code, "agent_refused")
        self.assertIsNone(self.accepted())

    def test_a_person_at_a_terminal_accepts(self):
        self.add()
        with person_tty():
            reply = self.run_as("feature.accept", {"id": "F1", "on": True, "confirm": True})
        self.assertTrue(reply["ok"])
        self.assertIsNotNone(self.accepted())

    def test_a_proven_browser_click_accepts(self):
        self.add()
        with browser_click():
            self.run_as("feature.accept", {"id": "F1", "on": True, "confirm": True}, source="gui")
        self.assertIsNotNone(self.accepted())

    def test_an_unproven_gui_source_is_refused(self):
        self.add()
        with self.assertRaises(RoadmapError):
            self.run_as("feature.accept", {"id": "F1", "on": True, "confirm": True}, source="gui")
        self.assertIsNone(self.accepted())


class UndoOfAcceptance(FeatureGuardCase):
    def test_the_person_undoes_their_accept_and_an_agent_cannot(self):
        self.add()
        with person_tty():
            reply = self.run_as("feature.accept", {"id": "F1", "on": True, "confirm": True})
        with self.assertRaises(RoadmapError) as ctx:
            self.run_as("undo", {"activity": reply["activity"]}, source="agent")
        self.assertEqual(ctx.exception.code, "agent_refused")
        self.assertIsNotNone(self.accepted())  # the refused undo changed nothing
        with browser_click():
            self.run_as("undo", {"activity": reply["activity"]}, source="gui")  # the claim was released: retryable
        self.assertIsNone(self.accepted())

    def test_the_person_undoes_a_clear_and_the_date_comes_back(self):
        self.add()
        with person_tty():
            accepted = self.run_as("feature.accept", {"id": "F1", "on": True, "confirm": True})
            cleared = self.run_as("feature.accept", {"id": "F1", "on": False})
            self.assertIsNone(self.accepted())
            self.run_as("undo", {"activity": cleared["activity"]})
        self.assertEqual(self.accepted(), featops_date(accepted))


def featops_date(reply):
    return reply["data"]["accepted"]


class RestoreIsSafe(FeatureGuardCase):
    def accept_then_remove(self):
        self.add()
        with person_tty():
            self.run_as("feature.accept", {"id": "F1", "on": True, "confirm": True})
        return self.run_as("feature.rm", {"id": "F1"})

    def test_an_agent_undo_cannot_restore_an_accepted_feature(self):
        removed = self.accept_then_remove()
        with self.assertRaises(RoadmapError) as ctx:
            self.run_as("undo", {"activity": removed["activity"]}, source="agent")
        self.assertEqual(ctx.exception.code, "agent_refused")
        self.assertEqual(features.load_doc(self.data)["features"], [])

    def test_the_person_undo_restores_the_accepted_date_as_it_was(self):
        removed = self.accept_then_remove()
        with person_tty():
            self.run_as("undo", {"activity": removed["activity"]})
        self.assertIsNotNone(self.accepted())

    def test_restore_of_an_unaccepted_feature_is_allowed_for_any_caller(self):
        self.add()
        removed = self.run_as("feature.rm", {"id": "F1"})
        self.run_as("undo", {"activity": removed["activity"]}, source="agent")
        self.assertEqual([f["id"] for f in features.load_doc(self.data)["features"]], ["F1"])
        self.assertIsNone(self.accepted())

    def test_restore_checks_the_phase_exists(self):
        with self.assertRaises(RoadmapError) as ctx:
            features.restore(self.data, {"id": "F5", "title": "Gone phase", "acc": "", "prio": 2, "parent": None,
                                         "phase": "ZZ", "hold": False, "accepted": None})
        self.assertEqual(ctx.exception.code, "not_found")
        self.assertEqual(features.load_doc(self.data)["features"], [])

    def test_restore_rejects_an_accepted_value_that_is_not_a_date(self):
        for bad in ("yesterday", "2026-13-45", "2026-1-1", 7):
            with self.assertRaises(RoadmapError) as ctx:
                featops._check_restore({"feature": {"id": "F5", "accepted": bad}})
            self.assertEqual(ctx.exception.code, "usage", bad)
        clean = featops._check_restore({"feature": {"id": "F5", "accepted": "2026-10-14"}})
        self.assertEqual(clean["feature"]["accepted"], "2026-10-14")


class SeparatorInTitleOrAcc(FeatureGuardCase):
    def test_add_and_set_refuse_the_plan_separator(self):
        with self.assertRaises(RoadmapError) as ctx:
            self.run_as("feature.add", {"title": "Visual # v2", "acc": "", "prio": 2, "phase": None, "parent": None})
        self.assertEqual(ctx.exception.code, "usage")
        with self.assertRaises(RoadmapError):
            self.run_as("feature.add", {"title": "Visual", "acc": "a # b", "prio": 2, "phase": None, "parent": None})
        self.add()
        with self.assertRaises(RoadmapError):
            self.run_as("feature.set", {"id": "F1", "acc": "x # y"})
        self.assertEqual(features.load_doc(self.data)["features"][0]["acc"], "reads at 375 px")


if __name__ == "__main__":
    unittest.main()
