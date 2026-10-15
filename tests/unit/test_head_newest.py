"""Head newest-entries regression: when the snapshot head cap (HEAD_BYTES_MAX) trims rows, the newest rows must stay.
Pure: records are built by hand, no file, network or service. Mirrors the setup in tests/unit/test_head_snapshot.py.

Checks, with 40 synthetic head entries H1..H40 whose ts increases (H40 is the newest):
(a) H40 is in the returned rows, (b) the serialized head block is <= HEAD_BYTES_MAX bytes,
(c) the rows keep the ids in descending order (newest first).

Current code: (a) and (b) pass; (c) fails (open rows are listed oldest first), so only (c) is marked expectedFailure.
TODO(remove expectedFailure): the other worker is fixing roadmap/core/snapshot.py. Once that fix lands, remove the
@unittest.expectedFailure marker on test_c_rows_are_newest_first; it is there only because the current code fails it.
"""

import json
import re
import unittest
from datetime import datetime, timedelta, timezone

from unittest import mock

from roadmap.core.snapshot import HEAD_BYTES_MAX, build_snapshot

NOW = datetime(2026, 10, 15, 12, 0, 0, tzinfo=timezone.utc)


def stamp(minutes_ago):
    return (NOW - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def entry(eid, minutes_ago, sum_text, kind="ask?", src="hook", sid="abc12345"):
    return {"v": 1, "t": "e", "id": eid, "ts": stamp(minutes_ago), "src": src, "sid": sid, "kind": kind,
            "sum": sum_text, "len": len(sum_text), "h": "sha1:000000000000"}


def newest_records():
    # H1 is the oldest (40 minutes ago), H40 the newest (1 minute ago); summaries are long enough to force a trim.
    return [entry("H%d" % i, 41 - i, "Long ask number %d about the export button and the map view layout %s"
                  % (i, "x" * 60)) for i in range(1, 41)]


def serialized_head(view):
    return json.dumps(view, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def id_number(row_id):
    return int(re.sub(r"\D", "", row_id) or 0)


class HeadNewestKept(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Cap forced to the old 3072 so the 40 rows overflow and the newest-first trim is exercised.
        with mock.patch("roadmap.core.snapshot.HEAD_BYTES_MAX", 3072):
            cls.full = build_snapshot({}, {}, NOW, head_records=newest_records())
        cls.head = cls.full["head"]
        cls.ids = [row["id"] for row in cls.head["rows"]]

    def test_rows_were_actually_trimmed(self):
        # Guard: the fixture must overflow the cap, otherwise the other checks prove nothing.
        self.assertLess(len(self.ids), 40)
        self.assertEqual(self.head["counts"]["open"], 40)

    def test_a_newest_id_h40_is_kept(self):
        self.assertIn("H40", self.ids)

    def test_b_serialized_head_fits_the_cap(self):
        self.assertLessEqual(len(serialized_head(self.head)), HEAD_BYTES_MAX)

    @unittest.expectedFailure  # Known failure on current code: open rows run oldest first. Remove after fix.
    def test_c_rows_are_newest_first(self):
        numbers = [id_number(row_id) for row_id in self.ids]
        self.assertEqual(numbers, sorted(numbers, reverse=True))


if __name__ == "__main__":
    unittest.main()
