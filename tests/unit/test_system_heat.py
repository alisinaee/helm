"""Tests for A2: heat per system component. A real git fixture repo is built in a temp folder (git argv lists only).

Covers: the 30-day window, commits mapped to components by glob (once per component), task ids in subjects linking
to running jobs, open Work items and open bug issues, closed items ignored, the sha cache, a folder outside git
(zero heat plus a warning), and that git is only ever called with an argument list.
"""

import datetime
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from roadmap.core import workstatus
from roadmap.errors import RoadmapError
from roadmap.services import git, system, systemheat

GIT_ENV_BASE = {"PATH": os.environ.get("PATH", ""), "GIT_CONFIG_NOSYSTEM": "1"}
COMPONENTS = [
    {"id": "services", "files": ["roadmap/services/**"]},
    {"id": "web", "files": ["web/**"]},
    {"id": "docs", "files": ["docs/**"]},
]


def _git(cwd, args, days_ago=None):
    env = dict(GIT_ENV_BASE, HOME=cwd)
    if days_ago is not None:
        when = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days_ago)
        stamp = when.strftime("%Y-%m-%dT%H:%M:%S +0000")
        env.update(GIT_AUTHOR_DATE=stamp, GIT_COMMITTER_DATE=stamp)
    subprocess.run(["git"] + args, cwd=cwd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   env=env)


def _write(root, rel, text="x = 1\n"):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _commit(root, subject, files, days_ago=None):
    for rel in files:
        _write(root, rel, subject + " " + rel + "\n")
    _git(root, ["add", "-A"])
    _git(root, ["-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", subject],
         days_ago=days_ago)


class HeatFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="sysheat-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = os.path.join(self.tmp, "proj")
        os.makedirs(self.root)
        systemheat._CACHE.clear()
        self.addCleanup(systemheat._CACHE.clear)
        _git(self.root, ["init", "-q"])
        # outside the 30-day window: must not count
        _commit(self.root, "R1.1 old services work", ["roadmap/services/old.py"], days_ago=40)
        # inside the window, task R7.108 touches services and web
        _commit(self.root, "R7.108 fix jobs", ["roadmap/services/jobs.py", "web/js/app.js"], days_ago=2)
        # untagged, touches web and docs
        _commit(self.root, "tidy", ["web/js/app.js", "docs/NOTES.md"])
        # untagged, touches only a file no component matches
        _commit(self.root, "misc", ["README.md"])

    def build(self, **kw):
        return systemheat.build(self.root, COMPONENTS, **kw)


class WindowAndMappingTests(HeatFixture):
    def test_window_glob_mapping_and_summary(self):
        out = self.build()
        heat = out["heat"]
        self.assertEqual(heat["services"]["commits30"], 1)
        self.assertEqual(heat["web"]["commits30"], 2)
        self.assertEqual(heat["docs"]["commits30"], 1)
        self.assertEqual(out["summary"]["commits"], 3)
        self.assertEqual(out["summary"]["untagged"], 2)
        self.assertEqual(out["summary"]["unmatchedFiles"], 1)
        self.assertEqual(out["warnings"], [])
        self.assertEqual(set(heat["web"]), {"commits30", "lastAt", "openWork", "runningJobs", "bugs"})

    def test_last_at_is_utc_iso_of_newest_commit(self):
        heat = self.build()["heat"]
        self.assertRegex(heat["web"]["lastAt"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
        self.assertGreater(heat["web"]["lastAt"], heat["services"]["lastAt"])
        self.assertIsNone(systemheat.build(self.root, [{"id": "nothing", "files": ["zzz/**"]}])["heat"]["nothing"]
                          ["lastAt"])

    def test_components_from_system_load_have_heat(self):
        comps = system.load(self.root)["components"]
        heat = systemheat.build(self.root, comps)["heat"]
        self.assertEqual(set(heat), {c["id"] for c in comps})


class TaskLinkTests(HeatFixture):
    def work(self, status, kind="task", tasks=("R7.108",)):
        return {"id": "W1", "kind": kind, "status": status, "tasks": list(tasks)}

    def test_open_work_counts_closed_does_not(self):
        heat = self.build(work=[self.work("Doing")])["heat"]
        self.assertEqual(heat["services"]["openWork"], 1)
        self.assertEqual(heat["web"]["openWork"], 1)
        self.assertEqual(heat["docs"]["openWork"], 0)
        closed = self.build(work=[self.work(workstatus.DONE)])["heat"]
        self.assertEqual(closed["services"]["openWork"], 0)

    def test_running_jobs_only(self):
        jobs = [{"id": "j1", "status": "running", "task": "R7.108"},
                {"id": "j2", "status": "done", "task": "R7.108"},
                {"id": "j3", "status": "running", "task": "R9.9"}]
        heat = self.build(jobs=jobs)["heat"]
        self.assertEqual(heat["services"]["runningJobs"], 1)
        self.assertEqual(heat["web"]["runningJobs"], 1)
        self.assertEqual(heat["docs"]["runningJobs"], 0)

    def test_bug_issues_and_bug_work_count(self):
        issues = [{"id": "I1", "kind": "bug", "status": "open", "tasks": ["R7.108"]},
                  {"id": "I2", "kind": "risk", "status": "open", "tasks": ["R7.108"]},
                  {"id": "I3", "kind": "bug", "status": "closed", "tasks": ["R7.108"]}]
        work = [self.work("Doing", kind="bug")]
        heat = self.build(issues=issues, work=work)["heat"]
        self.assertEqual(heat["services"]["bugs"], 2)
        self.assertEqual(heat["docs"]["bugs"], 0)


class CacheAndSafetyTests(HeatFixture):
    def test_history_cached_by_sha(self):
        first = systemheat.history(self.root)
        self.assertIs(systemheat.history(self.root), first)
        _commit(self.root, "R7.200 another", ["web/js/b.js"])
        second = systemheat.history(self.root)
        self.assertIsNot(second, first)
        self.assertEqual(len(second["commits"]), len(first["commits"]) + 1)

    def test_git_called_only_with_argument_list(self):
        with mock.patch.object(git, "run", wraps=git.run) as run:
            systemheat.history(self.root, use_cache=False)
        self.assertTrue(run.called)
        args = run.call_args[0][1]
        self.assertIsInstance(args, list)
        self.assertEqual(args[0], "log")
        self.assertIn("--since=30.days", args)
        self.assertIn("--name-only", args)

    def test_folder_outside_git_gives_zero_heat_and_warning(self):
        plain = os.path.join(self.tmp, "plain")
        os.makedirs(os.path.join(plain, "web"))
        _write(plain, "web/a.js")
        out = systemheat.build(plain, COMPONENTS)
        self.assertEqual(out["heat"]["web"]["commits30"], 0)
        self.assertIsNone(out["sha"])
        self.assertTrue(any("git history unavailable" in w for w in out["warnings"]))

    def test_relative_project_path_refused(self):
        with self.assertRaises(RoadmapError):
            systemheat.history("relative/path")


if __name__ == "__main__":
    unittest.main()
