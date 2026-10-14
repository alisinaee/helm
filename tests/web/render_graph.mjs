// Run the workflow graph model and layout in node (used by tests/web/test_workflow_graph.py). No DOM: buildGraph and
// layout are pure. argv: this script, the web directory, the fixtures directory. Prints one JSON object keyed by
// fixture name. Each case holds the graph of the snapshot, the graph of each filter, the expanded graph, and the
// dependency and time layouts. Every layout is also given as text (JSON.stringify), and a second build and layout of
// the same input is included, so the test can compare the output byte for byte.
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const [web, dir] = process.argv.slice(2);
const load = (name) => import(pathToFileURL(join(web, "js", "graph", name)).href);
const { buildGraph } = await load("model.js");
const { layout } = await load("layout.js");

const out = {};
const files = readdirSync(dir).filter((f) => f.endsWith(".json")).sort();
for (const file of files) {
  const snap = JSON.parse(readFileSync(join(dir, file), "utf8"));
  const now = Number(snap.now) || 0;
  const graph = buildGraph(snap, {});
  const dep = layout(graph, "dependency", "week", now);
  const time = layout(graph, "time", "week", now);
  const again = buildGraph(snap, {});
  out[file.replace(/\.json$/, "")] = {
    graph,
    graphText: JSON.stringify(graph),
    graphAgainText: JSON.stringify(again),
    expanded: buildGraph(snap, { expand: true }),
    status: buildGraph(snap, { status: ["done"] }),
    agent: buildGraph(snap, { agent: "haiku" }),
    phase: buildGraph(snap, { phase: "P1" }),
    dep,
    depText: JSON.stringify(dep),
    depAgainText: JSON.stringify(layout(again, "dependency", "week", now)),
    time,
    timeText: JSON.stringify(time),
    timeAgainText: JSON.stringify(layout(again, "time", "week", now)),
    timeAll: layout(graph, "time", "all", now),
    now,
  };
}
process.stdout.write(JSON.stringify(out));
