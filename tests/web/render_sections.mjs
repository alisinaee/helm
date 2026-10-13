// Render the Overview, Inbox and Activity views in node (used by tests/web/test_sections.py).
// argv: this script, web directory, golden snapshot JSON, synthetic snapshot JSON. Prints one JSON object with the HTML
// of each view. The synthetic snapshot carries questions, needs-you rows, limits at 90%, activity and blockers.
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

const web = process.argv[2];
const golden = JSON.parse(readFileSync(process.argv[3], "utf8"));
const synth = JSON.parse(readFileSync(process.argv[4], "utf8"));
const load = (name) => import(pathToFileURL(web + "/js/" + name).href);
const state = await load("state.js");
const overview = await load("views/overview.js");
const inbox = await load("views/inbox.js");
const activity = await load("views/activity.js");

const now = Date.parse("2026-10-13T12:00:00Z");
const projects = [
  { id: "splitnet", name: "split-net", progress: 0.5, tasks_left: 41, running: 0, need_user: 1, errors_count: 0,
    stale: false },
  { id: "quiet", name: "Quiet app", progress: 0.1, tasks_left: 9, running: 0, need_user: 0, errors_count: 0,
    stale: false },
];

function store(snaps) {
  const s = state.createStore();
  s.projects = projects;
  for (const [id, raw] of Object.entries(snaps)) {
    s.snapshots[id] = state.normalizeSnapshot(Object.assign({ project: { id: id, title: id } }, raw), now);
  }
  s.usage = state.normalizeUsage({ weeklyPercent: 62, source: "fixture", ageS: 60 }, now);
  return s;
}

const route = (name, id, section) => ({ name: name, id: id, section: section, view: null, item: null, filters: {} });
const prefs = { mode: null, open: {} };
// The same fields app.js adds to the view model (buildShellVm): the snapshots in scope.
const vmOf = (s, r) => {
  const vm = state.buildViewModel(s, r, prefs, now);
  const all = (s.projects || []).map((p) => s.snapshots[p.id]).filter(Boolean);
  vm.snapshotList = r.name === "project" ? [s.snapshots[r.id]].filter(Boolean) : all;
  vm.control = r.name === "project" && s.snapshots[r.id]
    ? { known: true, id: r.id, stopped: s.snapshots[r.id].control.stopped,
        blocked: s.snapshots[r.id].control.blocked, reason: s.snapshots[r.id].control.reason }
    : null;
  return vm;
};
const out = {};

// Project scope with the golden snapshot (no questions, limits or activity): empty states.
const goldenStore = store({ splitnet: golden });
out.overviewGolden = overview.sectionView(vmOf(goldenStore, route("project", "splitnet", "overview")));
out.inboxGolden = inbox.sectionView(vmOf(goldenStore, route("project", "splitnet", "inbox")));
out.activityGolden = activity.sectionView(vmOf(goldenStore, route("project", "splitnet", "activity")));

// Project scope with the synthetic snapshot.
const synthStore = store({ splitnet: synth });
out.overviewProject = overview.sectionView(vmOf(synthStore, route("project", "splitnet", "overview")));
out.inboxProject = inbox.sectionView(vmOf(synthStore, route("project", "splitnet", "inbox")));
out.activityProject = activity.sectionView(vmOf(synthStore, route("project", "splitnet", "activity")));

// All projects: one snapshot with the synthetic data, one without (its project has no snapshot yet).
const allStore = store({ splitnet: synth });
out.overviewAll = overview.sectionView(vmOf(allStore, route("home", null, "overview")));
out.inboxAll = inbox.sectionView(vmOf(allStore, route("home", null, "inbox")));
out.activityAll = activity.sectionView(vmOf(allStore, route("home", null, "activity")));

// A project whose data is not loaded yet shows a skeleton, not an empty page.
const loadingVm = vmOf(state.createStore(), route("project", "splitnet", "inbox"));
out.inboxLoading = inbox.sectionView(loadingVm);

console.log(JSON.stringify(out));
