"""Checks for the browser debug-log client (R7.16 step 4): web/js/log.js batches events to POST /api/v1/log, caps and
redacts them, fails quietly (one retry, then drop), stays silent on the phone page (no CSRF value), and is wired into
app.js, api.js and cmd.js. The node check runs the module in node with stub browser globals (no browser, no network).
The static checks read the sources. The node check is skipped when node is not installed.
"""

import json
import os
import re
import shutil
import subprocess
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
WEB_JS = os.path.join(REPO, "web", "js")
LOG_JS = os.path.join(WEB_JS, "log.js")
APP_JS = os.path.join(WEB_JS, "app.js")
API_JS = os.path.join(WEB_JS, "api.js")
CMD_JS = os.path.join(WEB_JS, "cmd.js")

EVENT_NAMES = ["ui.load", "ui.route", "ui.action", "ui.submit", "ui.mark", "ui.error", "ui.reject", "ui.csp",
               "ui.api", "ui.render", "ui.console"]
TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}[+-]\d{2}:\d{2}$")
INLINE_HANDLER = re.compile(r"\son[a-z]+\s*=\s*[\"'\\]")

NODE_SCRIPT = r"""
import { pathToFileURL } from "node:url";

const sent = [];
const winHandlers = {};
const docHandlers = {};
const logged = [];
let token = "tok123";
let replyOk = true;
let replyStatus = 200;
const meta = { getAttribute: function (name) { return name === "content" ? token : null; } };

Object.defineProperty(globalThis, "navigator", {
  value: { userAgent: "TestAgent/1.0 (node)", sendBeacon: function () { throw new Error("beacon used"); } },
  configurable: true,
});
globalThis.window = {
  location: { hash: "#/p/rb/work?f=state:todo&secret=1" },
  innerWidth: 1280, innerHeight: 800, devicePixelRatio: 2,
  addEventListener: function (type, fn) { (winHandlers[type] = winHandlers[type] || []).push(fn); },
};
globalThis.document = {
  documentElement: { getAttribute: function () { return "dark"; } },
  hidden: false,
  activeElement: null,
  querySelectorAll: function () { return token ? [meta] : []; },
  addEventListener: function (type, fn) { (docHandlers[type] = docHandlers[type] || []).push(fn); },
};
globalThis.fetch = function (url, init) {
  sent.push({ url: url, init: init });
  return Promise.resolve({ ok: replyOk, status: replyStatus });
};
console.error = function () { logged.push(Array.from(arguments).join(" ")); };

const L = await import(pathToFileURL(process.env.LOG_JS).href);
const tick = function () { return new Promise(function (r) { setTimeout(r, 0); }); };
async function pagehide() {
  (winHandlers.pagehide || []).forEach(function (fn) { fn(); });
  await tick();
}
function allEvents() {
  const out = [];
  sent.forEach(function (s) {
    JSON.parse(s.init.body).events.forEach(function (e) { out.push(e); });
  });
  return out;
}
const R = {};
const TS_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}[+-]\d{2}:\d{2}$/;

L.installLog();
const afterInstall = L.status();
R.activeDesktop = afterInstall.active;
R.sidLen = afterInstall.sid.length;

// Unknown names are refused; caps and redaction on a long, noisy error.
L.logEvent("ui.resize", "not in the list");
R.unknownBuffered = L.status().buffered - afterInstall.buffered;
L.logEvent("ui.error", "boom http://localhost:8780/js/app.js?token=SECRET#frag tok123 /Users/ali/Works/x " +
  "m".repeat(400), {
  deep: { a: { b: { c: 1 } } }, long: "y".repeat(900), arr: Array.from({ length: 30 }, function (_, i) { return i; }),
  token: "nope", session: "x",
});
await pagehide();
const first = sent[sent.length - 1];
const ev = JSON.parse(first.init.body).events.find(function (e) { return e.ev === "ui.error"; });
R.tsOk = TS_RE.test(ev.ts);
R.lvl = ev.lvl;
R.src = ev.src;
R.msgLen = ev.msg.length;
R.msgClean = !/SECRET|\?token|#frag|tok123|\/Users\//.test(JSON.stringify(ev));
R.tilde = ev.msg.indexOf("~/Works") >= 0;
R.route = ev.route;
R.dataKeys = Object.keys(ev.data).length;
R.longLen = ev.data.long.length;
R.arrLen = ev.data.arr.length;
R.tokenKey = Object.prototype.hasOwnProperty.call(ev.data, "token");
R.dataSize = JSON.stringify(ev.data).length;
R.method = first.init.method;
R.keepalive = first.init.keepalive === true;
R.credentials = first.init.credentials;
R.csrfHeader = first.init.headers["X-Roadmap-CSRF"];
R.url = first.url;
R.tokenNotInBodies = sent.every(function (s) { return s.init.body.indexOf("tok123") < 0; });

// Batching: 230 marks; the buffer keeps 200, and a flush sends them in batches of at most 50.
const beforeBatch = sent.length;
for (let i = 0; i < 230; i++) L.logEvent("ui.mark", "m" + i);
R.bufferCap = L.status().buffered;
R.droppedAtCap = L.status().dropped >= 30;
await pagehide();
const batches = sent.slice(beforeBatch);
R.batchCount = batches.length;
R.maxBatchEvents = Math.max.apply(null, batches.map(function (s) { return JSON.parse(s.init.body).events.length; }));
R.maxBodyBytes = Math.max.apply(null, batches.map(function (s) { return s.init.body.length; }));
R.batchedMarks = batches.reduce(function (n, s) { return n + JSON.parse(s.init.body).events.length; }, 0);

// Fail quiet: a 404 is retried once after the backoff, then the batch is dropped; nothing is logged about it.
replyOk = false;
replyStatus = 404;
const beforeFail = sent.length;
L.logEvent("ui.mark", "fail case");
await pagehide();
R.failFirstSends = sent.length - beforeFail;
R.failBufferAfter = L.status().buffered;
await new Promise(function (r) { setTimeout(r, 3300); });
R.failTotalSends = sent.length - beforeFail;
R.failBufferStill = L.status().buffered;
replyOk = true;
replyStatus = 200;

// The phone page carries no CSRF value: nothing is recorded or sent.
token = "";
const beforePhone = sent.length;
const bufPhone = L.status().buffered;
L.logEvent("ui.error", "phone error");
L.mark("phone mark");
L.logAction("toggle-section", null, null);
R.phoneActive = L.status().active;
R.phoneBuffered = L.status().buffered - bufPhone;
await pagehide();
R.phoneSends = sent.length - beforePhone;
token = "tok123";

// Switch off drops new events.
L.setEnabled(false);
const bufOff = L.status().buffered;
L.logEvent("ui.error", "off");
R.offBuffered = L.status().buffered - bufOff;
R.offStatus = L.status().enabled;
L.setEnabled(true);

// Form submits: the form id only, never a field value.
(docHandlers.submit || []).forEach(function (fn) {
  fn({ target: { tagName: "FORM", id: "pl-add", elements: [{ value: "SECRETVAL" }] } });
});
(docHandlers.submit || []).forEach(function (fn) { fn({ target: { tagName: "DIV", id: "x" } }); });
await pagehide();
R.submitForms = allEvents().filter(function (e) { return e.ev === "ui.submit"; }).map(function (e) {
  return e.data.form;
});
R.submitLeak = JSON.stringify(allEvents()).indexOf("SECRETVAL") >= 0;

// Named actions carry the target and the ref of the element, never its text.
const fakeEl = { getAttribute: function (n) {
  return { "data-section": "plan", "data-ref": "rb:rb/task/R1", "data-kind": "task" }[n] || null;
} };
L.logAction("toggle-section", fakeEl, null);
await pagehide();
const act = allEvents().filter(function (e) { return e.ev === "ui.action"; });
R.actionName = act[act.length - 1].msg;
R.actionRef = act[act.length - 1].ref;
R.actionTarget = act[act.length - 1].data.target;

// API timings: only slow (over 1.5 s), non-2xx (not 304) and network failures; path only, never the query.
const now = Date.now();
L.noteRequest("GET", "/api/v1/projects?x=secret", 200, now - 2000);
L.noteRequest("GET", "/api/v1/projects", 200, now);
L.noteRequest("GET", "/api/v1/projects", 304, now);
L.noteRequest("POST", "/api/v1/cmd", 409, now);
L.noteRequest("POST", "http://localhost:8780/api/v1/cmd", 0, now);
await pagehide();
const apiEv = allEvents().filter(function (e) { return e.ev === "ui.api"; });
R.apiCount = apiEv.length;
R.apiPaths = apiEv.map(function (e) { return e.data.path; });
R.apiLeak = JSON.stringify(apiEv).indexOf("secret") >= 0;

// The console wrappers call through and record a ui.console event.
console.error("bad thing", { a: 1 });
R.consoleCalled = logged.length === 1 && logged[0].indexOf("bad thing") === 0;
await pagehide();
const ce = allEvents().filter(function (e) { return e.ev === "ui.console"; });
R.consoleLvl = ce[ce.length - 1].lvl;
R.consoleMsg = ce[ce.length - 1].msg;

// Window error, unhandled rejection and CSP violation hooks.
(winHandlers.error || []).forEach(function (fn) {
  fn({ message: "Oops", filename: "http://localhost:8780/js/app.js?v=1", lineno: 3, colno: 4,
    error: { stack: "Error: Oops\n    at x (http://localhost:8780/js/app.js?v=1:3:4)" } });
});
(winHandlers.unhandledrejection || []).forEach(function (fn) { fn({ reason: new Error("rej") }); });
(docHandlers.securitypolicyviolation || []).forEach(function (fn) {
  fn({ violatedDirective: "script-src-elem", blockedURI: "https://evil.example/x.js?k=1" });
});
L.noteRoute();
L.noteRender("roadmap", Date.now() - 500);
L.noteRender("roadmap", Date.now());
await pagehide();
const every = allEvents();
const oops = every.find(function (e) { return e.ev === "ui.error" && e.msg === "Oops"; });
R.errLvl = oops.lvl;
R.errStackLeak = JSON.stringify(oops).indexOf("?v=1") >= 0;
const rej = every.find(function (e) { return e.ev === "ui.reject"; });
R.rejLvl = rej.lvl;
const csp = every.find(function (e) { return e.ev === "ui.csp"; });
R.cspBlocked = csp.data.blocked;
R.cspLeak = JSON.stringify(csp).indexOf("k=1") >= 0;
R.renderCount = every.filter(function (e) { return e.ev === "ui.render"; }).length;
const route = every.filter(function (e) { return e.ev === "ui.route"; }).pop();
R.routeClean = route.route.indexOf("?") < 0;
R.eventNames = Array.from(new Set(every.map(function (e) { return e.ev; }))).sort();

console.log(JSON.stringify(R));
process.exit(0);
"""


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def run_node():
    node = shutil.which("node")
    env = dict(os.environ, LOG_JS=LOG_JS)
    proc = subprocess.run(
        [node, "--experimental-default-type=module", "--input-type=module", "-e", NODE_SCRIPT],
        capture_output=True, text=True, check=False, timeout=60, env=env,
    )
    if proc.returncode != 0:
        raise AssertionError("log.js failed in node: " + proc.stderr[-800:])
    return json.loads(proc.stdout.strip().splitlines()[-1])


class LogClientNodeTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if shutil.which("node") is None:
            raise unittest.SkipTest("node is not installed; the log client check is skipped")
        cls.r = run_node()

    def test_desktop_page_is_active_and_sid_is_eight_hex(self):
        self.assertTrue(self.r["activeDesktop"])
        self.assertEqual(self.r["sidLen"], 8)

    def test_unknown_event_names_are_refused(self):
        self.assertEqual(self.r["unknownBuffered"], 0)

    def test_event_shape_and_level(self):
        self.assertTrue(self.r["tsOk"])
        self.assertEqual(self.r["src"], "ui")
        self.assertEqual(self.r["lvl"], "ERROR")

    def test_caps_hold(self):
        self.assertLessEqual(self.r["msgLen"], 300)
        self.assertLessEqual(self.r["dataKeys"], 20)
        self.assertEqual(self.r["longLen"], 200)
        self.assertEqual(self.r["arrLen"], 10)
        self.assertLessEqual(self.r["dataSize"], 1024)

    def test_no_query_no_token_no_home_path(self):
        self.assertTrue(self.r["msgClean"])
        self.assertTrue(self.r["tilde"])
        self.assertEqual(self.r["route"], "#/p/rb/work")
        self.assertFalse(self.r["tokenKey"])
        self.assertTrue(self.r["tokenNotInBodies"])

    def test_post_with_csrf_header_and_keepalive_only(self):
        self.assertEqual(self.r["method"], "POST")
        self.assertTrue(self.r["keepalive"])
        self.assertEqual(self.r["credentials"], "same-origin")
        self.assertEqual(self.r["csrfHeader"], "tok123")
        self.assertEqual(self.r["url"], "/api/v1/log")

    def test_buffer_cap_and_batches_of_fifty(self):
        self.assertEqual(self.r["bufferCap"], 200)
        self.assertTrue(self.r["droppedAtCap"])
        self.assertEqual(self.r["batchedMarks"], 200)
        self.assertEqual(self.r["batchCount"], 4)
        self.assertLessEqual(self.r["maxBatchEvents"], 50)
        self.assertLessEqual(self.r["maxBodyBytes"], 16 * 1024)

    def test_failed_send_is_retried_once_then_dropped_silently(self):
        self.assertEqual(self.r["failFirstSends"], 1)
        self.assertEqual(self.r["failTotalSends"], 2)
        self.assertEqual(self.r["failBufferAfter"], 0)
        self.assertEqual(self.r["failBufferStill"], 0)

    def test_phone_page_stays_silent(self):
        self.assertFalse(self.r["phoneActive"])
        self.assertEqual(self.r["phoneBuffered"], 0)
        self.assertEqual(self.r["phoneSends"], 0)

    def test_switch_off_drops_events(self):
        self.assertEqual(self.r["offBuffered"], 0)
        self.assertFalse(self.r["offStatus"])

    def test_submit_records_form_id_and_no_field_values(self):
        self.assertEqual(self.r["submitForms"], ["pl-add"])
        self.assertFalse(self.r["submitLeak"])

    def test_action_records_name_target_and_ref(self):
        self.assertEqual(self.r["actionName"], "toggle-section")
        self.assertEqual(self.r["actionRef"], "rb:rb/task/R1")
        self.assertEqual(self.r["actionTarget"], "plan")

    def test_api_failures_and_slow_calls_only_with_path(self):
        self.assertEqual(self.r["apiCount"], 3)
        self.assertEqual(self.r["apiPaths"], ["/api/v1/projects", "/api/v1/cmd", "/api/v1/cmd"])
        self.assertFalse(self.r["apiLeak"])

    def test_console_wrapper_calls_through_and_records(self):
        self.assertTrue(self.r["consoleCalled"])
        self.assertEqual(self.r["consoleLvl"], "ERROR")
        self.assertEqual(self.r["consoleMsg"], "bad thing")

    def test_window_hooks_record_errors_without_query_strings(self):
        self.assertEqual(self.r["errLvl"], "ERROR")
        self.assertFalse(self.r["errStackLeak"])
        self.assertEqual(self.r["rejLvl"], "ERROR")
        self.assertEqual(self.r["cspBlocked"], "evil.example")
        self.assertFalse(self.r["cspLeak"])

    def test_render_only_when_slow_and_route_has_no_query(self):
        self.assertEqual(self.r["renderCount"], 1)
        self.assertTrue(self.r["routeClean"])

    def test_only_listed_event_names_are_sent(self):
        for name in self.r["eventNames"]:
            self.assertIn(name, EVENT_NAMES)


class LogClientStaticTests(unittest.TestCase):

    def setUp(self):
        self.src = read(LOG_JS)

    def test_no_beacon_no_inner_html_no_console_log_no_eval(self):
        for word in ("sendBeacon", "innerHTML", "console.log", "eval(", "Function(", "<script", "style="):
            self.assertNotIn(word, self.src, word)

    def test_no_inline_handlers_in_the_module(self):
        self.assertIsNone(INLINE_HANDLER.search(self.src))

    def test_keepalive_is_always_on_for_the_post(self):
        self.assertIn("keepalive: true", self.src)
        self.assertNotIn("keepalive: false", self.src)

    def test_exports_the_small_api(self):
        for name in ("logEvent", "mark", "setEnabled", "status", "installLog", "logAction", "noteRequest",
                     "noteRender", "noteRoute"):
            self.assertRegex(self.src, r"export function " + name + r"\(", name)

    def test_event_list_is_closed_and_matches_the_spec(self):
        for name in EVENT_NAMES:
            self.assertIn('["' + name + '"', self.src, name)

    def test_timestamps_and_limits_are_spelled_out(self):
        self.assertIn("FLUSH_MS = 2000", self.src)
        self.assertIn("BATCH_MAX = 50", self.src)
        self.assertIn("BUFFER_MAX = 200", self.src)
        self.assertIn("SLOW_API_MS = 1500", self.src)
        self.assertIn("SLOW_RENDER_MS = 200", self.src)

    def test_hooks_are_wired_into_the_app_and_api_and_cmd(self):
        app = read(APP_JS)
        self.assertIn('from "./log.js"', app)
        self.assertIn("installLog();", app)
        self.assertIn("logAction(action, el, null);", app)
        self.assertIn("noteRender(", app)
        self.assertIn("noteRoute();", app)
        api = read(API_JS)
        self.assertIn("noteRequest(", api)
        self.assertIn('from "./log.js"', api)
        cmd = read(CMD_JS)
        self.assertIn("logAction(op, null,", cmd)

    def test_no_inline_handler_added_to_the_wired_files(self):
        for path in (APP_JS, API_JS, CMD_JS):
            self.assertIsNone(INLINE_HANDLER.search(read(path)), path)


if __name__ == "__main__":
    unittest.main()
