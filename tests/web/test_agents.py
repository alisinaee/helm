"""The Agents and Research views (WP34), rendered in node by tests/web/render_agents.mjs from synthetic snapshots.

Checks: a worker sits in a nested list under its lead; each running row has a Stop button (disabled when the job has no
task); the blocked badge and the 'handed to' chip appear; only the last 10 finished jobs are listed; the empty state
reads 'No agents running.'; the notes list and the plain-text reader escape their data (no markup from a note is ever
emitted); the onboarding steps tick from the snapshot; every data-action the views emit is handled by app.js; the
routes register both modules; and flow.css stays within its 4 KB budget. The node checks are skipped when node is not
installed.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

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
        job("J2", "running", model="grok-4.7-xhigh", task="P1.2", role="tests", parent="J1",
            started="2026-10-13T11:59:00Z", elapsed_s=60, tokensK=9, effort="medium"),
        job("J3", "running", model="cursor", task=None, role="docs", parent="J1",
            started="2026-10-13T11:59:30Z", elapsed_s=30),
        job("J4", "running", model="agy", task="P2.1", started="2026-10-13T11:50:00Z", elapsed_s=600,
            effort="low"),
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


class AgentsResearchTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if shutil.which("node") is None:
            raise unittest.SkipTest("node is not installed; the Agents and Research render checks are skipped")
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
        self.assertEqual(depths.count(0), 2)     # J1 and J4 are the roots
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
        for text in ("Opus 5.5", "cursor · Grok 4.7", "cursor · Auto", "agy · Gemini 3.8 Flash", "Haiku 5.5"):
            self.assertIn(">" + text + "</span>", html, text)
        self.assertNotIn('chip-neutral">grok-4.7-xhigh', html)
        self.assertNotIn(">cursor<", html)
        self.assertNotIn(">agy<", html)

    def test_effort_column_shows_the_level_or_the_engine_default(self):
        html = self.out["agentsProject"]
        self.assertEqual(html.count('<span class="rg-chips ag-effort">'), 14)  # 4 running and 10 finished rows
        self.assertIn('<span class="rg-chips ag-effort">high</span>', html)      # opus, recorded
        self.assertIn('<span class="rg-chips ag-effort">medium</span>', html)    # grok, recorded
        self.assertIn('<span class="rg-chips ag-effort">low</span>', html)       # agy, recorded
        self.assertEqual(html.count('<span class="rg-chips ag-effort">default</span>'), 10)  # haiku, not recorded
        self.assertEqual(html.count('<span class="rg-chips ag-effort">not set</span>'), 1)   # cursor, not recorded
        self.assertNotIn('ag-effort">\u2014', html)
        self.assertIn('<span class="ag-effort">Effort</span>', html)

    def test_each_row_has_a_stop_button_and_a_task_less_job_has_it_disabled(self):
        html = self.out["agentsProject"]
        self.assertEqual(html.count('data-action="agent-stop"'), 4)
        self.assertEqual(html.count('data-action="agent-stop" data-project="splitnet" data-task="P1.1"'), 1)
        disabled = re.findall(r'<button [^>]*data-action="agent-stop"[^>]*disabled', html)
        self.assertEqual(len(disabled), 1)

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
        self.assertIn("-webkit-line-clamp: 2;", read_text(os.path.join(WEB, "css", "components.css")))

    def test_rows_use_the_shared_fixed_tracks(self):
        html = self.out["agentsProject"]
        self.assertEqual(html.count('<div class="row-grid rg-agent">'), 14)
        self.assertNotIn("grid-area", html)
        self.assertNotIn("style=", html)

    def test_empty_state_reads_as_the_spec_says(self):
        self.assertIn("No agents running.", self.out["agentsIdle"])
        self.assertIn("No finished jobs yet.", self.out["agentsIdle"])
        self.assertIn('aria-busy="true"', self.out["agentsLoading"])

    def test_all_projects_lists_each_project_block(self):
        html = self.out["agentsAll"]
        self.assertIn('<h3 class="grp-h">split-net</h3>', html)

    def test_research_all_projects_asks_for_a_project(self):
        self.assertIn("Choose a project.", self.out["researchAll"])
        self.assertIn("#/p/splitnet/research", self.out["researchAll"])

    def test_research_loads_then_lists_notes_with_escaped_titles(self):
        self.assertIn("Loading the notes.", self.out["researchLoading"])
        html = self.out["researchList"]
        self.assertIn('data-action="note-open" data-project="splitnet" data-name="01-landscape.md"', html)
        self.assertIn("Landscape &lt;b&gt;tools&lt;/b&gt;", html)
        self.assertNotIn("<b>tools</b>", html)
        self.assertIn('aria-pressed="false"', html)

    def test_the_reader_shows_note_text_escaped_and_preformatted(self):
        html = self.out["researchReader"]
        self.assertIn('<pre class="note-text" tabindex="0">', html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt; &amp; more", html)
        self.assertNotIn("<script", html)
        self.assertIn('aria-pressed="true"', html)

    def test_empty_notes_show_the_steps_for_a_new_project(self):
        html = self.out["researchQuiet"]
        self.assertIn("No research notes yet.", html)
        self.assertIn("roadmap research new landscape", html)
        self.assertIn("--project quiet", html)

    def test_onboarding_ticks_come_from_the_snapshot(self):
        self.assertEqual(self.out["checklistSteps"], [True, True, True, True])
        self.assertIn("Onboarding 4 of 4", self.out["researchList"])
        self.assertIn("Onboarding 1 of 4", self.out["researchQuiet"])

    def test_every_data_action_emitted_is_handled_by_app_js(self):
        app = read_text(os.path.join(WEB, "js", "app.js"))
        emitted = set()
        for name in ("agentsProject", "agentsIdle", "researchList", "researchReader", "researchQuiet"):
            emitted.update(ACTIONS.findall(self.out[name]))
        self.assertTrue({"agent-stop", "note-open", "note-refresh"} <= emitted)
        for action in emitted:
            self.assertIn('"' + action + '"', app, action)

    def test_routes_register_both_modules(self):
        routes = read_text(os.path.join(WEB, "js", "routes.js"))
        self.assertIn('module: "./views/agents.js"', routes)
        self.assertIn('module: "./views/research.js"', routes)

    def test_flow_css_stays_within_its_budget(self):
        size = os.path.getsize(os.path.join(WEB, "css", "flow.css"))
        self.assertLessEqual(size, 4608, "flow.css is %d bytes" % size)

    def test_the_views_use_no_raw_colours(self):
        for name in ("agents.js", "research.js"):
            text = read_text(os.path.join(WEB, "js", "views", name))
            self.assertIsNone(re.search(r"#[0-9a-fA-F]{3,6}\b", text), name)


if __name__ == "__main__":
    unittest.main()
