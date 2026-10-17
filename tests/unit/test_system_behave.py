"""R11.103 System v2 behaviour diagrams: classes, deployment, use cases, activity (temp dir fixtures)."""

import json
import os
import tempfile
import unittest

from roadmap.services import system, system_behave as sb


def write(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = os.path.realpath(tmp.name)
        self.files = []

    def put(self, rel, text):
        write(self.root, rel, text)
        self.files.append(rel)

    def mapped(self, comps=None):
        comps = comps or [{"id": "app", "name": "App", "files": ["**"], "kind": "module"}]
        return {"components": comps}

    def run_fn(self, fn, comps=None):
        return fn(self.root, sorted(self.files), self.mapped(comps))


class ClassesTest(Base):
    def test_python_inheritance_and_js(self):
        self.put("pkg/a.py", "class Base:\n    x = 1\n    def go(self): pass\n    def _hid(self): pass\n"
                 "class Child(Base):\n    def __init__(self):\n        self.name = 1\n    def run(self): pass\n")
        self.put("web/m.js", "export class Foo extends Bar {}\nexport function helper() {}\n"
                 "export async function load() {}\n")
        self.put("tests/test_a.py", "class Skip: pass\n")
        d = self.run_fn(sb.classes)
        labels = {n["label"]: n for n in d["nodes"]}
        self.assertNotIn("Skip", labels)
        self.assertEqual(labels["Base"]["methods"], ["go"])
        self.assertEqual(labels["Base"]["attrs"], ["x"])
        self.assertEqual(labels["Child"]["attrs"], ["name"])
        self.assertEqual(labels["m.js"]["kind"], "module")
        self.assertEqual(labels["m.js"]["methods"], ["helper", "load"])
        ext = [(e["from"], e["to"]) for e in d["edges"] if e["kind"] == "extends"]
        self.assertEqual(ext, [(labels["Child"]["id"], labels["Base"]["id"])])
        self.assertEqual(d["groups"], [{"id": "app", "label": "App"}])

    def test_cap_and_override(self):
        self.put("big.py", "".join("class C%d: pass\n" % i for i in range(120)))
        write(self.root, "docs/system.json", json.dumps(
            {"classes": {"nodes": [{"id": "x", "label": "X", "sub": "", "kind": "class", "group": "app",
                                    "attrs": [], "methods": []}],
                         "edges": [{"from": "x", "to": "nope", "kind": "uses", "label": ""}]}}))
        d = self.run_fn(sb.classes)
        self.assertEqual(len(d["nodes"]), 81)
        self.assertIn("x", [n["id"] for n in d["nodes"]])
        self.assertEqual(d["edges"], [])

    def test_import_edges_between_module_nodes(self):
        self.put("web/js/a.js", "import { load } from './b.js';\nimport React from 'react';\n"
                 "export function run() { return load(); }\n")
        self.put("web/js/b.js", "export function load() { return 1; }\n")
        self.put("web/js/c.js", "export function other() { return 2; }\n")
        d = self.run_fn(sb.classes)
        ids = {n["id"] for n in d["nodes"]}
        imports = [(e["from"], e["to"]) for e in d["edges"] if e["kind"] == "imports"]
        self.assertTrue(d["edges"])
        self.assertIn(("mod:web/js/a.js", "mod:web/js/b.js"), imports)
        self.assertEqual(len(imports), 1)
        for e in d["edges"]:
            self.assertIn(e["from"], ids)
            self.assertIn(e["to"], ids)


class DeploymentTest(Base):
    def test_sources(self):
        self.put("Makefile", "serve:\n\tpython3 -m http.server 9000\ntest:\n\tpytest\n")
        self.put("deploy/com.x.plist", "<?xml version='1.0'?><plist><dict><key>Label</key><string>com.x.helper"
                 "</string><key>ProgramArguments</key><array><string>/bin/x</string><string>run</string></array>"
                 "</dict></plist>")
        self.put("package.json", json.dumps({"scripts": {"dev": "vite", "build": "x"}}))
        self.put("bin/tool", "#!/bin/sh\n")
        self.put("srv.py", "PORT = 8780\n")
        self.put("docs/tasks.json", "{}")
        os.makedirs(os.path.join(self.root, ".git"))
        d = self.run_fn(sb.deployment)
        ids = {n["id"]: n for n in d["nodes"]}
        self.assertEqual(ids["dev"]["kind"], "device")
        self.assertIn("proc:make-serve", ids)
        self.assertNotIn("proc:make-test", ids)
        self.assertEqual(ids["proc:deploy/com.x.plist"]["label"], "com.x.helper")
        self.assertEqual(ids["proc:deploy/com.x.plist"]["sub"], "/bin/x run")
        self.assertIn("proc:npm-dev", ids)
        self.assertNotIn("proc:npm-build", ids)
        self.assertIn("proc:bin/tool", ids)
        self.assertEqual(ids["store:docs/tasks.json"]["kind"], "store")
        self.assertEqual(ids["ext:browser"]["kind"], "external")
        http = [e for e in d["edges"] if e["from"] == "ext:browser"]
        self.assertEqual(http[0]["label"], "HTTP :8780")
        self.assertTrue(any(e["to"] == "store:docs/tasks.json" and e["kind"] == "data" for e in d["edges"]))

    def test_override(self):
        write(self.root, "docs/system.json", json.dumps(
            {"deployment": {"nodes": [{"id": "cloud", "label": "Cloud", "sub": "", "kind": "device", "group": "dev"}]}}))
        d = self.run_fn(sb.deployment)
        self.assertIn("cloud", [n["id"] for n in d["nodes"]])


class UsecasesTest(Base):
    def test_sources_and_links(self):
        self.put("cli.py", "def reg(sub):\n    sub.add_parser('board', help='show the board')\n")
        self.put("routes.py", "ROUTES = [\n(re.compile(r\"/api/v1/health\"), (\"GET\",), h),\n"
                 "(re.compile(r\"/api/v1/projects/(?P<id>[^/]+)/system\"), (\"GET\", \"POST\"), s),\n]\n")
        self.put("web/js/routes.js", "export const SECTIONS = [\n  { id: \"overview\", label: \"Overview\", module: \"a\" },\n"
                 "  { id: \"git\", label: \"Git\" },\n];\n")
        comps = [{"id": "app", "name": "App", "files": ["**"], "kind": "module"},
                 {"id": "bot", "name": "Bot", "files": ["nothing/**"], "kind": "agent"}]
        d = self.run_fn(sb.usecases, comps)
        by = {c["id"]: c for c in d["cases"]}
        self.assertEqual(by["cli:board"]["group"], "CLI")
        self.assertEqual(by["cli:board"]["sub"], "show the board")
        self.assertEqual(by["http:GET /projects/{id}/system"]["group"], "HTTP API")
        self.assertIn("http:POST /projects/{id}/system", by)
        self.assertEqual(by["ui:git"]["label"], "Git")
        links = {(x["actor"], x["case"]) for x in d["links"]}
        self.assertIn(("person", "cli:board"), links)
        self.assertIn(("person", "ui:git"), links)
        self.assertIn(("bot", "cli:board"), links)
        self.assertNotIn(("person", "http:GET /health"), links)
        self.assertEqual([a["id"] for a in d["actors"]], ["person", "bot"])

    def test_cap_and_override(self):
        self.put("cli.py", "def reg(s):\n" + "".join("    s.add_parser('c%d')\n" % i for i in range(90)))
        write(self.root, "docs/system.json", json.dumps(
            {"usecases": {"cases": [{"id": "extra", "label": "E", "group": "CLI", "sub": ""}],
                          "links": [{"actor": "person", "case": "extra"}]}}))
        d = self.run_fn(sb.usecases)
        self.assertEqual(len(d["cases"]), 61)
        self.assertIn({"actor": "person", "case": "extra"}, d["links"])


class ActivityTest(Base):
    SRC = ("def main(x):\n    setup()\n    if x:\n        a.b()\n    else:\n        raise ValueError('no')\n"
           "    for i in x:\n        step(i)\n    try:\n        risky()\n    except OSError:\n        log()\n"
           "    return 1\n\ndef _private():\n    pass\n")

    def test_steps(self):
        self.put("m.py", self.SRC)
        d = self.run_fn(sb.activity)
        self.assertEqual(len(d["items"]), 1)
        item = d["items"][0]
        self.assertEqual((item["name"], item["file"], item["line"], item["component"]), ("main", "m.py", 1, "app"))
        kinds = [s["kind"] for s in item["steps"]]
        for k in ("start", "action", "decision", "loop", "error", "end", "merge"):
            self.assertIn(k, kinds)
        labels = [s["label"] for s in item["steps"]]
        self.assertIn("a.b", labels)
        self.assertIn("setup", labels)
        edge_labels = {e["label"] for e in item["edges"]}
        self.assertTrue({"yes", "no", "next"} <= edge_labels)
        ids = {s["id"] for s in item["steps"]}
        self.assertTrue(all(e["from"] in ids and e["to"] in ids for e in item["edges"]))

    def test_collapse_and_caps(self):
        self.put("a.py", "def main():\n" + "".join("    f%d()\n" % i for i in range(10)))
        self.put("b.py", "def run():\n" + "".join("    if x%d:\n        g()\n" % i for i in range(60)))
        d = self.run_fn(sb.activity)
        by = {i["name"]: i for i in d["items"]}
        self.assertTrue(any("6 more steps" in s["label"] for s in by["main"]["steps"]))
        self.assertLessEqual(len(by["run"]["steps"]), 40)
        self.assertEqual(by["run"]["steps"][-1]["kind"], "end")

    def test_item_cap_js_skipped_and_override(self):
        comps = [{"id": "c%d" % i, "name": "C", "files": ["d%d/**" % i], "kind": "module"} for i in range(30)]
        for i in range(30):
            self.put("d%d/m.py" % i, "def main():\n    go()\n")
        self.put("x.js", "export function main() { go(); }\n")
        write(self.root, "docs/system.json", json.dumps(
            {"activities": [{"id": "mine", "component": "app", "name": "Mine", "file": "", "line": 0,
                             "steps": [], "edges": []}]}))
        d = self.run_fn(sb.activity, comps)
        self.assertEqual(len(d["items"]), 25)
        self.assertNotIn("x.js", [i["file"] for i in d["items"]])
        self.assertEqual(d["items"][-1]["id"], "mine")


if __name__ == "__main__":
    unittest.main()
