"""Tests for A8: `roadmap system check` and `roadmap system show`.

check passes on the seed docs/system.json of this repo and fails (exit 1, messages on the envelope) on a broken file
in a temp folder. show prints the components and edges of the seed.
"""

import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest

from roadmap import cli

REPO = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _run(argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = cli.main(argv)
    return code, out.getvalue()


class SystemCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="sysmap-cmd-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        os.makedirs(os.path.join(self.tmp, "docs"))
        os.makedirs(os.path.join(self.tmp, "roadmap", "services"))
        with open(os.path.join(self.tmp, "roadmap", "services", "jobs.py"), "w") as fh:
            fh.write("x = 1\n")

    def _write_system(self, text):
        with open(os.path.join(self.tmp, "docs", "system.json"), "w") as fh:
            fh.write(text)

    def test_seed_is_valid(self):
        code, text = _run(["system", "check", "--json", "--path", REPO])
        self.assertEqual(code, 0, text)
        env = json.loads(text)
        self.assertTrue(env["ok"])
        self.assertTrue(env["data"]["valid"])
        self.assertEqual(env["data"]["source"], "file")

    def test_seed_show_lists_components_and_edges(self):
        code, text = _run(["system", "show", "--json", "--path", REPO])
        self.assertEqual(code, 0)
        data = json.loads(text)["data"]
        ids = {c["id"] for c in data["components"]}
        for want in ("cli", "hooks", "services", "http-api", "store", "web-shell", "views", "graph-engine"):
            self.assertIn(want, ids)
        self.assertIn({"from": "http-api", "to": "services", "label": "calls use cases", "kind": "call"},
                      [{k: e[k] for k in ("from", "to", "label", "kind")} for e in data["edges"]])

    def test_bad_file_fails_with_message(self):
        self._write_system(json.dumps({"version": 1, "layers": ["service"],
                                       "components": [{"id": "a", "layer": "nope", "files": ["roadmap/**"]}]}))
        code, text = _run(["system", "check", "--json", "--path", self.tmp])
        self.assertEqual(code, 1)
        env = json.loads(text)
        self.assertFalse(env["ok"])
        self.assertIn("layer", env["error"]["message"])

    def test_broken_json_fails(self):
        self._write_system("{not json")
        code, text = _run(["system", "check", "--json", "--path", self.tmp])
        self.assertEqual(code, 1)
        self.assertIn("not valid JSON", json.loads(text)["error"]["message"])

    def test_missing_file_fails(self):
        code, text = _run(["system", "check", "--json", "--path", self.tmp])
        self.assertEqual(code, 1)
        self.assertIn("missing", json.loads(text)["error"]["message"])

    def test_good_small_file_passes(self):
        self._write_system(json.dumps({"version": 1, "layers": ["service"],
                                       "components": [{"id": "svc", "layer": "service",
                                                       "files": ["roadmap/services/**", "docs/**"]}]}))
        code, _ = _run(["system", "check", "--json", "--path", self.tmp])
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
