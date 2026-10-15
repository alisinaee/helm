"""Flow 3: limits. A global weekly percent row and a project token row are set through /api/v1/cmd, usage readings are
pushed with `roadmap usage push`, and the warn (at 80%), block (at 100%), sentinel, hook deny, override and fail-open
(stale usage) rules are checked end to end. Usage readings and the spend are stored only in the temp home."""

import datetime
import json
import os
import unittest

from tests.integration.harness import stack

AUTONOMY_NO_LIMIT = {"schemaVersion": 2, "limit": {"kind": "weekly", "stopAtPercent": 100}}


def push(sandbox, weekly):
    """A usage reading through the CLI (stdin), exactly as a person or a script would push it."""
    proc = sandbox.cli(["usage", "push"], stdin=json.dumps({"rateLimits": [{"kind": "seven_day",
                                                                          "percentUsed": weekly}]}))
    if proc.returncode != 0:
        raise AssertionError("usage push failed: " + proc.stderr)


def meter(snapshot, row_id):
    rows = snapshot["meters"]["limits"]
    return next(row for row in rows if row["id"] == row_id)


class LimitsFlowTests(unittest.TestCase):
    def setUp(self):
        self.sandbox, self.server = stack(self)
        self.sandbox.write_doc("autonomy.json", AUTONOMY_NO_LIMIT)
        self.server.cmd("limit.set", {"scope": "global", "window": "week", "kind": "pct", "value": 100,
                                      "action": "block"})
        self.server.cmd("limit.set", {"scope": "project", "window": "total", "kind": "tok", "value": 100})

    def test_warn_at_80_percent_then_block_at_100_then_override_lifts_it(self):
        sb, srv = self.sandbox, self.server
        push(sb, 85)
        shown = sb.cli(["limit", "show"])
        self.assertIn("L1 global week 85/100% WARN", shown.stdout)
        snap = srv.snapshot(sb.pid)
        self.assertEqual(meter(snap, "L1")["state"], "warn")
        self.assertFalse(os.path.exists(sb.sentinel))
        self.assertIsNone(sb.hook("Edit", {"file_path": "x.md"}))  # a warning never blocks

        # 60 K on one task, then 50 K on another: the project token row goes from 60% to 110%
        self.assertEqual(srv.cmd("task.status", {"id": "P0.2", "status": "done", "tokensK": 60})["data"]["budgetFed"],
                         True)
        self.assertIsNone(sb.hook("Edit", {"file_path": "x.md"}))
        self.assertTrue(srv.cmd("task.status", {"id": "P0.3", "status": "done", "tokensK": 50})["ok"])
        self.assertTrue(os.path.exists(sb.sentinel))
        reason = sb.hook("Edit", {"file_path": "x.md"})["hookSpecificOutput"]
        self.assertEqual(reason["permissionDecision"], "deny")
        self.assertIn("project budget 110% used", reason["permissionDecisionReason"])
        self.assertEqual(meter(srv.snapshot(sb.pid), "BUD")["state"], "block")

        # the same 50 K sent again is not counted twice
        srv.cmd("task.status", {"id": "P0.3", "status": "done", "tokensK": 50})
        spent = sb.read_doc("budget.json")["spent"]
        self.assertEqual(sum(sum(models.values()) for models in spent.values()), 110.0)

        push(sb, 100)
        self.assertIn("L1 global week 100/100% BLOCK", sb.cli(["limit", "show"]).stdout)
        self.assertEqual(meter(srv.snapshot(sb.pid), "L1")["state"], "block")
        self.assertIn("weekly usage 100%", sb.hook("Edit", {"file_path": "x.md"})["hookSpecificOutput"][
            "permissionDecisionReason"])

        overridden = sb.cli(["override", "--hours", "1"])
        self.assertEqual(overridden.returncode, 0, overridden.stderr)
        with open(os.path.join(sb.state_dir, "control-" + sb.pid + ".json"), encoding="utf-8") as fh:
            self.assertIsNotNone(json.load(fh)["overrideUntil"])
        # the sentinel stays (it follows the block); the override makes the gate let the work through
        self.assertIsNone(sb.hook("Edit", {"file_path": "x.md"}))

    def test_stale_usage_fails_open_even_with_a_sentinel_from_a_fresh_reading(self):
        sb, srv = self.sandbox, self.server
        push(sb, 100)
        self.assertTrue(os.path.exists(sb.sentinel))
        self.assertIsNotNone(sb.hook("Edit", {"file_path": "x.md"}))

        usage_path = os.path.join(sb.state_dir, "usage.json")
        with open(usage_path, encoding="utf-8") as fh:
            reading = json.load(fh)
        old = datetime.datetime.now().astimezone() - datetime.timedelta(minutes=120)  # past the 90-minute freshness rule
        reading["updated"] = old.isoformat(timespec="seconds")
        with open(usage_path, "w", encoding="utf-8") as fh:
            json.dump(reading, fh)

        self.assertIn("L1 global week ?/100% unknown", sb.cli(["limit", "show"]).stdout)
        self.assertIsNone(sb.hook("Edit", {"file_path": "x.md"}))
        self.assertFalse(os.path.exists(sb.sentinel))
        self.assertEqual(meter(srv.snapshot(sb.pid), "L1")["state"], "unknown")


if __name__ == "__main__":
    unittest.main()
