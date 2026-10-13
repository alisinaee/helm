// Render the Projects and Details views in node (used by tests/web/test_panel.py). argv: this script, web directory,
// snapshot JSON path. Prints one JSON object with the HTML of each case. The snapshot gets the keys the server adds for
// issues, questions, comments, the queue, subtasks and rules, so every branch of the views renders.
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

const web = process.argv[2];
const raw = JSON.parse(readFileSync(process.argv[3], "utf8"));
const load = (name) => import(pathToFileURL(web + "/js/" + name).href);
const state = await load("state.js");
const router = await load("router.js");
const projects = await load("views/projects.js");
const details = await load("views/details.js");

const now = Date.parse("2026-10-13T12:00:00Z");

function snapshotRaw(extra) {
  const tasks = raw.tasks.map(function (t) {
    if (t.id === "P0.1") return Object.assign({}, t, { subs: [{ t: "Write tests", d: true }, { t: "Ship", d: false }],
      capK: 40 });
    return t;
  });
  return Object.assign({ project: { id: "splitnet", title: "split-net" }, tasks: tasks, issues: [
    { id: "I1", title: "Queue stalls", kind: "blocker", sev: 1, status: "open", tasks: ["P0.1"], by: "" },
    { id: "I2", title: "Docs typo", kind: "bug", sev: 3, status: "open", tasks: [], by: "" },
  ], questions: [
    { id: "Q1", task: "P0.1", text: "Keep the old API?", opts: ["yes", "no"], status: "open", block: true },
    { id: "Q2", task: "", text: "Which host?", opts: [], status: "open", block: false },
  ], comments: { "P0.1": [{ by: "cli", at: "2026-10-12T10:00:00+03:30", t: "Looks right to me" }] },
  queue: [{ task: "P0.2", by: "cli", at: null }], control: { stopped: false, blocked: false, reason: "" } },
  extra || {});
}

function storeFor(snapRaw, extraProjects) {
  const store = state.createStore();
  store.projects = [
    { id: "splitnet", name: "split-net", progress: 0.5659, tasks_left: 41, running: 1, need_user: 3,
      errors_count: 0, stale: false },
    { id: "rb-site", name: "rb-site", progress: 0.2, tasks_left: 9, running: 2, need_user: 0, errors_count: 0,
      stale: false },
    { id: "idle", name: "Idle one", progress: 1, tasks_left: 0, running: 0, need_user: 0, errors_count: 0,
      stale: false },
  ].concat(extraProjects || []);
  store.snapshots.splitnet = state.normalizeSnapshot(snapRaw, now);
  store.conn = { ok: true, lastOkAt: now, error: null };
  return store;
}

function vmFor(store, hash) {
  const route = router.parseRoute(hash);
  const vm = state.buildViewModel(store, route, { mode: null, open: {} }, now);
  vm.ui = state.defaultUi();
  vm.conn = store.conn;
  vm.snapshotList = Object.values(store.snapshots);
  return vm;
}

const out = {};
const base = storeFor(snapshotRaw());
out.projectsProject = projects.projectsView(vmFor(base, "#/p/splitnet/work"));
out.projectsHome = projects.projectsView(vmFor(base, "#/all/work"));
out.projectsEmpty = projects.projectsView(vmFor(storeFor(snapshotRaw()), "#/all/work"));
const emptyStore = state.createStore();
emptyStore.projects = [];
out.projectsNone = projects.projectsView(vmFor(emptyStore, "#/all/work"));

const blockedRaw = snapshotRaw({ control: { stopped: false, blocked: true, reason: "weekly 72%", warn: [] } });
out.projectsBlocked = projects.projectsView(vmFor(storeFor(blockedRaw), "#/p/splitnet/work"));

out.detailsTask = details.detailsView(vmFor(base, "#/p/splitnet/work/i/P0.1"));
out.detailsIssue = details.detailsView(vmFor(base, "#/p/splitnet/work/i/I1"));
out.detailsQuestion = details.detailsView(vmFor(base, "#/p/splitnet/work/i/Q1"));
out.detailsCard = details.detailsView(vmFor(base, "#/p/splitnet/work"));
out.detailsMissing = details.detailsView(vmFor(base, "#/p/splitnet/work/i/P9.9"));
out.detailsHome = details.detailsView(vmFor(base, "#/all/work"));

const withRules = storeFor(snapshotRaw({ rules: [{ id: "R1", scope: "task:P0.1", text: "Keep it small" },
  { id: "R2", scope: "lead", text: "Not for this task" }] }));
out.detailsRules = details.detailsView(vmFor(withRules, "#/p/splitnet/work/i/P0.1"));

console.log(JSON.stringify(out));
