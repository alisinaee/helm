"""The Agents finished history (R7.60), rendered in node from an inline script (no page, no server).

Checks: the first 10 finished rows show, each with a select checkbox in its Stop cell; Remove selected is disabled until
a row is picked, then enabled and counted; Load more reveals the rows already known, then reads the next page from
GET .../jobs?offset&limit and appends it; the controls carry data-agent, not data-action; no inline style. The node
check is skipped when node is not installed.
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

SCRIPT = r"""
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
const input = JSON.parse(readFileSync(0, "utf8"));
const load = (name) => import(pathToFileURL(input.web + "/js/" + name).href);
const handlers = {};
const events = [];
globalThis.document = {
  dispatchEvent(ev) { events.push(ev.type); return true; },
  addEventListener(type, fn) { handlers[type] = fn; },
  querySelectorAll() { return []; },
};
const pad = (n) => String(n).padStart(2, "0");
const finished = (n) => ({ id: "F" + n, title: "job F" + n, model: "haiku", task: null, status: "done",
  started: "2026-10-13T09:00:00Z", ended: "2026-10-13T09:" + pad(n + 1) + ":00Z", elapsed_s: 60, tokensK: n + 1 });
// The job file, newest first: F12 is the newest of 13 finished jobs.
const server = [];
for (let n = 12; n >= 0; n -= 1) server.push(finished(n));
const served = [];
globalThis.fetch = async (url) => {
  const u = new URL(String(url), "http://localhost");
  served.push(u.pathname + u.search);
  const offset = Number(u.searchParams.get("offset"));
  const limit = Number(u.searchParams.get("limit"));
  const body = { offset: offset, limit: limit, total: server.length, rows: server.slice(offset, offset + limit) };
  return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
};
const state = await load("state.js");
const agents = await load("views/agents.js");
const now = Date.parse("2026-10-13T12:00:00Z");
const prefs = { mode: null, open: {} };
const range = (a, b) => { const out = []; for (let n = a; n <= b; n += 1) out.push(finished(n)); return out; };
const snapFor = (id, jobs) => {
  const s = state.createStore();
  s.projects = [{ id: id, name: id, progress: 0, tasks_left: 0, running: 0, need_user: 0, errors_count: 0,
    stale: false }];
  s.snapshots[id] = state.normalizeSnapshot({ project: { id: id, title: id }, jobs: jobs, blocked: [], tasks: [],
    phases: [], rules: null }, now);
  return s;
};
const vmOf = (s, id) => {
  const r = { name: "project", id: id, section: "agents", view: null, item: null, filters: {} };
  const vm = state.buildViewModel(s, r, prefs, now);
  vm.snapshotList = [s.snapshots[id]];
  return vm;
};
const el = (attrs, checked) => ({ checked: !!checked, getAttribute: (n) => (n in attrs ? attrs[n] : null),
  closest() { return this; } });
const out = {};
const busy = snapFor("busy", range(0, 11));
const ten = snapFor("ten", range(3, 12));
out.first = agents.sectionView(vmOf(busy, "busy"));
handlers.change({ target: el({ "data-agent": "select", "data-project": "busy", "data-id": "F11" }, true) });
out.picked = agents.sectionView(vmOf(busy, "busy"));
handlers.click({ target: { closest: () => el({ "data-agent": "more", "data-project": "busy" }) } });
out.revealed = agents.sectionView(vmOf(busy, "busy"));
out.tenFirst = agents.sectionView(vmOf(ten, "ten"));
handlers.click({ target: { closest: () => el({ "data-agent": "more", "data-project": "ten" }) } });
await new Promise((resolve) => setTimeout(resolve, 40));
out.tenLoaded = agents.sectionView(vmOf(ten, "ten"));
out.served = served;
out.renders = events.length;
console.log(JSON.stringify(out));
"""


def render():
    node = shutil.which("node")
    proc = subprocess.run([node, "--input-type=module", "-e", SCRIPT], input=json.dumps({"web": WEB}),
                          capture_output=True, text=True, check=False, timeout=60)
    if proc.returncode != 0:
        raise AssertionError("agents history script failed: " + proc.stderr[-800:])
    return json.loads(proc.stdout)


def select_rows(html):
    return len(re.findall(r'<input type="checkbox" data-agent="select"', html))


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class AgentsHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = render()

    def test_the_first_page_shows_ten_finished_rows_with_a_checkbox_each(self):
        html = self.out["first"]
        self.assertEqual(select_rows(html), 10)
        self.assertEqual(html.count('<li class="ag-row"><div class="row-grid rg-agent">'), 10)
        self.assertIn("Showing 10 of 12", html)
        self.assertIn('data-agent="select" data-project="busy" data-id="F11"', html)

    def test_remove_selected_starts_disabled_and_load_more_is_offered(self):
        html = self.out["first"]
        self.assertRegex(html, r'<button type="button" class="btn btn-small" data-agent="remove"'
                               r' data-project="busy" disabled>Remove selected</button>')
        self.assertIn('data-agent="more" data-project="busy">Load more</button>', html)

    def test_a_picked_row_stays_checked_and_enables_remove(self):
        html = self.out["picked"]
        self.assertRegex(html, r'data-id="F11"[^>]*checked')
        self.assertIn("1 selected", html)
        self.assertRegex(html, r'data-agent="remove" data-project="busy">Remove selected')
        self.assertNotIn('data-agent="remove" data-project="busy" disabled', html)

    def test_load_more_reveals_the_rows_already_known(self):
        self.assertEqual(select_rows(self.out["revealed"]), 12)
        self.assertIn("Showing 12 of 12", self.out["revealed"])

    def test_load_more_reads_the_next_page_from_the_paged_route(self):
        self.assertEqual(select_rows(self.out["tenFirst"]), 10)
        self.assertIn("/api/v1/projects/ten/jobs?offset=10&limit=10", self.out["served"])
        html = self.out["tenLoaded"]
        self.assertEqual(select_rows(html), 13)
        self.assertIn("Showing 13 of 13", html)
        self.assertNotIn('data-agent="more" data-project="ten"', html)

    def test_the_history_controls_use_data_agent_and_no_inline_style(self):
        for name in ("first", "picked", "revealed", "tenLoaded"):
            self.assertNotIn('data-action="more"', self.out[name])
            self.assertNotIn('data-action="remove"', self.out[name])
            self.assertNotIn("style=", self.out[name])

    def test_the_view_asks_the_person_only_op_for_removal(self):
        with open(os.path.join(WEB, "js", "views", "agents.js"), encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn('run("job.remove", { ids: ids }', text)
        self.assertIn("/jobs?offset=", text)


if __name__ == "__main__":
    unittest.main()
