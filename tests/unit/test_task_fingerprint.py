"""Task create dedupe (Q7): a new task whose title and phase match an existing task returns that task's id and
creates nothing. Title matching ignores case, punctuation and extra spaces; the phase must match too."""

import unittest

from roadmap.services import tasks
from tests.unit.test_tasks_service import EXAMPLE, ServiceCase


class FingerprintFunctionTests(unittest.TestCase):
    def test_case_punctuation_and_spacing_do_not_change_the_fingerprint(self):
        a = tasks.title_fingerprint("M1", "Scaffold repo, CI and lint")
        self.assertEqual(a, tasks.title_fingerprint("M1", "  scaffold   REPO CI and lint! "))

    def test_phase_is_part_of_the_fingerprint(self):
        self.assertNotEqual(tasks.title_fingerprint("M1", "Scaffold"), tasks.title_fingerprint("M2", "Scaffold"))

    def test_different_titles_differ(self):
        self.assertNotEqual(tasks.title_fingerprint("M1", "Scaffold"), tasks.title_fingerprint("M1", "Scaffold two"))


class CreateDedupeTests(ServiceCase):
    def test_same_title_in_same_phase_returns_existing_id_and_creates_nothing(self):
        self.plan(EXAMPLE)
        diff = self.plan("P M1 todo | Foundations\nT M1.9 todo 5 haiku/low | scaffold repo CI and LINT!\n")
        self.assertEqual(diff["tasks_added"], [])
        ids = [t["id"] for t in self.read()["tasks"]]
        self.assertEqual(len(ids), 5)
        self.assertNotIn("M1.9", ids)

    def test_same_title_in_another_phase_still_creates_a_task(self):
        self.plan(EXAMPLE)
        diff = self.plan("P M2 todo | Second\nT M2.1 todo 5 haiku/low | Scaffold repo, CI and lint\n")
        self.assertEqual(diff["tasks_added"], ["M2.1"])
        self.assertIn("M2.1", [t["id"] for t in self.read()["tasks"]])

    def test_repeat_of_a_new_title_in_one_input_creates_only_the_first(self):
        self.plan("P M3 todo | Third\nT M3.1 todo 5 haiku/low | Write docs\nT M3.2 todo 5 haiku/low | write docs.\n")
        ids = [t["id"] for t in self.read()["tasks"] if t["phase"] == "M3"]
        self.assertEqual(ids, ["M3.1"])


if __name__ == "__main__":
    unittest.main()
