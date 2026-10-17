"""R11.6: daily token history, totals and the remaining estimate."""

import unittest
from datetime import datetime

from roadmap.services import tokenhist

NOW = datetime(2026, 10, 17, 12, 0).astimezone().timestamp()


def job(jid, task, model, started, out=1000, tokens_k=None):
    row = {"id": jid, "task": task, "model": model, "status": "done", "started": started,
           "tokens": {"in": 10, "out": out, "cacheRead": 0, "cacheWrite": 0, "model": model}}
    if tokens_k:
        row["tokensK"] = tokens_k
    return row


def doc():
    return {"phases": [{"id": "R1", "name": "One"}], "tasks": [
        {"id": "R1.1", "phase": "R1", "status": "done", "tokensK": 50},
        {"id": "R1.2", "phase": "R1", "status": "partial", "tokensK": 100},
        {"id": "R1.3", "phase": "R1", "status": "todo", "tokensK": 40},
        {"id": "R1.4", "phase": "R1", "status": "hold", "note": "Deferred by rule", "tokensK": 900}]}


class TokenHistTests(unittest.TestCase):
    def build(self):
        jobs = [job("a", "R1.2", "haiku", "2026-10-17T09:00:00", out=2000, tokens_k=30),
                job("b", "R1.2", "sonnet", "2026-10-15T09:00:00", out=1000, tokens_k=20),
                job("c", "R1.1", "opus", "2026-09-01T09:00:00"),
                {"id": "d", "model": "haiku", "status": "done", "started": "2026-10-17T10:00:00"}]
        return tokenhist.build([("p", "P", jobs, doc())], [{"t": 5, "wk": 7}], now=NOW)

    def test_totals_by_scope_and_days(self):
        out = self.build()
        self.assertEqual(out["totals"]["today"]["jobs"], 2)
        self.assertEqual(out["totals"]["d7"]["jobs"], 3)
        self.assertEqual(out["totals"]["all"]["jobs"], 4)
        self.assertEqual(out["totals"]["today"]["out"], 2000)
        self.assertEqual(out["firstDay"], "2026-09-01")
        day = next(d for d in out["days"] if d["d"] == "2026-10-17")
        self.assertEqual(day["m"]["haiku"]["jobs"], 2)
        self.assertGreater(day["m"]["haiku"]["units"], 0)

    def test_remaining_subtracts_spent_and_skips_done_and_deferred(self):
        out = self.build()
        row = out["phases"][0]
        self.assertEqual(row["open"], 2)
        self.assertEqual(row["estK"], 140.0)
        self.assertEqual(row["spentK"], 50.0)
        self.assertEqual(row["remainingK"], 90.0)  # 100 - 50 + 40
        self.assertEqual(out["remainingK"], 90.0)

    def test_spent_never_makes_remaining_negative(self):
        jobs = [job("a", "R1.3", "haiku", "2026-10-17T09:00:00", tokens_k=500)]
        out = tokenhist.build([("p", "P", jobs, doc())], [], now=NOW)
        self.assertEqual(out["phases"][0]["remainingK"], 100.0)

    def test_tasks_phase_use_and_samples(self):
        out = self.build()
        self.assertEqual({t["id"] for t in out["tasks"]}, {"R1.1", "R1.2"})
        self.assertEqual(out["phaseUse"][0]["id"], "R1")
        self.assertEqual(out["samples"], [{"t": 5, "wk": 7}])

    def test_empty_input(self):
        out = tokenhist.build([], [], now=NOW)
        self.assertEqual(out["days"], [])
        self.assertEqual(out["remainingK"], 0)

    def test_collect_is_fail_open(self):
        out = tokenhist.collect([{"id": "x", "name": "x", "data_dir": "/nonexistent-dir"}], None, NOW)
        self.assertEqual(out["totals"]["all"]["jobs"], 0)


if __name__ == "__main__":
    unittest.main()
