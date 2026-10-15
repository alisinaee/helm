// Render the simple Tokens view (R7.28 B) in node with synthetic snapshots (used by tests/web/test_tokens_simple.py).
// argv: this script, web directory. Prints one JSON object with the HTML of each case.
import { pathToFileURL } from "node:url";

const web = process.argv[2];
const load = (name) => import(pathToFileURL(web + "/js/" + name).href);
const state = await load("state.js");
const tokens = await load("views/tokens.js");

const now = Date.parse("2026-10-13T12:00:00Z");
function snapshot(id, title, meters, extra) {
  return Object.assign({
    project: { id: id, title: title },
    summary: {},
    overall: { project: { progress: 0.5, done: 1, total: 2 } },
    phases: [{ id: "P1", name: "Phase one", done: 1, total: 2, progress: 0.5, state: "doing" }],
    tasks: [{ id: "T1", title: "Task one", phase: "P1", state: "done" }],
    budget: { phases: {}, models: {}, total: { spent: 17, limit: null } },
    meters: meters,
  }, extra || {});
}
const okMeters = {
  limits: [
    { id: "L2", scope: "global", window: "week", kind: "pct", used: 62, limit: 95, state: "ok", est: false,
      paceAt: null, src: "config", action: "block" },
    { id: "L1", scope: "project", window: "week", kind: "pct", used: 4, limit: 10, state: "ok", est: false,
      paceAt: null, src: "limits", action: "block" },
  ],
  today: { pts: 4.1, tokK: 12.5, estPts: null },
  week: { pct: 62, tokK: 300, estPts: 2.3 },
};
const blockedMeters = {
  limits: [
    { id: "L9", scope: "project", window: "week", kind: "pct", used: 11, limit: 10, state: "block", est: false,
      paceAt: null, src: "limits", action: "block" },
  ],
  today: { pts: 1, tokK: 2, estPts: null },
  week: { pct: 11, tokK: 150, estPts: 1.5 },
};

const store = state.createStore();
store.projects = [
  { id: "splitnet", name: "split-net", progress: 0.5, tasks_left: 1, running: 0, need_user: 0, errors_count: 0,
    stale: false },
  { id: "alpha", name: "alpha", progress: 0.2, tasks_left: 3, running: 0, need_user: 0, errors_count: 0,
    stale: false },
];
store.snapshots.splitnet = state.normalizeSnapshot(snapshot("splitnet", "split-net", okMeters), now);
store.snapshots.alpha = state.normalizeSnapshot(snapshot("alpha", "alpha", blockedMeters), now);
store.snapshots.splitnet.usage = state.normalizeUsage({ weeklyPercent: 63, fiveHourPercent: 26,
  weeklyResetsAt: "2026-10-16T12:00:00Z", source: "fixture", ageS: 60 }, now);
const prefs = { mode: null, open: {} };

function vmOf(route, usage) {
  const s = usage ? state.createStore() : store;
  if (usage) {
    s.projects = store.projects;
    const withUsage = Object.assign({}, store.snapshots.splitnet, { usage: state.normalizeUsage(usage, now) });
    s.snapshots = Object.assign({}, store.snapshots, { splitnet: withUsage });
  }
  const vm = state.buildViewModel(s, route, prefs, now);
  if (route.name === "home") vm.snapshotList = [s.snapshots.splitnet, s.snapshots.alpha];
  return vm;
}

const out = {};
out.project = tokens.sectionView(vmOf({ name: "project", id: "splitnet" }));
out.blocked = tokens.sectionView(vmOf({ name: "project", id: "alpha" }));
out.global = tokens.sectionView(vmOf({ name: "home", id: null }));
out.noToken = tokens.sectionView(vmOf({ name: "project", id: "splitnet" },
  { syncError: "no_token", veryOld: true, lastError: "no token", source: "manual push", ageS: 9000 }));

const empty = state.createStore();
empty.projects = [];
out.empty = tokens.sectionView(state.buildViewModel(empty, { name: "home", id: null }, prefs, now));

// The top bar text (topbar.js): the weekly share from snap.usage and the weekly stop from the meter rows.
const topbar = await load("views/topbar.js");
const bar = (route, rows, usage) => topbar.topbarView({ route: route, control: null, conn: { ok: true },
  meterRows: rows, usage: usage, theme: "auto", ui: { panelOpen: true } });
out.topbar = bar({ name: "project", id: "splitnet" }, okMeters.limits, { weeklyPercent: 63 });
out.topbarAll = bar({ name: "home", id: null }, okMeters.limits, { weeklyPercent: 63 });
out.topbarOff = bar({ name: "home", id: null }, [], { weeklyPercent: 12 });
out.topbarUnknown = bar({ name: "home", id: null }, null, null);
console.log(JSON.stringify(out));
