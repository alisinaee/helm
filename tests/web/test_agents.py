"""The Agents view (WP34), rendered in node by tests/web/render_agents.mjs from synthetic snapshots.

Checks: a worker sits in a nested list under its lead; each running row has a Stop button (disabled when the job has no
task); the blocked badge and the 'handed to' chip appear; only the last 10 finished jobs are listed; the empty state
reads 'No agents running.'; every data-action the views emit is handled by app.js; the routes register the agents
module; and flow.css stays within its 4 KB budget. The node checks are skipped when node is not installed.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from tests.web.test_shell import FLOW_CSS_MAX

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
WEB = os.path.join(REPO, "web")
RENDER = os.path.join(TESTS, "web", "render_agents.mjs")

INLINE = re.compile(r'\sstyle\s*=|\son[a-z]{3,}\s*=', re.IGNORECASE)
ACTIONS = re.compile(r'data-action="([^"]+)"')
TREE_ROW = re.compile(r'<li class="ag-row" data-depth="(\d+)">')


def read_text(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def job(jid, status, **extra):
    row = {"id": jid, "title": "job " + jid, "model": "haiku", "task": None, "status": status,
           "started": "2026-10-13T11:00:00Z", "ended": None, "elapsed_s": None, "tokensK": None}
    row.update(extra)
    return row


def synthetic():
    running = [
        job("J1", "running", model="opus", task="P1.1", role="lead", started="2026-10-13T11:58:00Z",
            elapsed_s=120, tokensK=40, parent=None, effort="high"),
        job("J2", "running", model="cursor", engine_model="grok-4.7-xhigh", task="P1.2", role="tests", parent="J1",
            started="2026-10-13T11:59:00Z", elapsed_s=60, tokensK=9, effort="medium"),
        job("J3", "running", model="cursor", engine_model="auto", task=None, role="docs", parent="J1",
            started="2026-10-13T11:59:30Z", elapsed_s=30),
        job("J4", "running", model="agy", task="P2.1", started="2026-10-13T11:50:00Z", elapsed_s=600,
            effort="low"),
        job("J5", "running", model="opencode", task="P2.2", started="2026-10-13T11:55:00Z", elapsed_s=300,
            effort="xhigh", engine_model="laguna-s-2.1"),
    ]
    finished = []
    for n in range(12):
        finished.append(job("F%d" % n, "done" if n % 4 else "failed", task="P0.%d" % n,
                            started="2026-10-13T09:00:00Z", ended="2026-10-13T09:%02d:00Z" % (n + 1),
                            elapsed_s=60.0 + n, tokensK=float(n + 1)))
    tasks = [{"id": "P1.1", "title": "Engine", "phase": "P1", "state": "active", "tokensK": 10, "checkK": 0,
              "model": "opus"}]
    phases = [{"id": "P1", "title": "Engine", "approved": True}]
    busy = {"project": {"id": "splitnet", "title": "split-net"}, "jobs": running + finished,
            "blocked": ["P1.2"], "tasks": tasks, "phases": phases, "rules": [{"id": "R1", "scope": "project",
                                                                              "kind": "stop", "text": "x",
                                                                              "value": None}]}
    quiet = {"project": {"id": "quiet", "title": "quiet"}, "jobs": [], "blocked": [], "tasks": [], "phases": [],
             "rules": None}
    return {"busy": busy, "quiet": quiet}


def render(path):
    node = shutil.which("node")
    proc = subprocess.run([node, "--experimental-default-type=module", RENDER, WEB, path],
                          capture_output=True, text=True, check=False, timeout=60)
    if proc.returncode != 0:
        raise AssertionError("render_agents.mjs failed: " + proc.stderr[-800:])
    return json.loads(proc.stdout)


class AgentsTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if shutil.which("node") is None:
            raise unittest.SkipTest("node is not installed; the Agents render checks are skipped")
        cls.tmp = tempfile.mkdtemp(prefix="ag-test-")
        path = os.path.join(cls.tmp, "synthetic.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(synthetic(), fh)
        cls.out = render(path)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(getattr(cls, "tmp", ""), ignore_errors=True)

    def test_views_render_and_emit_no_inline_handlers_or_scripts(self):
        for name, html in self.out.items():
            if not isinstance(html, str):
                continue
            self.assertGreater(len(html), 20, name)
            self.assertIsNone(INLINE.search(html), name)
            self.assertNotIn("<script", html, name)

    def test_the_worker_is_nested_under_its_lead(self):
        html = self.out["agentsProject"]
        self.assertIn('<ul class="ag-kids"', html)
        depths = [int(d) for d in TREE_ROW.findall(html)]
        self.assertEqual(depths.count(0), 3)     # J1, J4 and J5 are the roots
        self.assertEqual(depths.count(1), 2)     # J2 and J3 are workers under J1
        lead = html.index('<span class="rg-t ag-title" title="job J1">job J1</span>')
        worker = html.index('<span class="rg-t ag-title" title="job J2">job J2</span>')
        self.assertLess(lead, worker)
        self.assertLess(worker, html.index("job J4"))

    def test_rows_show_model_role_task_elapsed_tokens_and_badges(self):
        html = self.out["agentsProject"]
        self.assertIn("Delegated to tests, docs", html)
        self.assertIn(">blocked<", html)
        self.assertIn('href="#/p/splitnet/work/i/P1.1"', html)
        self.assertIn('class="rg-num num">', html)
        self.assertIn("data-started-ms=", html)

    def test_model_column_shows_the_exact_engine(self):
        html = self.out["agentsProject"]
        for text in ("Opus 5.5", "cursor · grok-4.7", "cursor · auto", "agy · Gemini 3.8 Flash", "Haiku 5.5"):
            self.assertIn(">" + text + "</span>", html, text)
        self.assertNotIn('chip-neutral">grok-4.7-xhigh', html)
        self.assertNotIn(">cursor<", html)
        self.assertNotIn(">agy<", html)

    def test_model_chip_shows_the_engine_model_when_recorded(self):
        html = self.out["agentsProject"]
        self.assertIn(">opencode · laguna-s-2.1</span>", html)
        self.assertNotIn(">opencode</span>", html)

    def test_effort_column_shows_the_level_or_the_engine_default(self):
        html = self.out["agentsProject"]
        self.assertEqual(html.count('<span class="rg-chips ag-effort">'), 15)  # 5 running and 10 finished rows
        self.assertIn('<span class="rg-chips ag-effort">xhigh</span>', html)     # opencode, recorded
        self.assertIn('<span class="rg-chips ag-effort">high</span>', html)      # opus, recorded
        self.assertIn('<span class="rg-chips ag-effort">med</span>', html)    # grok, recorded
        self.assertIn('<span class="rg-chips ag-effort">low</span>', html)       # agy, recorded
        # haiku (10), cursor (1) and the task-less agents show a short dash when no level is recorded
        self.assertEqual(html.count('<span class="rg-chips ag-effort">\u2013</span>'), 11)
        self.assertIn('<span class="ag-effort">Effort</span>', html)

    def test_head_opencode_and_cursor_effort_come_from_the_engine_name(self):
        head = job("H1", "running", model="head", task=None, started="2026-10-13T11:00:00Z")
        grok = job("G1", "running", model="cursor", engine_model="grok-4.7-xhigh", task=None)
        opencode = job("O1", "running", model="opencode", engine_model="laguna-s-2.1", task=None)
        path = os.path.join(self.tmp, "engines.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"busy": {"project": {"id": "splitnet", "title": "split-net"}, "jobs": [head, grok, opencode],
                                "blocked": [], "tasks": [], "phases": [], "rules": None}}, fh)
        html = render(path)["agentsProject"]
        self.assertIn(">head · Opus 5.5</span>", html)
        self.assertIn(">cursor · grok-4.7</span>", html)
        self.assertIn(">opencode · laguna-s-2.1</span>", html)
        self.assertIn('<span class="rg-chips ag-effort">xhigh</span>', html)   # cursor, from its engine model
        self.assertEqual(html.count('<span class="rg-chips ag-effort">\u2013</span>'), 2)  # head and opencode
        self.assertNotIn(">head<", html)
        self.assertNotIn(">Cursor", html)

    def test_each_row_has_a_stop_button_and_a_task_less_job_has_it_disabled(self):
        html = self.out["agentsProject"]
        self.assertEqual(html.count('data-action="agent-stop"'), 5)
        self.assertEqual(html.count('data-action="agent-stop" data-project="splitnet" data-task="P1.1"'), 1)
        disabled = re.findall(r'<button [^>]*data-action="agent-stop"[^>]*disabled', html)
        self.assertEqual(len(disabled), 1)

    def test_delegated_chip_shows_the_engine_model_of_an_opencode_worker(self):
        lead = job("L1", "running", model="opencode", task=None, engine_model="laguna-s-2.1")
        worker = job("W1", "running", model="opencode", task=None, parent="L1", engine_model="laguna-s-2.1")
        path = os.path.join(self.tmp, "delegated.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"busy": {"project": {"id": "splitnet", "title": "split-net"}, "jobs": [lead, worker],
                                "blocked": [], "tasks": [], "phases": [], "rules": None}}, fh)
        html = render(path)["agentsProject"]
        self.assertIn("Delegated to opencode · laguna-s-2.1", html)

    def test_only_the_last_ten_finished_jobs_are_listed(self):
        html = self.out["agentsProject"]
        self.assertIn("Recently finished jobs", html)
        self.assertEqual(html.count('<li class="ag-row"><div class="row-grid rg-agent">'), 10)
        self.assertIn("Failed", html)

    def test_effort_column_is_always_visible(self):
        html = self.out["agentsProject"]
        self.assertIn('class="ag-list" aria-label="Running agents"', html)
        self.assertIn('class="ag-list" aria-label="Last finished jobs"', html)
        self.assertNotIn("ag-noeffort", html)
        self.assertIn('<span class="ag-effort">Effort</span>', html)
        self.assertIn("text-overflow: ellipsis", read_text(os.path.join(WEB, "css", "components.css")))

    def test_title_column_and_icon_actions(self):
        html = self.out["agentsProject"]
        self.assertEqual(html.count('class="ag-lead"'), 15 + 2)   # rows plus the two headers
        self.assertIn('<span class="rg-main">Title</span>', html)
        self.assertIn('aria-label="Stop P1.1"', html)
        self.assertIn('class="ag-dot"', html)
        self.assertNotIn(">Stop</button>", html)
        self.assertNotIn("not yet", html)
        self.assertIn('<div class="ag-foot">', html)

    def test_rows_use_the_shared_fixed_tracks(self):
        html = self.out["agentsProject"]
        self.assertEqual(html.count('<div class="row-grid rg-agent">'), 15)
        self.assertNotIn("grid-area", html)
        self.assertNotIn("style=", html)

    def test_claimed_jobs_show_a_claimed_chip_in_both_lists(self):
        for name in ("agents.js", "running.js"):
            text = read_text(os.path.join(WEB, "js", "views", name))
            self.assertIn('"claimed"', text, name)
        self.assertIn('"claimed", "neutral"', read_text(os.path.join(WEB, "js", "views", "agents.js")))

    def test_phone_rows_label_effort_task_elapsed_and_tokens(self):
        css = read_text(os.path.join(WEB, "css", "components.css"))
        self.assertIn('content: "Effort "', css)
        self.assertIn('content: "Elapsed "', css)
        self.assertIn('content: "Tokens "', css)

    def test_empty_state_reads_as_the_spec_says(self):
        self.assertIn("No agents running.", self.out["agentsIdle"])
        self.assertIn("No finished jobs yet.", self.out["agentsIdle"])
        self.assertIn('aria-busy="true"', self.out["agentsLoading"])

    def test_all_projects_lists_each_project_block(self):
        html = self.out["agentsAll"]
        self.assertIn('<h3 class="grp-h">split-net</h3>', html)

    def test_every_data_action_emitted_is_handled_by_app_js(self):
        app = read_text(os.path.join(WEB, "js", "app.js"))
        emitted = set()
        for name in ("agentsProject", "agentsIdle"):
            emitted.update(ACTIONS.findall(self.out[name]))
        self.assertIn("agent-stop", emitted)
        for action in emitted:
            self.assertIn('"' + action + '"', app, action)

    def test_routes_register_both_modules(self):
        routes = read_text(os.path.join(WEB, "js", "routes.js"))
        self.assertIn('module: "./views/agents.js"', routes)

    def test_flow_css_stays_within_its_budget(self):
        size = os.path.getsize(os.path.join(WEB, "css", "flow.css"))
        self.assertLessEqual(size, FLOW_CSS_MAX, "flow.css is %d bytes" % size)

    def test_the_views_use_no_raw_colours(self):
        for name in ("agents.js",):
            text = read_text(os.path.join(WEB, "js", "views", name))
            self.assertIsNone(re.search(r"#[0-9a-fA-F]{3,6}\b", text), name)


if __name__ == "__main__":
    unittest.main()
