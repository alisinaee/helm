"""R7.22 step 3 (W2.b): backlog tasks are in the snapshot and the status line, and never count as active.

Backlog tasks (docs/BACKLOG-SPEC.md section 2) are excluded from tasks_total, tasks_left, tokens_roadmap_k, phase
totals and progress, and project progress. They show as backlog_count and backlog_tokens_k, in the summary and per
phase. Projects without backlog tasks get the same keys as before (the golden snapshot test checks that).
"""

import json
import unittest
from datetime import datetime, timezone

from roadmap.commands.status import fold_backlog
from roadmap.core.snapshot import build_snapshot

NOW = datetime(2026, 10, 15, 12, 0, 0, tzinfo=timezone.utc)


def task(tid, phase, status, tokens=10.0):
    return {"id": tid, "phase": phase, "title": tid + " title", "status": status, "tokensK": tokens,
            "model": "haiku", "check": "sonnet", "checkK": 0, "needsUser": False}


def tasks_file(*rows):
    phases = [{"id": "P1", "name": "Core", "status": "todo"}, {"id": "P2", "name": "Ideas", "status": "todo"}]
    return json.dumps({"updated": "2026-10-15", "phases": phases, "tasks": list(rows)})


def snap(*rows):
    return build_snapshot({"tasks.json": tasks_file(*rows)}, {}, NOW)


class BacklogSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.rows = [task("P1.1", "P1", "done", 20.0), task("P1.2", "P1", "todo", 30.0),
                     task("P1.3", "P1", "backlog", 5.0), task("P2.1", "P2", "backlog", 7.0),
                     task("P2.2", "P2", "backlog", 3.0)]
        self.snap = snap(*self.rows)
        self.summary = self.snap["summary"]
        self.phases = {p["id"]: p for p in self.snap["phases"]}

    def test_summary_totals_leave_backlog_out(self):
        self.assertEqual(self.summary["tasks_total"], 2)
        self.assertEqual(self.summary["tasks_left"], 1)
        self.assertEqual(self.summary["tokens_left_k"], 30.0)
        self.assertEqual(self.summary["tokens_roadmap_k"], 50.0)
        self.assertEqual(self.summary["backlog_count"], 3)
        self.assertEqual(self.summary["backlog_tokens_k"], 15.0)

    def test_project_progress_leaves_backlog_out(self):
        project = self.snap["overall"]["project"]
        self.assertEqual(project["total"], 2)
        self.assertEqual(project["done"], 1)
        self.assertEqual(project["todo"], 1)
        self.assertEqual(project["progress"], 0.5)

    def test_phase_with_backlog_has_counts_and_no_extra_progress(self):
        p1 = self.phases["P1"]
        self.assertEqual((p1["total"], p1["done"]), (2, 1))
        self.assertEqual(p1["progress"], 0.5)
        self.assertEqual((p1["backlog_count"], p1["backlog_tokens_k"]), (1, 5.0))
        self.assertNotIn("only_backlog", p1)

    def test_phase_with_only_backlog_shows_no_percent(self):
        p2 = self.phases["P2"]
        self.assertEqual(p2["total"], 0)
        self.assertIsNone(p2["progress"])
        self.assertTrue(p2["only_backlog"])
        self.assertEqual((p2["backlog_count"], p2["backlog_tokens_k"]), (2, 10.0))

    def test_backlog_tasks_stay_in_the_task_list_with_their_state(self):
        states = {t["id"]: t["state"] for t in self.snap["tasks"]}
        self.assertEqual(states["P2.1"], "backlog")
        self.assertEqual(len(self.snap["tasks"]), 5)

    def test_no_backlog_keys_without_backlog_tasks(self):
        plain = snap(task("P1.1", "P1", "done"), task("P1.2", "P1", "todo"))
        self.assertNotIn("backlog_count", plain["summary"])
        self.assertNotIn("backlog_tokens_k", plain["summary"])
        for p in plain["phases"]:
            self.assertNotIn("backlog_count", p)
            self.assertNotIn("only_backlog", p)
        self.assertEqual(plain["summary"]["tasks_total"], 2)

    def test_status_header_counts_exclude_backlog(self):
        base = ["demo  updated 2026-10-15  5 tasks: 1 done, 0 partial, 1 todo, 0 hold",
                "left 1 (~30k)  needs-you 0  running 0", "P1 Core 50% | P2 Ideas 0%"]
        doc = {"phases": [{"id": "P1", "name": "Core", "status": "todo"}, {"id": "P2", "name": "Ideas"}],
               "tasks": [row for row in self.rows]}
        lines = fold_backlog(base, doc)
        self.assertEqual(lines[0], "demo  updated 2026-10-15  2 tasks: 1 done, 0 partial, 1 todo, 0 hold, backlog 3")
        self.assertEqual(lines[1], base[1])
        self.assertIn("P1 Core 50%", lines[2])

    def test_status_fold_is_a_no_op_without_backlog(self):
        base = ["demo  updated never  1 tasks: 0 done, 0 partial, 1 todo, 0 hold", "left 1 (~1k)"]
        self.assertEqual(fold_backlog(base, {"tasks": [task("P1.1", "P1", "todo")]}), base)


if __name__ == "__main__":
    unittest.main()
