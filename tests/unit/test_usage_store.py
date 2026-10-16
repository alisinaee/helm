"""Usage store, mirror, push, loop and CLI tests. ROADMAP_HOME is a temp dir; the keychain and the endpoint are fakes.

Every test patches the real read_keychain_token and http_fetch in setUp, so a default call still gets a fake.
"""

import contextlib
import datetime
import io
import json
import os
import threading
import time
import unittest
from unittest import mock

from roadmap.cli import main
from roadmap.errors import RoadmapError
from roadmap.services import usage as uc
from roadmap.store import config as config_store
from roadmap.store import paths, schema
from tests.unit.test_store_support import HomeCase, mode_of
from tests.unit.test_usage_collector import FAKE_TOKEN, GOOD_REPLY


# Both window resets are set relative to the run time: a passed reset has no current percent (R7.x), so a fixed
# date in GOOD_REPLY would silently turn every percent into None once it is in the past.
NOW_UTC = datetime.datetime.now(datetime.timezone.utc)
SEVEN_DAY_RESET_Z = (NOW_UTC + datetime.timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")


def fresh_reply():
    """GOOD_REPLY with both resets in the future (a passed reset has no current percent)."""
    later = (NOW_UTC + datetime.timedelta(hours=3)).isoformat(timespec="seconds")
    return dict(GOOD_REPLY, five_hour=dict(GOOD_REPLY["five_hour"], resets_at=later),
                seven_day=dict(GOOD_REPLY["seven_day"], resets_at=SEVEN_DAY_RESET_Z))


def read_text(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def write_text(path, text):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def run_cli(argv, stdin_text=""):
    """Run the CLI in-process and return (exit code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with mock.patch("sys.stdin", io.StringIO(stdin_text)), \
            contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


class UsageCase(HomeCase):
    def setUp(self):
        super().setUp()
        self.fetches = []
        self.token_reads = 0
        for patcher in (
            mock.patch.object(uc, "read_keychain_token", side_effect=self._fake_token),
            mock.patch.object(uc, "http_fetch", side_effect=self._fake_fetch),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def _fake_token(self):
        self.token_reads += 1
        return FAKE_TOKEN

    def _fake_fetch(self, token):
        self.fetches.append(token)
        return fresh_reply()

    def config_with(self, projects=(), mirror=True, interval=120):
        cfg = config_store.default_config()
        cfg["usage"] = {"intervalS": interval, "mirrorToProjects": mirror}
        cfg["projects"] = list(projects)
        return cfg

    def project(self, pid, autonomy=None):
        """A project folder with docs/ and, when autonomy is given, an autonomy.json holding that object."""
        folder = self.make_project(pid)
        docs = os.path.join(folder, "docs")
        os.makedirs(docs, exist_ok=True)
        if autonomy is not None:
            write_text(os.path.join(docs, "autonomy.json"), json.dumps(autonomy))
        return {"id": pid, "name": pid, "path": folder, "dataDir": "docs", "addedAt": "2026-10-13T00:00:00Z"}

    def autonomy_of(self, project):
        return json.loads(read_text(os.path.join(project["path"], "docs", "autonomy.json")))

    def store_path(self):
        return paths.usage_file()


class StoreTests(UsageCase):
    def test_sync_stores_usage_with_schema_and_no_last_error(self):
        result = uc.sync_once(self.config_with())
        self.assertEqual(result["usage"]["weeklyPercent"], 62.4)
        self.assertEqual(result["usage"]["fiveHourPercent"], 17)
        self.assertIs(result["usage"]["stale"], False)
        stored = json.loads(read_text(self.store_path()))
        self.assertEqual(stored["schemaVersion"], schema.current_version("usage"))
        self.assertEqual(stored["source"], uc.SOURCE_ENDPOINT)
        self.assertIsNone(stored["lastError"])
        self.assertEqual(mode_of(self.store_path()), 0o600)
        self.assertEqual(self.fetches, [FAKE_TOKEN])

    def test_show_before_any_read_is_empty_and_stale(self):
        view = uc.show(self.config_with())
        self.assertIsNone(view["weeklyPercent"])
        self.assertIs(view["stale"], True)
        self.assertIsNone(view["ageS"])

    def test_failed_sync_keeps_last_good_values_and_records_reason(self):
        uc.sync_once(self.config_with())

        def failing_fetch(token):
            raise uc.UsageError("usage endpoint answered HTTP 500")

        with mock.patch.object(uc, "http_fetch", side_effect=failing_fetch):
            with self.assertRaisesRegex(uc.UsageError, "HTTP 500"):
                uc.sync_once(self.config_with())
        view = uc.show(self.config_with())
        self.assertEqual(view["weeklyPercent"], 62.4)
        self.assertEqual(view["lastError"], "usage endpoint answered HTTP 500")

        uc.sync_once(self.config_with())
        self.assertIsNone(uc.show(self.config_with())["lastError"])

    def test_stale_flag_from_age_against_the_ninety_minute_limit(self):
        now = datetime.datetime.now(datetime.timezone.utc)

        def stamp(seconds_ago):
            return (now - datetime.timedelta(seconds=seconds_ago)).astimezone().isoformat(timespec="seconds")

        uc._update_store({"weeklyPercent": 1, "updated": stamp(100)})
        fresh = uc.show(self.config_with(interval=120), now=now)
        self.assertIs(fresh["stale"], False)
        self.assertEqual(fresh["ageS"], 100)
        self.assertEqual(fresh["maxAgeS"], 90 * 60)

        uc._update_store({"updated": stamp(91 * 60)})
        self.assertIs(uc.show(self.config_with(interval=120), now=now)["stale"], True)

    def test_newer_store_file_is_refused_and_untouched(self):
        os.makedirs(paths.state_dir(), exist_ok=True)
        write_text(self.store_path(), json.dumps({"schemaVersion": 9, "weeklyPercent": 1}))
        before = read_text(self.store_path())
        with self.assertRaises(RoadmapError) as cm:
            uc.show(self.config_with())
        self.assertEqual(cm.exception.code, "newer_schema")
        self.assertEqual(read_text(self.store_path()), before)


class MirrorTests(UsageCase):
    def test_v1_autonomy_keeps_limit_and_gets_usage_block(self):
        proj = self.project("alpha", {"limit": {"stopAtPercent": 65}, "usage": {"weeklyPercent": 1}})
        result = uc.sync_once(self.config_with([proj]))
        self.assertEqual(result["mirrors"], [{"project": "alpha", "status": "ok"}])
        saved = self.autonomy_of(proj)
        self.assertEqual(saved["schemaVersion"], 2)
        self.assertEqual(saved["limit"], {"stopAtPercent": 65})
        self.assertEqual(saved["usage"]["weeklyPercent"], 62.4)
        self.assertEqual(saved["usage"]["source"], uc.SOURCE_ENDPOINT)
        self.assertNotIn("lastError", saved["usage"])

    def test_v2_autonomy_keeps_limit_and_other_keys(self):
        proj = self.project("beta", {"schemaVersion": 2, "limit": {"stopAtPercent": 70}, "note": "kept"})
        uc.sync_once(self.config_with([proj]))
        saved = self.autonomy_of(proj)
        self.assertEqual(saved["limit"], {"stopAtPercent": 70})
        self.assertEqual(saved["note"], "kept")
        self.assertEqual(saved["usage"]["fiveHourPercent"], 17)

    def test_mirror_disabled_leaves_project_file_alone(self):
        proj = self.project("gamma", {"limit": {"stopAtPercent": 65}})
        path = os.path.join(proj["path"], "docs", "autonomy.json")
        before = read_text(path)
        result = uc.sync_once(self.config_with([proj], mirror=False))
        self.assertEqual(result["mirrors"], [])
        self.assertEqual(read_text(path), before)

    def test_missing_autonomy_is_skipped_not_created(self):
        proj = self.project("delta")
        result = uc.sync_once(self.config_with([proj]))
        self.assertEqual(result["mirrors"][0]["status"], "skipped")
        self.assertFalse(os.path.exists(os.path.join(proj["path"], "docs", "autonomy.json")))

    def test_one_failing_project_does_not_stop_the_others(self):
        bad = self.project("epsilon", {"schemaVersion": 3, "limit": {}})
        good = self.project("zeta", {"limit": {"stopAtPercent": 65}})
        result = uc.sync_once(self.config_with([bad, good]))
        statuses = {m["project"]: m["status"] for m in result["mirrors"]}
        self.assertEqual(statuses, {"epsilon": "failed", "zeta": "ok"})
        self.assertEqual(self.autonomy_of(bad)["schemaVersion"], 3)
        self.assertEqual(self.autonomy_of(good)["usage"]["weeklyPercent"], 62.4)


class PushTests(UsageCase):
    def test_push_stores_rate_limits_and_mirrors(self):
        proj = self.project("eta", {"limit": {"stopAtPercent": 65}})
        text = json.dumps({"rateLimits": [{"kind": "seven_day", "percentUsed": 61,
                                           "resetsAt": SEVEN_DAY_RESET_Z}]})
        result = uc.push(text, self.config_with([proj]))
        self.assertEqual(result["usage"]["weeklyPercent"], 61)
        self.assertEqual(result["usage"]["weeklyResetsAt"], SEVEN_DAY_RESET_Z)
        self.assertEqual(result["usage"]["source"], uc.SOURCE_PUSH)
        self.assertIsNone(result["usage"]["fiveHourPercent"])
        self.assertEqual(self.autonomy_of(proj)["usage"]["weeklyPercent"], 61)
        self.assertEqual(self.autonomy_of(proj)["limit"], {"stopAtPercent": 65})

    def test_partial_push_keeps_the_other_window(self):
        uc.push(json.dumps({"rateLimits": [{"kind": "five_hour", "percentUsed": 20}]}), self.config_with())
        result = uc.push(json.dumps({"rateLimits": [{"kind": "seven_day", "percentUsed": 33.33}]}),
                         self.config_with())
        self.assertEqual(result["usage"]["fiveHourPercent"], 20)
        self.assertEqual(result["usage"]["weeklyPercent"], 33.3)

    def test_bad_push_input_is_rejected_with_usage_exit(self):
        cases = {
            "not json": "{",
            "no list": json.dumps({"rateLimits": "x"}),
            "out of range": json.dumps({"rateLimits": [{"kind": "seven_day", "percentUsed": 150}]}),
            "not a number": json.dumps({"rateLimits": [{"kind": "seven_day", "percentUsed": "lots"}]}),
            "no known window": json.dumps({"rateLimits": [{"kind": "monthly", "percentUsed": 5}]}),
        }
        for label, text in cases.items():
            with self.subTest(label), self.assertRaises(RoadmapError) as cm:
                uc.push(text, self.config_with())
            self.assertEqual(cm.exception.exit, 2)
            self.assertEqual(cm.exception.code, "invalid_input")
        self.assertFalse(os.path.exists(self.store_path()))


class LoopTests(UsageCase):
    def run_with(self, outcomes):
        """Run the loop: each sync call pops an outcome ('ok' or 'fail'); the wait stops it after the outcomes end."""
        delays = []
        calls = iter(outcomes)

        def sync():
            if next(calls) == "fail":
                raise uc.UsageError("usage endpoint answered HTTP 503")

        def wait(seconds):
            delays.append(seconds)
            return len(delays) > len(outcomes)

        with self.assertLogs("roadmap", "WARNING") as logs:
            uc.run_loop(threading.Event(), self.config_with(), sync=sync, wait=wait)
        return delays, logs.output

    def test_backoff_schedule_after_three_failures(self):
        delays, logs = self.run_with(["fail"] * 5)
        self.assertEqual(delays, [120, 120, 120, 600, 600, 600])
        self.assertEqual(len(logs), 5)

    def test_success_resets_the_backoff(self):
        delays, _ = self.run_with(["fail", "fail", "fail", "ok", "fail"])
        self.assertEqual(delays, [120, 120, 120, 600, 120, 120])

    def test_interval_setting_is_used_and_never_below_the_minimum(self):
        self.assertEqual(uc.usage_wait_s(0, 300), 300)
        self.assertEqual(uc.usage_wait_s(3, 300), 600)
        self.assertEqual(uc._interval(self.config_with(interval=1)), uc.MIN_INTERVAL_S)

    def test_stop_event_set_means_no_sync(self):
        stop = threading.Event()
        stop.set()
        calls = []
        uc.run_loop(stop, self.config_with(), sync=lambda: calls.append(1))
        self.assertEqual(calls, [])

    def test_loop_failures_are_logged_without_the_token(self):
        def leaky_keychain():
            raise RuntimeError("boom " + FAKE_TOKEN)

        waits = []

        def wait(seconds):
            waits.append(seconds)
            return len(waits) > 2

        with mock.patch.object(uc, "read_keychain_token", side_effect=leaky_keychain):
            with self.assertLogs("roadmap", "WARNING") as logs:
                uc.run_loop(threading.Event(), self.config_with(), wait=wait)
        self.assertEqual(len(logs.output), 2)
        self.assertIn("unexpected failure (RuntimeError)", logs.output[0])
        self.assertNotIn(FAKE_TOKEN, "\n".join(logs.output))


class ConcurrencyTests(UsageCase):
    def test_concurrent_syncs_write_one_at_a_time(self):
        real_write = schema.write_data
        state = {"inside": 0, "overlap": 0}
        guard = threading.Lock()

        def slow_write(kind, path, data):
            with guard:
                state["inside"] += 1
                if state["inside"] > 1:
                    state["overlap"] += 1
            time.sleep(0.02)
            real_write(kind, path, data)
            with guard:
                state["inside"] -= 1

        errors = []

        def worker():
            try:
                uc.sync_once(self.config_with())
            except Exception as exc:  # collected for the assertion below
                errors.append(exc)

        with mock.patch.object(uc.schema, "write_data", side_effect=slow_write):
            threads = [threading.Thread(target=worker) for _ in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(30)
        self.assertEqual(errors, [])
        self.assertEqual(state["overlap"], 0)
        stored = json.loads(read_text(self.store_path()))
        self.assertEqual(stored["weeklyPercent"], 62.4)


class TokenHygieneTests(UsageCase):
    def test_token_never_reaches_stdout_stderr_or_the_store(self):
        def leaky_keychain():
            raise RuntimeError("boom " + FAKE_TOKEN)

        with mock.patch.object(uc, "read_keychain_token", side_effect=leaky_keychain):
            code, out, err = run_cli(["usage", "sync", "--json"])
        self.assertEqual(code, 6)
        body = json.loads(out)
        self.assertEqual(body["error"]["code"], "external")
        self.assertEqual(body["error"]["message"], "could not read usage: unexpected failure (RuntimeError)")
        self.assertNotIn(FAKE_TOKEN, out + err)
        self.assertNotIn(FAKE_TOKEN, read_text(self.store_path()) if os.path.exists(
            self.store_path()) else "")

    def test_successful_sync_output_has_no_token(self):
        code, out, err = run_cli(["usage", "sync", "--json"])
        self.assertEqual(code, 0)
        self.assertNotIn(FAKE_TOKEN, out + err)
        self.assertEqual(self.token_reads, 1)


class CliTests(UsageCase):
    def test_push_then_show_json(self):
        code, out, _ = run_cli(["usage", "push", "--json"],
                               '{"rateLimits":[{"kind":"seven_day","percentUsed":61,'
                               '"resetsAt":"' + SEVEN_DAY_RESET_Z + '"}]}')
        self.assertEqual(code, 0)
        self.assertIs(json.loads(out)["ok"], True)
        code, out, _ = run_cli(["usage", "show", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["data"]["usage"]["weeklyPercent"], 61)

    def test_push_bad_input_exit_2_envelope(self):
        code, out, _ = run_cli(["usage", "push", "--json"], "nope")
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out)["error"]["code"], "invalid_input")

    def test_show_plain_text(self):
        run_cli(["usage", "push"], '{"rateLimits":[{"kind":"seven_day","percentUsed":61}]}')
        code, out, _ = run_cli(["usage", "show"])
        self.assertEqual(code, 0)
        self.assertIn("week 61%", out)

    def test_sync_failure_exit_6(self):
        with mock.patch.object(uc, "http_fetch", side_effect=uc.UsageError("usage endpoint not reachable")):
            code, out, _ = run_cli(["usage", "sync", "--json"])
        self.assertEqual(code, 6)
        self.assertIn("could not read usage: usage endpoint not reachable", json.loads(out)["error"]["message"])


if __name__ == "__main__":
    unittest.main()
