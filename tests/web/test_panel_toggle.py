"""Checks for the always-visible side panel toggle in the top bar (R7.23).

The toggle is the last button of the top bar's tools. It uses the same panel-toggle action as the project crumb and the
"]" key, names its state in aria-label and title, and reports aria-pressed for the side panel. The render check runs
web/js/views/topbar.js in node with the panel open and closed; it is skipped when node is not installed.
"""

import json
import os
import shutil
import subprocess
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
WEB = os.path.join(REPO, "web")
TOPBAR = os.path.join(WEB, "js", "views", "topbar.js")
ICONS = os.path.join(WEB, "icons.svg")
KEYS = os.path.join(WEB, "js", "keys.js")

NODE_SCRIPT = """
import { pathToFileURL } from "node:url";
globalThis.window = { matchMedia: () => ({ matches: false }) };
const top = await import(pathToFileURL(process.env.WEB_DIR + "/js/views/topbar.js").href);
const base = {
  route: { name: "project", id: "alpha", section: "work", view: "board" },
  project: { name: "alpha" }, control: { known: true, stopped: false, id: "alpha" },
  conn: { ok: true }, meterRows: null, theme: "auto",
};
const out = {
  open: top.topbarView(Object.assign({}, base, { ui: { panelOpen: true } })),
  closed: top.topbarView(Object.assign({}, base, { ui: { panelOpen: false } })),
  unset: top.topbarView(Object.assign({}, base, { ui: { panelOpen: null } })),
  noUi: top.topbarView(base),
};
console.log(JSON.stringify(out));
"""


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def toggle_button(html):
    start = html.rfind('<button type="button" class="btn" data-action="panel-toggle"')
    assert start >= 0, "no panel toggle button in the top bar"
    return html[start:html.index("</button>", start) + len("</button>")]


class PanelToggleStatic(unittest.TestCase):

    def test_icon_symbol_exists_once(self):
        self.assertEqual(read(ICONS).count('id="i-panel"'), 1)

    def test_topbar_source_has_the_toggle_with_the_existing_action(self):
        src = read(TOPBAR)
        self.assertIn('data-action="panel-toggle" data-focus="panel-toggle"', src)
        self.assertIn("/icons.svg#i-panel", src)
        self.assertIn("(])", src)

    def test_crumb_toggle_is_kept(self):
        self.assertIn('class="crumb-proj" data-action="panel-toggle"', read(TOPBAR))

    def test_shortcut_named_in_title_exists_in_keys(self):
        self.assertIn('["]", "Show or hide the side panel"]', read(KEYS))

    def test_no_inline_style_or_handler_in_topbar(self):
        src = read(TOPBAR)
        self.assertNotIn(" style=", src)
        self.assertNotIn(" onclick=", src)

    def test_lines_fit_120_columns(self):
        for line in read(TOPBAR).splitlines():
            self.assertLessEqual(len(line), 120, line)


class PanelToggleRender(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        node = shutil.which("node")
        if node is None:
            raise unittest.SkipTest("node is not installed; the panel toggle render check is skipped")
        env = dict(os.environ, WEB_DIR=WEB)
        proc = subprocess.run([node, "--input-type=module", "-e", NODE_SCRIPT], env=env,
                              capture_output=True, text=True, timeout=60)
        if proc.returncode != 0:
            raise AssertionError("topbar render failed: " + proc.stderr)
        cls.out = json.loads(proc.stdout)

    def test_open_panel_shows_hide_label_and_expanded(self):
        btn = toggle_button(self.out["open"])
        self.assertIn('aria-pressed="true"', btn)
        self.assertIn('aria-label="Hide side panel"', btn)
        self.assertIn('title="Hide side panel (])"', btn)

    def test_closed_panel_shows_show_label_and_collapsed(self):
        btn = toggle_button(self.out["closed"])
        self.assertIn('aria-pressed="false"', btn)
        self.assertIn('aria-label="Show side panel"', btn)

    def test_unset_panel_state_follows_the_wide_screen_default(self):
        # panelOpen null means "not chosen yet": the panel is docked open on wide screens (render stubs a wide screen).
        btn = toggle_button(self.out["unset"])
        self.assertIn('aria-pressed="true"', btn)

    def test_missing_ui_reads_as_closed_and_does_not_throw(self):
        self.assertIn('aria-pressed="false"', toggle_button(self.out["noUi"]))

    def test_toggle_is_the_last_control_in_the_tools_row(self):
        html = self.out["open"]
        tools = html[html.index('<div class="top-tools">'):]
        self.assertTrue(toggle_button(html) in tools)
        self.assertLess(tools.index('aria-label="Keyboard shortcuts"'), tools.index('data-action="panel-toggle"'))
        self.assertEqual(html.count('data-action="panel-toggle"'), 2)


if __name__ == "__main__":
    unittest.main()
