// Render the Agents view in node (used by tests/web/test_agents.py). No DOM: the views return HTML
// strings. argv: this script, web directory, synthetic snapshot JSON path. Prints one JSON object with the HTML
// of each view and a few results.
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

const web = process.argv[2];
const synth = JSON.parse(readFileSync(process.argv[3], "utf8"));
const load = (name) => import(pathToFileURL(web + "/js/" + name).href);

const state = await load("state.js");
const agents = await load("views/agents.js");

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

console.log(JSON.stringify(out));
