// Render the job lists and the panels that carry copy-reference buttons in node
// (used by tests/web/test_ref_wiring_p7.py).
// argv: this script, web directory, snapshot JSON (the golden snapshot with jobs and meters added). Prints one JSON
// object with the HTML of each view: Running now, Agents, Activity, Recent progress, Work (List), Tokens (project and
// all projects) and the Usage band.
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

const web = process.argv[2];
const raw = JSON.parse(readFileSync(process.argv[3], "utf8"));
const load = (name) => import(pathToFileURL(web + "/js/" + name).href);
const state = await load("state.js");
const running = await load("views/running.js");
const agents = await load("views/agents.js");
const activity = await load("views/activity.js");
const recent = await load("views/recent.js");
const work = await load("views/work.js");
const tokens = await load("views/tokens.js");
const usage = await load("views/usage.js");

const now = Date.parse("2026-10-13T12:00:00Z");
const projects = [
  { id: "splitnet", name: "split-net", progress: 0.5, tasks_left: 41, running: 2, need_user: 0, errors_count: 0,
    stale: false },
];

const s = state.createStore();
s.projects = projects;
s.snapshots.splitnet = state.normalizeSnapshot(Object.assign({ project: { id: "splitnet", title: "split-net" } }, raw),
  now);
s.usage = state.normalizeUsage({ weeklyPercent: 62, fiveHourPercent: 20, source: "fixture", ageS: 60 }, now);

const route = (name, id, section, view) => ({ name: name, id: id, section: section, view: view || null, item: null,
  filters: {} });
const prefs = { mode: null, open: {} };
const vmOf = (r) => {
  const vm = state.buildViewModel(s, r, prefs, now);
  const all = (s.projects || []).map((p) => s.snapshots[p.id]).filter(Boolean);
  vm.snapshotList = r.name === "project" ? [s.snapshots[r.id]].filter(Boolean) : all;
  return vm;
};

const out = {};
const project = vmOf(route("project", "splitnet", "overview"));
out.running = running.runningSection(project);
out.agents = agents.sectionView(vmOf(route("project", "splitnet", "agents")));
out.agentsAll = agents.sectionView(vmOf(route("home", null, "agents")));
out.activity = activity.sectionView(vmOf(route("project", "splitnet", "activity")));
out.recent = recent.recentSection(project);
out.work = work.sectionView(vmOf(route("project", "splitnet", "work", "list")));
out.tokens = tokens.sectionView(vmOf(route("project", "splitnet", "tokens")));
out.tokensAll = tokens.sectionView(vmOf(route("home", null, "tokens")));
out.usage = usage.usageView(vmOf(route("project", "splitnet", "overview")));
console.log(JSON.stringify(out));
