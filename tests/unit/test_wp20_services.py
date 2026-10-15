"""WP20 services: caps, archive behaviour, idempotent spend, subtasks (add, toggle, undo), queue, activity, lock and
atomic-write behaviour through the store layer. Every test runs under its own ROADMAP_HOME temp dir."""

import datetime
import json
import os
import unittest
from unittest import mock

from roadmap.errors import EXIT_CONFLICT, EXIT_NOT_FOUND, EXIT_USAGE, RoadmapError
from roadmap.services import activity, budget, comments, issues, queue, questions, tasks
from roadmap.store import atomic, jsonl, lock
from tests.unit.test_store_support import HomeCase

T0 = datetime.datetime(2026, 10, 13, 9, 0, 0, tzinfo=datetime.timezone.utc)


def at(minutes):
    return T0 + datetime.timedelta(minutes=minutes)


class DocsCase(HomeCase):
    def setUp(self):
        super().setUp()
        self.docs = os.path.join(self.make_project("demo"), "docs")
        os.makedirs(self.docs)

    def read_json(self, name):
        with open(os.path.join(self.docs, name), encoding="utf-8") as fh:
            return json.load(fh)

    def read_lines(self, name):
        path = os.path.join(self.docs, name)
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]

    def write_raw(self, name, text):
        with open(os.path.join(self.docs, name), "w", encoding="utf-8") as fh:
            fh.write(text)

    def write_tasks(self, task_list, phases=None):
        doc = {"schemaVersion": 1, "updated": "2026-10-01",
               "phases": phases if phases is not None else [{"id": "P1", "name": "Engine", "status": "todo"}],
               "tasks": task_list}
        atomic.write_json(os.path.join(self.docs, "tasks.json"), doc)


class IssuesTests(DocsCase):
    def test_lazy_file_and_schema_version(self):
        self.assertFalse(os.path.exists(os.path.join(self.docs, "issues.json")))
        issue = issues.open_issue(self.docs, "Login fails", "bug", sev=1, tasks=["P1.2"], now=at(0))
        self.assertEqual(issue["id"], "I1")
        self.assertEqual(self.read_json("issues.json")["schemaVersion"], 1)
        self.assertEqual(issues.list_issues(self.docs)[0]["title"], "Login fails")

    def test_bad_input_is_refused_and_nothing_is_written(self):
        with self.assertRaises(RoadmapError) as ctx:
            issues.open_issue(self.docs, "", "bug")
        self.assertEqual(ctx.exception.exit, EXIT_USAGE)
        for kwargs in ({"kind": "gossip"}, {"kind": "bug", "sev": 4},
                       {"kind": "bug", "tasks": ["P1.%d" % n for n in range(1, 7)]}):
            with self.assertRaises(RoadmapError):
                issues.open_issue(self.docs, "x", **kwargs)
        with self.assertRaises(RoadmapError):
            issues.open_issue(self.docs, "a" * 121, "bug")
        self.assertFalse(os.path.exists(os.path.join(self.docs, "issues.json")))

    def test_200_open_is_the_cap(self):
        for n in range(200):
            issues.open_issue(self.docs, "issue %d" % n, "risk", now=at(n))
        with self.assertRaises(RoadmapError) as ctx:
            issues.open_issue(self.docs, "one too many", "risk")
        self.assertEqual(ctx.exception.exit, EXIT_CONFLICT)
        self.assertEqual(len(issues.list_issues(self.docs)), 200)

    def test_closed_beyond_newest_100_move_to_archive(self):
        moved = 0
        for n in range(105):
            issue = issues.open_issue(self.docs, "i%d" % n, "bug", now=at(n))
            moved += issues.close(self.docs, issue["id"], now=at(200 + n))["archived"]
        self.assertEqual(len(self.read_json("issues.json")["issues"]), 100)
        archived = self.read_lines("issues-archive.jsonl")
        self.assertEqual(len(archived), 5)
        self.assertEqual(sorted(a["id"] for a in archived), ["I1", "I2", "I3", "I4", "I5"])
        self.assertEqual(moved, 5)
        # the next id never reuses an archived number
        self.assertEqual(issues.open_issue(self.docs, "new", "bug")["id"], "I106")

    def test_close_and_reopen(self):
        issue = issues.open_issue(self.docs, "x", "blocker", now=at(0))
        closed = issues.close(self.docs, issue["id"], now=at(5))
        self.assertEqual(closed["status"], "closed")
        self.assertEqual(issues.list_issues(self.docs), [])
        reopened = issues.set_status(self.docs, issue["id"], "open")
        self.assertIsNone(reopened["closed"])
        with self.assertRaises(RoadmapError) as ctx:
            issues.close(self.docs, "I99")
        self.assertEqual(ctx.exception.exit, EXIT_NOT_FOUND)


class QuestionsTests(DocsCase):
    def test_ask_answer_and_option_check(self):
        q = questions.ask(self.docs, "P1.2", "Keep the old API?", opts=["yes", "no"], default="no",
                          block=True, timeout_s=600, now=at(0))
        self.assertEqual(q["id"], "Q1")
        free = questions.answer(self.docs, "Q1", "maybe", now=at(1))
        self.assertEqual(free["answer"], "maybe")
        questions.reopen(self.docs, "Q1")
        answered = questions.answer(self.docs, "Q1", "no", now=at(2))
        self.assertEqual((answered["status"], answered["answer"]), ("answered", "no"))
        with self.assertRaises(RoadmapError) as ctx:
            questions.answer(self.docs, "Q1", "yes", now=at(3))
        self.assertEqual(ctx.exception.exit, EXIT_CONFLICT)

    def test_default_must_be_an_option(self):
        with self.assertRaises(RoadmapError):
            questions.ask(self.docs, "P1.1", "Pick", opts=["a", "b"], default="c")
        with self.assertRaises(RoadmapError):
            questions.ask(self.docs, "P1.1", "Pick", opts=["a"] * 6, default="a")

    def test_fifty_open_is_the_cap(self):
        for n in range(50):
            questions.ask(self.docs, "P1.1", "q%d" % n, now=at(n))
        with self.assertRaises(RoadmapError) as ctx:
            questions.ask(self.docs, "P1.1", "one more")
        self.assertEqual(ctx.exception.exit, EXIT_CONFLICT)

    def test_answered_beyond_50_move_to_archive(self):
        for n in range(55):
            questions.ask(self.docs, "P1.1", "q%d" % n, now=at(n))
            questions.answer(self.docs, "Q%d" % (n + 1), "ok", now=at(100 + n))
        self.assertEqual(len(self.read_json("questions.json")["questions"]), 50)
        self.assertEqual(len(self.read_lines("questions-archive.jsonl")), 5)

    def test_timeout_takes_the_default(self):
        questions.ask(self.docs, "P1.1", "Go?", opts=["go", "stop"], default="stop", block=True, timeout_s=60,
                      now=at(0))
        questions.ask(self.docs, "P1.1", "Later?", timeout_s=3600, now=at(0))
        self.assertEqual(questions.expire(self.docs, now=at(0.5)), [])
        self.assertEqual(questions.expire(self.docs, now=at(2)), ["Q1"])
        q1 = questions.get(self.docs, "Q1")
        self.assertEqual((q1["status"], q1["answer"]), ("defaulted", "stop"))
        self.assertEqual(questions.get(self.docs, "Q2")["status"], "open")


class CommentsTests(DocsCase):
    def test_twenty_per_target_then_oldest_archived(self):
        for n in range(22):
            comments.add(self.docs, "P1.2", "lead", "note %d" % n, now=at(n))
        self.assertEqual(len(comments.list_comments(self.docs, on="P1.2")), 20)
        archived = self.read_lines("comments-archive.jsonl")
        self.assertEqual([c["t"] for c in archived], ["note 0", "note 1"])

    def test_targets_are_separate_and_text_is_capped(self):
        comments.add(self.docs, "P1.2", "lead", "a", now=at(0))
        comments.add(self.docs, "I3", "lead", "b", now=at(1))
        self.assertEqual([c["t"] for c in comments.list_comments(self.docs, on="I3")], ["b"])
        with self.assertRaises(RoadmapError):
            comments.add(self.docs, "P1.2", "lead", "x" * 281)
        with self.assertRaises(RoadmapError):
            comments.add(self.docs, "bad target!", "lead", "x")

    def test_file_cap_moves_the_oldest_to_archive(self):
        with mock.patch.object(comments, "FILE_MAX_BYTES", 3000):
            for n in range(40):
                comments.add(self.docs, "P%d.1" % n, "lead", "text %d %s" % (n, "y" * 200), now=at(n))
        size = os.path.getsize(os.path.join(self.docs, "comments.json"))
        self.assertLessEqual(size, 3000)
        self.assertGreater(len(self.read_lines("comments-archive.jsonl")), 0)
        kept = comments.list_comments(self.docs)
        self.assertEqual(kept[-1]["on"], "P39.1")


class BudgetTests(DocsCase):
    def test_job_spend_is_recorded_once_per_job_id(self):
        self.assertTrue(budget.record_job_spend(self.docs, "j1", "P1.1", "sonnet", 35))
        self.assertFalse(budget.record_job_spend(self.docs, "j1", "P1.1", "sonnet", 35))
        self.assertTrue(budget.record_job_spend(self.docs, "j2", "P1.1", "sonnet", 5))
        doc = budget.get(self.docs)
        self.assertEqual(doc["spent"], {"P1.1": {"sonnet": 40.0}})
        self.assertEqual(doc["jobs"], ["j1", "j2"])

    def test_task_tokens_only_when_the_task_has_no_spend(self):
        self.assertTrue(budget.record_task_tokens(self.docs, "P1.1", "haiku", 20))
        self.assertFalse(budget.record_task_tokens(self.docs, "P1.1", "haiku", 99))
        budget.record_job_spend(self.docs, "j9", "P1.2", "opus", 7)
        self.assertFalse(budget.record_task_tokens(self.docs, "P1.2", "opus", 50))
        self.assertEqual(budget.get(self.docs)["spent"]["P1.1"], {"haiku": 20.0})

    def test_job_ids_are_kept_to_500(self):
        for n in range(510):
            budget.record_job_spend(self.docs, "j%d" % n, None, "agy", 1)
        doc = budget.get(self.docs)
        self.assertEqual(len(doc["jobs"]), 500)
        self.assertEqual(doc["spent"]["-"]["agy"], 510.0)
        self.assertFalse(budget.record_job_spend(self.docs, "j509", None, "agy", 1))

    def test_limits_are_set_and_cleared(self):
        budget.set_limit(self.docs, "project", None, 500)
        budget.set_limit(self.docs, "models", "sonnet", 120)
        limits = budget.set_limit(self.docs, "models", "sonnet", None)
        self.assertEqual(limits["project"], 500.0)
        self.assertEqual(limits["models"], {})
        with self.assertRaises(RoadmapError):
            budget.set_limit(self.docs, "phases", "P1", -3)
        with self.assertRaises(RoadmapError):
            budget.set_limit(self.docs, "weeks", "P1", 3)


class QueueTests(DocsCase):
    def test_enqueue_dedupe_cap_and_dequeue(self):
        queue.enqueue(self.docs, "P1.1", "lead", now=at(0))
        with self.assertRaises(RoadmapError) as ctx:
            queue.enqueue(self.docs, "P1.1", "lead")
        self.assertEqual(ctx.exception.exit, EXIT_CONFLICT)
        for n in range(2, 51):
            queue.enqueue(self.docs, "P1.%d" % n, "lead")
        with self.assertRaises(RoadmapError):
            queue.enqueue(self.docs, "P9.9", "lead")
        self.assertEqual(len(queue.list_queue(self.docs)), 50)
        self.assertTrue(queue.dequeue(self.docs, "P1.1"))
        self.assertFalse(queue.dequeue(self.docs, "P1.1"))
        self.assertEqual(self.read_json("queue.json")["schemaVersion"], 1)


class ActivityTests(DocsCase):
    def test_ids_increase_and_summary_is_cut(self):
        first = activity.append(self.docs, "cli", "task.done", "x" * 100, now=at(0))
        second = activity.append(self.docs, "gui", "issue.new", "short", undo=True, now=at(1))
        self.assertEqual((first["id"], second["id"]), ("A1", "A2"))
        self.assertEqual(len(first["sum"]), 60)
        self.assertTrue(second["undo"])
        with self.assertRaises(RoadmapError):
            activity.append(self.docs, "robot", "x", "y")

    def test_keeps_the_newest_500_lines(self):
        with mock.patch.object(activity, "KEEP", 5):
            for n in range(8):
                activity.append(self.docs, "cli", "op", "line %d" % n)
        lines = self.read_lines("activity.jsonl")
        self.assertEqual([line["id"] for line in lines], ["A4", "A5", "A6", "A7", "A8"])
        self.assertEqual([line["id"] for line in activity.recent(self.docs, 2)], ["A7", "A8"])

    def test_id_continues_after_a_damaged_last_line(self):
        activity.append(self.docs, "cli", "op", "one")
        with open(os.path.join(self.docs, "activity.jsonl"), "a", encoding="utf-8") as fh:
            fh.write("not json\n")
        self.assertEqual(activity.append(self.docs, "cli", "op", "two")["id"], "A2")
        self.assertEqual(len(activity.recent(self.docs)), 2)


class SubtaskTests(DocsCase):
    def setUp(self):
        super().setUp()
        self.write_tasks([{"id": "P1.1", "phase": "P1", "title": "A", "status": "todo", "tokensK": 10,
                           "thinking": "low", "model": "haiku", "needsUser": False, "check": "none", "checkK": 0},
                          {"id": "P1.2", "phase": "P1", "title": "B", "status": "partial", "tokensK": 10,
                           "thinking": "low", "model": "haiku", "needsUser": False, "check": "none", "checkK": 0}])

    def task(self, task_id):
        return tasks.get(self.docs, task_id)

    def test_add_then_tick_the_first_moves_todo_to_partial_never_done(self):
        self.assertEqual(tasks.add_subtask(self.docs, "P1.1", "write tests")["addr"], "P1.1/1")
        tasks.add_subtask(self.docs, "P1.1", "docs")
        result = tasks.toggle_subtask(self.docs, "P1.1/1")
        self.assertTrue(result["done"])
        self.assertEqual(self.task("P1.1")["status"], "partial")
        tasks.toggle_subtask(self.docs, "P1.1/2")
        self.assertEqual(self.task("P1.1")["status"], "partial")
        self.assertEqual(self.task("P1.1")["subs"], [{"t": "write tests", "d": True}, {"t": "docs", "d": True}])

    def test_undo_restores_tick_and_status(self):
        tasks.add_subtask(self.docs, "P1.1", "a")
        result = tasks.toggle_subtask(self.docs, "P1.1/1")
        self.assertEqual(self.task("P1.1")["status"], "partial")
        tasks.undo_subtask(self.docs, result)
        self.assertEqual(self.task("P1.1")["status"], "todo")
        self.assertFalse(self.task("P1.1")["subs"][0]["d"])

    def test_addresses_and_limits(self):
        for bad in ("P1.1", "P1.1/0", "P1.1/x", "P1.1/9"):
            with self.assertRaises(RoadmapError):
                tasks.toggle_subtask(self.docs, bad)
        with self.assertRaises(RoadmapError) as ctx:
            tasks.add_subtask(self.docs, "P9.9", "nope")
        self.assertEqual(ctx.exception.exit, EXIT_NOT_FOUND)
        with self.assertRaises(RoadmapError):
            tasks.add_subtask(self.docs, "P1.1", "x" * 81)
        for n in range(12):
            tasks.add_subtask(self.docs, "P1.1", "s%d" % n)
        with self.assertRaises(RoadmapError):
            tasks.add_subtask(self.docs, "P1.1", "thirteenth")

    def test_subtask_writes_keep_the_task_file_schema_at_1(self):
        tasks.add_subtask(self.docs, "P1.2", "first")
        self.assertEqual(self.read_json("tasks.json")["schemaVersion"], 1)
        self.assertEqual(self.read_json("tasks.json")["updated"], "2026-10-01")


class LockAndStoreTests(DocsCase):
    def test_a_held_lock_refuses_a_write_with_locked(self):
        held = lock.locked(self.docs, timeout=0.01)
        with held:
            with self.assertRaises(RoadmapError) as ctx:
                issues.open_issue(self.docs, "blocked", "bug")
        self.assertEqual(ctx.exception.exit, EXIT_CONFLICT)
        self.assertFalse(os.path.exists(os.path.join(self.docs, "issues.json")))

    def test_writes_leave_no_temp_files(self):
        issues.open_issue(self.docs, "x", "bug")
        comments.add(self.docs, "P1.1", "lead", "y")
        self.assertEqual([n for n in os.listdir(self.docs) if n.endswith(".tmp")], [])

    def test_archive_lines_round_trip_through_read_objects(self):
        path = os.path.join(self.docs, "x-archive.jsonl")
        jsonl.append_line(path, {"id": "I1"})
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("garbage\n")
        objects, bad = jsonl.read_objects(path)
        self.assertEqual((objects, bad), ([{"id": "I1"}], 1))


if __name__ == "__main__":
    unittest.main()
