// Render the Tokens, Rules and Settings views in node with a synthetic snapshot that carries meters.limits (used by
// tests/web/test_admin.py). argv: this script, web directory. Prints one JSON object with the HTML of each view.
import { pathToFileURL } from "node:url";

const web = process.argv[2];
const load = (name) => import(pathToFileURL(web + "/js/" + name).href);
const state = await load("state.js");
const tokens = await load("views/tokens.js");
const rules = await load("views/rules.js");
const settings = await load("views/settings.js");

const now = Date.parse("2026-10-13T12:00:00Z");
const raw = {
  project: { id: "splitnet", title: "split-net" },
  summary: {},
  overall: { project: { progress: 0.5, done: 1, total: 2 } },
  phases: [{ id: "P1", name: "Phase one", done: 1, total: 2, progress: 0.5, state: "doing" }],
  tasks: [{ id: "T1", title: "Task one", phase: "P1", state: "done" }],
  budget: {
    phases: { P1: { spent: 12, limit: 50 } },
    models: { sonnet: { spent: 5, limit: null } },
    total: { spent: 17, limit: 100 },
    tasks: { T1: { spent: 12, limit: 10 } },
  },
  meters: {
    limits: [
      { id: "L1", scope: "project", window: "day", kind: "pct", used: 4.1, limit: 10, state: "ok", est: false,
        paceAt: "2026-10-13T16:40:00+03:30", src: "limits", action: "block" },
      { id: "L2", scope: "global", window: "week", kind: "pct", used: 62, limit: 60, state: "block", est: false,
        paceAt: "2026-10-13T16:40:00+03:30", src: "config", action: "block" },
      { id: "AUTO", scope: "project", window: "week", kind: "acct", used: null, limit: 72, state: "unknown",
        est: false, paceAt: null, src: "autonomy", action: "block" },
      { id: "L3", scope: "project", window: "day", kind: "tok", used: 12.5, limit: 50, state: "ok", est: true,
        paceAt: null, src: "limits", action: "warn" },
    ],
    today: { pts: 4.1, tokK: 12.5, estPts: null },
    week: { pct: 62, tokK: 300, estPts: 2.3 },
  },
  rules: [
    { id: "R1", scope: "all", kind: "do", text: "Keep replies short.", value: null },
    { id: "R2", scope: "sonnet", kind: "budget", text: "Budget per task", value: 40 },
  ],
  control: {},
};

const store = state.createStore();
store.projects = [{ id: "splitnet", name: "split-net", progress: 0.5, tasks_left: 1, running: 0, need_user: 0,
  errors_count: 0, stale: false }];
store.snapshots.splitnet = state.normalizeSnapshot(raw, now);
store.usage = state.normalizeUsage({ weeklyPercent: 63, fiveHourPercent: 26, source: "fixture", ageS: 60 }, now);
const prefs = { mode: null, open: {} };

function projectVm(route) {
  return state.buildViewModel(store, route || { name: "project", id: "splitnet" }, prefs, now);
}

function globalVm() {
  const vm = state.buildViewModel(store, { name: "home", id: null }, prefs, now);
  vm.snapshotList = [store.snapshots.splitnet];
  return vm;
}

const limits = await load("views/limits.js");
const out = {};
out.project_tokens = tokens.sectionView(projectVm());
out.global_tokens = tokens.sectionView(globalVm());
limits.limitAction("lim-add", null);
out.project_add = tokens.sectionView(projectVm());
out.global_add = tokens.sectionView(globalVm());
limits.limitAction("lim-add", null);
out.project_rules = rules.sectionView(projectVm());
out.global_rules = rules.sectionView(globalVm());
out.settings = settings.sectionView(globalVm());
const empty = state.createStore();
empty.projects = store.projects;
empty.snapshots.splitnet = state.normalizeSnapshot(Object.assign({}, raw, { meters: { limits: [],
  today: {}, week: {} } }), now);
const emptyVm = state.buildViewModel(empty, { name: "project", id: "splitnet" }, prefs, now);
out.empty_tokens = tokens.sectionView(emptyVm);
console.log(JSON.stringify(out));
