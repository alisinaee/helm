"""WP22 regression tests for the R3 review (docs/reviews/R3-cmd-limits-cursor-auto.md) and its known extra bugs.

Each test names the finding it guards. Temp ROADMAP_HOME and temp projects only, injected times, no network.
"""

import datetime
import json
import os
import unittest
from unittest import mock

from roadmap.errors import RoadmapError
from roadmap.http import security
from roadmap.services import agentguard, commands, cmdops, hooks, ledger, limits
from roadmap.store import config, jsonl, paths
from tests.api.support import ServerCase
from tests.unit.test_cmdops import OpsCase
from tests.unit.test_control_support import ControlCase, write_json
from tests.unit.test_store_support import HomeCase


def at(hour, minute=0, day=13):
    """A local aware time on 2026-10-<day>."""
    return datetime.datetime(2026, 10, day, hour, minute).astimezone()


# ---------------------------------------------------------------- finding 1 and 8: the browser proof

class BrowserProofTests(unittest.TestCase):
    def test_a_proof_needs_this_servers_origin_and_same_origin_fetch(self):
        good = {"Origin": "http://127.0.0.1:8780", "Sec-Fetch-Site": "same-origin"}
        self.assertTrue(security.browser_proof(good, 8780))
        self.assertTrue(security.browser_proof({"Origin": "http://localhost:8780",
                                                "Sec-Fetch-Site": "same-origin"}, 8780))
        self.assertFalse(security.browser_proof({"Sec-Fetch-Site": "same-origin"}, 8780))
        self.assertFalse(security.browser_proof({"Origin": "http://127.0.0.1:8780"}, 8780))
        self.assertFalse(security.browser_proof({"Origin": "http://evil.example",
                                                 "Sec-Fetch-Site": "same-origin"}, 8780))
        self.assertFalse(security.browser_proof({"Origin": "http://127.0.0.1:8780",
                                                 "Sec-Fetch-Site": "cross-site"}, 8780))

    def test_the_guard_trusts_a_gui_call_only_inside_a_proof_and_never_edits_the_environment(self):
        with mock.patch.dict(os.environ, {"CLAUDECODE": "1"}):
            self.assertTrue(agentguard.is_agent("gui"))
            with agentguard.browser_proven(True):
                self.assertFalse(agentguard.is_agent("gui"))
                self.assertEqual(os.environ.get("CLAUDECODE"), "1")
                self.assertTrue(agentguard.is_agent("agent"))
            self.assertTrue(agentguard.is_agent("gui"))  # the mark is gone after the block

    def test_a_proof_on_one_thread_does_not_reach_another(self):
        import threading
        seen = []
        with mock.patch.dict(os.environ, {"CLAUDECODE": "1"}):
            with agentguard.browser_proven(True):
                worker = threading.Thread(target=lambda: seen.append(agentguard.is_agent("gui")))
                worker.start()
                worker.join(5)
        self.assertEqual(seen, [True])


class CmdRouteProofTests(ServerCase):
    """A loosening write on the main listener: refused from an agent's shell unless the browser proof is there."""

    def setUp(self):
        super().setUp()
        env = mock.patch.dict(os.environ, {})
        env.start()
        self.addCleanup(env.stop)
        os.environ["CLAUDECODE"] = "1"  # the server runs in an agent's shell

    def unproven(self):
        return {"X-Roadmap-CSRF": self.token, "Sec-Fetch-Site": "same-origin", "Content-Type": "application/json"}

    def test_a_write_without_the_browser_proof_cannot_loosen_even_with_the_csrf_token(self):
        res = self.request("POST", "/api/v1/cmd", headers=self.unproven(),
                           body=json.dumps({"op": "control.resume", "args": {}}).encode("utf-8"))
        self.assertEqual(res.status, 409, res.body[:200])
        self.assertEqual(res.json()["error"]["code"], "agent_refused")

    def test_a_write_with_the_browser_proof_can_loosen_and_the_environment_is_untouched(self):
        proven = dict(self.write_headers(), Origin="http://127.0.0.1:%d" % self.port)
        res = self.request("POST", "/api/v1/cmd", headers=proven,
                           body=json.dumps({"op": "control.resume", "args": {}}).encode("utf-8"))
        self.assertEqual(res.status, 200, res.body[:200])
        self.assertEqual(os.environ.get("CLAUDECODE"), "1")


# ---------------------------------------------------------------- finding 2: a broken project file

class LimitsRegressionTests(ControlCase):
    def setUp(self):
        super().setUp()
        self.now = at(14, 2)
        self.project = config.get_project("demo")

    def test_a_project_file_with_a_newer_schema_keeps_the_global_rows(self):
        limits.add(self.project, "global", "day", "pct", 10, now=self.now)
        write_json(os.path.join(self.docs, "autonomy.json"), {"schemaVersion": 99, "limit": {"stopAtPercent": 50}})
        rows = limits.evaluate_rows(self.project, now=self.now, strict=True)
        self.assertEqual([row["scope"] for row in rows], ["global"])

    # ---------------------------------------------------------- finding 7: a reading from the future

    def test_a_usage_reading_from_the_future_is_not_fresh(self):
        path = paths.usage_file()
        write_json(path, {"schemaVersion": 1, "weeklyPercent": 50, "updated": (self.now + datetime.timedelta(
            hours=1)).isoformat(timespec="seconds")})
        self.assertEqual(limits._usage_state(self.now), (50.0, False))
        write_json(path, {"schemaVersion": 1, "weeklyPercent": 50, "updated": (self.now - datetime.timedelta(
            minutes=5)).isoformat(timespec="seconds")})
        self.assertEqual(limits._usage_state(self.now), (50.0, True))

    # ---------------------------------------------------------- finding 10: non-finite numbers

    def test_a_non_finite_limit_value_is_refused(self):
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value), self.assertRaises(RoadmapError) as ctx:
                limits.check_spec("global", "day", "pct", value)
            self.assertEqual(ctx.exception.code, "usage")


class RemovalRegressionTests(ControlCase):
    def test_a_warning_budget_removed_and_undone_stays_a_warning(self):
        from roadmap.services import budget
        budget.set_project_limit(self.docs, 200, "warn")
        project = config.get_project("demo")
        removed = limits.rm(project, "BUD", now=at(14, 2))
        self.assertEqual(removed["action"], "warn")
        # the undo of the removal is limit.set with the removed row's action: it must come back as a warning
        limits.add(project, "project", "total", "tok", removed["value"], action=removed["action"], now=at(14, 2))
        self.assertEqual(budget.get(self.docs)["limitAction"], "warn")


# ---------------------------------------------------------------- finding 3: weekly readings

class LedgerReadingTests(HomeCase):
    def points(self):
        return ledger.read()[0]["days"][at(12).date().isoformat()]["pts"]

    def test_a_small_dip_in_the_weekly_percent_adds_nothing_and_keeps_the_baseline(self):
        ledger.record_reading(62, now=at(12, 0))
        ledger.record_reading(61, now=at(12, 1))  # jitter: two writers, rounding
        self.assertEqual(self.points(), 0.0)
        ledger.record_reading(70, now=at(12, 2))  # 8 more than the 62 baseline, not 70
        self.assertEqual(self.points(), 8.0)

    def test_a_large_drop_is_the_weekly_reset_and_adds_the_new_value(self):
        ledger.record_reading(62, now=at(12, 0))
        ledger.record_reading(5, now=at(12, 1))
        self.assertEqual(self.points(), 5.0)

    def test_readings_outside_zero_to_the_bound_are_refused_and_write_nothing(self):
        for value in (-5, float("inf"), float("nan"), 1e9, True):
            with self.subTest(value=value):
                self.assertIsNone(ledger.record_reading(value, now=at(12, 0)))
        self.assertEqual(ledger.read()[1], "missing")

    # ---------------------------------------------------------- finding 6: trimming keeps the week

    def test_trimming_the_file_never_drops_a_day_of_this_week(self):
        now = at(12, 0, day=13)
        for day in range(7, 14):
            for project in range(40):
                ledger.record_spend("project-%02d" % project, 10, now=at(9, 0, day=day))
        doc, status = ledger.read()
        self.assertEqual(status, "ok")
        self.assertEqual(sorted(doc["days"]), ["2026-10-%02d" % day for day in range(7, 14)])
        self.assertEqual(ledger.tokens_k(doc, None, "week", now), 2800.0)
        self.assertLessEqual(ledger._size(doc), ledger.MAX_BYTES + 512)


# ---------------------------------------------------------------- finding 4: a phone undo

class PhoneUndoTests(OpsCase):
    def test_the_phone_may_undo_its_own_change(self):
        act = self.run_op("task.status", {"id": "P1.1", "status": "done"}, source="phone")["activity"]
        self.assertTrue(self.run_op("undo", {"activity": act}, source="phone")["ok"])

    def test_the_phone_may_not_undo_a_change_made_by_the_cli(self):
        act = self.run_op("task.status", {"id": "P1.1", "status": "done"}, source="cli")["activity"]
        with self.assertRaises(RoadmapError) as ctx:
            self.run_op("undo", {"activity": act}, source="phone")
        self.assertEqual(ctx.exception.code, "forbidden")
        self.assertEqual(self.status_of_task(), "done")  # nothing was undone

    def status_of_task(self):
        from roadmap.services import tasks
        return tasks.get(self.data_dir, "P1.1").get("status")


# ---------------------------------------------------------------- finding 5: undo runs once

class UndoOnceTests(OpsCase):
    def change(self):
        return self.run_op("task.status", {"id": "P1.1", "status": "done"}, source="gui")["activity"]

    def undo_file(self):
        return commands.records.file_of(self.data_dir, commands.UNDO_FILE)

    def test_a_second_undo_of_the_same_change_is_refused(self):
        act = self.change()
        self.run_op("undo", {"activity": act}, source="gui")
        with self.assertRaises(RoadmapError) as ctx:
            self.run_op("undo", {"activity": act}, source="gui")
        self.assertEqual(ctx.exception.code, "conflict")

    def test_an_undo_already_in_progress_blocks_a_second_one(self):
        act = self.change()
        jsonl.append_line(self.undo_file(), {"undoing": act, "at": "2026-10-13T12:00:00+00:00"})
        with self.assertRaises(RoadmapError) as ctx:
            self.run_op("undo", {"activity": act}, source="gui")
        self.assertEqual(ctx.exception.code, "conflict")

    def test_a_failed_undo_releases_its_claim_so_it_can_be_tried_again(self):
        before = self.status_of_task()
        act = self.change()
        real = commands._execute
        calls = []

        def flaky(*args, **kwargs):
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("disk full (simulated)")
            return real(*args, **kwargs)

        with mock.patch.object(commands, "_execute", flaky):
            with self.assertRaises(RuntimeError):
                self.run_op("undo", {"activity": act}, source="gui")
            self.assertTrue(self.run_op("undo", {"activity": act}, source="gui")["ok"])
        self.assertEqual(self.status_of_task(), before)

    def status_of_task(self):
        from roadmap.services import tasks
        return tasks.get(self.data_dir, "P1.1").get("status")


# ---------------------------------------------------------------- finding 9 and 10: task tokens and JSON numbers

class ArgumentTests(unittest.TestCase):
    def test_task_tokens_have_a_ceiling_checked_before_anything_is_written(self):
        for tokens in (10 ** 400, commands.TOKENS_K_MAX + 1):
            with self.subTest(tokens=tokens), self.assertRaises(RoadmapError) as ctx:
                commands._check_task_status({"id": "P1.1", "status": "done", "tokensK": tokens})
            self.assertEqual(ctx.exception.code, "usage")
        self.assertEqual(commands._check_task_status({"id": "P1.1", "status": "done", "tokensK": 5000})["tokensK"],
                         5000)

    def test_json_nan_and_infinity_are_refused_on_the_cmd_body(self):
        with self.assertRaises(ValueError):
            security.strict_json_loads('{"op": "budget.set", "args": {"value": NaN}}')
        with self.assertRaises(ValueError):
            security.strict_json_loads('{"value": Infinity}')
        self.assertEqual(security.strict_json_loads('{"value": 1.5}'), {"value": 1.5})

    def test_a_non_finite_budget_or_rule_value_is_refused(self):
        with self.assertRaises(RoadmapError) as ctx:
            cmdops._number_or_none({"value": float("nan")}, "value")
        self.assertEqual(ctx.exception.code, "usage")
        with self.assertRaises(RoadmapError) as ctx:
            cmdops._check_rules_add({"scope": "project", "kind": "tokens", "text": "cap", "value": float("inf")})
        self.assertEqual(ctx.exception.code, "usage")


# ---------------------------------------------------------------- finding (d): watch while blocked

class HooksWatchTests(unittest.TestCase):
    def test_watch_is_allowed_while_a_project_is_blocked(self):
        self.assertTrue(hooks._allowed_while_blocked("roadmap watch"))
        self.assertFalse(hooks._allowed_while_blocked("roadmap task start P1.1"))


if __name__ == "__main__":
    unittest.main()
