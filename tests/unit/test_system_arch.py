"""System views (R10.33): roadmap/services/system_arch.py derives the C4, module, layer, data and flow views from a
project's code. A temp project (no git, so no cache) with a Python package, a web folder and a tests folder checks:
Python absolute and relative imports and JS relative imports become module and component edges; tests stay out;
sqlite3 and subprocess with "git" become external systems; http.server marks the server container; fetch("/api")
links the web container to it; data file names become stores with reads / writes; derived flows start at entries;
docs/system.json containers and flows override; a symlinked source file is never read; every view edge joins nodes
of that view, and every node has details."""

import json
import os
import shutil
import tempfile
import unittest

from roadmap.services import system, system_arch

FILES = {
    "app/__init__.py": "",
    "app/__main__.py": "from app import cli\ncli.main()\n",
    "app/cli.py": "import sys\nfrom app.services import jobs\n\ndef main():\n    jobs.run()\n",
    "app/server.py": "from http.server import ThreadingHTTPServer\nfrom .services import jobs\n",
    "app/services/__init__.py": "",
    "app/services/jobs.py": ("import json, subprocess, sqlite3\nfrom ..core import fmt\nfrom . import store\n"
                             "\ndef run():\n    subprocess.run(['git', 'log'])\n"
                             "    save('jobs.json')\n\ndef save(x):\n    write_atomic(x)\n"),
    "app/services/store.py": "import sqlite3\nSQL = 'CREATE TABLE IF NOT EXISTS jobs (id)'\nNAME = 'tasks.json'\n",
    "app/core/__init__.py": "",
    "app/core/fmt.py": "import requests\nimport yaml\n",
    "web/index.html": "<script type=module src=js/app.js></script>",
    "web/js/app.js": "import { draw } from './views/main.js';\nfetch('/api/v1/x').then(draw);\n",
    "web/js/views/main.js": "import { esc } from '../dom.js';\nimport React from 'react';\nexport function draw() {}\n",
    "web/js/dom.js": "export function esc(s) { return s; }\n",
    "tests/test_jobs.py": "from app.services import jobs\nfrom app.core import fmt\n",
    "docs/readme.md": "# x\n",
}


class SystemArchTest(unittest.TestCase):
    def setUp(self):
        self.root = os.path.realpath(tempfile.mkdtemp())
        for rel, text in FILES.items():
            path = os.path.join(self.root, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
        self.secret = tempfile.mkdtemp()
        with open(os.path.join(self.secret, "leak.py"), "w", encoding="utf-8") as fh:
            fh.write("import leakedpackage\n")
        os.symlink(os.path.join(self.secret, "leak.py"), os.path.join(self.root, "app", "leak.py"))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)
        shutil.rmtree(self.secret, ignore_errors=True)

    def arch(self):
        mapped = system.load(self.root, use_cache=False)
        commits = [{"sha": "a" * 40, "at": 1790000000, "subject": "R1: jobs", "tasks": ["R1"],
                    "files": ["app/services/jobs.py"]}]
        jobs = [{"id": "j1", "task": "R1", "model": "opus", "status": "running", "title": "t", "started": "x"}]
        return system_arch.analyze(self.root, mapped, commits, jobs, use_cache=False)

    def test_module_edges_from_python_and_js_imports(self):
        mods = self.arch()["views"]["modules"]
        pairs = {(e["from"], e["to"]) for e in mods["edges"]}
        self.assertIn(("m:app/services", "m:app/core"), pairs)  # relative ..core
        self.assertIn(("m:app", "m:app/services"), pairs)  # absolute app.services
        self.assertIn(("m:web/js", "m:web/js/views"), pairs)
        self.assertIn(("m:web/js/views", "m:web/js"), pairs)
        self.assertNotIn("m:tests", {n["id"] for n in mods["nodes"]})
        self.assertTrue(all(n["group"].startswith("t") for n in mods["nodes"]))
        self.assertIn("Tier 1", mods["groups"][0]["label"])

    def test_externals_and_stores(self):
        a = self.arch()
        ctx = a["views"]["context"]
        ids = {n["id"] for n in ctx["nodes"]}
        self.assertTrue({"p:user", "sys", "x:sqlite", "x:git", "x:http-apis"} <= ids, ids)
        self.assertNotIn("leakedpackage", json.dumps(a))
        data = a["views"]["data"]
        labels = {(e["from"].split(":")[0], e["to"], e["label"]) for e in data["edges"]}
        self.assertIn(("c", "s:jobs-json", "reads, writes"), labels)
        self.assertIn(("c", "s:tasks-json", "reads"), labels)
        self.assertIn("jobs", a["details"]["x:sqlite"]["notes"] + json.dumps(a["details"]["s:tasks-json"]))
        self.assertEqual(a["details"]["s:tasks-json"]["tables"], ["jobs"])

    def test_containers_server_web_and_http_edge(self):
        cont = self.arch()["views"]["containers"]
        nodes = {n["id"]: n for n in cont["nodes"]}
        web = [n for n in nodes.values() if "Web UI" in n["label"]]
        py = [n for n in nodes.values() if n["label"] == "app (Python)"]
        self.assertEqual(len(web), 1)
        self.assertEqual(len(py), 1)
        self.assertIn("HTTP server", py[0]["sub"])
        self.assertIn("CLI", py[0]["sub"])
        edges = {(e["from"], e["to"]): e["label"] for e in cont["edges"]}
        self.assertEqual(edges.get((web[0]["id"], py[0]["id"])), "HTTP JSON /api")
        self.assertIn(("p:user", web[0]["id"]), edges)

    def test_views_are_consistent_and_detailed(self):
        a = self.arch()
        for name, view in a["views"].items():
            ids = {n["id"] for n in view["nodes"]}
            groups = {g["id"] for g in view["groups"]}
            for e in view["edges"]:
                self.assertIn(e["from"], ids, (name, e))
                self.assertIn(e["to"], ids, (name, e))
            for n in view["nodes"]:
                self.assertIn(n["group"], groups, (name, n))
                self.assertIn(n["id"], a["details"], (name, n["id"]))
        comp = next(d for d in a["details"].values() if d.get("kind") == "component" and d["commits30"])
        self.assertEqual(comp["jobs"][0]["id"], "j1")
        self.assertEqual(comp["files"][0]["commits"], 1)
        self.assertGreater(a["stats"]["imports"], 5)

    def test_derived_flows_start_at_entries(self):
        flows = self.arch()["flows"]
        self.assertTrue(flows)
        self.assertTrue(all(f["derived"] for f in flows))
        self.assertEqual(flows[0]["steps"][0]["from"], "p:user")

    def test_system_json_containers_and_flows(self):
        decl = {"version": 1, "layers": ["ui", "core"],
                "components": [{"id": "web", "name": "Web", "layer": "ui", "files": ["web/**"]},
                               {"id": "app", "name": "App", "layer": "core", "files": ["app/**"]}],
                "edges": [{"from": "web", "to": "app", "label": "fetch", "kind": "call"}],
                "containers": [{"id": "spa", "name": "SPA", "tech": "JS", "components": ["web"]},
                               {"id": "srv", "name": "Server", "components": ["app", "ghost"]}],
                "flows": [{"id": "load", "name": "Load", "steps": [
                    {"from": "user", "to": "web", "label": "open"},
                    {"from": "web", "to": "app", "label": "GET"},
                    {"from": "app", "to": "web", "label": "200", "reply": True}]}]}
        with open(os.path.join(self.root, "docs", "system.json"), "w", encoding="utf-8") as fh:
            json.dump(decl, fh)
        a = self.arch()
        names = [n["label"] for n in a["views"]["containers"]["nodes"] if n["id"].startswith("k:")]
        self.assertEqual(names, ["SPA", "Server"])
        flow = a["flows"][0]
        self.assertEqual((flow["name"], flow["derived"]), ("Load", False))
        self.assertEqual([p["id"] for p in flow["participants"]], ["p:user", "c:web", "c:app"])
        self.assertTrue(flow["steps"][2]["reply"])
        layers = a["views"]["layers"]
        self.assertEqual([g["id"] for g in layers["groups"]][:2], ["l:ui", "l:core"])
        comps = a["views"]["components"]
        self.assertIn({"from": "c:web", "to": "c:app", "label": "fetch", "kind": "call", "count": 0,
                       "derived": False}, comps["edges"])


if __name__ == "__main__":
    unittest.main()
