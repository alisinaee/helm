"""A3 (R7.69): the head's close guard, checked before a head write in the CLI (commands/head.py _guard_head_write).
`head set Hn status=done` needs a note with a real ref (a commit sha that exists, an existing job id, or answer: text
of 20+ characters that does not repeat a head close of the last hour); a fourth head close inside one minute is
refused ("use head next"); a head bind that leaves an entry on umbrella tasks alone is refused, head t included. The
person's writes are not guarded. Temp data folder and temp git repo; no service is started."""

import argparse
import os
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from roadmap.commands import head as chead
from roadmap.errors import RoadmapError
from roadmap.services import gitops
from roadmap.services import head as store

T0 = datetime(2026, 10, 15, 9, 0, 0, tzinfo=timezone.utc)
ANSWER = "answer: the bind guard now refuses umbrella only binds"


def _git(repo, *args):
    return subprocess.run(["git", "-C", repo, "-c", "user.name=t", "-c", "user.email=t@example.com"] + list(args),
                          check=True, capture_output=True, text=True).stdout.strip()


class CloseGuard(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = os.path.join(self.tmp.name, "data")
        self.repo = os.path.join(self.tmp.name, "repo")
        os.makedirs(self.data)
        os.makedirs(self.repo)
        _git(self.repo, "init", "-q")
        _git(self.repo, "commit", "-q", "--allow-empty", "-m", "R7.69 guard")
        self.sha = _git(self.repo, "rev-parse", "HEAD")
        for patcher in (
                mock.patch.dict(os.environ, {"ROADMAP_HOME": self.tmp.name}),
                mock.patch.object(gitops, "_root", return_value=self.repo),
                mock.patch.object(store.jobs, "list_jobs", return_value=[{"id": "j701"}]),
                mock.patch.object(chead.tasks, "resolve", return_value=("roadmap", self.data)),
                mock.patch.object(chead.agentguard, "person_context", return_value=False)):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.args = argparse.Namespace(project=None)

    def ask(self, n=0):
        return store.capture(self.data, "ask %d" % n, kind="ask")["id"]

    def close(self, eid, note, at):
        """The head's set status=done: the CLI guard, then the write it allows."""
        chead._guard_head_write(self.args, eid, status="done", note=note, now=at)
        return store.update(self.data, eid, by="head", sets={"status": "done"}, note=note, now=at)

    def test_generic_note_refused(self):
        with self.assertRaises(RoadmapError) as ctx:
            self.close(self.ask(), "ok done", T0)
        self.assertIn("real ref", ctx.exception.message)

    def test_real_sha_accepted(self):
        eid = self.ask()
        self.close(eid, "shipped in " + self.sha, T0)
        self.assertEqual(store.rows(self.data)[0]["status"], "done")

    def test_unknown_sha_refused(self):
        with self.assertRaises(RoadmapError):
            self.close(self.ask(), "shipped in deadbeefdeadbeefdeadbeefdeadbeefdeadbeef", T0)

    def test_existing_job_id_accepted_and_missing_refused(self):
        self.close(self.ask(1), "done by job j701", T0)
        with self.assertRaises(RoadmapError):
            self.close(self.ask(2), "done by job j999", T0 + timedelta(hours=1))

    def test_answer_needs_twenty_characters(self):
        with self.assertRaises(RoadmapError):
            self.close(self.ask(), "answer: too short", T0)

    def test_repeated_answer_refused_within_hour(self):
        first, second = self.ask(1), self.ask(2)
        self.close(first, ANSWER, T0)
        with self.assertRaises(RoadmapError) as ctx:
            self.close(second, ANSWER, T0 + timedelta(minutes=10))
        self.assertIn("repeats", ctx.exception.message)
        self.close(second, ANSWER, T0 + timedelta(hours=2))  # the hour has passed

    def test_fourth_close_in_a_minute_refused(self):
        ids = [self.ask(n) for n in range(4)]
        for offset, eid in enumerate(ids[:3]):
            self.close(eid, "done by job j701 %d" % offset, T0 + timedelta(seconds=offset))
        with self.assertRaises(RoadmapError) as ctx:
            self.close(ids[3], "done by job j701 last", T0 + timedelta(seconds=3))
        self.assertIn("use head next", ctx.exception.message)
        self.close(ids[3], "done by job j701 later", T0 + timedelta(seconds=61))

    def test_person_closes_are_not_counted_or_guarded(self):
        ids = [self.ask(n) for n in range(5)]
        for eid in ids[:4]:
            store.update(self.data, eid, by="person", sets={"status": "done"}, now=T0)
        self.close(ids[4], "shipped in " + self.sha, T0)

    def test_person_write_skips_the_guard(self):
        with mock.patch.object(chead.agentguard, "person_context", return_value=True):
            chead._guard_head_write(self.args, self.ask(), status="done", note=None, now=T0)

    def test_umbrella_only_bind_refused(self):
        eid = self.ask()
        with self.assertRaises(RoadmapError) as ctx:
            chead._guard_head_write(self.args, eid, adds=["task:R7.31"], now=T0)
        self.assertIn("umbrella", ctx.exception.message)

    def test_umbrella_with_real_task_accepted(self):
        eid = self.ask()
        chead._guard_head_write(self.args, eid, adds=["task:R7.31", "task:R7.69"], now=T0)
        store.update(self.data, eid, by="head", links=["+task:R7.31", "+task:R7.69"], now=T0)
        chead._guard_head_write(self.args, eid, adds=["task:R7.69"], now=T0)
        chead._guard_head_write(self.args, eid, removes=["task:R7.31"], now=T0)


if __name__ == "__main__":
    unittest.main()
