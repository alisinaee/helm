"""R11.7 shared section toolbar (web/js/toolbar.js, web/css/toolbar.css): node render of toolbarHtml from a config
plus static contract checks (a11y attributes, collapsed by default, storage in try/catch, no inline style or on*=,
the pattern doc and the checklist rule)."""

import json
import os
import re
import shutil
import subprocess
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WEB = os.path.join(REPO, "web")
TOOLBAR_JS = os.path.join(WEB, "js", "toolbar.js")

CFG = {
    "key": "work",
    "label": "Work toolbar",
    "views": [{"id": "board", "label": "Board", "current": True}, {"id": "list", "label": "List"}],
    "search": {"value": "", "placeholder": "Search tasks"},
    "groups": [
        {"id": "status", "label": "Status", "options": [
            {"token": "status:todo", "label": "To do", "on": True, "count": 4},
            {"token": "status:hold", "label": "Hold"}]},
        {"id": "model", "label": "Model", "options": [
            {"token": "model:haiku", "label": "Haiku", "on": True},
            {"token": "model:agy", "label": "agy <x>"}]},
    ],
    "actions": [{"id": "new", "label": "New task", "primary": True}, {"id": "a2", "label": "Two"},
                {"id": "a3", "label": "Three"}],
    "overflow": [{"id": "export", "label": "Export"}],
}


def read(*p):
    with open(os.path.join(REPO, *p), encoding="utf-8") as f:
        return f.read()


def render(cfgs):
    """Run toolbarHtml and the pure helpers in node for each config; return the parsed JSON list."""
    code = (
        "globalThis.window={localStorage:{getItem(){throw new Error('blocked')},setItem(){throw new Error('x')}}};"
        "import('file://" + TOOLBAR_JS + "').then(m=>{const cfgs=" + json.dumps(cfgs) + ";"
        "console.log(JSON.stringify({html:cfgs.map(c=>m.toolbarHtml(c)),count:m.activeCount(cfgs[0]),"
        "tog:[m.toggleToken('a,b','b'),m.toggleToken('a','c'),m.toggleToken('','a')],open:m.isOpen('work')}));})"
    )
    out = subprocess.run(["node", "--input-type=module", "-e", code], capture_output=True, text=True, timeout=30)
    if out.returncode:
        raise AssertionError(out.stderr)
    return json.loads(out.stdout)


@unittest.skipUnless(shutil.which("node"), "node missing")
class ToolbarRenderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        closed_empty = dict(CFG, key="Empty Key!", groups=[{"id": "s", "label": "S", "options": [
            {"token": "s:a", "label": "A"}]}], overflow=[], views=[{"id": "one", "label": "One"}], search=None)
        cls.out = render([CFG, dict(CFG, open=True), closed_empty])
        cls.html, cls.open_html, cls.empty = cls.out["html"]

    def test_helpers(self):
        self.assertEqual(self.out["count"], 2)
        self.assertEqual(self.out["tog"], ["a", "a,c", "a"])
        self.assertFalse(self.out["open"])  # storage that throws reads as closed

    def test_collapsed_by_default(self):
        self.assertRegex(self.html, r'data-tb-toggle="pop" aria-haspopup="dialog" aria-expanded="false"'
                         r' aria-controls="tb-work-pop"')
        self.assertRegex(self.html, r'<div class="tb-pop" id="tb-work-pop" role="dialog" aria-label="Filters" hidden>')
        self.assertIn('aria-expanded="true"', self.open_html)
        self.assertNotRegex(self.open_html, r'id="tb-work-pop"[^>]*hidden')

    def test_badge_and_applied_chips(self):
        self.assertIn('<span class="tb-count">2</span>', self.html)
        self.assertIn('aria-label="Filters, 2 active"', self.html)
        self.assertEqual(len(re.findall(r'class="tb-chip" data-tb-remove=', self.html)), 2)
        self.assertIn('aria-label="Remove filter Status: To do"', self.html)
        self.assertIn('class="tb-applied" role="group" aria-label="Active filters"', self.html)
        self.assertNotIn("tb-applied", self.empty)  # no active filter: no chip line
        self.assertNotIn("tb-count", self.empty)

    def test_rows_controls_and_escaping(self):
        self.assertEqual(len(re.findall(r'data-tb-view="', self.html)), 2)
        self.assertIn('aria-pressed="true" data-tb-view="board"', self.html)
        self.assertIn('data-focus="tb-work-v-list"', self.html)  # focus survives a view switch (dom.patch)
        self.assertIn("agy &lt;x&gt;", self.html)
        self.assertNotIn("<x>", self.html)
        self.assertEqual(len(re.findall(r'data-tb-act="a\d"|data-tb-act="new"', self.html)), 2)  # max 2 actions
        self.assertIn('aria-haspopup="menu"', self.html)
        self.assertIn('role="menuitem"', self.html)
        self.assertIn('data-tb-search', self.html)
        self.assertEqual(len(re.findall(r'type="checkbox" id="tb-work-o\d-\d"', self.html)), 4)
        self.assertIn('data-tb="empty-key-"', self.empty)
        self.assertNotIn("tb-seg", self.empty)  # a single view gets no switcher
        self.assertNotIn("tb-more", self.empty)
        self.assertNotIn("tb-search", self.empty)

    def test_many_views_become_a_select(self):
        many = dict(CFG, key="rules", views=[{"id": v, "label": v.title(), "current": v == "a"}
                                             for v in ("a", "b", "c", "d", "e")])
        h = render([many])["html"][0]
        self.assertNotIn("tb-seg-btn", h)
        self.assertRegex(h, r'<select class="tb-view-select" data-tb-view-select[^>]*>')
        self.assertIn('<option value="a" selected>A</option>', h)
        self.assertIn('<option value="e">E</option>', h)

    def test_popover_follows_filters_in_the_row(self):
        row = self.html.split('<div class="tb-row">', 1)[1].split('<div class="tb-acts">', 1)[0]
        self.assertLess(row.index('tb-filters'), row.index('tb-pop"'))
        self.assertIn('aria-haspopup="dialog"', self.html)

    def test_aria_controls_resolve(self):
        for h in (self.html, self.open_html, self.empty):
            ids = set(re.findall(r'\sid="([^"]+)"', h))
            for c in re.findall(r'aria-controls="([^"]+)"', h):
                self.assertIn(c, ids)

    def test_no_inline_style_or_handlers(self):
        for h in (self.html, self.open_html, self.empty):
            self.assertNotRegex(h, r'\sstyle\s*=|\son[a-z]{3,}\s*=')


class ToolbarStaticTest(unittest.TestCase):
    def test_js_contract(self):
        js = read("web", "js", "toolbar.js")
        for needle in ("rb.toolbar", "localStorage", "catch", "Escape", "Tab", "rb:toolbar", "aria-expanded",
                       "initToolbars", "openFilters", "focus()"):
            self.assertIn(needle, js)
        self.assertNotIn("innerHTML", js)

    def test_css_contract(self):
        css = read("web", "css", "toolbar.css")
        self.assertIn("flex-wrap: wrap", css)
        self.assertIn("gap: 6px var(--sp-2)", css)
        self.assertIn("min-width: 160px", css)
        self.assertNotIn("max-height: 40px", css)
        self.assertIn("position: sticky", css)
        self.assertIn("@media (max-width: 767px)", css)
        self.assertIn(":focus-visible", css)
        self.assertNotRegex(css, r"#[0-9a-fA-F]{3,6}\b")
        self.assertLessEqual(os.path.getsize(os.path.join(WEB, "css", "toolbar.css")), 6 * 1024)

    def test_documented(self):
        doc = read("docs", "TOOLBAR-PATTERN.md")
        for needle in ("toolbarHtml", "data-tb", "aria-controls", "Work", "Activity", "Priority"):
            self.assertIn(needle, doc)
        self.assertIn("Section toolbars: one compact row, filters collapsed", read("docs", "UI-CHECKLIST.md"))


if __name__ == "__main__":
    unittest.main()
