"""The Planner is wired into the shell (WP55, R10.7: now a view of Work, no nav entry), the module bound by work.js,
the Work drawer's feature chips and "Link to feature" picker, and the icon. Reads the files only; no browser needed.
"""

import importlib.util
import os
import re
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
WEB = os.path.join(REPO, "web")
SMOKE = os.path.join(REPO, "tools", "ui_smoke.py")


def read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as fh:
        return fh.read()


class PlannerWireTest(unittest.TestCase):
    def test_registry_has_no_planner_section_any_more(self):
        routes = read(WEB, "js", "routes.js")
        ids = re.findall(r'\{ id: "([a-z]+)"', routes)
        self.assertNotIn("planner", ids)
        self.assertIn("work", ids)
        self.assertNotIn("views/planner.js", routes)

    def test_smoke_covers_planner_as_a_work_view(self):
        spec = importlib.util.spec_from_file_location("ui_smoke", SMOKE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertNotIn("planner", module.SECTIONS)
        self.assertIn("planner", module.WORK_VIEWS)
        self.assertIn("work/planner", module.MARKERS)

    def test_icon_symbol_exists_once(self):
        icons = read(WEB, "icons.svg")
        self.assertEqual(icons.count('id="i-planner"'), 1)

    def test_app_binds_planner_once_and_routes_feature_picker(self):
        app = read(WEB, "js", "app.js")
        self.assertIn('section.id === "planner"', app)
        self.assertIn("mod.bind(document.getElementById(\"main\"))", app)
        self.assertIn('addEventListener("change", onChange)', app)
        self.assertIn('"feat-link"', app)
        self.assertIn("featureLinkChange", app)

    def test_drawer_chip_links_to_planner_feature_and_picker_uses_feature_link(self):
        details = read(WEB, "js", "views", "details.js")
        self.assertIn('"/planner?f="', details)  # the legacy link; routes.js redirects it to Work > Planner
        self.assertIn('data-side="feat-link"', details)
        self.assertIn('run("feature.link", { task: task, feats: [feat] }', details)

    def test_drawer_feature_section_is_left_out_without_a_features_block(self):
        details = read(WEB, "js", "views", "details.js")
        self.assertIn("if (!snap.features) return", details)

    def test_snapshot_normalizer_keeps_the_features_block(self):
        state = read(WEB, "js", "state.js")
        self.assertIn("features: raw.features", state)


if __name__ == "__main__":
    unittest.main()
