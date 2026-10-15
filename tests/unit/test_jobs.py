"""Tests for the job command and the job registry: ids, finishing, tokens, errors, pruning and concurrency."""

import json
import os
import subprocess
import sys
import unittest

from roadmap.services import jobs
from tests.unit.test_jobs_support import FixtureCase, run_cli
from tests.unit.test_store_support import REPO, mode_of


class JobCommandTests(FixtureCase):
    def test_start_json_envelope_and_file(self):
        code, out, _ = run_cli(["job", "start", "x", "haiku", "P0.8", "--json"])
        self.assertEqual(code, 0)
        body = json.loads(out)
        self.assertIs(body["ok"], True)
        self.assertEqual(body["data"]["id"], "j1")
        self.assertEqual(body["data"]["task"], "P0.8")
        self.assertEqual(body["data"]["status"], "running")
        stored = self.read_jobs()
        self.assertEqual(len(stored), 1)
        with open(self.jobs_file(), encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["schemaVersion"], 1)

    def test_new_jobs_file_is_private(self):
        run_cli(["job", "start", "x", "haiku"])
        self.assertEqual(mode_of(self.jobs_file()), 0o600)

    def test_start_plain_prints_only_the_id(self):
        code, out, err = run_cli(["job", "start", "x", "haiku", "WP4"])
        self.assertEqual((code, out, err), (0, "j1\n", ""))

    def test_start_without_task_has_no_task_key(self):
        run_cli(["job", "start", "no task", "sonnet", "--json"])
        self.assertNotIn("task", self.read_jobs()[0])

    def test_start_unknown_task_is_not_found(self):
        code, out, _ = run_cli(["job", "start", "x", "haiku", "P9.9", "--json"])
        self.assertEqual(code, 3)
        self.assertEqual(json.loads(out)["error"]["code"], "not_found")
        self.assertEqual(self.read_jobs(), [])

    def test_start_records_effort_only_when_given(self):
        run_cli(["job", "start", "x", "opus", "--effort", "xhigh"])
        run_cli(["job", "start", "y", "haiku"])
        first, second = self.read_jobs()
        self.assertEqual(first["effort"], "xhigh")
        self.assertNotIn("effort", second)

    def test_start_records_engine_model_only_when_given(self):
        run_cli(["job", "start", "x", "opencode", "--engine-model", " laguna-s-2.1 "])
        run_cli(["job", "start", "y", "opencode"])
        first, second = self.read_jobs()
        self.assertEqual(first["engine_model"], "laguna-s-2.1")
        self.assertNotIn("engine_model", second)
        self.assertEqual(first["model"], "opencode")

    def test_start_bad_effort_is_usage_error(self):
        code, out, _ = run_cli(["job", "start", "x", "opus", "--effort", "turbo", "--json"])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out)["error"]["code"], "usage")
        self.assertEqual(self.read_jobs(), [])

    def test_start_bad_model_is_usage_error(self):
        code, out, _ = run_cli(["job", "start", "x", "gpt", "--json"])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out)["error"]["code"], "usage")

    def test_start_missing_arguments_is_usage_error(self):
        code, _, err = run_cli(["job", "start"])
        self.assertEqual(code, 2)
        self.assertIn("roadmap:", err)

    def test_start_empty_title_is_usage_error(self):
        code, _, _ = run_cli(["job", "start", "   ", "haiku"])
        self.assertEqual(code, 2)

    def test_unknown_project_is_not_found(self):
        code, out, _ = run_cli(["job", "list", "--project", "nope", "--json"])
        self.assertEqual(code, 3)
        self.assertEqual(json.loads(out)["error"]["code"], "not_found")

    def test_unknown_env_project_is_not_found(self):
        self._set_env("ROADMAP_PROJECT", "nope")
        code, _, _ = run_cli(["job", "list"])
        self.assertEqual(code, 3)

    def test_cwd_inside_project_resolves_without_env(self):
        self._set_env("ROADMAP_PROJECT", None)
        saved = os.getcwd()
        os.chdir(os.path.join(self.project, "docs"))
        self.addCleanup(os.chdir, saved)
        code, out, _ = run_cli(["job", "start", "from cwd", "opus", "--json"])
        self.assertEqual(code, 0, out)
        self.assertEqual(len(self.read_jobs()), 1)

    def test_outside_any_project_is_not_found(self):
        self._set_env("ROADMAP_PROJECT", None)
        saved = os.getcwd()
        os.chdir(self.tmp)
        self.addCleanup(os.chdir, saved)
        code, _, _ = run_cli(["job", "list"])
        self.assertEqual(code, 3)

    def test_done_records_tokens_and_note(self):
        run_cli(["job", "start", "x", "haiku", "P0.8"])
        code, out, _ = run_cli(["job", "done", "j1", "n", "--tokens", "5", "--json"])
        self.assertEqual(code, 0)
        data = json.loads(out)["data"]
        self.assertEqual(data["status"], "done")
        self.assertEqual(data["tokensK"], 5.0)
        self.assertEqual(data["note"], "n")
        self.assertIn("ended", data)
        stored = self.read_jobs()[0]
        self.assertEqual(stored["status"], "done")
        self.assertEqual(stored["tokensK"], 5.0)

    def test_fail_marks_failed_and_plain_output(self):
        run_cli(["job", "start", "x", "haiku"])
        code, out, _ = run_cli(["job", "fail", "j1", "boom"])
        self.assertEqual((code, out), (0, "j1 failed\n"))
        self.assertEqual(self.read_jobs()[0]["status"], "failed")

    def test_finishing_a_finished_job_is_conflict_and_changes_nothing(self):
        run_cli(["job", "start", "x", "haiku"])
        run_cli(["job", "done", "j1", "first", "--tokens", "3"])
        code, out, _ = run_cli(["job", "done", "j1", "second", "--tokens", "9", "--json"])
        self.assertEqual(code, 4)
        self.assertEqual(json.loads(out)["error"]["code"], "conflict")
        stored = self.read_jobs()[0]
        self.assertEqual(stored["tokensK"], 3.0)
        self.assertEqual(stored["note"], "first")

    def test_finish_unknown_job_is_not_found(self):
        code, out, _ = run_cli(["job", "done", "j99", "--json"])
        self.assertEqual(code, 3)
        self.assertEqual(json.loads(out)["error"]["code"], "not_found")

    def test_bad_tokens_are_usage_errors(self):
        run_cli(["job", "start", "x", "haiku"])
        for value in ("abc", "-1", "nan", "inf"):
            code, _, _ = run_cli(["job", "done", "j1", "--tokens", value])
            self.assertEqual(code, 2, value)
        self.assertEqual(self.read_jobs()[0]["status"], "running")

    def test_list_json_and_plain(self):
        run_cli(["job", "start", "first", "haiku", "P0.8"])
        run_cli(["job", "start", "second", "opus"])
        code, out, _ = run_cli(["job", "list", "--json"])
        self.assertEqual(code, 0)
        rows = json.loads(out)["data"]["jobs"]
        self.assertEqual([r["id"] for r in rows], ["j1", "j2"])
        code, out, _ = run_cli(["job", "list"])
        self.assertIn("[P0.8]", out)
        self.assertIn("second", out)

    def test_list_empty_plain(self):
        code, out, _ = run_cli(["job", "list"])
        self.assertEqual((code, out), (0, "no jobs\n"))

    def test_prune_keeps_running_and_newest_two_hundred_finished(self):
        rows = []
        for n in range(1, 206):
            status = "running" if n in (1, 2) else "done"
            rows.append({"id": "j%d" % n, "title": "t", "model": "haiku", "status": status,
                         "started": "2026-10-01T00:00:00+00:00",
                         "ended": "2026-10-01T%02d:%02d:00+00:00" % (n // 60, n % 60) if status != "running" else None})
        self.write_jobs({"schemaVersion": 1, "jobs": rows})
        code, out, _ = run_cli(["job", "prune", "--json"])
        self.assertEqual(code, 0)
        data = json.loads(out)["data"]
        self.assertEqual(data, {"removed": 3, "kept": 202})
        kept = {j["id"] for j in self.read_jobs()}
        self.assertIn("j1", kept)
        self.assertIn("j2", kept)
        self.assertNotIn("j3", kept)  # the three oldest finished jobs go
        self.assertIn("j205", kept)

    def test_corrupt_file_stops_with_invalid_data_and_is_left_alone(self):
        with open(self.jobs_file(), "w", encoding="utf-8") as fh:
            fh.write("{not json")
        for argv in (["job", "list", "--json"], ["job", "start", "x", "haiku", "--json"],
                     ["job", "done", "j1", "--json"], ["job", "prune", "--json"]):
            code, out, _ = run_cli(argv)
            self.assertEqual(code, 5, argv)
            self.assertEqual(json.loads(out)["error"]["code"], "invalid_data")
        with open(self.jobs_file(), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "{not json")

    def test_jobs_without_a_list_is_invalid_data(self):
        self.write_jobs({"schemaVersion": 1})
        code, _, _ = run_cli(["job", "list"])
        self.assertEqual(code, 5)

    def test_newer_schema_is_refused_and_left_alone(self):
        self.write_jobs({"schemaVersion": 2, "jobs": []})
        code, out, _ = run_cli(["job", "start", "x", "haiku", "--json"])
        self.assertEqual(code, 5)
        self.assertEqual(json.loads(out)["error"]["code"], "newer_schema")
        with open(self.jobs_file(), encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["schemaVersion"], 2)

    def test_concurrent_starts_from_two_processes_get_distinct_ids(self):
        env = dict(os.environ, ROADMAP_HOME=os.environ["ROADMAP_HOME"], ROADMAP_PROJECT="demo",
                   PYTHONPATH=REPO)
        procs = [subprocess.Popen([sys.executable, "-m", "roadmap", "job", "start", "p%d" % n, "haiku",
                                   "--json"], cwd=REPO, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  text=True) for n in range(4)]
        ids = []
        for proc in procs:
            out, err = proc.communicate(timeout=60)
            self.assertEqual(proc.returncode, 0, err)
            ids.append(json.loads(out)["data"]["id"])
        self.assertEqual(sorted(ids), ["j1", "j2", "j3", "j4"])
        self.assertEqual(len(self.read_jobs()), 4)


class JobRegistryTests(FixtureCase):
    def test_next_id_follows_the_highest_existing_id(self):
        self.write_jobs({"jobs": [{"id": "j7", "status": "done", "title": "old", "model": "haiku"}]})
        job = jobs.start_job(self.docs, "new", "opus")
        self.assertEqual(job["id"], "j8")

    def test_data_dir_of_joins_path_and_data_dir(self):
        project = {"id": "demo", "path": self.project, "dataDir": "docs"}
        self.assertEqual(jobs.data_dir_of(project), self.docs)


if __name__ == "__main__":
    unittest.main()
