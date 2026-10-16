// Render the System view in node (tests/web/test_system_view.py). fetch serves a fixture payload, a 404 or a 500.
import { pathToFileURL } from "node:url";

const web = process.argv[2];
const mod = await import(pathToFileURL(web + "/js/views/system.js").href);
const payload = {
  components: [
    { id: "web-ui", name: "Web UI with a very long component name", layer: "ui", files: ["web/a.js", "web/b.js"] },
    { id: "api", name: "HTTP API", layer: "service", files: ["r.py"] },
    { id: "store", name: "Store", layer: "data", files: [] },
  ],
  edges: [{ from: "web-ui", to: "api", kind: "call" }, { from: "api", to: "store", kind: "data" },
    { from: "web-ui", to: "store", kind: "data" }],
  heat: { "web-ui": { commits: 8, jobs: 1, work: 2, score: 1 }, api: { commits: 4 } },
  warnings: ["system.json: bad"], sha: "abc",
};
let mode = "ok";
globalThis.document = { dispatchEvent() { return true; }, addEventListener() {}, getElementById() { return null; } };
globalThis.fetch = async () => {
  if (mode === "404") return new Response('{"error":{"code":"not_found","message":"no"}}', { status: 404 });
  if (mode === "500") return new Response('{"error":{"code":"x","message":"boom"}}', { status: 500 });
  return new Response(JSON.stringify(payload), { status: 200, headers: { "Content-Type": "application/json" } });
};
const pause = () => new Promise((r) => setTimeout(r, 60));
const vm = (id) => ({ route: { name: "project", id, section: "system", view: null, item: null, filters: {} } });
const out = {};
for (const [key, m] of [["ok", "ok"], ["missing", "404"], ["broken", "500"]]) {
  mode = m;
  out[key + "Loading"] = mod.sectionView(vm(key));
  await pause();
  out[key] = mod.sectionView(vm(key));
}
mode = "ok";
out.emptyBody = mod.bodyHtml("e", { data: { components: [] } });
out.global = mod.sectionView({ route: { name: "home", id: null, section: "system" } });
console.log(JSON.stringify(out));
process.exit(0);
