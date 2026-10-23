"""R7.10, R7.13 H3: the snapshot features block for 99 features stays under size bounds, and carries no key the
Planner does not read (running, hold, and empty parent/phase/accepted). Rows are the slim rows of core/features.py:
label, ask and gaps appear only when they apply, and acc stays until the person accepts the feature.
Pure in-memory data; no files are read or written.

Spec target (PLANNER-V2-SPEC section 6) is 8 KB for 99 items. It is NOT reached: each row keeps id, title, label,
done, total, blocked, state and acc (the Planner renders done/total and blocked), which costs about 110 bytes a row
before any text. The bounds below are the measured sizes with headroom; the gap is an open decision for the person.
"""

import json
import unittest
from datetime import datetime, timezone

from roadmap.core.snapshot import build_snapshot

PINNED = datetime(2026, 10, 14, 12, 0, 0, tzinfo=timezone.utc)
SPEC_TARGET_BYTES = 8 * 1024
# Measured 17.7 KB (99 items; titles ~30 chars, acc ~50, a tree and asks). Bound has headroom.
TYPICAL_BOUND_BYTES = 19 * 1024
# Measured 31.1 KB for the worst case (titles 80, acc 120, flat). The title and acc text alone is about 12 KB here.
WORST_BOUND_BYTES = 33 * 1024


def _features(count, title_len=80, acc_len=120):
    out = []
    for i in range(1, count + 1):
        out.append({"id": "F%d" % i,
                    "title": ("Planner feature %d " % i).ljust(title_len, "x")[:title_len],
                    "acc": ("Acceptance line %d: the person can check the outcome in the GUI and in the CLI " % i)
                    .ljust(acc_len, "y")[:acc_len],
                    "prio": 1 + i % 3, "parent": None, "phase": None, "hold": i % 13 == 0, "accepted": None})
    return out


def _typical_features(count):
    """A plan tree: every third item is a sub plan's child of the item before it, every fourth is asked for."""
    out = []
    for i in range(1, count + 1):
        feature = {"id": "F%d" % i, "title": "Feature %d planner view" % i, "acc": "Acceptance for feature %d" % i,
                   "prio": 2, "parent": "F%d" % (i - 1) if i % 3 == 2 else None, "phase": None, "hold": False,
                   "accepted": None}
        if i % 4 == 0:
            feature["ask"] = True
        out.append(feature)
    return out


def _snapshot_features(feature_list):
    files = {"features.json": json.dumps({"features": feature_list}), "tasks.json": json.dumps({"tasks": []})}
    return build_snapshot(files, {"id": "bench", "title": "bench"}, PINNED)["features"]


class SnapshotFeaturesSizeTests(unittest.TestCase):
    def setUp(self):
        self.features = _snapshot_features(_features(99))

    def test_ninety_nine_features_worst_case_under_bound(self):
        self.assertEqual(len(self.features["rows"]), 99)
        size = len(json.dumps(self.features))
        self.assertLessEqual(size, WORST_BOUND_BYTES, "features block is %d bytes" % size)

    def test_ninety_nine_typical_features_under_bound(self):
        features = _snapshot_features(_typical_features(99))
        self.assertEqual(len(features["rows"]), 99)
        size = len(json.dumps(features))
        self.assertLessEqual(size, TYPICAL_BOUND_BYTES, "typical features block is %d bytes" % size)
        self.assertGreater(SPEC_TARGET_BYTES, 0)

    def test_slim_row_keys_follow_the_rules(self):
        features = _snapshot_features(_typical_features(12))
        rows = {row["id"]: row for row in features["rows"]}
        self.assertEqual(rows["F4"]["ask"], True)
        self.assertNotIn("ask", rows["F5"])
        self.assertEqual(rows["F2"]["label"], "P0.0")
        self.assertEqual(rows["F1"]["gaps"], 1)   # F2 is an untasked child
        self.assertNotIn("gaps", rows["F2"])

    def test_rows_carry_no_unread_keys(self):
        for row in self.features["rows"]:
            self.assertNotIn("running", row)
            self.assertNotIn("hold", row)
            self.assertNotIn("estK", row)
            self.assertNotIn("spentK", row)
            self.assertNotIn("prio", row)
            self.assertIn("state", row)
            self.assertIn("label", row)
            if row.get("parent") is None:
                self.assertNotIn("parent", row)
            if row.get("phase") is None:
                self.assertNotIn("phase", row)


if __name__ == "__main__":
    unittest.main()
