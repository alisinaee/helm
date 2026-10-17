// Render the System views in node (tests/web/test_system_view.py). fetch serves a fixture payload, a 404 or a 500.
import { pathToFileURL } from "node:url";

const web = process.argv[2];
const mod = await import(pathToFileURL(web + "/js/views/system.js").href);
const comps = {
  groups: [{ id: "k:web", label: "Web app [browser]" }, { id: "k:py", label: "Python app" }],
  nodes: [
    { id: "c:ui", label: "Web UI with a very long component name", sub: "JS · 9 files", kind: "component",
      group: "k:web", tone: 0 },
    { id: "c:api", label: "HTTP API", sub: "Python · 3 files", kind: "component", group: "k:py", tone: 1 },
    { id: "c:store", label: "Store", sub: "Python · 2 files", kind: "store", group: "k:py", tone: 1 },
  ],
  edges: [{ from: "c:ui", to: "c:api", label: "GET snapshot", kind: "call", count: 0, derived: false },
    { from: "c:api", to: "c:store", label: "uses store", kind: "import", count: 7, derived: true },
    { from: "c:store", to: "c:api", label: "uses api", kind: "cycle", count: 1, derived: true }],
};
const containers = {
  groups: [{ id: "people", label: "People" }, { id: "containers", label: "Containers" },
    { id: "stores", label: "Stores" }, { id: "external", label: "External systems" }],
  nodes: [{ id: "p:user", label: "User", sub: "", kind: "person", group: "people" },
    { id: "k:web", label: "Web app", sub: "browser", kind: "container", group: "containers" },
    { id: "s:files", label: "Data files", sub: "jobs.json", kind: "store", group: "stores" },
    { id: "x:git", label: "Git", sub: "used by 2 files", kind: "external", group: "external" }],
  edges: [{ from: "p:user", to: "k:web", label: "opens in browser", kind: "call" },
    { from: "k:web", to: "s:files", label: "reads, writes", kind: "data" },
    { from: "k:web", to: "x:git", label: "runs git", kind: "call" }],
};
const data = { groups: [{ id: "code", label: "Code" }, { id: "files", label: "Data files" }], nodes: [], edges: [] };
for (let i = 0; i < 4; i++) data.nodes.push({ id: "c:" + i, label: "comp " + i, kind: "component", group: "code" });
for (let j = 0; j < 6; j++) data.nodes.push({ id: "s:" + j, label: "f" + j + ".json", kind: "store", group: "files" });
for (let i = 0; i < 4; i++) {
  for (let j = 0; j < 5; j++) data.edges.push({ from: "c:" + i, to: "s:" + j, label: j % 2 ? "reads" : "reads, writes",
    kind: "data" });
}
const flow = { id: "f1", name: "Page load", notes: "Every 2 s.", participants: [{ id: "p:user", label: "User" },
  { id: "c:ui", label: "Web UI" }, { id: "c:api", label: "HTTP API" }],
steps: [{ from: "p:user", to: "c:ui", label: "open" }, { from: "c:ui", to: "c:api", label: "GET /snapshot" },
  { from: "c:api", to: "c:api", label: "check origin" }, { from: "c:api", to: "c:ui", label: "200 JSON", reply: true }] };
const payload = {
  components: [{ id: "ui", name: "Web UI", layer: "ui", files: [] }], edges: [], heat: {},
  warnings: ["system.json: bad"], sha: "abc",
  arch: { views: { components: comps, containers: containers, data: data, context: containers, modules: comps,
    layers: comps }, flows: [flow], stats: { sourceFiles: 12, lines: 3400, imports: 40 },
  details: { "c:api": { kind: "component", title: "HTTP API", commits30: 4, heat: { runningJobs: 1 } } } },
};
const catalog = [
  { id: "components", family: "structure", label: "Components", score: 80, available: true },
  { id: "containers", family: "structure", label: "Containers", score: 50, available: true },
  { id: "context", family: "structure", label: "Context", score: 10, available: true },
  { id: "modules", family: "structure", label: "Modules", score: 90, available: false, reason: "no modules" },
  { id: "flows", family: "behaviour", label: "Flows", score: 60, available: true },
  { id: "data", family: "data", label: "Data", score: 40, available: true },
  { id: "classes", family: "structure", label: "Classes", score: 99, available: true },
];
let mode = "ok";
globalThis.document = { dispatchEvent() { return true; }, addEventListener() {}, getElementById() { return null; } };
globalThis.fetch = async () => {
  if (mode === "404") return new Response('{"error":{"code":"not_found","message":"no"}}', { status: 404 });
  if (mode === "500") return new Response('{"error":{"code":"x","message":"boom"}}', { status: 500 });
  if (mode === "cat") return new Response(JSON.stringify(Object.assign({}, payload,
    { arch: Object.assign({}, payload.arch, { catalog: catalog }) })), { status: 200 });
  const body = mode === "old" ? Object.assign({}, payload, { arch: undefined }) : payload;
  return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
};
const pause = () => new Promise((r) => setTimeout(r, 60));
const vm = (id) => ({ route: { name: "project", id, section: "system", view: null, item: null, filters: {} } });
const out = {};
for (const [key, m] of [["ok", "ok"], ["missing", "404"], ["broken", "500"], ["old", "old"], ["cat", "cat"]]) {
  mode = m;
  out[key + "Loading"] = mod.sectionView(vm(key));
  await pause();
  out[key] = mod.sectionView(vm(key));
}
mode = "ok";
out.containers = mod.graphSvg(containers, {}, "Containers view");
out.flow = mod.flowSvg(flow);
out.matrix = mod.matrixSvg(data);
out.open = [mod.openingView({ w: 400, h: 300 }, { w: 1200, h: 800 }), mod.openingView({ w: 4000, h: 3000 },
  { w: 1200, h: 800 })];
out.fit = [mod.openingView({ w: 1200, h: 400 }, { w: 1200, h: 800 }), mod.openingView({ w: 20000, h: 100 },
  { w: 1000, h: 500 })];
out.views = mod.VIEWS.map((v) => v[0]);
out.global = mod.sectionView({ route: { name: "home", id: null, section: "system" } });
console.log(JSON.stringify(out));
process.exit(0);
