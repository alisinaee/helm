// Run the workflow diagram's pure parts in node (used by tests/web/test_workflow_diagram.py). viewport.js has pure
// gesture, key and view functions, so they are driven here with synthetic pointer input. buildMap() needs
// document.createElementNS, so a small stand-in records elements, attributes and children. argv: this script, the web
// directory, the graph fixtures directory. Prints one JSON object.
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const [web, dir] = process.argv.slice(2);
const load = (name) => import(pathToFileURL(join(web, "js", "graph", name)).href);

class El {
  constructor(tag) {
    this.tagName = tag;
    this.attrs = {};
    this.children = [];
  }
  setAttribute(k, v) {
    this.attrs[k] = String(v);
  }
  getAttribute(k) {
    return Object.prototype.hasOwnProperty.call(this.attrs, k) ? this.attrs[k] : null;
  }
  appendChild(c) {
    this.children.push(c);
    return c;
  }
}

class Txt {
  constructor(s) {
    this.nodeType = 3;
    this.data = s;
  }
}

globalThis.document = {
  createElementNS(ns, tag) {
    return new El(tag);
  },
  createTextNode(s) {
    return new Txt(s);
  },
};

const vp = await load("viewport.js");
const model = await load("model.js");
const layoutMod = await load("layout.js");
const render = await load("render.js");

function walk(node, fn) {
  if (!node || node.nodeType === 3) return;
  fn(node);
  node.children.forEach((c) => walk(c, fn));
}

function gestureCase(start, script) {
  const taps = { last: null };
  const g = vp.createGestures(start, taps);
  const res = script(g);
  return { res: res, view: g.view };
}

const out = {};
const origin = { k: 1, x: 0, y: 0 };

out.pan40 = gestureCase(origin, (g) => {
  g.down(1, 100, 100);
  g.move(1, 120, 104);
  g.move(1, 140, 100);
  return g.up(1, 140, 100, 0);
});

out.tap = gestureCase(origin, (g) => {
  g.down(1, 100, 100);
  g.move(1, 103, 102);
  return g.up(1, 103, 102, 0);
});

out.jitterAt6 = gestureCase(origin, (g) => {
  g.down(1, 100, 100);
  g.move(1, 106, 100);
  return g.up(1, 106, 100, 0);
});

out.pinch = gestureCase(origin, (g) => {
  g.down(1, 100, 100);
  g.down(2, 140, 100);
  g.move(2, 180, 100);
  const end1 = g.up(2, 180, 100, 0);
  const end2 = g.up(1, 100, 100, 0);
  return [end1, end2];
});

out.doubleTap = (() => {
  const taps = { last: null };
  const g = vp.createGestures(origin, taps);
  g.down(1, 50, 50);
  const first = g.up(1, 50, 50, 1000);
  g.down(1, 52, 50);
  const second = g.up(1, 52, 50, 1200);
  return { first: first, second: second, k: g.view.k };
})();

out.slowTwoTaps = (() => {
  const taps = { last: null };
  const g = vp.createGestures(origin, taps);
  g.down(1, 50, 50);
  g.up(1, 50, 50, 1000);
  g.down(1, 50, 50);
  return { second: g.up(1, 50, 50, 1900) };
})();

out.wheelIn = gestureCase(origin, (g) => {
  g.wheel(-200, 0, 0);
  return null;
});

out.zoomClamp = {
  max: vp.zoomAt({ k: 2, x: 0, y: 0 }, 99, 0, 0).k,
  min: vp.zoomAt({ k: 1, x: 0, y: 0 }, 0.01, 0, 0).k,
};

out.zoomKeepsPoint = (() => {
  const v = vp.zoomAt({ k: 1, x: 10, y: 10 }, 2, 110, 60);
  return { x: (110 - v.x) / v.k, y: (60 - v.y) / v.k };
})();

out.keys = {
  plus: vp.keyPlan("+", false),
  minus: vp.keyPlan("-", false),
  zero: vp.keyPlan("0", false),
  escape: vp.keyPlan("Escape", false),
  arrow: vp.keyPlan("ArrowLeft", false),
  shiftArrow: vp.keyPlan("ArrowLeft", true),
  other: vp.keyPlan("a", false),
};

const grid = [
  { key: "a", cx: 0, cy: 0 },
  { key: "b", cx: 200, cy: 0 },
  { key: "c", cx: 0, cy: 60 },
  { key: "d", cx: 200, cy: 60 },
];
out.nearest = {
  right: vp.nearest(grid, grid[0], [1, 0]).key,
  down: vp.nearest(grid, grid[0], [0, 1]).key,
  left: vp.nearest(grid, grid[0], [-1, 0]),
  fromD_up: vp.nearest(grid, grid[3], [0, -1]).key,
};

out.fit = vp.fitView({ w: 400, h: 200 }, { w: 800, h: 600 });
out.open = vp.openView({ w: 384, h: 900 }, { w: 825, h: 560 });
out.openWide = vp.openView({ w: 4000, h: 900 }, { w: 825, h: 560 });

out.cases = {};
const files = readdirSync(dir).filter((f) => f.endsWith(".json")).sort();
for (const file of files) {
  const snap = JSON.parse(readFileSync(join(dir, file), "utf8"));
  const now = Number(snap.now) || 0;
  const graph = model.buildGraph(snap, {});
  const lay = layoutMod.layout(graph, "dependency", "week", now);
  const built = render.buildMap(graph, lay, "demo");
  const nodes = [];
  const styled = [];
  const hatch = [];
  walk(built.svg, (n) => {
    if (n.getAttribute("style") !== null) styled.push(n.tagName);
    if (n.tagName === "pattern" && n.getAttribute("id") === "wfg-hatch") hatch.push(n.tagName);
    if (n.getAttribute("data-wf-item") !== null) {
      nodes.push({ id: n.getAttribute("data-wf-item"), label: n.getAttribute("aria-label"),
        role: n.getAttribute("role"), tabindex: n.getAttribute("tabindex") });
    }
  });
  const edgeBoth = graph.edges.every((e) => {
    const down = render.closureOf(graph, e.from);
    const up = render.closureOf(graph, e.to);
    return down && up && down.has(e.to) && up.has(e.from);
  });
  out.cases[file.replace(/\.json$/, "")] = {
    graphNodes: graph.nodes.length,
    interactiveNodes: graph.nodes.filter((n) => n.type !== "phase").length,
    graphEdges: graph.edges.length,
    svgNodes: nodes.length,
    nodes: nodes,
    styledElements: styled,
    hatchDefs: hatch.length,
    transform: built.vp.getAttribute("transform"),
    closureContainsSelf: graph.nodes.every((n) => render.closureOf(graph, n.id).has(n.id)),
    edgeBothWays: edgeBoth,
    closureOfMissing: render.closureOf(graph, "no-such-node"),
  };
}

process.stdout.write(JSON.stringify(out));
