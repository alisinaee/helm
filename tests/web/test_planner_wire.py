"""The Planner is wired into the shell (WP55): a nav entry between Roadmap and Work, the module bound once in app.js,
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
    def test_registry_puts_planner_between_roadmap_and_work(self):
        routes = read(WEB, "js", "routes.js")
        ids = re.findall(r'\{ id: "([a-z]+)"', routes)
        self.assertLess(ids.index("roadmap"), ids.index("planner"))
        self.assertEqual(ids.index("planner"), ids.index("work") - 1)
        self.assertIn('module: "./views/planner.js"', routes)

    def test_smoke_section_list_includes_planner_in_registry_order(self):
        spec = importlib.util.spec_from_file_location("ui_smoke", SMOKE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertIn("planner", module.SECTIONS)
        self.assertLess(module.SECTIONS.index("roadmap"), module.SECTIONS.index("planner"))
        self.assertLess(module.SECTIONS.index("planner"), module.SECTIONS.index("work"))

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
        self.assertIn('"/planner?f="', details)
        self.assertIn('data-side="feat-link"', details)
        self.assertIn('run("feature.link", { task: task, feats: [feat] }', details)

    def test_drawer_feature_section_is_left_out_without_a_features_block(self):
        details = read(WEB, "js", "views", "details.js")
        self.assertIn("if (!snap.features) return", details)

    def test_snapshot_normalizer_keeps_the_features_block(self):
        state = read(WEB, "js", "state.js")
        self.assertIn("features: raw.features", state)

    def test_nav_entry_uses_planner_icon(self):
        routes = read(WEB, "js", "routes.js")
        self.assertIn('icon: "planner"', routes)


if __name__ == "__main__":
    unittest.main()
