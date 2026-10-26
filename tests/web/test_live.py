"""R7.82 U2: web/js/live.js pure helpers (node) and the wiring in app.js (source checks)."""

import json
import os
import shutil
import subprocess
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
JS = os.path.join(REPO, "web", "js")

HARNESS = r"""
const L = await import(process.argv[1]);
const out = {
  need: [L.refreshNeeded("a", "b"), L.refreshNeeded("a", "a"), L.refreshNeeded(null, "a"), L.refreshNeeded("a", "")],
  back: [0, 1, 2, 3, 4, 9].map(L.backoffDelay),
  poll: [L.pollInterval(2000, true), L.pollInterval(2000, false), L.pollInterval(60000, true)],
  health: [L.streamHealthy(true, 100, 200), L.streamHealthy(true, 100, 100 + L.STREAM_SILENCE_MS),
           L.streamHealthy(false, 100, 200), L.streamHealthy(true, 0, 5)],
  rev: [L.parseRev('{"project":"p","rev":"r1"}'), L.parseRev("nope"), L.parseRev('{"project":1}')],
  noES: L.startLive({ ES: null }).healthy(),
};
console.log(JSON.stringify(out));
"""


def read(name):
    with open(os.path.join(JS, name), encoding="utf-8") as fh:
        return fh.read()


class LiveHelpers(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_helpers(self):
        res = subprocess.run(["node", "--input-type=module", "-e", HARNESS, "file://" + os.path.join(JS, "live.js")],
                             capture_output=True, text=True, timeout=30)
        self.assertEqual(res.returncode, 0, res.stderr)
        out = json.loads(res.stdout)
        self.assertEqual(out["need"], [True, False, True, False])
        self.assertEqual(out["back"], [2000, 4000, 8000, 15000, 15000, 15000])
        self.assertEqual(out["poll"], [30000, 2000, 60000])
        self.assertEqual(out["health"], [True, False, False, False])
        self.assertEqual(out["rev"], [{"project": "p", "rev": "r1"}, None, None])
        self.assertFalse(out["noES"])

    def test_wiring(self):
        app = read("app.js")
        self.assertIn('from "./live.js"', app)
        self.assertIn("startLive(", app)
        self.assertIn("pollInterval(", app)
        self.assertIn("/api/v1/stream", read("live.js"))
        self.assertIn("streamStatus", read("api.js"))


if __name__ == "__main__":
    unittest.main()
