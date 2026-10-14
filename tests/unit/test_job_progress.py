"""Tests for job progress (WP62): live tokens on a running job, and job done --tokens counting only the rest.

The budget must never count the same thousands twice: progress adds what is new, and done adds its total minus
the progress already counted. Runs in a temp ROADMAP_HOME with the fixture project (through the CLI)."""

import datetime
import json

from roadmap.core import parsers
from roadmap.services import budget, jobs
from tests.unit.test_jobs_support import FixtureCase, run_cli


class ProgressCase(FixtureCase):
    def start(self, task="P0.8"):
        code, out, err = run_cli(["job", "start", "x", "haiku", task])
        self.assertEqual(code, 0, err)
        return out.strip()

    def progress(self, value, job="j1"):
        return run_cli(["job", "progress", job, "--tokens", str(value), "--json"])

    def spent(self):
        return budget.get(self.docs)["spent"]


class ProgressTests(ProgressCase):
    def test_progress_updates_snapshot_fields_of_a_running_job(self):
        self.start()
        code, out, err = self.progress(12.5)
        self.assertEqual(code, 0, err)
        data = json.loads(out)["data"]
        self.assertEqual((data["status"], data["tokensK"], data["progressK"]), ("running", 12.5, 12.5))
        stored = self.read_jobs()[0]
        self.assertEqual((stored["tokensK"], stored["progressK"]), (12.5, 12.5))
        with open(self.jobs_file(), encoding="utf-8") as fh:
            job = parsers.parse_jobs(fh.read(), datetime.datetime.now(datetime.timezone.utc))[0][0]
        self.assertEqual(job["tokensK"], 12.5)

    def test_plain_output_names_the_reading(self):
        self.start()
        code, out, err = run_cli(["job", "progress", "j1", "--tokens", "7"])
        self.assertEqual((code, out, err), (0, "j1 progress 7.0k\n", ""))

    def test_progress_is_counted_in_the_budget_when_it_moves(self):
        self.start()
        self.progress(10)
        self.assertEqual(self.spent(), {"P0.8": {"haiku": 10.0}})

    def test_same_reading_again_adds_nothing(self):
        self.start()
        self.progress(10)
        code, out, err = self.progress(10)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.spent(), {"P0.8": {"haiku": 10.0}})

    def test_progress_on_a_finished_job_is_conflict(self):
        self.start()
        run_cli(["job", "done", "j1"])
        code, out, _ = self.progress(5)
        self.assertEqual(code, 4)
        self.assertEqual(json.loads(out)["error"]["code"], "conflict")
        self.assertEqual(self.spent(), {})

    def test_progress_unknown_job_is_not_found(self):
        code, out, _ = self.progress(5, job="j9")
        self.assertEqual(code, 3)
        self.assertEqual(json.loads(out)["error"]["code"], "not_found")

    def test_progress_cannot_go_down(self):
        self.start()
        self.progress(10)
        code, out, _ = self.progress(4)
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out)["error"]["code"], "usage")
        self.assertEqual(self.read_jobs()[0]["progressK"], 10.0)
        self.assertEqual(self.spent(), {"P0.8": {"haiku": 10.0}})

    def test_bad_tokens_are_usage_errors(self):
        self.start()
        for value in ("abc", "-1", "nan", "inf"):
            with self.subTest(value=value):
                code, _, _ = run_cli(["job", "progress", "j1", "--tokens", value, "--json"])
                self.assertEqual(code, 2)
        self.assertNotIn("progressK", self.read_jobs()[0])

    def test_tokens_flag_is_required(self):
        self.start()
        code, _, err = run_cli(["job", "progress", "j1"])
        self.assertEqual(code, 2)
        self.assertIn("--tokens", err)

    def test_progress_without_a_task_is_counted_under_the_dash(self):
        self.start(task=None)
        self.progress(3)
        self.assertEqual(self.spent(), {"-": {"haiku": 3.0}})


class NoDoubleCountTests(ProgressCase):
    def test_done_adds_only_the_part_not_yet_counted(self):
        self.start()
        self.progress(10)
        code, out, err = run_cli(["job", "done", "j1", "--tokens", "25", "--json"])
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["data"]["tokensK"], 25.0)
        self.assertEqual(self.spent(), {"P0.8": {"haiku": 25.0}})

    def test_many_readings_then_done_still_total_the_final_value(self):
        self.start()
        for value in (4, 9, 12):
            self.progress(value)
        self.assertEqual(self.spent(), {"P0.8": {"haiku": 12.0}})
        run_cli(["job", "done", "j1", "--tokens", "12"])
        self.assertEqual(self.spent(), {"P0.8": {"haiku": 12.0}})

    def test_done_without_tokens_keeps_the_counted_progress(self):
        self.start()
        self.progress(8)
        code, out, err = run_cli(["job", "done", "j1"])
        self.assertEqual((code, out), (0, "j1 done\n"), err)
        self.assertEqual(self.spent(), {"P0.8": {"haiku": 8.0}})

    def test_done_total_equal_to_progress_adds_nothing_more(self):
        self.start()
        self.progress(6)
        run_cli(["job", "done", "j1", "--tokens", "6"])
        self.assertEqual(self.spent(), {"P0.8": {"haiku": 6.0}})

    def test_done_total_below_progress_is_refused_and_job_stays_running(self):
        self.start()
        self.progress(10)
        code, out, _ = run_cli(["job", "done", "j1", "--tokens", "5", "--json"])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out)["error"]["code"], "usage")
        stored = self.read_jobs()[0]
        self.assertEqual((stored["status"], stored["progressK"]), ("running", 10.0))
        self.assertEqual(self.spent(), {"P0.8": {"haiku": 10.0}})

    def test_done_without_progress_counts_the_full_total_as_before(self):
        self.start()
        run_cli(["job", "done", "j1", "--tokens", "5"])
        self.assertEqual(self.spent(), {"P0.8": {"haiku": 5.0}})

    def test_finishing_twice_does_not_add_again(self):
        self.start()
        self.progress(10)
        run_cli(["job", "done", "j1", "--tokens", "12"])
        code, _, _ = run_cli(["job", "done", "j1", "--tokens", "12"])
        self.assertEqual(code, 4)
        self.assertEqual(self.spent(), {"P0.8": {"haiku": 12.0}})

    def test_remainder_helper(self):
        self.assertEqual(jobs.budget_remainder({"progressK": 10}, 25), 15.0)
        self.assertEqual(jobs.budget_remainder({}, 25), 25.0)
        self.assertEqual(jobs.budget_remainder({"progressK": 30}, 25), 0.0)
