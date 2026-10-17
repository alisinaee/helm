"""Tests for System v2 task binding and the arch extension (R11.101). A real git fixture repo in a temp folder."""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from roadmap.services import system, system_arch, system_tasks, system_v2, systemheat

ENV = {"PATH": os.environ.get("PATH", ""), "GIT_CONFIG_NOSYSTEM": "1"}


def _git(cwd, args):
    subprocess.run(["git"] + args, cwd=cwd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   env=dict(ENV, HOME=cwd))


def _write(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _commit(root, subject, files):
    for rel in files:
        _write(root, rel, subject + " " + rel + "\n")
    _git(root, ["add", "-A"])
    _git(root, ["-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", subject])


SYSTEM = {"version": 1, "layers": ["code"], "views": ["er", "components"],
          "components": [
              {"id": "web", "name": "Web UI", "layer": "code", "files": ["web/**"], "tasks": ["R9.1"], "work": ["W2"]},
              {"id": "core", "name": "Core engine", "layer": "code", "files": ["core/**"]}]}
TASKS = [
    {"id": "R1.2", "phase": "R1", "title": "first", "status": "done", "model": "haiku"},
    {"id": "R1.3", "phase": "R1", "title": "second", "status": "doing", "model": "sonnet"},
    {"id": "R9.1", "phase": "R9", "title": "explicit", "status": "todo"},
    {"id": "R5.1", "phase": "R5", "title": "touches core/x.py", "status": "hold"},
    {"id": "R5.2", "phase": "R5", "title": "no match here", "status": "todo", "refs": ["file:web/b.js"]},
    {"id": "R5.3", "phase": "R5", "title": "x", "status": "todo", "note": "the Core engine needs it"},
]
WORK = [{"id": "W1", "kind": "task", "title": "card one", "status": "Doing", "tasks": ["R1.3"]},
        {"id": "W2", "kind": "issue", "title": "explicit card", "status": "Done", "tasks": []}]


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="systasks-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = os.path.join(self.tmp, "proj")
        os.makedirs(self.root)
        self.data = os.path.join(self.tmp, "data")
        os.makedirs(self.data)
        for mod in (system, systemheat, system_arch, system_v2):
            getattr(mod, "_CACHE").clear()
            self.addCleanup(getattr(mod, "_CACHE").clear)
        _git(self.root, ["init", "-q"])
        _write(self.root, "docs/system.json", json.dumps(SYSTEM))
        _commit(self.root, "init", ["README.md"])
        _commit(self.root, "R1.2: x", ["web/a.js"])
        _commit(self.root, "R1.3: y", ["web/c.js", "core/z.py"])
        self.mapped = system.load(self.root)
        self.commits = systemheat.history(self.root)["commits"]

    def bind(self):
        return system_tasks.bind(self.mapped, self.commits, TASKS, WORK, SYSTEM)


class BindTest(Fixture):
    def test_commit_binds_with_title_status(self):
        web = self.bind()["web"]
        row = next(r for r in web["board"] if r["id"] == "R1.2")
        self.assertEqual((row["title"], row["status"], row["phase"], row["model"]), ("first", "done", "R1", "haiku"))

    def test_explicit_refs_paths_words(self):
        out = self.bind()
        web_ids = [r["id"] for r in out["web"]["board"]]
        self.assertIn("R9.1", web_ids)       # explicit
        self.assertIn("R5.2", web_ids)       # file ref
        core_ids = [r["id"] for r in out["core"]["board"]]
        self.assertIn("R5.1", core_ids)      # path in title
        self.assertIn("R5.3", core_ids)      # name as whole word in note
        self.assertNotIn("R5.1", web_ids)

    def test_order_and_work(self):
        web = self.bind()["web"]
        self.assertEqual([r["id"] for r in web["board"]], ["R1.3", "R5.2", "R9.1", "R1.2"])
        self.assertEqual([w["id"] for w in web["work"]], ["W2", "W1"])
        self.assertEqual(next(r for r in web["board"] if r["id"] == "R1.3")["work"], "W1")

    def test_progress(self):
        self.assertEqual(self.bind()["web"]["progress"], {"done": 1, "total": 4, "pct": 25})
        out = system_tasks.bind(self.mapped, [], [], WORK, SYSTEM)
        self.assertEqual(out["web"]["progress"], {"done": 1, "total": 1, "pct": 100})

    def test_cap(self):
        many = [{"id": "R7.%d" % i, "title": "the Web UI thing", "status": "todo"} for i in range(60)]
        out = system_tasks.bind(self.mapped, [], many, [], SYSTEM)
        self.assertEqual(len(out["web"]["board"]), 40)
        self.assertEqual(out["web"]["progress"]["total"], 60)


class ExtendTest(Fixture):
    def _extend(self):
        arch = system_arch.analyze(self.root, self.mapped, self.commits, [])
        from roadmap.services import tasks as tasks_svc
        with open(os.path.join(self.data, "tasks.json"), "w", encoding="utf-8") as fh:
            json.dump({"schemaVersion": 1, "phases": [], "tasks": TASKS}, fh)
        return system_v2.extend(self.root, self.mapped, arch, self.data, self.commits), tasks_svc

    def test_catalog_all_ids_and_details(self):
        arch, _ = self._extend()
        ids = [r["id"] for r in arch["catalog"]]
        self.assertEqual(sorted(ids), sorted(["context", "containers", "components", "modules", "layers", "flows",
                                              "data", "classes", "deployment", "usecases", "activity", "states", "er"]))
        self.assertEqual(ids[:2], ["er", "components"])      # pinned first, in the declared order
        for row in arch["catalog"]:
            self.assertEqual(set(row), {"id", "family", "label", "score", "available", "reason", "derived"})
            self.assertTrue(0 <= row["score"] <= 100)
        det = arch["details"]["c:web"]
        self.assertEqual(det["refId"], "web")
        self.assertIn("R1.2", [r["id"] for r in det["board"]])
        self.assertIn("pct", det["progress"])

    def test_raising_diagram_only_warns(self):
        boom = mock.Mock(side_effect=RuntimeError("boom"))
        fake = mock.Mock(classes=boom, deployment=lambda *a: {"nodes": [{"id": "n"}], "edges": []},
                         usecases=boom, activity=boom)

        def imp(name):
            if name.endswith("system_behave"):
                return fake
            raise ImportError(name)
        with mock.patch.object(system_v2.importlib, "import_module", side_effect=imp):
            arch, _ = self._extend()
        self.assertTrue(any("classes failed: boom" in w for w in arch["warnings"]))
        self.assertTrue(any("er unavailable" in w for w in arch["warnings"]))
        by = {r["id"]: r for r in arch["catalog"]}
        self.assertTrue(by["deployment"]["available"])
        self.assertFalse(by["classes"]["available"])
        self.assertIsNotNone(arch["views"])


if __name__ == "__main__":
    unittest.main()
