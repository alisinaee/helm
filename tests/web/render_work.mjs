// Render the Work views in node with the golden snapshot (used by tests/web/test_work.py). No DOM: the views are
// plain functions that return HTML strings. argv: this script, web directory, snapshot JSON path. Prints one JSON
// object: the HTML of the Board, List (grouped by phase), List (sorted by id, descending) and Tree views, the Board
// with a filter that matches nothing, and the results of the sort and filter helpers.
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

const web = process.argv[2];
const raw = JSON.parse(readFileSync(process.argv[3], "utf8"));
const load = (name) => import(pathToFileURL(web + "/js/" + name).href);
const state = await load("state.js");
const work = await load("views/work.js");
const board = await load("views/board.js");
const list = await load("views/list.js");

const now = Date.parse("2026-10-13T12:00:00Z");
const snap = Object.assign({ project: { id: "splitnet", title: "split-net" } }, raw);
const store = state.createStore();
store.projects = [{ id: "splitnet", name: "split-net", progress: 0.5, tasks_left: 41, running: 0,
  need_user: 0, errors_count: 0, stale: false }];
store.snapshots.splitnet = state.normalizeSnapshot(snap, now);

function viewOf(route) {
  const vm = state.buildViewModel(store, Object.assign({ name: "project", id: "splitnet", section: "work",
    view: null, item: null, filters: {} }, route), { mode: null, open: {} }, now);
  return work.sectionView(vm);
}

const out = {
  board: viewOf({ view: "board" }),
  list: viewOf({ view: "list", filters: { g: "phase" } }),
  listSorted: viewOf({ view: "list", filters: {} }),
  tree: viewOf({ view: "tree" }),
  boardEmptyFilter: viewOf({ view: "board", filters: { f: "status:hold,model:agy" } }),
  taskCount: store.snapshots.splitnet.tasks.filter(function (t) {
    return t.state !== "deferred";
  }).length,
  sortIdDesc: list.sortTasks(board.workTasks(store.snapshots.splitnet, now), "id:desc").map(function (t) {
    return t.id;
  }),
  nextSort: [list.nextSort("", "id"), list.nextSort("id:asc", "id"), list.nextSort("id:desc", "title")],
  filters: board.parseFilters("needs,model:haiku,status:todo,bogus,phase:P1").tokens,
  toggled: [board.toggleToken("needs", "blocked"), board.toggleToken("needs,blocked", "needs")],
};
console.log(JSON.stringify(out));
