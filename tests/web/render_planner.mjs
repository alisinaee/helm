// Render the Planner in node with a fixture snapshot (used by tests/web/test_planner_view.py). No DOM: plannerHtml()
// returns HTML strings. argv: this script, web directory, snapshot JSON path. Prints one JSON object with the HTML of
// each case: the default view, a view with a feature open and its menu, the uncovered filter, an empty features list,
// and the add form. Also the list of onclick-free ids that bind() would use (checked by the Python test).
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

const web = process.argv[2];
const snap = JSON.parse(readFileSync(process.argv[3], "utf8"));
const planner = await import(pathToFileURL(web + "/js/views/planner.js").href);

const base = { status: "", phase: "", unaccepted: false, open: {}, menu: null, adding: false };
const withState = (extra) => Object.assign({}, base, extra);
const emptySnap = Object.assign({}, snap, {
  features: { rows: [], uncovered: [], orphans: snap.tasks.map((t) => t.id), counts: {} },
});

const out = {
  defaultView: planner.plannerHtml(snap, withState({})),
  openAndMenu: planner.plannerHtml(snap, withState({ open: { F2: true, F3: true }, menu: "F2" })),
  uncoveredFilter: planner.plannerHtml(snap, withState({ status: "uncovered" })),
  unacceptedFilter: planner.plannerHtml(snap, withState({ unaccepted: true })),
  noMatch: planner.plannerHtml(snap, withState({ status: "defer" })),
  emptyFeatures: planner.plannerHtml(emptySnap, withState({})),
  addForm: planner.plannerHtml(snap, withState({ adding: true })),
};
console.log(JSON.stringify(out));
