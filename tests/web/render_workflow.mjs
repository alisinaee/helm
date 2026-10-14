// Render the Workflow view in node (used by tests/web/test_workflow_view.py). No DOM: the renderers return HTML strings.
// fetch serves each fixture project's snapshot, and Date.now is pinned to the fixture's clock so the ranges are
// deterministic. argv: this script, web directory, fixture JSON path. Prints one JSON object with the markup of each
// case and of the section view (Timeline, Map, Table, the empty project and the global scope).
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

const web = process.argv[2];
const fixture = JSON.parse(readFileSync(process.argv[3], "utf8"));
const load = (name) => import(pathToFileURL(web + "/js/" + name).href);

Date.now = () => fixture.now;
const CASES = ["empty", "running", "blocked", "handoff"];
const byId = {};
for (const name of CASES) byId[fixture[name].project.id] = fixture[name];
const served = [];
globalThis.document = { dispatchEvent() { return true; } };
globalThis.fetch = async (url) => {
  const id = decodeURIComponent(String(url).split("/")[4]);
  served.push(id);
  const raw = byId[id];
  const body = raw || { error: { code: "not_found", message: "no such project" } };
  return new Response(JSON.stringify(body), { status: raw ? 200 : 404,
    headers: { "Content-Type": "application/json" } });
};

const wf = await load("views/workflow.js");
const pause = () => new Promise((resolve) => setTimeout(resolve, 40));
const now = fixture.now;
const out = { cases: {}, sections: {}, served };

for (const name of CASES) {
  const model = wf.layout(byId[fixture[name].project.id], "week", now);
  out.cases[name] = {
    timeline: wf.timelineSvg(model),
    map: "",
    mapStacked: "", // the Map view moved to web/js/graph/render.js (WP72); covered by test_workflow_diagram.py
    table: wf.tableHtml(model),
    jobs: model.jobCount,
    lanes: model.lanes.map((lane) => lane.label),
    empty: model.empty,
  };
}

const projectRoute = (id, view) => ({ name: "project", id: id, section: "workflow", view: view, item: null,
  filters: { f: "range:week" } });
const projectVm = (id, view) => ({ route: projectRoute(id, view), project: { snapshot: byId[id] },
  projects: [], snapshotList: [], home: { loading: false }, projectsError: null });
const rendered = async (make) => {
  make();
  await pause();
  return make();
};

out.sections.timeline = await rendered(() => wf.sectionView(projectVm("alpha", null)));
out.sections.map = await rendered(() => wf.sectionView(projectVm("alpha", "map")));
out.sections.table = await rendered(() => wf.sectionView(projectVm("alpha", "table")));
out.sections.empty = await rendered(() => wf.sectionView(projectVm("empty", null)));

const projects = ["alpha", "beta", "gamma", "empty"].map((id) => ({ id: id, name: byId[id].project.title }));
const allVm = () => ({ route: { name: "home", id: null, section: "workflow", view: null, item: null,
  filters: { f: "range:all" } }, projects: projects, snapshotList: projects, home: { loading: false },
  projectsError: null });
out.sections.all = await rendered(() => wf.sectionView(allVm()));
console.log(JSON.stringify(out));
