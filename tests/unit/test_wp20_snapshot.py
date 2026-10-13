"""WP20 parsers and snapshot: parsers never raise on corrupt input, subs/capK/approved/parent/role appear only when
present, the new snapshot keys are empty without their files and correct on a full fixture, and tasks.json stays at
schema 1."""

import datetime
import json
import unittest

from roadmap.core import parsers
from roadmap.core.snapshot import build_snapshot
from roadmap.store import schema

NOW = datetime.datetime(2026, 10, 13, 12, 0, 0, tzinfo=datetime.timezone.utc)
CONFIG = {"id": "demo", "title": "demo"}
CORRUPT = ["", "{", "[]", "42", '{"issues": 7}', '{"issues": [1, "x", {"id": ""}]}', "\x00\x01"]


def task(tid, **extra):
    base = {"id": tid, "phase": tid.split(".")[0], "title": "T " + tid, "status": "todo", "tokensK": 10,
            "thinking": "low", "model": "haiku", "needsUser": False, "check": "none", "checkK": 0}
    base.update(extra)
    return base


def fixture_files():
    tasks = {"schemaVersion": 1, "updated": "2026-10-12",
             "phases": [{"id": "P1", "name": "Engine", "status": "partial", "approved": True},
                        {"id": "P2", "name": "UI", "status": "todo"}],
             "tasks": [task("P1.1", status="done", tokensK=20),
                       task("P1.2", status="partial", needsUser=True,
                            subs=[{"t": "wire it", "d": True}, {"t": "test it", "d": False}], capK=40),
                       task("P2.1", phase="P2", title="Panel")]}
    jobs = {"schemaVersion": 1, "jobs": [
        {"id": "j1", "title": "Build engine", "model": "opus", "task": "P1.2", "status": "running",
         "started": "2026-10-13T11:30:00+00:00", "ended": None, "parent": None, "role": "lead"},
        {"id": "j2", "title": "Write tests", "model": "haiku", "task": "P1.2", "status": "running",
         "started": "2026-10-13T11:40:00+00:00", "ended": None, "parent": "j1", "role": "worker"},
        {"id": "j3", "title": "Done one", "model": "sonnet", "task": "P1.1", "status": "done",
         "started": "2026-10-13T10:00:00+00:00", "ended": "2026-10-13T10:05:00+00:00", "tokensK": 33}]}
    issues = {"schemaVersion": 1, "issues": [
        {"id": "I1", "title": "Build breaks", "kind": "blocker", "sev": 1, "status": "open", "tasks": ["P1.2"],
         "by": "lead", "created": "2026-10-13T09:00:00+00:00", "closed": None, "note": None},
        {"id": "I2", "title": "Old", "kind": "bug", "sev": 3, "status": "closed", "tasks": [], "by": "",
         "created": "2026-10-01T09:00:00+00:00", "closed": "2026-10-02T09:00:00+00:00", "note": None},
        {"id": "I3", "title": "Doing", "kind": "risk", "sev": 2, "status": "doing", "tasks": ["P2.1"], "by": "",
         "created": "2026-10-13T09:30:00+00:00", "closed": None, "note": "watch"}]}
    questions = {"schemaVersion": 1, "questions": [
        {"id": "Q1", "task": "P1.2", "text": "Keep the old API?", "opts": ["yes", "no"], "def": "no", "block": True,
         "timeoutS": 600, "status": "open", "answer": None, "asked": "2026-10-13T11:00:00+00:00", "answered": None},
        {"id": "Q2", "task": "P2.1", "text": "Colour?", "opts": [], "def": None, "block": False, "timeoutS": None,
         "status": "open", "answer": None, "asked": "2026-10-13T11:05:00+00:00", "answered": None},
        {"id": "Q3", "task": "P2.1", "text": "Old?", "opts": ["a"], "def": "a", "block": True, "timeoutS": None,
         "status": "answered", "answer": "a", "asked": "2026-10-13T08:00:00+00:00",
         "answered": "2026-10-13T08:01:00+00:00"}]}
    comments = {"schemaVersion": 1, "comments": [
        {"on": "P1.2", "by": "lead", "at": "2026-10-13T10:00:00+00:00", "t": "c%d" % n} for n in range(1, 6)]
        + [{"on": "I1", "by": "me", "at": "2026-10-13T10:10:00+00:00", "t": "blocking"}]}
    budget = {"schemaVersion": 1, "limits": {"project": 200, "phases": {"P1": 100}, "models": {"haiku": 50},
                                              "tasks": {"P1.2": 40}},
              "spent": {"P1.1": {"sonnet": 35}, "P1.2": {"haiku": 20, "opus": 10}}, "jobs": ["j3"]}
    queue = {"schemaVersion": 1, "entries": [{"task": "P2.1", "by": "lead", "at": "2026-10-13T11:50:00+00:00"}]}
    activity = "\n".join(json.dumps({"id": "A%d" % n, "at": "2026-10-13T11:00:00+00:00", "src": "cli",
                                     "op": "task.done", "sum": "line %d" % n, "undo": False})
                         for n in range(1, 21)) + "\n"
    dumps = lambda doc: json.dumps(doc)  # noqa: E731
    return {"tasks.json": dumps(tasks), "jobs.json": dumps(jobs), "autonomy.json": None,
            "issues.json": dumps(issues), "questions.json": dumps(questions), "comments.json": dumps(comments),
            "budget.json": dumps(budget), "queue.json": dumps(queue), "activity.jsonl": activity}


class ParsersNeverRaise(unittest.TestCase):
    def test_every_parser_survives_corrupt_text(self):
        parse_all = [
            lambda t: parsers.parse_tasks(t), lambda t: parsers.parse_jobs(t, NOW),
            lambda t: parsers.parse_autonomy(t), lambda t: parsers.parse_issues(t),
            lambda t: parsers.parse_questions(t), lambda t: parsers.parse_comments(t),
            lambda t: parsers.parse_budget(t), lambda t: parsers.parse_queue(t),
            lambda t: parsers.parse_activity(t),
        ]
        for text in CORRUPT:
            for parse in parse_all:
                value, errors = parse(text)
                self.assertIsInstance(errors, list)
                self.assertTrue(value is not None or parse is parse_all[2])  # autonomy gives None, by contract

    def test_bad_items_are_skipped_with_an_error_each(self):
        items, errors = parsers.parse_issues(json.dumps({"issues": [
            {"id": "I1", "title": "ok", "kind": "bug", "sev": 2, "status": "open"},
            {"id": "I2", "title": "bad kind", "kind": "gossip", "sev": 2, "status": "open"},
            {"id": "I3", "title": "bad sev", "kind": "bug", "sev": 9, "status": "open"}]}))
        self.assertEqual([i["id"] for i in items], ["I1"])
        self.assertEqual(len(errors), 2)

    def test_budget_bad_numbers_are_dropped(self):
        doc, errors = parsers.parse_budget(json.dumps({"limits": {"project": "lots"},
                                                       "spent": {"P1.1": {"haiku": "3"}}}))
        self.assertIsNone(doc["limits"]["project"])
        self.assertEqual(doc["spent"], {"P1.1": {}})
        self.assertEqual(len(errors), 2)


class OptionalKeys(unittest.TestCase):
    def test_subs_are_capped_at_12_and_text_at_80(self):
        subs, errors = parsers.parse_subs([{"t": "x" * 100, "d": True, "subs": [{"t": "nested"}]}]
                                          + [{"t": "s%d" % n} for n in range(20)])
        self.assertEqual(len(subs), 12)
        self.assertEqual(len(subs[0]["t"]), 80)
        self.assertEqual(subs[0]["d"], True)
        self.assertNotIn("subs", subs[0])
        self.assertEqual(subs[1], {"t": "s0", "d": False})
        self.assertTrue(errors)

    def test_task_and_phase_keys_appear_only_when_in_the_file(self):
        doc, errors = parsers.parse_tasks(json.dumps({
            "phases": [{"id": "P1", "name": "x", "status": "todo"}, {"id": "P2", "name": "y", "approved": True}],
            "tasks": [task("P1.1"), task("P1.2", capK=12.5, subs=[{"t": "a", "d": True}]),
                      task("P1.3", capK="many")]}))
        plain, capped, bad = doc["tasks"]
        self.assertNotIn("subs", plain)
        self.assertNotIn("capK", plain)
        self.assertEqual(capped["capK"], 12.5)
        self.assertEqual(capped["subs"], [{"t": "a", "d": True}])
        self.assertNotIn("capK", bad)
        self.assertNotIn("approved", doc["phases"][0])
        self.assertIs(doc["phases"][1]["approved"], True)
        self.assertEqual(len(errors), 1)

    def test_job_parent_and_role(self):
        jobs, _ = parsers.parse_jobs(json.dumps({"jobs": [
            {"id": "j1", "status": "running", "parent": "j0", "role": "worker"},
            {"id": "j2", "status": "running"}]}), NOW)
        self.assertEqual((jobs[0]["parent"], jobs[0]["role"]), ("j0", "worker"))
        self.assertNotIn("parent", jobs[1])


class SnapshotKeys(unittest.TestCase):
    def test_project_without_the_new_files_gets_empty_keys(self):
        files = {"tasks.json": json.dumps({"phases": [], "tasks": [task("P1.1")]}), "jobs.json": None,
                 "autonomy.json": None}
        snap = build_snapshot(files, CONFIG, NOW)
        self.assertEqual(snap["issues"], [])
        self.assertEqual(snap["questions"], [])
        self.assertEqual(snap["comments"], {})
        self.assertEqual(snap["budget"], {})
        self.assertEqual(snap["blocked"], [])
        self.assertEqual(snap["needsYou"], [])
        self.assertEqual(snap["queue"], [])
        self.assertEqual(snap["activity"], [])
        self.assertEqual(snap["control"], {})
        self.assertEqual(snap["agents"], {"running": [], "groups": {}, "roots": []})
        self.assertEqual(snap["errors"], [])

    def test_full_fixture(self):
        snap = build_snapshot(fixture_files(), CONFIG, NOW)
        self.assertEqual(snap["errors"], [])
        self.assertEqual([i["id"] for i in snap["issues"]], ["I1", "I3"])
        self.assertEqual([q["id"] for q in snap["questions"]], ["Q1", "Q2"])
        self.assertEqual(snap["blocked"], ["P1.2"])
        self.assertEqual([c["t"] for c in snap["comments"]["P1.2"]], ["c3", "c4", "c5"])
        self.assertEqual(snap["comments"]["I1"][0]["t"], "blocking")
        needs = [(row["kind"], row["id"]) for row in snap["needsYou"]]
        self.assertIn(("task", "P1.2"), needs)
        self.assertIn(("question", "Q1"), needs)
        self.assertNotIn(("question", "Q2"), needs)
        self.assertEqual(snap["agents"]["groups"], {"j1": ["j2"]})
        self.assertEqual(snap["agents"]["roots"], ["j1"])
        self.assertEqual([r["role"] for r in snap["agents"]["running"]], ["lead", "worker"])
        self.assertEqual(snap["queue"][0]["task"], "P2.1")
        self.assertEqual(len(snap["activity"]), 15)
        self.assertEqual(snap["activity"][-1]["id"], "A20")

    def test_budget_percentages(self):
        budget = build_snapshot(fixture_files(), CONFIG, NOW)["budget"]
        self.assertEqual(budget["total"], {"spent": 65.0, "limit": 200.0, "pct": 32.5})
        self.assertEqual(budget["phases"]["P1"], {"spent": 65.0, "limit": 100.0, "pct": 65.0})
        self.assertEqual(budget["phases"]["P2"], {"spent": 0.0, "limit": None, "pct": None})
        self.assertEqual(budget["models"]["haiku"], {"spent": 20.0, "limit": 50.0, "pct": 40.0})
        self.assertEqual(budget["tasks"]["P1.2"], {"spent": 30.0, "limit": 40.0, "pct": 75.0})

    def test_old_keys_unchanged_for_the_fixture_tasks(self):
        snap = build_snapshot(fixture_files(), CONFIG, NOW)
        phase = snap["phases"][0]
        self.assertIs(phase["approved"], True)
        self.assertEqual(snap["tasks"][1]["subs"], [{"t": "wire it", "d": True}, {"t": "test it", "d": False}])


class SchemaNotBumped(unittest.TestCase):
    def test_tasks_stays_at_1_and_new_kinds_start_at_1(self):
        self.assertEqual(schema.current_version("tasks"), 1)
        for kind in ("issues", "questions", "comments", "budget", "queue"):
            self.assertEqual(schema.current_version(kind), 1)


class LoaderNames(unittest.TestCase):
    def test_loader_reads_the_new_files(self):
        from roadmap.services import loader
        for name in ("issues.json", "questions.json", "comments.json", "budget.json", "queue.json",
                     "activity.jsonl"):
            self.assertIn(name, loader.BASE_FILES)


if __name__ == "__main__":
    unittest.main()
