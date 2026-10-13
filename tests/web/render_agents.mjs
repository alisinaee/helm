// Render the Agents and Research views in node (used by tests/web/test_agents.py). No DOM: the views return HTML
// strings. fetch is replaced by a stub that serves the notes API from the test's own data. argv: this script, web
// directory, synthetic snapshot JSON path. Prints one JSON object with the HTML of each view and a few results.
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

const web = process.argv[2];
const synth = JSON.parse(readFileSync(process.argv[3], "utf8"));
const load = (name) => import(pathToFileURL(web + "/js/" + name).href);

// The render events research.js sends after a request. No page here, so the event goes nowhere.
globalThis.document = { dispatchEvent() { return true; } };
const NOTE_TEXT = "# Landscape <b>tools</b>\n\n## Question\n<script>alert(1)</script> & more\n";
const served = [];
globalThis.fetch = async (url) => {
  served.push(String(url));
  const path = String(url);
  if (path.endsWith("/notes")) {
    const rows = path.includes("/quiet/") ? [] : [{ name: "01-landscape.md", title: "Landscape <b>tools</b>",
      size: NOTE_TEXT.length, lines: 4 }];
    return new Response(JSON.stringify({ notes: rows }), { status: 200,
      headers: { "Content-Type": "application/json" } });
  }
  return new Response(NOTE_TEXT, { status: 200, headers: { "Content-Type": "text/plain; charset=utf-8" } });
};

const state = await load("state.js");
const agents = await load("views/agents.js");
const research = await load("views/research.js");

const now = Date.parse("2026-10-13T12:00:00Z");
const projects = [
  { id: "splitnet", name: "split-net", progress: 0.5, tasks_left: 41, running: 4, need_user: 0, errors_count: 0,
    stale: false },
  { id: "quiet", name: "Quiet app", progress: 0, tasks_left: 9, running: 0, need_user: 0, errors_count: 0,
    stale: false },
];

function store(snaps) {
  const s = state.createStore();
  s.projects = projects;
  for (const [id, raw] of Object.entries(snaps)) {
    s.snapshots[id] = state.normalizeSnapshot(Object.assign({ project: { id: id, title: id } }, raw), now);
  }
  return s;
}

const route = (name, id, section) => ({ name: name, id: id, section: section, view: null, item: null, filters: {} });
const prefs = { mode: null, open: {} };
const vmOf = (s, r) => {
  const vm = state.buildViewModel(s, r, prefs, now);
  const all = (s.projects || []).map((p) => s.snapshots[p.id]).filter(Boolean);
  vm.snapshotList = r.name === "project" ? [s.snapshots[r.id]].filter(Boolean) : all;
  return vm;
};

const out = {};
const busy = store({ splitnet: synth.busy, quiet: synth.quiet });
out.agentsProject = agents.sectionView(vmOf(busy, route("project", "splitnet", "agents")));
out.agentsAll = agents.sectionView(vmOf(busy, route("home", null, "agents")));
const idle = store({ quiet: synth.quiet });
out.agentsIdle = agents.sectionView(vmOf(idle, route("project", "quiet", "agents")));
out.agentsLoading = agents.sectionView(vmOf(state.createStore(), route("project", "splitnet", "agents")));

// Research: the all-projects message, then a project whose notes load in two steps (loading, then the list).
out.researchAll = research.sectionView(vmOf(busy, route("home", null, "research")));
out.researchLoading = research.sectionView(vmOf(busy, route("project", "splitnet", "research")));
await new Promise((resolve) => setTimeout(resolve, 30));
out.researchList = research.sectionView(vmOf(busy, route("project", "splitnet", "research")));
research.pageAction("note-open", {
  getAttribute(name) {
    return { "data-project": "splitnet", "data-name": "01-landscape.md" }[name] || null;
  },
});
await new Promise((resolve) => setTimeout(resolve, 30));
out.researchReader = research.sectionView(vmOf(busy, route("project", "splitnet", "research")));
research.pageAction("note-open", {
  getAttribute(name) {
    return { "data-project": "quiet", "data-name": "01-none.md" }[name] || null;
  },
});
out.researchQuietLoading = research.sectionView(vmOf(busy, route("project", "quiet", "research")));
await new Promise((resolve) => setTimeout(resolve, 30));
out.researchQuiet = research.sectionView(vmOf(busy, route("project", "quiet", "research")));
out.served = served;
out.checklistSteps = research.onboardingSteps(busy.snapshots.splitnet).map((s) => s.done);
console.log(JSON.stringify(out));
