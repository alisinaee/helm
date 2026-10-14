"""WP33 checks for the Tokens, Rules and Settings screens: the files exist and resolve, admin.css stays within its
budget
and uses tokens only, no inline style or handler appears in the new files, and the views render in node (skipped when
node is not installed) from a synthetic snapshot that carries meters.limits.
"""

import json
import os
import re
import shutil
import subprocess
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
WEB = os.path.join(REPO, "web")
JS = os.path.join(WEB, "js")
VIEWS = os.path.join(JS, "views")
CSS_DIR = os.path.join(WEB, "css")
RENDER = os.path.join(TESTS, "web", "render_admin.mjs")
NEW_VIEWS = ("tokens.js", "limits.js", "rules.js", "settings.js")
CSS_BUDGET = 3500
HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")
IMPORT = re.compile(r'from\s+"(\.[^"]+)"')
INLINE = re.compile(r'\sstyle\s*=|\son[a-z]{3,}\s*=|<script', re.IGNORECASE)
CONTROLS = re.compile(r'aria-controls="([^"]+)"')
IDS = re.compile(r'\sid="([^"]+)"')


def read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


class AdminFiles(unittest.TestCase):
    def test_new_view_files_exist(self):
        for name in NEW_VIEWS:
            self.assertTrue(os.path.isfile(os.path.join(VIEWS, name)), name)

    def test_routes_point_at_the_new_modules(self):
        routes = read(os.path.join(JS, "routes.js"))
        for name in ("tokens.js", "rules.js", "settings.js"):
            self.assertIn('"./views/%s"' % name, routes, name)

    def test_relative_imports_resolve(self):
        for name in NEW_VIEWS + ("../cmd.js",):
            path = os.path.normpath(os.path.join(VIEWS, name))
            if not os.path.isfile(path):
                continue
            for target in IMPORT.findall(read(path)):
                resolved = os.path.normpath(os.path.join(os.path.dirname(path), target))
                self.assertTrue(os.path.isfile(resolved), "%s imports %s" % (name, target))

    def test_app_dispatches_the_new_actions(self):
        app = read(os.path.join(JS, "app.js"))
        self.assertIn("limitAction(action, el)", app)
        self.assertIn("settingsAction(action, el)", app)

    def test_new_files_have_no_hex_colour_or_inline_markup(self):
        for name in NEW_VIEWS:
            text = read(os.path.join(VIEWS, name))
            self.assertIsNone(HEX.search(text), name)
            self.assertIsNone(INLINE.search(text), name)
            self.assertNotIn("innerHTML", text, name)


class AdminCss(unittest.TestCase):
    def test_admin_css_is_within_budget_and_token_only(self):
        path = os.path.join(CSS_DIR, "admin.css")
        text = read(path)
        self.assertLessEqual(os.path.getsize(path), CSS_BUDGET)
        self.assertTrue(text.lstrip().startswith("/*"))
        self.assertIsNone(HEX.search(text))
        self.assertNotIn("style=", text)

    def test_admin_css_has_the_spec_classes(self):
        text = read(os.path.join(CSS_DIR, "admin.css"))
        for cls in ("lim-row", "step", "lim-range", "mtick", "pace", "met", "rule-row", "tk-table", "is-sheet"):
            self.assertIn("." + cls, text, cls)


@unittest.skipIf(shutil.which("node") is None, "node is not installed")
class AdminRender(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        proc = subprocess.run(
            [shutil.which("node"), "--experimental-default-type=module", RENDER, WEB],
            capture_output=True, text=True, check=False, timeout=60,
        )
        if proc.returncode != 0:
            raise AssertionError("render failed: " + proc.stderr[-800:])
        cls.out = json.loads(proc.stdout)

    def test_every_view_renders_without_inline_markup(self):
        for name, html in self.out.items():
            self.assertTrue(html, name)
            self.assertIsNone(INLINE.search(html), name)
            self.assertNotIn("undefined", html, name)
            self.assertNotIn("NaN", html, name)

    def test_controls_name_elements_in_the_same_output(self):
        for name, html in self.out.items():
            ids = set(IDS.findall(html))
            for target in CONTROLS.findall(html):
                self.assertIn(target, ids, "%s: aria-controls=%s" % (name, target))

    def test_meters_show_day_and_week_with_pace_and_unknown(self):
        html = self.out["project_tokens"]
        self.assertIn("Today", html)
        self.assertIn("This week", html)
        self.assertIn("At this pace: limit reached about 16:40", html)
        self.assertIn("Limit reached.", self.out["global_tokens"])
        self.assertIn('data-state="unknown"', html)
        self.assertIn("mtick-warn", html)
        self.assertIn("mtick-day", html)

    def test_estimates_are_marked(self):
        self.assertIn("≈ ", self.out["project_tokens"])

    def test_limit_rows_show_source_for_read_only_rows(self):
        html = self.out["project_tokens"]
        self.assertIn("Read only, from autonomy.json", html)
        self.assertIn("Read only, from All projects", html)

    def test_editor_fields_have_labels(self):
        html = self.out["project_tokens"]
        self.assertIn('<span class="lim-label">Window</span>', html)
        self.assertIn('aria-label="Limit for L1, percent"', html)

    def test_presets_show_in_scope_rules(self):
        self.assertIn("Stay under 10% a day", self.out["project_add"])
        self.assertIn("Weekly 60%", self.out["project_add"])
        self.assertNotIn("Daily for all projects", self.out["project_add"])
        self.assertIn("Daily for all projects", self.out["global_add"])

    def test_empty_state_has_the_presets(self):
        html = self.out["empty_tokens"]
        self.assertIn("No limits. Agents may use your whole weekly allowance.", html)
        self.assertIn("Stay under 10% a day", html)

    def test_spend_and_override_sections(self):
        html = self.out["project_tokens"]
        self.assertIn("Top 5 tasks by spend", html)
        self.assertIn('data-action="lim-override"', html)
        self.assertNotIn("data-action=\"lim-override\"", self.out["global_tokens"])
        self.assertIn("Spend by project", self.out["global_tokens"])

    def test_rules_render_tabs_rows_and_sync(self):
        html = self.out["project_rules"]
        self.assertIn("Keep replies short.", html)
        self.assertIn("Budget per task (40k)", html)
        self.assertIn('data-action="rule-sync"', html)
        self.assertIn("A backup copy", html)
        self.assertIn('maxlength="160"', html)
        self.assertIn("Rules belong to one project.", self.out["global_rules"])

    def test_settings_have_theme_density_and_phone_note(self):
        html = self.out["settings"]
        self.assertIn('data-action="set-theme"', html)
        self.assertIn('data-action="set-density"', html)
        self.assertIn("Read only on a phone", html)
        self.assertIn('data-action="help-open"', html)


if __name__ == "__main__":
    unittest.main()
