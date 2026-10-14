"""WP52: the feature service and its ops (roadmap/services/features.py, featops.py), the snapshot key and the
status line.

Runs in-process under a temp ROADMAP_HOME with the demo project from CmdCase (tasks P1.1 to P1.3 and P2.1). Agent
refusal is tested with CLAUDECODE set in this process only; the environment is restored after each test.
"""

import datetime
import json
import os
import unittest
from unittest import mock

from roadmap.core import planfmt
from roadmap.core.snapshot import build_snapshot
from roadmap.errors import RoadmapError
from roadmap.services import commands, features, tasks
from roadmap.store import lock
from tests.unit.test_cmd_support import CmdCase

FIXTURE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures", "splitnet")
PINNED_NOW = datetime.datetime(2026, 10, 13, 12, 0, 0, tzinfo=datetime.timezone.utc)


class FeatureCase(CmdCase):
    def setUp(self):
        super().setUp()
        env = mock.patch.dict(os.environ, {})
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("CLAUDECODE", None)

    def add(self, title="Roadmap visual", **extra):
        args = {"title": title, "acc": extra.pop("acc", "it reads at 375 px"), "prio": 2, "phase": None,
                "parent": None}
        args.update(extra)
        reply = self.op("feature.add", args)
        return reply

    def task_feats(self, task_id):
        return {t["id"]: t.get("feats") for t in tasks.load(self.data)["tasks"]}[task_id]

    def run_agent(self, op, args, source="cli"):
        with mock.patch.dict(os.environ, {"CLAUDECODE": "1"}):
            return self.op(op, args) if source == "cli" else commands.run(op, args, source, self.data)


class OpsAndUndo(FeatureCase):
    def test_add_assigns_the_next_id_logs_one_line_and_undoes(self):
        reply = self.add("Roadmap visual")
        self.assertEqual(reply["data"]["id"], "F1")
        self.assertTrue(reply["undo"])
        self.assertEqual([x["id"] for x in features.load_doc(self.data)["features"]], ["F1"])
        second = self.add("Second")
        self.assertEqual(second["data"]["id"], "F2")
        undone = commands.run("undo", {"activity": reply["activity"]}, "cli", self.data)
        self.assertEqual(undone["data"]["undone"], reply["activity"])
        self.assertEqual([x["id"] for x in features.load_doc(self.data)["features"]], ["F2"])

    def test_title_and_acc_limits_are_enforced(self):
        with self.assertRaises(RoadmapError) as ctx:
            self.add("x" * 81)
        self.assertEqual(ctx.exception.code, "usage")
        with self.assertRaises(RoadmapError):
            self.add("ok", acc="y" * 161)

    def test_parent_is_one_level_only(self):
        self.add("Top")
        self.add("Child", parent="F1")
        with self.assertRaises(RoadmapError) as ctx:
            self.add("Grandchild", parent="F2")
        self.assertIn("one level only", ctx.exception.message)

    def test_sixty_features_is_the_most(self):
        recs = [features.record_of("F%d" % n, "feature %d" % n) for n in range(1, 61)]
        with lock.locked(self.data):
            features.apply_records(self.data, recs)
        with self.assertRaises(RoadmapError) as ctx:
            self.add("one too many")
        self.assertEqual(ctx.exception.code, "conflict")

    def test_set_changes_fields_and_undo_restores_them(self):
        self.add("Roadmap visual")
        reply = self.op("feature.set", {"id": "F1", "title": "Planner visual", "phase": "P1"})
        row = features.row_of(self.data, "F1")
        self.assertEqual((row["title"], row["phase"]), ("Planner visual", "P1"))
        commands.run("undo", {"activity": reply["activity"]}, "cli", self.data)
        row = features.row_of(self.data, "F1")
        self.assertEqual((row["title"], row["phase"]), ("Roadmap visual", None))

    def test_link_and_unlink_write_feats_and_undo(self):
        self.add("Visual")
        self.add("Ops")
        link = self.op("feature.link", {"task": "P1.1", "feats": ["F1", "F2"]})
        self.assertEqual(self.task_feats("P1.1"), ["F1", "F2"])
        self.assertEqual(link["data"]["added"], ["F1", "F2"])
        unlink = self.op("feature.unlink", {"task": "P1.1", "feats": ["F1"]})
        self.assertEqual(self.task_feats("P1.1"), ["F2"])
        commands.run("undo", {"activity": unlink["activity"]}, "cli", self.data)
        self.assertEqual(self.task_feats("P1.1"), ["F2", "F1"])

    def test_a_task_takes_at_most_three_features(self):
        for n in range(1, 5):
            self.add("feature %d" % n)
        self.op("feature.link", {"task": "P1.2", "feats": ["F1", "F2", "F3"]})
        with self.assertRaises(RoadmapError):
            self.op("feature.link", {"task": "P1.2", "feats": ["F4"]})
        self.assertEqual(self.task_feats("P1.2"), ["F1", "F2", "F3"])

    def test_link_rejects_an_unknown_feature_or_task(self):
        self.add("Visual")
        with self.assertRaises(RoadmapError) as ctx:
            self.op("feature.link", {"task": "P1.1", "feats": ["F9"]})
        self.assertEqual(ctx.exception.code, "not_found")
        with self.assertRaises(RoadmapError) as ctx:
            self.op("feature.link", {"task": "P9.9", "feats": ["F1"]})
        self.assertEqual(ctx.exception.code, "not_found")

    def test_rm_only_when_no_tasks_and_undo_restores(self):
        self.add("Visual")
        self.op("feature.link", {"task": "P1.1", "feats": ["F1"]})
        with self.assertRaises(RoadmapError) as ctx:
            self.op("feature.rm", {"id": "F1"})
        self.assertEqual(ctx.exception.code, "conflict")
        self.op("feature.unlink", {"task": "P1.1", "feats": ["F1"]})
        removed = self.op("feature.rm", {"id": "F1"})
        self.assertEqual(features.load_doc(self.data)["features"], [])
        commands.run("undo", {"activity": removed["activity"]}, "cli", self.data)
        self.assertEqual([f["id"] for f in features.load_doc(self.data)["features"]], ["F1"])


class AcceptRules(FeatureCase):
    def test_an_agent_shell_is_refused_with_ask_the_person(self):
        self.add("Visual")
        for source in ("agent", "phone"):
            with self.assertRaises(RoadmapError) as ctx:
                commands.run("feature.accept", {"id": "F1", "on": True}, source, self.data)
            self.assertEqual(ctx.exception.code, "agent_refused")
            self.assertEqual(ctx.exception.next, "ask the person")
        with self.assertRaises(RoadmapError):
            self.run_agent("feature.accept", {"id": "F1", "on": True})
        self.assertIsNone(features.load_doc(self.data)["features"][0]["accepted"])

    def test_a_person_accepts_with_todays_date_and_undo_clears_it(self):
        self.add("Visual")
        with self.assertRaises(RoadmapError) as ctx:
            self.op("feature.accept", {"id": "F1", "on": True})
        self.assertEqual(ctx.exception.code, "conflict")
        reply = self.op("feature.accept", {"id": "F1", "on": True, "confirm": True})
        self.assertEqual(features.load_doc(self.data)["features"][0]["accepted"], planfmt.today())
        commands.run("undo", {"activity": reply["activity"]}, "cli", self.data)
        self.assertIsNone(features.load_doc(self.data)["features"][0]["accepted"])

    def test_a_done_feature_accepts_without_confirm(self):
        self.add("Visual")
        self.op("feature.link", {"task": "P1.1", "feats": ["F1"]})
        self.op("task.status", {"id": "P1.1", "status": "done"})
        self.op("feature.accept", {"id": "F1", "on": True})
        self.assertIsNotNone(features.load_doc(self.data)["features"][0]["accepted"])


class ApplyRecords(FeatureCase):
    def test_apply_keeps_accepted_and_is_idempotent(self):
        self.add("Visual")
        self.op("feature.accept", {"id": "F1", "on": True, "confirm": True})
        with lock.locked(self.data):
            result = features.apply_records(self.data, [features.record_of("F1", "Visual", "new acc", 1)])
        self.assertEqual(result["changed"], ["F1"])
        row = features.load_doc(self.data)["features"][0]
        self.assertEqual((row["prio"], row["acc"]), (1, "new acc"))
        self.assertIsNotNone(row["accepted"])
        with lock.locked(self.data):
            again = features.apply_records(self.data, [features.record_of("F1", "Visual", "new acc", 1)])
        self.assertEqual((again["added"], again["changed"], again["wrote"]), ([], [], False))

    def test_unknown_phase_is_refused_and_nothing_is_written(self):
        with lock.locked(self.data), self.assertRaises(RoadmapError):
            features.apply_records(self.data, [features.record_of("F1", "Visual", phase="R99")])
        self.assertFalse(os.path.exists(os.path.join(self.data, "features.json")))

    def test_plan_f_lines_go_through_tasks_apply(self):
        code_text = "F F1 - 2 P1 - | Roadmap visual # reads at 375 px\nL F1 P1.1\n"
        records_list, errors = planfmt.parse_plan(code_text)
        self.assertEqual(errors, [])
        tasks.apply(self.data, records_list)
        self.assertEqual([f["id"] for f in features.load_doc(self.data)["features"]], ["F1"])
        self.assertEqual(self.task_feats("P1.1"), ["F1"])


class ViewsAndStatus(FeatureCase):
    def test_status_line_is_absent_without_a_file_and_counts_otherwise(self):
        self.assertIsNone(features.status_line(self.data))
        self.add("Visual")
        self.add("Ops")
        self.op("feature.link", {"task": "P1.1", "feats": ["F1"]})
        self.op("task.status", {"id": "P1.1", "status": "done"})
        self.assertEqual(features.status_line(self.data),
                         "features: 2 (1 done, 0 doing, 0 todo, 1 uncovered; 3 orphan tasks)")
        self.op("feature.link", {"task": "P1.2", "feats": ["F2"]})
        self.op("feature.link", {"task": "P1.1", "feats": ["F2"]})
        self.assertEqual(features.status_line(self.data),
                         "features: 2 (1 done, 1 doing, 0 todo, 0 uncovered; 2 orphan tasks)")

    def test_snapshot_key_is_present_and_empty_without_a_file(self):
        with open(os.path.join(FIXTURE_DIR, "tasks.json"), encoding="utf-8") as fh:
            text = fh.read()
        snap = build_snapshot({"tasks.json": text}, {"id": "splitnet"}, PINNED_NOW)
        view = snap["features"]
        self.assertEqual((view["rows"], view["uncovered"]), ([], []))
        self.assertEqual(view["counts"], {"total": 0, "done": 0, "doing": 0, "todo": 0, "uncovered": 0})
        # with no features every task is an orphan
        self.assertEqual(view["orphans"], [t["id"] for t in json.loads(text)["tasks"]])

    def test_snapshot_counts_orphans_and_uncovered(self):
        with open(os.path.join(FIXTURE_DIR, "tasks.json"), encoding="utf-8") as fh:
            text = fh.read()
        first = json.loads(text)["tasks"][0]["id"]
        feats = {"schemaVersion": 1, "features": [
            {"id": "F1", "title": "Covered", "acc": "", "prio": 2, "parent": None, "phase": None, "hold": False,
             "accepted": None},
            {"id": "F2", "title": "Nothing", "acc": "", "prio": 2, "parent": None, "phase": None, "hold": False,
             "accepted": None}]}
        tasks_doc = json.loads(text)
        tasks_doc["tasks"][0]["feats"] = ["F1"]
        files = {"tasks.json": json.dumps(tasks_doc), "features.json": json.dumps(feats)}
        view = build_snapshot(files, {"id": "splitnet"}, PINNED_NOW)
        self.assertEqual(view["features"]["uncovered"], ["F2"])
        self.assertEqual(view["features"]["orphans"], [t["id"] for t in tasks_doc["tasks"][1:]])
        # the rows carry no task list; the task itself names its feature in feats
        self.assertNotIn("tasks", view["features"]["rows"][0])
        self.assertEqual(view["tasks"][0]["feats"], ["F1"])
        self.assertEqual(view["tasks"][0]["id"], first)
        self.assertEqual(view["errors"], [])

    def test_sixty_features_snapshot_size_stays_near_measured_size(self):
        """WP53b: the rows drop the task id list and keep acc only for features that are not done. The 14 fixed keys
        cost about 190 bytes a row, so 60 rows cannot reach 6 KB or 8 KB; they measure about 14 KB here (was 15.9 KB).
        This test guards that measured size (a regression bound) and the row shape."""
        with open(os.path.join(FIXTURE_DIR, "tasks.json"), encoding="utf-8") as fh:
            text = fh.read()
        task_ids = [t["id"] for t in json.loads(text)["tasks"]][:120]
        tasks_doc = json.loads(text)
        feats = []
        for n in range(1, 61):
            feats.append({"id": "F%d" % n, "title": "Feature %d planner" % n,
                          "acc": "Acceptance for feature %d" % n, "prio": 1 + n % 3, "parent": None,
                          "phase": None, "hold": False, "accepted": None})
            for k in range(2):
                task = tasks_doc["tasks"][(2 * (n - 1) + k) % len(task_ids)]
                task["feats"] = (task.get("feats") or []) + ["F%d" % n]
        files_without = {"tasks.json": json.dumps(tasks_doc)}
        files_with = dict(files_without, **{"features.json": json.dumps({"schemaVersion": 1, "features": feats})})
        base = build_snapshot(files_without, {"id": "splitnet"}, PINNED_NOW)
        full = build_snapshot(files_with, {"id": "splitnet"}, PINNED_NOW)
        self.assertEqual(len(full["features"]["rows"]), 60)
        size = len(json.dumps(full["features"], separators=(",", ":")))
        self.assertEqual(set(base) | {"features"}, set(full))
        self.assertLessEqual(size, 15 * 1024, "features key is %d bytes" % size)
        for row in full["features"]["rows"]:
            self.assertNotIn("tasks", row)
            self.assertEqual("acc" in row, row["state"] != "done", row["id"])


if __name__ == "__main__":
    unittest.main()
