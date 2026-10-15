// Render the Rules view in node for tests/web/test_ux_rules.py. Only state.js and rules.js load, so other views in
// flux do not break it. argv: this script, web directory. Prints one JSON object: all (tab All) and phase (a tab with
// no rules in it).
import { pathToFileURL } from "node:url";

const web = process.argv[2];
const load = (name) => import(pathToFileURL(web + "/js/" + name).href);
const state = await load("state.js");
const rules = await load("views/rules.js");

const now = Date.parse("2026-10-13T12:00:00Z");
const raw = {
  project: { id: "splitnet", title: "split-net" },
  summary: {},
  phases: [],
  tasks: [],
  rules: [{ id: "R1", scope: "all", kind: "do", text: "Keep replies short.", value: null }],
  control: {},
};
const store = state.createStore();
store.projects = [{ id: "splitnet", name: "split-net", progress: 0, tasks_left: 0, running: 0, need_user: 0,
  errors_count: 0, stale: false }];
store.snapshots.splitnet = state.normalizeSnapshot(raw, now);
const prefs = { mode: null, open: {} };
const vm = () => state.buildViewModel(store, { name: "project", id: "splitnet" }, prefs, now);

const out = {};
out.all = rules.sectionView(vm());
rules.ruleAction("rule-tab", { getAttribute: (k) => (k === "data-tab" ? "phase" : null) });
out.phase = rules.sectionView(vm());
console.log(JSON.stringify(out));
