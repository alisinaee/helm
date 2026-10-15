"""HEAD-V3 H1 (R7.83): a head row sends `dup` as an object {id, score}, the shape web/js/views/head.js reads
(row.dup.id for the Merge button). Pure: rows are built by hand, no file or network.
Checks: the id and score pass through, a missing score becomes null, no dup key when there is no duplicate."""

import unittest
from datetime import datetime, timezone

from roadmap.core.snapshot import head_row

NOW = datetime(2026, 10, 15, 12, 0, 0, tzinfo=timezone.utc)


def folded(dup):
    row = {"id": "H9", "kind": "ask?", "sum": "x", "status": "doing", "ts": "2026-10-15T12:00:00Z",
           "stale": False, "carried": False, "links": []}
    if dup is not None:
        row["dup"] = dup
    return row


class HeadRowDupShape(unittest.TestCase):
    def test_dup_is_an_object_with_id_and_score(self):
        row = head_row(folded({"id": "H2", "score": 0.73}), NOW)
        self.assertEqual(row["dup"], {"id": "H2", "score": 0.73})
        self.assertIsInstance(row["dup"], dict)

    def test_missing_score_is_sent_as_null(self):
        row = head_row(folded({"id": "H2"}), NOW)
        self.assertEqual(row["dup"], {"id": "H2", "score": None})

    def test_dup_key_left_out_without_a_duplicate(self):
        self.assertNotIn("dup", head_row(folded(None), NOW))
        self.assertNotIn("dup", head_row(folded({}), NOW))


if __name__ == "__main__":
    unittest.main()
