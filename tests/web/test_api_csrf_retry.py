"""Checks for the write path's CSRF retry in web/js/api.js (R7.61). A tab that loaded before a server restart holds the
old
CSRF value, so postJson gets 403 with a CSRF message. The client re-reads the value from the served page (GET /, same
origin) and retries once. Only a 403 that names the CSRF token is retried, and only when the page holds a different
value. The node checks run api.js with stub browser globals and no timers; they are skipped when node is not installed.
"""

import json
import os
import shutil
import subprocess
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
API_JS = os.path.join(REPO, "web", "js", "api.js")

NODE_SCRIPT = r"""
import { pathToFileURL } from "node:url";

const queue = [];
const posts = [];
const reads = [];
globalThis.setTimeout = function (fn) { queue.push(fn); return queue.length; };
globalThis.clearTimeout = function () {};
globalThis.window = { location: { hash: "#/" }, addEventListener: function () {} };
const scenario = JSON.parse(process.env.SCENARIO);
const page = "OLD";
const meta = { getAttribute: function (name) { return name === "content" ? page : null; } };
globalThis.document = {
  querySelectorAll: function () { return [meta]; },
  addEventListener: function () {},
};
const reply = function (status, body) {
  return { ok: status >= 200 && status < 300, status: status, json: function () { return Promise.resolve(body); } };
};
// The server accepts only scenario.accept; otherwise it answers scenario.refusal with a 403 body.
globalThis.fetch = function (url, init) {
  if (url === "/") {
    reads.push(url);
    const html = '<head><meta name="csrf" content="' + scenario.page + '"><meta name="csrf" content="__CSRF__"></head>';
    return Promise.resolve({ ok: true, status: 200, text: function () { return Promise.resolve(html); } });
  }
  const sent = init.headers["X-Roadmap-CSRF"];
  posts.push({ url: url, method: init.method, header: sent });
  if (sent === scenario.accept) return Promise.resolve(reply(200, { ok: true }));
  return Promise.resolve(reply(403, { error: { code: "forbidden", message: scenario.refusal } }));
};

const A = await import(pathToFileURL(process.env.API_JS).href);
let outcome = null;
try {
  const res = await A.postJson("/api/v1/cmd", { x: 1 });
  outcome = { ok: true, status: res.status, data: res.data };
} catch (err) {
  outcome = { ok: false, status: err.status, code: err.code };
}
console.log(JSON.stringify({
  outcome: outcome,
  posts: posts.map(function (p) { return { method: p.method, header: p.header, url: p.url }; }),
  reads: reads.length,
}));
"""

CSRF_REFUSAL = "this write needs the page's own CSRF token from the same origin"


def _node():
    return shutil.which("node")


def _run_node(page, accept, refusal):
    scenario = {"page": page, "accept": accept, "refusal": refusal}
    env = dict(os.environ, API_JS=API_JS, SCENARIO=json.dumps(scenario))
    proc = subprocess.run(
        [_node(), "--experimental-default-type=module", "--input-type=module", "-e", NODE_SCRIPT],
        capture_output=True, text=True, check=False, timeout=60, env=env,
    )
    if proc.returncode != 0:
        raise AssertionError("api.js failed in node: " + proc.stderr[-800:])
    return json.loads(proc.stdout.strip().splitlines()[-1])


class ApiCsrfRetrySourceTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with open(API_JS, encoding="utf-8") as fh:
            cls.text = fh.read()

    def test_retry_only_on_403_naming_csrf(self):
        self.assertIn("response.status === 403", self.text)
        self.assertIn('/CSRF/i.test(named', self.text)

    def test_reread_uses_same_origin_page_and_no_cache(self):
        self.assertIn('fetch("/", { credentials: "same-origin", cache: "no-store" })', self.text)

    def test_single_retry_and_no_loop(self):
        self.assertNotIn("while (true)", self.text)
        self.assertEqual(self.text.count("sendPost(url, body, freshToken)"), 1)

    def test_no_inline_script_or_style(self):
        self.assertNotIn("<script", self.text)
        self.assertNotIn("style=", self.text)

    def test_line_length_within_120(self):
        for number, line in enumerate(self.text.splitlines(), 1):
            self.assertLessEqual(len(line), 120, "api.js line %d is %d chars" % (number, len(line)))


@unittest.skipIf(_node() is None, "node is not installed")
class ApiCsrfRetryNodeTests(unittest.TestCase):

    def test_stale_token_is_reread_and_retry_is_accepted(self):
        result = _run_node("NEW", "NEW", CSRF_REFUSAL)
        self.assertEqual([p["header"] for p in result["posts"]], ["OLD", "NEW"])
        self.assertEqual(result["reads"], 1)
        self.assertTrue(result["outcome"]["ok"])

    def test_retry_happens_only_once_when_refused_again(self):
        result = _run_node("NEW", "NOPE", CSRF_REFUSAL)
        self.assertEqual([p["header"] for p in result["posts"]], ["OLD", "NEW"])
        self.assertEqual(result["reads"], 1)
        self.assertFalse(result["outcome"]["ok"])
        self.assertEqual(result["outcome"]["status"], 403)

    def test_same_value_in_page_means_no_retry(self):
        result = _run_node("OLD", "NEW", CSRF_REFUSAL)
        self.assertEqual([p["header"] for p in result["posts"]], ["OLD"])
        self.assertEqual(result["reads"], 1)
        self.assertFalse(result["outcome"]["ok"])

    def test_non_csrf_403_is_not_retried(self):
        result = _run_node("NEW", "NEW", "something else refused")
        self.assertEqual([p["header"] for p in result["posts"]], ["OLD"])
        self.assertEqual(result["reads"], 0)
        self.assertEqual(result["outcome"]["status"], 403)


if __name__ == "__main__":
    unittest.main()
