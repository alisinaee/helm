"""WP41: the Stop pickup and the SessionStart context carry the task's rules (rule: lines) and its definition of done
(done: lines). Each test runs in a temp ROADMAP_HOME; nothing touches the real home or the running service."""

import datetime
import json
import os
import time
import unittest
from unittest import mock

from roadmap.services import hooks, queue
from tests.unit.test_hook_enforce import MOMENT, GateCase

BASE = "roadmap: queued request P0.1 is waiting; run roadmap inbox and start it."


class RulesCase(GateCase):
    def write_rules(self, text):
        with open(os.path.join(self.docs, "rules.txt"), "w", encoding="utf-8") as fh:
            fh.write(text)

    def stop_event(self, session="s1", now=None):
        return hooks.run_hook(json.dumps({"hook_event_name": "Stop", "cwd": self.project, "session_id": session,
                                          "stop_hook_active": False}), now=(now or MOMENT.timestamp()))

    def start(self):
        return hooks.run_hook(json.dumps({"hook_event_name": "SessionStart", "cwd": self.project}),
                              now=MOMENT.timestamp())

    def added(self, reason):
        return reason[len(BASE):].lstrip("\n")


class PickupRulesTests(RulesCase):
    def setUp(self):
        super().setUp()
        queue.enqueue(self.docs, "P0.1", by="lead", now=MOMENT)

    def test_a_task_with_rules_gets_rule_and_done_lines(self):
        self.write_rules("R1 all do | Run the tests before you finish.\n"
                         "R2 task:P0.1 dont | Do not touch the parser cache.\n"
                         "R3 phase:P0 done | Unit tests pass and the docs are updated.\n"
                         "R4 task:P1.1 do | Only for P1.1.\n")
        reply = self.stop_event()
        self.assertEqual(reply["decision"], "block")
        self.assertTrue(reply["reason"].startswith(BASE))
        lines = self.added(reply["reason"]).split("\n")
        self.assertEqual(lines, ["rule: R1 all do | Run the tests before you finish.",
                                 "rule: R2 task:P0.1 dont | Do not touch the parser cache.",
                                 "done: R3 phase:P0 done | Unit tests pass and the docs are updated."])

    def test_a_project_with_no_rules_adds_nothing(self):
        self.assertEqual(self.stop_event()["reason"], BASE)
        self.write_rules("# only a comment\n")
        queue.enqueue(self.docs, "P1.1", by="lead", now=MOMENT)
        reply = self.stop_event(session="s2")
        self.assertNotIn("rule:", reply["reason"])
        self.assertNotIn("done:", reply["reason"])
        self.assertTrue(reply["reason"].startswith("roadmap: queued request "))

    def test_the_added_text_is_capped_at_800_characters(self):
        text = "".join("R%d all do | %s\n" % (i, ("word " * 40).strip()[:160]) for i in range(1, 40))
        self.write_rules(text)
        reply = self.stop_event()
        added = self.added(reply["reason"])
        self.assertTrue(added)
        self.assertLessEqual(len(added), 800)
        self.assertTrue(all(line.startswith("rule: R") for line in added.split("\n")))

    def test_rule_text_is_redacted(self):
        self.write_rules("R1 all do | Use key sk-ant-abcdefgh12345678 only from the vault.\n")
        reply = self.stop_event()
        self.assertNotIn("abcdefgh12345678", reply["reason"])
        self.assertIn("[redacted]", reply["reason"])

    def test_a_corrupt_rules_file_fails_open_and_the_pickup_is_still_surfaced(self):
        with open(os.path.join(self.docs, "rules.txt"), "wb") as fh:
            fh.write(b"\xff\xfe\x00 not utf-8 \xff")
        reply = self.stop_event()
        self.assertEqual(reply["decision"], "block")
        self.assertEqual(reply["reason"], BASE)

    def test_the_three_pickups_per_session_cap_still_holds_with_rules(self):
        self.write_rules("R1 all do | Run the tests.\n")
        for i in range(3):
            reply = self.stop_event(session="x")
            self.assertEqual(reply["decision"], "block")
            self.assertIn("rule: R1", reply["reason"])
            queue.dequeue(self.docs, "P0.1")
            queue.enqueue(self.docs, "P0.1", by="lead", now=MOMENT + datetime.timedelta(minutes=i + 1))
        self.assertIsNone(self.stop_event(session="x"))  # the session has had its three
        self.assertIsNone(self.stop_event(session="y"))  # the queued task set has had its three blocks

    def test_a_slow_rules_read_is_cut_off_and_the_pickup_still_surfaces(self):
        self.write_rules("R1 all do | Run the tests.\n")

        def slow(*args, **kwargs):
            time.sleep(1.0)
            return ["rule: never shown"]

        with mock.patch.object(hooks.rules, "show", side_effect=slow):
            began = time.monotonic()
            reply = self.stop_event()
            elapsed = time.monotonic() - began
        self.assertEqual(reply["decision"], "block")
        self.assertEqual(reply["reason"], BASE)
        self.assertLess(elapsed, 0.3 + 0.5)
        self.assertIn("rules omitted for P0.1: timeout", self.log_text())

    def test_no_time_left_in_the_budget_omits_the_rules(self):
        self.write_rules("R1 all do | Run the tests.\n")
        self.assertEqual(hooks._rule_lines(self.docs, "P0.1", lambda: 10.0, 0.0), [])


class SessionStartRulesTests(RulesCase):
    def test_session_start_adds_the_rules_of_the_first_queued_task(self):
        queue.enqueue(self.docs, "P0.1", by="lead", now=MOMENT)
        self.write_rules("R1 task:P0.1 do | Read the parser first.\nR2 task:P1.1 do | Not this one.\n"
                         "R3 task:P0.1 done | The parser tests pass.\n")
        context = self.start()["hookSpecificOutput"]["additionalContext"].split("\n")
        self.assertEqual(context[0], "queued: P0.1 (lead)")
        self.assertEqual(context[1:], ["rule: R1 task:P0.1 do | Read the parser first.",
                                       "done: R3 task:P0.1 done | The parser tests pass."])

    def test_session_start_without_rules_keeps_its_lines(self):
        queue.enqueue(self.docs, "P0.1", by="lead", now=MOMENT)
        self.assertEqual(self.start()["hookSpecificOutput"]["additionalContext"], "queued: P0.1 (lead)")


class RulesHelperTests(RulesCase):
    def test_the_rule_lines_are_at_most_twelve_from_show(self):
        self.write_rules("".join("R%d all do | Short rule %d.\n" % (i, i) for i in range(1, 16)))
        lines = hooks._task_rule_lines(self.docs, "P0.1")
        self.assertLessEqual(len(lines), 12)
        self.assertTrue(lines[-1].startswith("rule: +"))


if __name__ == "__main__":
    unittest.main()
