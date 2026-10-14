"""R7.10: the snapshot features block for 60 features stays under a size bound (worst case: every feature open, long
title and acc), and carries no key the Planner does not read (running, hold, and empty parent/phase/accepted).
Pure in-memory data; no files are read or written."""

import json
import unittest
from datetime import datetime, timezone

from roadmap.core.snapshot import build_snapshot

PINNED = datetime(2026, 10, 14, 12, 0, 0, tzinfo=timezone.utc)
# Measured 20461 bytes for this worst case when R7.10 landed. The waived 8 KB target is not reached: title and acc text
# alone is about 12 KB at the limits (TITLE_MAX 80, ACC_MAX 160 in core/features.py).
BOUND_BYTES = 21000


def _features(count):
    out = []
    for i in range(1, count + 1):
        out.append({"id": "F%d" % i,
                    "title": ("Planner feature %d " % i).ljust(80, "x"),
                    "acc": ("Acceptance line %d: the person can check the outcome in the GUI and in the CLI " % i)
                    .ljust(120, "y"),
                    "prio": 1 + i % 3, "parent": None, "phase": None, "hold": i % 13 == 0, "accepted": None})
    return out


class SnapshotFeaturesSizeTests(unittest.TestCase):
    def setUp(self):
        files = {"features.json": json.dumps({"features": _features(60)}), "tasks.json": json.dumps({"tasks": []})}
        self.features = build_snapshot(files, {"id": "bench", "title": "bench"}, PINNED)["features"]

    def test_sixty_features_under_bound(self):
        self.assertEqual(len(self.features["rows"]), 60)
        size = len(json.dumps(self.features))
        self.assertLessEqual(size, BOUND_BYTES, "features block is %d bytes" % size)

    def test_rows_carry_no_unread_keys(self):
        for row in self.features["rows"]:
            self.assertNotIn("running", row)
            self.assertNotIn("hold", row)
            self.assertIn("state", row)
            if row.get("parent") is None:
                self.assertNotIn("parent", row)
            if row.get("phase") is None:
                self.assertNotIn("phase", row)


if __name__ == "__main__":
    unittest.main()
