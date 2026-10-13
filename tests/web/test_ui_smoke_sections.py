"""The Chrome smoke test covers every section of the router (WP35b).

tools/ui_smoke.py keeps its own section list, and its routes must reach every section in web/js/routes.js. A new
section has to be added to the smoke too, or this test fails. Chrome is not needed: the test reads the lists only.
"""

import importlib.util
import os
import re
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
ROUTES_JS = os.path.join(REPO, "web", "js", "routes.js")
SMOKE = os.path.join(REPO, "tools", "ui_smoke.py")
SECTION_IDS = re.compile(r'\{\s*id:\s*"([a-z]+)"')
SETTINGS_ID = re.compile(r'export const SETTINGS = \{\s*id:\s*"([a-z]+)"')


def registry_ids(text):
    """The section ids of SECTIONS in routes.js, then the id of SETTINGS."""
    block = re.search(r"export const SECTIONS = \[(.*?)\n\];", text, re.S)
    if block is None:
        raise AssertionError("routes.js has no SECTIONS array")
    settings = SETTINGS_ID.search(text)
    if settings is None:
        raise AssertionError("routes.js has no SETTINGS id")
    return SECTION_IDS.findall(block.group(1)) + [settings.group(1)]


def load_smoke():
    spec = importlib.util.spec_from_file_location("ui_smoke", SMOKE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class UiSmokeSectionsTest(unittest.TestCase):
    def setUp(self):
        self.smoke = load_smoke()
        with open(ROUTES_JS, encoding="utf-8") as fh:
            self.expected = registry_ids(fh.read())

    def test_smoke_section_list_equals_router_registry(self):
        self.assertEqual(list(self.smoke.SECTIONS), self.expected)

    def test_every_registry_section_has_a_smoke_route(self):
        ids = {"alpha": "a1", "beta": "b1", "gamma": "g1"}
        reached = set()
        for _label, path, _marker, _shot in self.smoke.routes(ids):
            parts = path.split("/")
            reached.add(parts[2] if parts[0] == "p" else parts[1])
        missing = [section for section in self.expected if section not in reached]
        self.assertEqual(missing, [], "sections with no smoke route")


if __name__ == "__main__":
    unittest.main()
