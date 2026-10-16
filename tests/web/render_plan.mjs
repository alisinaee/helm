// Render the Roadmap view, and the restored Overview sections, in node (used by tests/web/test_plan.py).
// argv: this script, web directory, golden snapshot JSON, synthetic snapshot JSON. Prints one JSON object with the HTML
// of each view. The synthetic snapshot has a blocker on P2.1, one approved phase, one unapproved phase with a budget,
// a deferred task and a title that needs escaping.
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

const web = process.argv[2];
const golden = JSON.parse(readFileSync(process.argv[3], "utf8"));
const synth = JSON.parse(readFileSync(process.argv[4], "utf8"));
const load = (name) => import(pathToFileURL(web + "/js/" + name).href);
const state = await load("state.js");
const roadmap = await load("views/roadmap.js");
const overview = await load("views/overview.js");

const now = Date.parse("2026-10-13T12:00:00Z");

function store(snaps) {
  const s = state.createStore();
  s.projects = [{ id: "splitnet", name: "split-net", progress: 0.5, tasks_left: 41, running: 0, need_user: 1,
    errors_count: 0, stale: false }];
  for (const [id, raw] of Object.entries(snaps)) {
    s.snapshots[id] = state.normalizeSnapshot(Object.assign({ project: { id: id, title: id } }, raw), now);
  }
  s.usage = state.normalizeUsage({ weeklyPercent: 62, source: "fixture", ageS: 60 }, now);
  return s;
}

const prefs = { mode: null, open: {} };
// The fields app.js adds to the view model: the snapshots in scope, the control state and the meter rows.
function vmOf(s, route, prefOpen) {
  const vm = state.buildViewModel(s, route, Object.assign({}, prefs, { open: prefOpen || {} }), now);
  vm.snapshotList = route.name === "project" ? [s.snapshots[route.id]].filter(Boolean) : [];
  vm.control = null;
  return vm;
}
const project = (section, view, filters) => ({ name: "project", id: "splitnet", section: section, view: view || null,
  item: null, filters: filters || {} });
const home = (section) => ({ name: "home", id: null, section: section, view: null, item: null, filters: {} });

const out = {};
const goldenStore = store({ splitnet: golden });
out.lanesGolden = roadmap.sectionView(vmOf(goldenStore, project("roadmap")));
out.timelineGolden = roadmap.sectionView(vmOf(goldenStore, project("roadmap", "timeline")));
out.overviewGolden = overview.sectionView(vmOf(goldenStore, project("overview")));

const synthStore = store({ splitnet: synth });
out.lanesSynth = roadmap.sectionView(vmOf(synthStore, project("roadmap")));
out.timelineSynth = roadmap.sectionView(vmOf(synthStore, project("roadmap", "timeline")));
out.overviewSynth = overview.sectionView(vmOf(synthStore, project("overview")));

// No plan: the phases list is empty, so the Roadmap and the empty issue list say what to do.
const emptyStore = store({ splitnet: { project: { id: "splitnet", title: "split-net" }, phases: [], tasks: [],
  issues: [] } });
out.lanesEmpty = roadmap.sectionView(vmOf(emptyStore, project("roadmap")));

// Not in a project: both sections say the page belongs to one project.
out.roadmapAll = roadmap.sectionView(vmOf(synthStore, home("roadmap")));

// A project whose data is not loaded yet shows a skeleton, not an empty page.
out.roadmapLoading = roadmap.sectionView(vmOf(state.createStore(), project("roadmap")));

console.log(JSON.stringify(out));
