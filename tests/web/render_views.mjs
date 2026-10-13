// Render the project and home views in node with a snapshot (used by tests/web/test_views.py).
// argv: this script, web directory, snapshot JSON path. Prints one JSON object with the HTML of each view.
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

const web = process.argv[2];
const raw = JSON.parse(readFileSync(process.argv[3], "utf8"));
const load = (name) => import(pathToFileURL(web + "/js/" + name).href);
const state = await load("state.js");
const home = await load("views/home.js");

const now = Date.parse("2026-10-13T12:00:00Z");
const snap = Object.assign({ project: { id: "splitnet", title: "split-net" } }, raw);
const store = state.createStore();
store.projects = [{ id: "splitnet", name: "split-net", progress: 0.5659, tasks_left: 41, running: 2,
  need_user: 3, errors_count: 0, stale: false }];
store.snapshots.splitnet = state.normalizeSnapshot(snap, now);
store.usage = state.normalizeUsage({ weeklyPercent: 63, fiveHourPercent: 26, source: "fixture", ageS: 60 }, now);
const route = { name: "project", id: "splitnet" };
const modes = {
  default: { mode: null, open: {} },
  minimal: { mode: "minimal", open: {} },
  expanded: { mode: "expanded", open: {} },
};
const out = {};
for (const name of Object.keys(modes)) {
  out[name] = home.projectView(state.buildViewModel(store, route, modes[name], now));
}
out.home = home.homeView(state.buildViewModel(store, { name: "home", id: null }, { mode: null, open: {} }, now));
console.log(JSON.stringify(out));
