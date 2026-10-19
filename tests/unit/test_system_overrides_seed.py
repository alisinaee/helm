"""The seed docs/system.json (R11.111) loads through the real system loader with no dropped entries.

Every task id bound on a component exists in docs/tasks.json, and the diagram override keys are well formed.
"""

import json
import os
import unittest

from roadmap.services import system

REPO = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))


class SystemOverridesSeed(unittest.TestCase):
    def test_seed_validates_through_loader(self):
        specs, layers, edges, dropped = system._read_declared(REPO)
        self.assertEqual(dropped, [])
        self.assertTrue(specs)
        self.assertTrue(edges)

    def test_loader_uses_the_file(self):
        out = system.load(REPO, use_cache=False)
        self.assertNotEqual(out["source"], "baseline")
        self.assertFalse([w for w in out["warnings"] if w.startswith("system.json")], out["warnings"])

    def test_bound_tasks_exist_on_the_board(self):
        with open(os.path.join(REPO, "docs", "tasks.json"), encoding="utf-8") as fh:
            known = {t["id"] for t in json.load(fh)["tasks"]}
        with open(os.path.join(REPO, "docs", "system.json"), encoding="utf-8") as fh:
            data = json.load(fh)
        bound = [tid for comp in data["components"] for tid in comp.get("tasks", [])]
        self.assertEqual([tid for tid in bound if tid not in known], [])

    def test_override_keys_have_the_expected_shape(self):
        with open(os.path.join(REPO, "docs", "system.json"), encoding="utf-8") as fh:
            data = json.load(fh)
        self.assertEqual(data["version"], 1)
        self.assertTrue(all(isinstance(x, dict) and x.get("id") and x.get("name") for x in data["external"]))
        nodes = data["deployment"]["nodes"]
        self.assertTrue(all(isinstance(n, dict) and n.get("id") and n.get("label") for n in nodes))


if __name__ == "__main__":
    unittest.main()
