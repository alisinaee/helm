"""The System context menu (R11.105): web/js/views/system-menu.js pure helpers: items per kind, disabled Tasks at 0,
progress text, escaping, inline task list, placeMenu clamping at all four edges, keyboard plan (nextIndex)."""

import json
import os
import shutil
import subprocess
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(os.path.dirname(TESTS), "web")
NODE = shutil.which("node")
SCRIPT = r"""
const { pathToFileURL } = await import("node:url");
const m = await import(pathToFileURL(process.argv[1] + "/js/views/system-menu.js").href);
const acts = (t, d, o) => m.menuItems(t, d, o).map((i) => i.action);
const d = { board: [{ id: "R1", title: "Fix <b>", status: "doing" }], work: [{ id: "W3", title: "Card", status: "open" }],
  progress: { done: 1, total: 4, pct: 25 } };
const many = { board: Array.from({ length: 14 }, (_, i) => ({ id: "R" + i, title: "t", status: "todo" })), work: [] };
const box = { x: 0, y: 0, w: 500, h: 400 }, size = { w: 100, h: 80 };
const it = [{ disabled: false }, { disabled: true }, { disabled: false }];
console.log(JSON.stringify({
  comp: acts({ id: "c:a", kind: "component", group: false }, d, { expanded: false, canDrill: false }),
  grp: acts({ id: "k:a", kind: "container", group: true }, d, { expanded: true, canDrill: true }),
  grpLabel: m.menuItems({ id: "g", kind: "group", group: true }, d, { expanded: true }).find((i) => i.action === "toggle").label,
  tasks: m.menuItems({ id: "c:a", kind: "component" }, d, {}).find((i) => i.action === "tasks"),
  tasks0: m.menuItems({ id: "c:a", kind: "component" }, null, {}).find((i) => i.action === "tasks"),
  html: m.menuHtml({ id: "c:a", label: "A <script>", kind: "component" }, d, { pid: "p1" }),
  open: m.menuHtml({ id: "c:a", label: "A", kind: "component" }, d, { pid: "p1", showTasks: true }),
  many: m.menuHtml({ id: "c:a", label: "A", kind: "component" }, many, { pid: "p1", showTasks: true }),
  noProg: m.menuHtml({ id: "c:a", label: "A", kind: "component" }, { progress: { done: 0, total: 0, pct: 0 } }, {}),
  place: [m.placeMenu({ x: 10, y: 10 }, size, box), m.placeMenu({ x: 480, y: 10 }, size, box),
    m.placeMenu({ x: 10, y: 390 }, size, box), m.placeMenu({ x: -5, y: -5 }, size, box),
    m.placeMenu({ x: 600, y: 600 }, size, { x: 20, y: 30, w: 500, h: 400 })],
  keys: [m.nextIndex(it, 0, "ArrowDown"), m.nextIndex(it, 2, "ArrowDown"), m.nextIndex(it, 0, "ArrowUp"),
    m.nextIndex(it, 1, "Home"), m.nextIndex(it, 0, "End"), m.nextIndex(it, 0, "x")],
}));
"""


@unittest.skipIf(NODE is None, "node is not installed")
class SystemMenuTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        proc = subprocess.run([NODE, "--experimental-default-type=module", "-e", SCRIPT, WEB],
                              capture_output=True, text=True, check=False, timeout=60)
        if proc.returncode != 0:
            raise AssertionError(proc.stderr)
        cls.out = json.loads(proc.stdout)

    def test_items_per_kind(self):
        base = ["details", "tasks", "work", "copy", "ask"]
        self.assertEqual(self.out["comp"], base + ["views"])
        self.assertEqual(self.out["grp"], base + ["toggle", "drill", "views"])
        self.assertEqual(self.out["grpLabel"], "Collapse")

    def test_tasks_disabled_at_zero(self):
        self.assertEqual(self.out["tasks"]["label"], "Tasks (2)")
        self.assertFalse(self.out["tasks"].get("disabled"))
        self.assertEqual(self.out["tasks0"]["label"], "Tasks (0)")
        self.assertTrue(self.out["tasks0"]["disabled"])

    def test_html_header_progress_and_escape(self):
        h = self.out["html"]
        self.assertIn('role="menu"', h)
        self.assertIn("A &lt;script&gt;", h)
        self.assertNotIn("<script>", h)
        self.assertIn("1/4 done", h)
        self.assertIn('data-sys-menu="details" data-sys-id="c:a"', h)
        self.assertIn("sys-menu-sep", h)
        self.assertIn(" disabled", self.out["noProg"])
        self.assertNotIn("done</span>", self.out["noProg"])
        self.assertNotIn("style=", h)

    def test_inline_list(self):
        self.assertNotIn("sys-menu-list", self.out["html"])
        o = self.out["open"]
        self.assertIn("sys-menu-list", o)
        self.assertIn("Fix &lt;b&gt;", o)
        self.assertIn("#/p/p1/work/i/W3", o)
        self.assertIn("#/p/p1/planner?f=R1", o)
        self.assertEqual(self.out["many"].count('class="sys-menu-row"'), 12)
        self.assertIn("+2 more", self.out["many"])

    def test_place_clamps_all_edges(self):
        a, right, bottom, topleft, off = self.out["place"]
        self.assertEqual(a, {"x": 10, "y": 10})
        self.assertEqual(right, {"x": 400, "y": 10})
        self.assertEqual(bottom, {"x": 10, "y": 320})
        self.assertEqual(topleft, {"x": 0, "y": 0})
        self.assertEqual(off, {"x": 420, "y": 350})

    def test_keyboard_plan(self):
        self.assertEqual(self.out["keys"], [2, 0, 2, 0, 2, 0])


if __name__ == "__main__":
    unittest.main()
