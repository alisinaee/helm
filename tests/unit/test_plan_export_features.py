"""Tests for plan export with features (WP59b): F lines first, the f: token on T lines, the export then import round
trip, the phase filter, and that a project without features exports exactly as before.
"""

import os
import unittest

from roadmap.core import planfmt
from roadmap.errors import RoadmapError
from roadmap.services import tasks
from tests.unit.test_store_support import HomeCase

PROJECT_ID = "demo"
BASE = """P M1 todo | Foundations
T M1.1 todo 5 haiku/low | Scaffold
T M1.2 todo 8 sonnet/medium | Data model
P M2 todo | Surfaces
T M2.1 todo 3 cursor/high | Sync
"""


class ExportCase(HomeCase):
    def setUp(self):
        super().setUp()
        self.folder = self.make_project(PROJECT_ID)
        self.docs = os.path.join(self.folder, "docs")
        os.makedirs(self.docs)

    def run_plan(self, text):
        records, errors = planfmt.parse_plan(text)
        self.assertEqual(errors, [])
        return tasks.apply(self.docs, records, project_id=PROJECT_ID)

    def export(self, phase=None):
        return tasks.export_lines(self.docs, phase=phase)

    def raw_state(self):
        out = []
        for name in ("tasks.json", "features.json"):
            path = os.path.join(self.docs, name)
            with open(path, "rb") as fh:
                out.append(fh.read() if os.path.exists(path) else None)
        return out


class ExportWithoutFeaturesTests(ExportCase):
    def test_old_project_exports_phase_and_task_lines_only(self):
        self.run_plan(BASE)
        self.assertEqual(self.export(), [
            "P M1 todo | Foundations",
            "T M1.1 todo 5 haiku/low | Scaffold",
            "T M1.2 todo 8 sonnet/medium | Data model",
            "P M2 todo | Surfaces",
            "T M2.1 todo 3 cursor/high | Sync",
        ])

    def test_old_project_export_is_byte_for_byte_the_same_as_the_line_formatters(self):
        self.run_plan(BASE)
        doc = tasks.load(self.docs)
        expected = [planfmt.format_phase(p) for p in doc["phases"]]
        expected = [expected[0], planfmt.format_task(doc["tasks"][0]), planfmt.format_task(doc["tasks"][1]),
                    expected[1], planfmt.format_task(doc["tasks"][2])]
        self.assertEqual(self.export(), expected)

    def test_unknown_phase_is_not_found(self):
        self.run_plan(BASE)
        with self.assertRaises(RoadmapError) as ctx:
            self.export("P9")
        self.assertEqual(ctx.exception.code, "not_found")


class ExportWithFeaturesTests(ExportCase):
    def setUp(self):
        super().setUp()
        self.run_plan(BASE)
        self.run_plan("F F3 - 2 M1 - | Visual # lanes\n"
                      "F F7 hold 1 - F3 | Sub\n"
                      "F F9 - 3 M2 - | Surface only\n"
                      "T M1.1 todo 5 haiku/low f:F3,F7 | Scaffold # note\n"
                      "L F9 M2.1\n")

    def test_feature_lines_come_first_in_file_order(self):
        lines = self.export()
        self.assertEqual(lines[:3], [
            "F F3 - 2 M1 - | Visual # lanes",
            "F F7 hold 1 - F3 | Sub",
            "F F9 - 3 M2 - | Surface only",
        ])
        self.assertEqual(lines[3], "P M1 todo | Foundations")

    def test_task_line_carries_the_f_token(self):
        self.assertIn("T M1.1 todo 5 haiku/low f:F3,F7 | Scaffold # note", self.export())
        self.assertIn("T M2.1 todo 3 cursor/high f:F9 | Sync", self.export())
        self.assertNotIn("f:", [line for line in self.export() if line.startswith("T M1.2")][0])

    def test_export_then_import_is_idempotent(self):
        text = "\n".join(self.export()) + "\n"
        records, errors = planfmt.parse_plan(text)
        self.assertEqual(errors, [])
        before = self.raw_state()
        diff = tasks.apply(self.docs, records, project_id=PROJECT_ID)
        self.assertEqual((diff["changed"], diff["wrote"]), (0, False))
        self.assertEqual(self.raw_state(), before)

    def test_phase_export_keeps_its_own_features_and_the_ones_it_links(self):
        lines = self.export("M2")
        self.assertEqual(lines[0], "F F9 - 3 M2 - | Surface only")
        self.assertEqual(lines[1:], ["P M2 todo | Surfaces", "T M2.1 todo 3 cursor/high f:F9 | Sync"])

    def test_phase_export_pulls_in_linked_features_and_parents(self):
        lines = self.export("M1")
        self.assertEqual(lines[:2], ["F F3 - 2 M1 - | Visual # lanes", "F F7 hold 1 - F3 | Sub"])
        self.assertNotIn("F F9 - 3 M2 - | Surface only", lines)

    def test_phase_export_round_trips_into_the_same_project(self):
        text = "\n".join(self.export("M1")) + "\n"
        records, errors = planfmt.parse_plan(text)
        self.assertEqual(errors, [])
        diff = tasks.apply(self.docs, records, project_id=PROJECT_ID)
        self.assertEqual(diff["changed"], 0)


if __name__ == "__main__":
    unittest.main()
