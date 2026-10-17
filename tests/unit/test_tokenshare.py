"""R10.35: weekly-limit share per job from usage samples."""

import os
import tempfile
import unittest

from roadmap.services import tokenshare


def job(jid, start, end, units):
    return {"id": jid, "units": units, "status": "done", "started": start, "ended": end}


class TokenShareTests(unittest.TestCase):
    def test_rise_split_by_units_and_reset_skipped(self):
        a = job("a", "2026-10-16T10:00:00Z", "2026-10-16T11:00:00Z", 100)
        b = job("b", "2026-10-16T10:00:00Z", "2026-10-16T11:00:00Z", 300)
        t0 = 1792144800  # 2026-10-16T10:00:00Z
        samples = [{"t": t0, "wk": 10}, {"t": t0 + 3600, "wk": 14}, {"t": t0 + 7200, "wk": 2}]
        out = tokenshare.estimate([a, b], samples, now=t0 + 9000)
        self.assertAlmostEqual(out["a"], 1.0, 2)
        self.assertAlmostEqual(out["b"], 3.0, 2)

    def test_job_spread_over_windows_counts_by_overlap(self):
        a = job("a", "2026-10-16T10:00:00Z", "2026-10-16T12:00:00Z", 100)
        t0 = 1792144800
        samples = [{"t": t0, "wk": 0}, {"t": t0 + 3600, "wk": 1}, {"t": t0 + 7200, "wk": 3}]
        self.assertAlmostEqual(tokenshare.estimate([a], samples, now=t0 + 9000)["a"], 3.0, 2)

    def test_no_job_in_window_and_annotate_and_record(self):
        self.assertEqual(tokenshare.estimate([], [{"t": 1, "wk": 1}, {"t": 2, "wk": 5}]), {})
        with tempfile.TemporaryDirectory() as tmp:
            f = os.path.join(tmp, "s.jsonl")
            self.assertTrue(tokenshare.record(10, 5, now=1000, file_path=f))
            self.assertFalse(tokenshare.record(10, 5, now=1100, file_path=f))
            self.assertTrue(tokenshare.record(12, 6, now=1200, file_path=f))
            self.assertEqual(len(tokenshare.read_samples(f)), 2)
            j = [{"id": "x", "units": 5, "status": "done", "started": "1970-01-01T00:16:50Z",
                  "ended": "1970-01-01T00:20:00Z", "estPct": 9}]
            tokenshare.annotate(j, now=5000, file_path=f)
            self.assertAlmostEqual(j[0]["estPct"], 2.0, 2)


if __name__ == "__main__":
    unittest.main()
