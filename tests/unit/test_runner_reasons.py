"""A4: runners take a task id and report failure reasons. Service tests use a temp data folder; the shell runners run
against a stub project folder (stub bin/roadmap, stub review tool, stub opencode on PATH). No real cursor-agent or
opencode runs, and nothing touches the real home or port 8780."""

import datetime
import os
import shutil
import stat
import subprocess
import tempfile
import unittest

from roadmap.services import jobs
from tests.unit.test_cmd_support import CmdCase
from tests.unit.test_project_support import REPO

NOW = datetime.datetime(2026, 10, 15, 12, 0, 0, tzinfo=datetime.timezone.utc)
RUNNER = os.path.join(REPO, "tools", "cursor-job.sh")
OC_RUNNER = os.path.join(REPO, "tools", "oc-job.sh")

STUB_ROADMAP = """#!/bin/bash
echo "$*" >> "$ROOT_STUB/calls.log"
if [ "$1" = job ] && [ "$2" = start ]; then echo j7; fi
"""

STUB_REVIEW = """#!/bin/bash
# $1 outfile, $2 prompt. A prompt containing FAIL errors out on stderr.
if [ "$2" = FAIL ]; then echo "Error: Insufficient account funds" >&2; exit 1; fi
echo "findings" > "$1"
"""

STUB_OPENCODE = """#!/bin/bash
echo "$*" >> "$ROOT_STUB/opencode.log"
echo "answer"
"""


def _executable(path, text):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


class ReasonServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def _running(self, model="cursor"):
        return jobs.start_job(self.data, "review", model, environ={})["id"]

    def test_first_error_line_is_first_nonblank_line_cut_to_80(self):
        text = "\n  \nFirst error line " + "x" * 200 + "\nsecond"
        self.assertEqual(jobs.first_error_line(text), ("First error line " + "x" * 200)[:80])
        self.assertEqual(len(jobs.first_error_line(text)), 80)
        self.assertEqual(jobs.first_error_line("  \n "), "")

    def test_fail_stores_the_reason(self):
        job_id = self._running("opencode")
        job = jobs.finish_job(self.data, job_id, "failed", reason="Something odd\nmore")
        self.assertEqual(job["reason"], "Something odd")
        self.assertEqual(jobs.list_jobs(self.data)[0]["reason"], "Something odd")

    def test_unknown_reason_does_not_block_the_engine(self):
        job_id = self._running("cursor")
        jobs.finish_job(self.data, job_id, "failed", reason="model not found")
        self.assertEqual(jobs.unavailable_engines(self.data, NOW), {})
        self.assertEqual(jobs.engines_line(self.data, NOW), "")

    def test_known_patterns_block_the_engine_for_six_hours(self):
        for reason in ("Insufficient account funds", "HTTP 403 forbidden", "Cannot connect to host"):
            job_id = self._running("cursor")
            jobs.finish_job(self.data, job_id, "failed", reason=reason)
            blocked = jobs.unavailable_engines(self.data, NOW)
            self.assertEqual(list(blocked), ["cursor"], reason)
            self.assertEqual(blocked["cursor"]["reason"], reason)
        # the block is stamped with the real clock, so check the six-hour edge against that clock
        base = datetime.datetime.now(datetime.timezone.utc)
        self.assertTrue(jobs.unavailable_engines(self.data, base + datetime.timedelta(hours=5, minutes=59)))
        self.assertEqual(jobs.unavailable_engines(self.data, base + datetime.timedelta(hours=6, minutes=1)), {})

    def test_block_is_per_engine(self):
        job_id = self._running("opencode")
        jobs.finish_job(self.data, job_id, "failed", reason="403 Forbidden")
        self.assertEqual(list(jobs.unavailable_engines(self.data, NOW)), ["opencode"])
        self.assertEqual(jobs.unavailable_engines(self.data, NOW).get("cursor"), None)

    def test_engines_line_is_one_line_with_time_and_reason(self):
        job_id = self._running("cursor")
        jobs.finish_job(self.data, job_id, "failed", reason="Insufficient account funds")
        line = jobs.engines_line(self.data, NOW)
        self.assertNotIn("\n", line)
        self.assertTrue(line.startswith("engines unavailable: cursor until "), line)
        self.assertIn("(Insufficient account funds)", line)

    def test_corrupt_state_file_reads_as_no_blocks(self):
        with open(os.path.join(self.data, jobs.ENGINES_FILE), "w", encoding="utf-8") as fh:
            fh.write("{not json")
        self.assertEqual(jobs.unavailable_engines(self.data, NOW), {})


class ReasonCliTests(CmdCase):
    def test_job_fail_reason_is_stored_and_listed(self):
        code, out, _ = self.cli(["job", "start", "review", "cursor"])
        self.assertEqual(code, 0)
        job_id = out.strip()
        code, _, err = self.cli(["job", "fail", job_id, "--reason", "Insufficient account funds: top up\nmore"])
        self.assertEqual(code, 0, err)
        code, out, _ = self.cli(["job", "list"])
        self.assertEqual(code, 0)
        self.assertIn("engines unavailable: cursor until ", out)
        self.assertEqual(out.count("engines unavailable"), 1)


class RunnerScriptTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.bin = os.path.join(self.root, "stubs")
        os.makedirs(os.path.join(self.root, "bin"))
        os.makedirs(os.path.join(self.root, "tools"))
        os.makedirs(self.bin)
        _executable(os.path.join(self.root, "bin", "roadmap"), STUB_ROADMAP)
        _executable(os.path.join(self.root, "tools", "cursor-review2.sh"), STUB_REVIEW)
        _executable(os.path.join(self.bin, "opencode"), STUB_OPENCODE)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _env(self):
        env = dict(os.environ)
        env["ROOT_STUB"] = self.root
        env["ROADMAP_ROOT"] = self.root
        env["PATH"] = self.bin + os.pathsep + env.get("PATH", "")
        env.pop("OC_MODEL", None)
        return env

    def _run(self, script, args, env=None):
        return subprocess.run(["bash", script] + args, cwd=self.root, env=env or self._env(),
                              capture_output=True, text=True, timeout=60)

    def _calls(self):
        path = os.path.join(self.root, "calls.log")
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as fh:
            return [line.strip() for line in fh if line.strip()]

    def test_cursor_new_form_binds_the_given_task(self):
        res = self._run(RUNNER, ["R7.44", "review x", "high", os.path.join(self.root, "out.txt"), "ok prompt"])
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("job start cursor: review x cursor R7.44 --effort high", self._calls()[0])
        self.assertIn("job done j7", self._calls()[-1])
        self.assertNotIn("R7.31", " ".join(self._calls()))

    def test_cursor_old_form_still_binds_r7_31(self):
        res = self._run(RUNNER, ["review x", "medium", os.path.join(self.root, "out.txt"), "ok prompt"])
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("job start cursor: review x cursor R7.31 --effort medium", self._calls()[0])

    def test_cursor_failure_sends_the_first_error_line_as_reason(self):
        res = self._run(RUNNER, ["R7.44", "review x", "high", os.path.join(self.root, "out.txt"), "FAIL"])
        self.assertEqual(res.returncode, 1)
        fail = [c for c in self._calls() if c.startswith("job fail j7")]
        self.assertEqual(len(fail), 1)
        self.assertIn("--reason Error: Insufficient account funds", fail[0])

    def test_oc_runner_uses_opencode_with_default_model_and_task(self):
        out = os.path.join(self.root, "oc.txt")
        res = self._run(OC_RUNNER, ["R7.44", "oc review", "low", out, "hello"])
        self.assertEqual(res.returncode, 0, res.stderr)
        with open(os.path.join(self.root, "opencode.log"), encoding="utf-8") as fh:
            self.assertEqual(fh.read().strip(), "run -m opencode/big-pickle hello")
        self.assertIn("job start opencode: oc review opencode R7.44 --effort low", self._calls()[0])
        self.assertIn("job done j7", self._calls()[-1])

    def test_oc_runner_honours_oc_model(self):
        env = self._env()
        env["OC_MODEL"] = "opencode/other"
        res = self._run(OC_RUNNER, ["R7.44", "oc review", "low", os.path.join(self.root, "oc.txt"), "hi"], env=env)
        self.assertEqual(res.returncode, 0, res.stderr)
        with open(os.path.join(self.root, "opencode.log"), encoding="utf-8") as fh:
            self.assertIn("-m opencode/other", fh.read())

    def test_oc_runner_needs_five_arguments(self):
        res = self._run(OC_RUNNER, ["R7.44", "only two"])
        self.assertEqual(res.returncode, 2)


if __name__ == "__main__":
    unittest.main()
