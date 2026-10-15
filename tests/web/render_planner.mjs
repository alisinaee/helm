// Render the Planner v2 in node with a fake snapshot that has a 3-level plan tree
// (used by tests/web/test_planner_view.py).
// No DOM: plannerHtml() returns HTML strings. argv: this script, web directory. Prints one JSON object with the HTML of
// each case.
import { pathToFileURL } from "node:url";

const web = process.argv[2];
const planner = await import(pathToFileURL(web + "/js/views/planner.js").href);

const row = (id, label, title, extra) => Object.assign({ id: id, label: label, title: title, phase: "R1", done: 0,
  total: 0, blocked: 0, state: "todo" }, extra);
const rows = [
  row("F1", "P0", "Research", { state: "done", done: 1, total: 1, acc: "brief and risks" }),
  row("F4", "P1", "Requirements", { done: 0, total: 2, gaps: 1, acc: "every ask has acceptance" }),
  row("F5", "P1.0", "Offline sync", { parent: "F4", ask: true, total: 2, acc: "edits merge on reconnect" }),
  row("F6", "P1.1", "Export to PDF", { parent: "F4", ask: true, state: "uncovered", acc: "one click, A4" }),
  row("F7", "P2", "Core engine", { state: "doing", total: 1 }),
  row("F8", "P2.0", "Storage layer", { parent: "F7", state: "doing", total: 1 }),
  row("F9", "P2.0.0", "Schema and migrations", { parent: "F8", state: "doing", total: 1 }),
  row("F10", "P3", "Parked", { state: "hold", accepted: "2026-10-01" }),
];
const task = (id, title, state, feats) => ({ id: id, title: title, state: state, phase: "R1", model: "haiku",
  feats: feats });
const snap = {
  tasks: [task("R1.1", "Merge rules", "todo", ["F5"]), task("R1.2", "Collect asks", "todo", []),
    task("R1.3", "Wire export", "todo", []), task("R2.1", "Schema", "partial", ["F9", "F8", "F5"]),
    task("R0.1", "Write brief", "done", ["F1"])],
  blocked: [],
  features: { rows: rows, uncovered: ["F6"], orphans: ["R1.2", "R1.3"], counts: {} },
};
const emptySnap = { tasks: snap.tasks, features: { rows: [], uncovered: [], orphans: ["R1.2"], counts: {} } };
const base = { status: "", unaccepted: false, open: {}, menu: null, edit: null, pick: null, project: "demo",
  focus: "", panels: { wait: true, orph: true, unc: false } };
const withState = (extra) => Object.assign({}, base, extra);

const out = {
  defaultView: planner.plannerHtml(snap, withState({})),
  allOpen: planner.plannerHtml(snap, withState({
    open: { F1: true, F4: true, F5: true, F7: true, F8: true, F9: true } })),
  menu: planner.plannerHtml(snap, withState({ menu: "F5" })),
  menuFirst: planner.plannerHtml(snap, withState({ menu: "F1" })),
  menuDeep: planner.plannerHtml(snap, withState({ menu: "F9", open: { F7: true, F8: true } })),
  rename: planner.plannerHtml(snap, withState({ edit: { kind: "rename", id: "F5" } })),
  addTop: planner.plannerHtml(snap, withState({ edit: { kind: "add", id: "" } })),
  addSub: planner.plannerHtml(snap, withState({ edit: { kind: "add", id: "F4" } })),
  assign: planner.plannerHtml(snap, withState({ pick: { kind: "assign", task: "R1.2" } })),
  link: planner.plannerHtml(snap, withState({ menu: null, pick: { kind: "link", id: "F6" } })),
  doingFilter: planner.plannerHtml(snap, withState({ status: "doing" })),
  unaccepted: planner.plannerHtml(snap, withState({ unaccepted: true })),
  noMatch: planner.plannerHtml(snap, withState({ status: "hold", unaccepted: true })),
  empty: planner.plannerHtml(emptySnap, withState({})),
};
console.log(JSON.stringify(out));
