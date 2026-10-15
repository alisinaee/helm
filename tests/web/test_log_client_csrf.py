"""Checks for the browser log client's CSRF handling (R7.58): web/js/log.js posts with fetch and the X-Roadmap-CSRF
header (never sendBeacon, which cannot set headers). When the server refuses a batch with 403 because the tab still
holds the CSRF value of a server that has since restarted, the client re-reads the value from the served page (GET /,
same origin) and retries once. The node check runs log.js with stub browser globals and no timers; it is skipped when
node is not installed. The server guard (roadmap/http/security.py) is not touched by this change.
"""

import json
import os
import shutil
import subprocess
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
LOG_JS = os.path.join(REPO, "web", "js", "log.js")

NODE_SCRIPT = r"""
import { pathToFileURL } from "node:url";

const realTimeout = globalThis.setTimeout;
const queue = [];
const posts = [];
const reads = [];
let page = "OLD";

globalThis.setTimeout = function (fn) { queue.push(fn); return queue.length; };
globalThis.clearTimeout = function () {};
Object.defineProperty(globalThis, "navigator", {
  value: { userAgent: "TestAgent/1.0 (node)" }, configurable: true,
});
globalThis.window = {
  location: { hash: "#/" }, innerWidth: 1280, innerHeight: 800, devicePixelRatio: 1,
  addEventListener: function () {},
};
const meta = { getAttribute: function (name) { return name === "content" ? page : null; } };
globalThis.document = {
  documentElement: { getAttribute: function () { return "light"; } },
  hidden: false,
  activeElement: null,
  querySelectorAll: function () { return [meta]; },
  addEventListener: function () {},
};
// The server: it accepts only the value of the page it started with (NEW after the restart).
globalThis.fetch = function (url, init) {
  if (url === "/") {
    reads.push(url);
    const html = '<head><meta name="csrf" content="NEW"><meta name="csrf" content="__CSRF__"></head>';
    return Promise.resolve({ ok: true, status: 200, text: function () { return Promise.resolve(html); } });
  }
  const sent = init.headers["X-Roadmap-CSRF"];
  posts.push({ url: url, method: init.method, header: sent, keepalive: init.keepalive === true });
  return Promise.resolve({ ok: sent === "NEW", status: sent === "NEW" ? 204 : 403 });
};

const L = await import(pathToFileURL(process.env.LOG_JS).href);

async function settle() {
  for (let i = 0; i < 20; i += 1) {
    while (queue.length) queue.shift()();
    await new Promise(function (r) { realTimeout(r, 0); });
  }
}

L.installLog();
L.logEvent("ui.error", "boom", null);
L.mark("first");
await settle();

const out = {
  posts: posts.map(function (p) { return { method: p.method, header: p.header, keepalive: p.keepalive }; }),
  reads: reads.length,
  sent: L.status().sent,
  dropped: L.status().dropped,
};
console.log(JSON.stringify(out));
"""


def _node():
    return shutil.which("node")


def _run_node():
    node = _node()
    env = dict(os.environ, LOG_JS=LOG_JS)
    proc = subprocess.run(
        [node, "--experimental-default-type=module", "--input-type=module", "-e", NODE_SCRIPT],
        capture_output=True, text=True, check=False, timeout=60, env=env,
    )
    if proc.returncode != 0:
        raise AssertionError("log.js failed in node: " + proc.stderr[-800:])
    return json.loads(proc.stdout.strip().splitlines()[-1])


class LogClientCsrfSourceTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with open(LOG_JS, encoding="utf-8") as fh:
            cls.text = fh.read()

    def test_posts_with_fetch_and_csrf_header_not_beacon(self):
        self.assertNotIn("sendBeacon", self.text)
        self.assertIn('"X-Roadmap-CSRF": csrfValue()', self.text)
        self.assertIn('method: "POST"', self.text)

    def test_refresh_only_on_403_and_only_from_same_origin_page(self):
        self.assertIn('if (status === 403)', self.text)
        self.assertIn('fetch("/", { credentials: "same-origin", cache: "no-store" })', self.text)

    def test_line_length_within_120(self):
        for number, line in enumerate(self.text.splitlines(), 1):
            self.assertLessEqual(len(line), 120, "log.js line %d is %d chars" % (number, len(line)))


@unittest.skipIf(_node() is None, "node is not installed")
class LogClientCsrfNodeTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.result = _run_node()

    def test_first_post_uses_the_stale_value_and_is_refused(self):
        first = self.result["posts"][0]
        self.assertEqual(first["header"], "OLD")
        self.assertEqual(first["method"], "POST")
        self.assertTrue(first["keepalive"] is False)

    def test_value_is_reread_from_the_page_and_the_retry_is_accepted(self):
        self.assertEqual(self.result["reads"], 1)
        self.assertEqual(self.result["posts"][-1]["header"], "NEW")
        self.assertEqual(len(self.result["posts"]), 2)
        self.assertEqual(self.result["sent"], 3)  # ui.load, ui.error and ui.mark in the one retried batch
        self.assertEqual(self.result["dropped"], 0)


if __name__ == "__main__":
    unittest.main()
