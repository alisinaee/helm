"""System v2 diagram renderers (R11.107), run in node over web/js/graph/sysdiagrams.js.

Each renderer on a small fixture: finite w/h, expected ids and labels, no two node boxes overlap, every node box lies
inside the drawing, text is escaped, selected/near options style nodes, empty input gives "Nothing to draw", and
60 entities / 80 classes render in under 50 ms.
"""

import json
import os
import re
import shutil
import subprocess
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(os.path.dirname(TESTS), "web")
NODE = shutil.which("node")

SCRIPT = r"""
(async () => {
  const { readFileSync } = await import("node:fs");
  const { join } = await import("node:path");
  const { pathToFileURL } = await import("node:url");
  const m = await import(pathToFileURL(join(process.argv[1], "js", "graph", "sysdiagrams.js")).href);
  const input = JSON.parse(readFileSync(0, "utf8"));
  const out = {};
  for (const [name, c] of Object.entries(input)) {
    const fn = m[c.fn];
    const r = fn(c.data, c.opts ? { selected: c.opts.selected, near: c.opts.near ? new Set(c.opts.near) : null,
      open: c.opts.open ? new Set(c.opts.open) : undefined, aspect: c.opts.aspect } : undefined);
    let ms = Infinity;
    if (c.time) for (let i = 0; i < 5; i++) {
      const t = process.hrtime.bigint();
      fn(c.data);
      ms = Math.min(ms, Number(process.hrtime.bigint() - t) / 1e6);
    }
    out[name] = { ...r, ms };
  }
  console.log(JSON.stringify(out));
})();
"""

ER = {"entities": [
    {"id": "task", "label": "Task", "source": "sql", "file": "a.sql", "parent": "item",
     "attrs": [{"name": "id", "type": "int", "pk": True}, {"name": "project_id", "type": "int", "fk": True},
               {"name": "title", "type": "text"}]},
    {"id": "project", "label": "Project <b>", "attrs": [{"name": "id", "type": "int", "pk": True}]},
    {"id": "item", "label": "Item", "attrs": []},
    {"id": "log", "label": "Log", "attrs": [{"name": "task_id", "type": "int", "fk": True}]}],
    "relations": [{"from": "project", "to": "task", "label": "has tasks in the project", "card": "1-n"},
                  {"from": "log", "to": "task", "card": "n-n", "implied": True},
                  {"from": "task", "to": "task", "label": "blocks", "card": "1-1"},
                  {"from": "task", "to": "ghost"}]}
STATES = {"id": "m", "name": "m", "states": ["todo", "doing", "done", "stuck"], "initial": "todo",
          "transitions": [{"from": "todo", "to": "doing", "label": "start"}, {"from": "doing", "to": "done", "label": "ok"},
                          {"from": "doing", "to": "doing", "label": "tick", "guessed": True},
                          {"from": "doing", "to": "todo", "label": "back"}, {"from": "todo", "to": "doing", "label": "again"}]}
UC = {"actors": [{"id": "person", "label": "Person", "kind": "person"}, {"id": "agent", "label": "Agent <x>", "kind": "agent"}],
      "groups": [{"id": "cli", "label": "CLI"}, {"id": "http", "label": "HTTP API"}],
      "cases": [{"id": "uc1", "label": "Add a task to the board quickly", "group": "cli"}, {"id": "uc2", "label": "List", "group": "cli"},
                {"id": "uc3", "label": "GET /api/tasks", "group": "http"}, {"id": "uc4", "label": "Loose"}],
      "links": [{"actor": "person", "case": "uc1"}, {"actor": "agent", "case": "uc3"}, {"actor": "agent", "case": "nope"}]}
ACT = {"id": "a", "steps": [
    {"id": "s", "kind": "start", "label": "start"}, {"id": "a1", "kind": "action", "label": "Read file"},
    {"id": "d", "kind": "decision", "label": "valid?"}, {"id": "a2", "kind": "action", "label": "Parse"},
    {"id": "er", "kind": "error", "label": "Raise <bad>"}, {"id": "m", "kind": "merge", "label": ""},
    {"id": "e", "kind": "end", "label": "end"}],
    "edges": [{"from": "s", "to": "a1"}, {"from": "a1", "to": "d"}, {"from": "d", "to": "a2", "label": "yes"},
              {"from": "d", "to": "er", "label": "no"}, {"from": "a2", "to": "m"}, {"from": "er", "to": "m"},
              {"from": "m", "to": "e"}, {"from": "m", "to": "a1", "label": "retry"}]}
DEP = {"groups": [{"id": "mac", "label": "Mac"}, {"id": "cloud", "label": "Cloud"}],
       "nodes": [{"id": "srv", "label": "helm serve", "sub": ":8780", "kind": "process", "group": "mac"},
                 {"id": "db", "label": "tasks.json", "kind": "store", "group": "mac"},
                 {"id": "api", "label": "Anthropic API", "kind": "external", "group": "cloud"},
                 {"id": "free", "label": "Browser", "kind": "external"}],
       "edges": [{"from": "srv", "to": "db", "label": "writes"}, {"from": "free", "to": "srv", "label": "http"},
                 {"from": "srv", "to": "api"}]}
CLS = {"groups": [{"id": "core", "label": "Core"}, {"id": "web", "label": "Web"}],
       "nodes": [{"id": "Base", "label": "Base", "kind": "class", "group": "core", "attrs": ["a", "b"], "methods": ["run()"]},
                 {"id": "Child", "label": "Child <T>", "kind": "class", "group": "core",
                  "attrs": ["x%d" % i for i in range(12)], "methods": ["m%d()" % i for i in range(3)]},
                 {"id": "fn", "label": "helper", "kind": "function", "group": "web", "attrs": [], "methods": []}],
       "edges": [{"from": "Child", "to": "Base", "kind": "extends"}, {"from": "fn", "to": "Child", "kind": "uses", "label": "calls"}]}


def big_er(n=60):
    ents = [{"id": "e%d" % i, "label": "Entity %d" % i,
             "attrs": [{"name": "col_%d" % j, "type": "text", "pk": j == 0, "fk": j == 1} for j in range(6)]} for i in range(n)]
    rels = [{"from": "e%d" % i, "to": "e%d" % ((i * 7 + 3) % n), "label": "r", "card": "1-n"} for i in range(n)]
    return {"entities": ents, "relations": rels}


def big_cls(n=80):
    nodes = [{"id": "C%d" % i, "label": "Class%d" % i, "kind": "class", "group": "g%d" % (i % 5),
              "attrs": ["a%d" % j for j in range(4)], "methods": ["m%d()" % j for j in range(10)]} for i in range(n)]
    edges = [{"from": "C%d" % i, "to": "C%d" % (i // 2), "kind": "extends" if i % 3 else "uses"} for i in range(1, n)]
    return {"groups": [{"id": "g%d" % i, "label": "G%d" % i} for i in range(5)], "nodes": nodes, "edges": edges}


def mod_cls(mods=40, per=6):
    nodes = [{"id": "M%d.C%d" % (m, i), "label": "C%d" % i, "kind": "class", "group": "m%d" % m,
              "attrs": ["a"], "methods": ["f()"]} for m in range(mods) for i in range(per)]
    edges = [{"from": "M%d.C0" % m, "to": "M%d.C1" % ((m + 1) % mods), "kind": "uses"} for m in range(mods)]
    edges += [{"from": "M%d.C%d" % (m, i), "to": "M%d.C0" % ((m + 2) % mods), "kind": "uses"}
              for m in range(mods) for i in (2, 3)]
    return {"groups": [{"id": "m%d" % m, "label": "mod%d" % m} for m in range(mods)], "nodes": nodes, "edges": edges}


CASES = {
    "er": {"fn": "erSvg", "data": ER}, "state": {"fn": "stateSvg", "data": STATES},
    "uc": {"fn": "usecaseSvg", "data": UC}, "act": {"fn": "activitySvg", "data": ACT},
    "dep": {"fn": "deploymentSvg", "data": DEP}, "cls": {"fn": "classSvg", "data": CLS},
    "er_sel": {"fn": "erSvg", "data": ER, "opts": {"selected": "task", "near": ["task", "log"]}},
    "bigER": {"fn": "erSvg", "data": big_er(), "time": True},
    "bigCls": {"fn": "classSvg", "data": big_cls(), "time": True},
    "modCls": {"fn": "classSvg", "data": mod_cls(), "opts": {"aspect": 1.78}},
    "five": {"fn": "classSvg", "data": mod_cls(5, 14), "opts": {"aspect": 1300 / 560}},
    "modOpen": {"fn": "classSvg", "data": mod_cls(), "opts": {"aspect": 1.78, "open": ["m3"]}},
}
for _fn in ("erSvg", "stateSvg", "usecaseSvg", "activitySvg", "deploymentSvg", "classSvg"):
    CASES["empty_" + _fn] = {"fn": _fn, "data": {}}
    CASES["null_" + _fn] = {"fn": _fn, "data": None}

IDS = {"er": ["task", "project", "item", "log"], "state": ["todo", "doing", "done", "stuck"],
       "uc": ["person", "agent", "uc1", "uc2", "uc3", "uc4"], "act": ["s", "a1", "d", "a2", "er", "m", "e"],
       "dep": ["srv", "db", "api", "free"], "cls": ["Base", "Child", "fn"]}


def overlap(a, b):
    return a["x"] < b["x"] + b["w"] and b["x"] < a["x"] + a["w"] and a["y"] < b["y"] + b["h"] and b["y"] < a["y"] + a["h"]


@unittest.skipUnless(NODE, "node is not installed")
class SysDiagramsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        p = subprocess.run([NODE, "-e", SCRIPT, WEB], input=json.dumps(CASES), capture_output=True, text=True, timeout=60)
        if p.returncode:
            raise RuntimeError(p.stderr)
        cls.out = json.loads(p.stdout)

    def test_sizes_and_boxes(self):
        for name in IDS:
            r = self.out[name]
            self.assertTrue(r["w"] > 24 and r["h"] > 24 and r["w"] < 5000 and r["h"] < 5000, name)
            ids = [b["id"] for b in r["boxes"]]
            for i in IDS[name]:
                self.assertIn(i, ids, name)
                self.assertIn('data-sys="%s"' % i, r["inner"], name)
            self.assertEqual(len(ids), len(set(ids)), name)
            for a in r["boxes"]:
                self.assertTrue(a["x"] >= 0 and a["y"] >= 0 and a["x"] + a["w"] <= r["w"] and a["y"] + a["h"] <= r["h"], (name, a))
            for i, a in enumerate(r["boxes"]):
                for b in r["boxes"][i + 1:]:
                    self.assertFalse(overlap(a, b), (name, a, b))

    def test_markup_contract(self):
        for name in IDS:
            inner = self.out[name]["inner"]
            self.assertIn("<defs>", inner)
            self.assertNotIn("<svg", inner)
            self.assertNotIn(" style=", inner)
            self.assertNotIn(" onclick", inner)
            for node in re.findall(r"<g class=\"wfg-n[^>]*>", inner):
                for attr in ("data-sys=", "data-wf-item=", 'tabindex="-1"', 'role="button"', "aria-label="):
                    self.assertIn(attr, node)
            for mid in re.findall(r'url\(#(sysd-[\w-]+)\)', inner):
                self.assertIn('id="%s"' % mid, inner)
            self.assertNotRegex(inner, r'(fill|stroke)="#')

    def test_labels_and_shapes(self):
        self.assertIn("Project &lt;b&gt;", self.out["er"]["inner"])
        self.assertNotIn("<b>", self.out["er"]["inner"])
        self.assertIn("PK", self.out["er"]["inner"])
        self.assertIn("FK", self.out["er"]["inner"])
        self.assertIn("sysd-many", self.out["er"]["inner"])
        self.assertIn("sysd-tri", self.out["er"]["inner"])
        self.assertIn("stroke-dasharray", self.out["er"]["inner"])
        self.assertIn("start", self.out["state"]["inner"])
        self.assertIn("<circle", self.out["state"]["inner"])
        self.assertIn("Agent &lt;x&gt;", self.out["uc"]["inner"])
        self.assertIn("<ellipse", self.out["uc"]["inner"])
        self.assertIn("HTTP API", self.out["uc"]["inner"])
        self.assertIn("var(--danger)", self.out["act"]["inner"])
        self.assertIn("Raise &lt;bad&gt;", self.out["act"]["inner"])
        self.assertIn("valid?", self.out["act"]["inner"])
        self.assertIn("<polygon", self.out["dep"]["inner"])
        self.assertIn("stroke-dasharray", self.out["dep"]["inner"])
        self.assertIn("Child &lt;T&gt;", self.out["cls"]["inner"])
        self.assertIn("+4 more", self.out["cls"]["inner"])
        self.assertIn("sysd-open", self.out["cls"]["inner"])

    def test_modules_collapsed_by_default(self):
        r = self.out["modCls"]
        self.assertEqual(len(r["boxes"]), 40)
        self.assertTrue(all(b["id"].startswith("g:") for b in r["boxes"]))
        self.assertIn("6 classes", r["inner"])
        self.assertIn('aria-expanded="false"', r["inner"])
        self.assertIn('data-sys-tog="cls:m0"', r["inner"])
        self.assertGreater(r["w"] / r["h"], 1.2)
        self.assertLess(r["w"] / r["h"], 2.6)
        self.assertGreater(1600 / r["w"], 0.6)
        self.assertGreater(900 / r["h"], 0.6)
        for i, a in enumerate(r["boxes"]):
            for b in r["boxes"][i + 1:]:
                self.assertFalse(overlap(a, b))

    def test_modules_aggregate_edges(self):
        r = self.out["modCls"]
        self.assertEqual(r["inner"].count("<path class=\"sys-e"), 80)
        self.assertRegex(r["inner"], r'data-from="g:m0" data-to="g:m1"')
        self.assertIn("(2)", r["inner"])

    def test_five_modules_in_rows(self):
        r = self.out["five"]
        self.assertEqual(len(r["boxes"]), 5)
        ys = sorted({b["y"] for b in r["boxes"]})
        self.assertLessEqual(len(ys), 2)
        self.assertGreaterEqual(max(sum(1 for b in r["boxes"] if b["y"] == y) for y in ys), 3)
        self.assertRegex(r["inner"], r'data-from="g:m0" data-to="g:m1"')
        self.assertIn("uses mod2 (2)", r["inner"])

    def test_module_expand(self):
        r = self.out["modOpen"]
        ids = [b["id"] for b in r["boxes"]]
        self.assertIn("M3.C0", ids)
        self.assertNotIn("g:m3", ids)
        self.assertIn("g:m3", [b["id"] for b in r["bands"]])
        self.assertIn('aria-expanded="true"', r["inner"])
        self.assertEqual(len(ids), 39 + 6)
        for i, a in enumerate(r["boxes"]):
            for b in r["boxes"][i + 1:]:
                self.assertFalse(overlap(a, b))

    def test_selected_and_near(self):
        base = self.out["er"]["inner"]
        sel = self.out["er_sel"]["inner"]
        self.assertNotIn("wfg-dim", base)
        self.assertEqual(sel.count('class="wfg-n wfg-dim"'), 2)
        self.assertIn('aria-pressed="true"', sel)
        self.assertIn("var(--focus)", sel)
        self.assertNotIn("var(--focus)", base)

    def test_empty_input(self):
        for fn in ("erSvg", "stateSvg", "usecaseSvg", "activitySvg", "deploymentSvg", "classSvg"):
            for pre in ("empty_", "null_"):
                r = self.out[pre + fn]
                self.assertIn("Nothing to draw", r["inner"])
                self.assertEqual(r["boxes"], [])
                self.assertTrue(0 < r["w"] < 400 and 0 < r["h"] < 100)

    def test_deterministic_and_fast(self):
        self.assertLess(self.out["bigER"]["ms"], 50)
        self.assertLess(self.out["bigCls"]["ms"], 50)
        for name in ("bigER", "bigCls"):
            r = self.out[name]
            for i, a in enumerate(r["boxes"]):
                for b in r["boxes"][i + 1:]:
                    self.assertFalse(overlap(a, b), (name, a, b))
        self.assertEqual(len(self.out["bigER"]["boxes"]), 60)
        self.assertEqual(len(self.out["bigCls"]["boxes"]), 5)


if __name__ == "__main__":
    unittest.main()
