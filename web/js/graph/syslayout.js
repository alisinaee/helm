// System map layout (R10.22, A4). systemLayout(system) places the components of a system description (docs/system.json
// v1 shape: layers, components, edges) in columns, one column per layer, in layer order. Pure: no DOM, no clock, no
// randomness, so the same input gives the same JSON. Components are sorted by id first, so input order does not
// matter.
//
// Cards. Each card is CARD_W by CARD_H. Inside a column the cards stack top to bottom; the stack is centred on the
// tallest column. Four barycenter sweeps (alternating left-to-right and right-to-left) order the cards of a column by
// the mean row
// of their neighbours in other columns, ties broken by the previous row and then by id.
//
// Edges. Every route is an orthogonal polyline that leaves the source card on its right side and enters the target
// card on its left side. Edges sharing a side get their own port, spread along it by the other end's row.
// An edge into the next column is one step: a vertical run in the gap between the two
// columns. Any other edge (skipping columns, same column or backwards) drops to a channel below all cards, so its
// horizontal runs never cross a card. Vertical runs share a gap and are spaced evenly inside it; channels are
// spaced by CH_STEP. Self loops, duplicate edges and edges with unknown ends are dropped and reported in `warnings`.

export const CARD_W = 200;
export const CARD_H = 64;
export const ROW_GAP = 40;
export const COL_GAP = 72;
export const MARGIN = 16;
export const HEAD_H = 32;

const SWEEPS = 4;
const CH_PAD = 16;
const CH_STEP = 10;
const PORT_PAD = 10;
const OTHER = "other";

function cmp(a, b) {
  if (a < b) return -1;
  return a > b ? 1 : 0;
}

function round1(v) {
  return Math.round(v * 10) / 10;
}

// Parse the components: skip entries without a usable id, drop duplicates, and sort by id.
function readComponents(sys, warnings) {
  const seen = new Set();
  const out = [];
  (Array.isArray(sys.components) ? sys.components : []).forEach((c) => {
    if (!c || typeof c.id !== "string" || c.id === "") {
      warnings.push("component without id skipped");
      return;
    }
    if (seen.has(c.id)) {
      warnings.push("duplicate component " + c.id + " skipped");
      return;
    }
    seen.add(c.id);
    out.push({
      id: c.id,
      name: typeof c.name === "string" && c.name !== "" ? c.name : c.id,
      kind: typeof c.kind === "string" ? c.kind : "module",
      layer: typeof c.layer === "string" && c.layer !== "" ? c.layer : OTHER,
    });
  });
  return out.sort((a, b) => cmp(a.id, b.id));
}

// Layer order: the declared list when there is one (undeclared layers go to "other"), otherwise sorted layer names.
// "other" always comes last.
function layerOrder(sys, comps, warnings) {
  const declared = (Array.isArray(sys.layers) ? sys.layers : []).filter((l) => typeof l === "string" && l !== "");
  const order = [];
  const add = (l) => {
    if (l !== OTHER && order.indexOf(l) < 0) order.push(l);
  };
  if (declared.length) {
    declared.forEach(add);
    comps.forEach((c) => {
      if (declared.indexOf(c.layer) < 0 && c.layer !== OTHER) {
        warnings.push("component " + c.id + " has unknown layer " + c.layer + "; placed in " + OTHER);
        c.layer = OTHER;
      }
    });
  } else {
    comps.forEach((c) => add(c.layer));
  }
  if (comps.some((c) => c.layer === OTHER)) order.push(OTHER);
  return order;
}

// Edges sorted by from, then to. Duplicates and self loops are dropped.
function readEdges(sys, byId, warnings) {
  const seen = new Set();
  const out = [];
  (Array.isArray(sys.edges) ? sys.edges : []).forEach((e) => {
    if (!e || typeof e.from !== "string" || typeof e.to !== "string") {
      warnings.push("edge without from/to skipped");
      return;
    }
    if (!byId.has(e.from) || !byId.has(e.to)) {
      warnings.push("edge " + e.from + " > " + e.to + " skipped: unknown component");
      return;
    }
    if (e.from === e.to) return;
    const key = e.from + ">" + e.to;
    if (seen.has(key)) return;
    seen.add(key);
    out.push({
      from: e.from,
      to: e.to,
      label: typeof e.label === "string" ? e.label : "",
      kind: typeof e.kind === "string" ? e.kind : "call",
    });
  });
  return out.sort((a, b) => cmp(a.from, b.from) || cmp(a.to, b.to));
}

// Order the cards of every column by barycenter, alternating direction. Rows are rewritten after each column.
function orderCards(columns, adj, byId) {
  const n = columns.length;
  for (let s = 0; s < SWEEPS; s += 1) {
    const idx = [];
    for (let i = 0; i < n; i += 1) idx.push(s % 2 === 0 ? i : n - 1 - i);
    idx.forEach((ci) => {
      const keyed = columns[ci].cards.map((c) => {
        const others = adj.get(c.id).map((id) => byId.get(id)).filter((m) => m.col !== ci);
        const bary = others.length ? others.reduce((sum, m) => sum + m.row, 0) / others.length : c.row;
        return { c, bary };
      });
      keyed.sort((a, b) => a.bary - b.bary || a.c.row - b.c.row || cmp(a.c.id, b.c.id));
      columns[ci].cards = keyed.map((k) => k.c);
      columns[ci].cards.forEach((c, i) => {
        c.row = i;
      });
    });
  }
}

export function systemLayout(system) {
  const sys = system && typeof system === "object" ? system : {};
  const warnings = [];
  const comps = readComponents(sys, warnings);
  const order = layerOrder(sys, comps, warnings);
  const used = order.filter((l) => comps.some((c) => c.layer === l));
  const colOf = new Map(used.map((l, i) => [l, i]));
  const cards = comps.map((c) => ({
    id: c.id,
    name: c.name,
    kind: c.kind,
    layer: c.layer,
    col: colOf.get(c.layer),
    row: 0,
  }));
  const byId = new Map(cards.map((c) => [c.id, c]));
  const links = readEdges(sys, byId, warnings);

  const columns = used.map((layer, index) => ({ layer, index, cards: [] }));
  cards.forEach((c) => columns[c.col].cards.push(c));
  columns.forEach((col) => col.cards.forEach((c, i) => {
    c.row = i;
  }));
  const adj = new Map(cards.map((c) => [c.id, []]));
  links.forEach((l) => {
    adj.get(l.from).push(l.to);
    adj.get(l.to).push(l.from);
  });
  orderCards(columns, adj, byId);

  // Geometry. Gap g (0..ncol) is the strip [colX(g) - COL_GAP, colX(g)); gap g sits left of column g.
  const ncol = columns.length;
  const colX = (c) => MARGIN + COL_GAP + c * (CARD_W + COL_GAP);
  const top = HEAD_H + MARGIN;
  const step = CARD_H + ROW_GAP;
  const maxRows = columns.reduce((m, col) => Math.max(m, col.cards.length), 0);
  const bodyH = maxRows ? (maxRows - 1) * step + CARD_H : 0;
  columns.forEach((col) => {
    const h = col.cards.length ? (col.cards.length - 1) * step + CARD_H : 0;
    const off = Math.round((bodyH - h) / 2);
    col.cards.forEach((c) => {
      c.x = colX(col.index);
      c.y = top + off + c.row * step;
    });
  });
  const bodyBottom = top + bodyH;

  // Plan the routes. Each vertical run is recorded against its gap; channel rows are numbered in link order.
  const gapRuns = new Map();
  const addRun = (gap, run) => {
    if (!gapRuns.has(gap)) gapRuns.set(gap, []);
    gapRuns.get(gap).push(run);
  };
  let channelCount = 0;
  // Ports: the edges leaving (or entering) one card are ordered by the other end's centre and spread along the side.
  const port = new Map();
  const spread = (key, ids, card, otherOf) => {
    const sorted = ids.slice().sort((p, q) => otherOf(p) - otherOf(q) || p - q);
    sorted.forEach((i, k) => {
      port.set(key + i, round1(card.y + PORT_PAD + ((k + 0.5) * (CARD_H - 2 * PORT_PAD)) / sorted.length));
    });
  };
  cards.forEach((c) => {
    const out = [];
    const inn = [];
    links.forEach((l, i) => {
      if (l.from === c.id) out.push(i);
      if (l.to === c.id) inn.push(i);
    });
    spread("o", out, c, (i) => byId.get(links[i].to).y);
    spread("i", inn, c, (i) => byId.get(links[i].from).y);
  });
  const plans = links.map((l, i) => {
    const a = byId.get(l.from);
    const b = byId.get(l.to);
    const ay = port.get("o" + i);
    const by = port.get("i" + i);
    if (b.col === a.col + 1) {
      const run = { i, y1: ay, y2: by, x: 0 };
      addRun(a.col + 1, run);
      return { direct: true, a, b, ay, by, runs: [run] };
    }
    const chY = bodyBottom + CH_PAD + channelCount * CH_STEP;
    channelCount += 1;
    const src = { i, y1: ay, y2: chY, x: 0 };
    const dst = { i, y1: chY, y2: by, x: 0 };
    addRun(a.col + 1, src);
    addRun(b.col, dst);
    return { direct: false, a, b, ay, by, chY, runs: [src, dst] };
  });
  gapRuns.forEach((runs, gap) => {
    runs.sort((p, q) => p.y1 - q.y1 || p.y2 - q.y2 || p.i - q.i);
    runs.forEach((r, k) => {
      r.x = round1(colX(gap) - COL_GAP + ((k + 1) * COL_GAP) / (runs.length + 1));
    });
  });

  const routes = links.map((l, i) => {
    const p = plans[i];
    const x0 = p.a.x + CARD_W;
    const x1 = p.b.x;
    let points;
    if (p.direct) {
      const xg = p.runs[0].x;
      points = [[x0, p.ay], [xg, p.ay], [xg, p.by], [x1, p.by]];
    } else {
      const xs = p.runs[0].x;
      const xt = p.runs[1].x;
      points = [[x0, p.ay], [xs, p.ay], [xs, p.chY], [xt, p.chY], [xt, p.by], [x1, p.by]];
    }
    points = points.map((q) => [round1(q[0]), round1(q[1])]);
    const d = points.map((q, k) => (k === 0 ? "M " : "L ") + q[0] + " " + q[1]).join(" ");
    return { from: l.from, to: l.to, label: l.label, kind: l.kind, d, points };
  });

  const height = (channelCount ? bodyBottom + CH_PAD + channelCount * CH_STEP : bodyBottom) + MARGIN;
  const width = colX(ncol) + MARGIN;
  const sorted = cards.slice().sort((p, q) => p.col - q.col || p.row - q.row || cmp(p.id, q.id));
  return {
    width,
    height,
    layers: used.slice(),
    columns: columns.map((col) => ({
      layer: col.layer,
      index: col.index,
      x: colX(col.index),
      w: CARD_W,
      count: col.cards.length,
    })),
    cards: sorted.map((c) => ({
      id: c.id,
      name: c.name,
      kind: c.kind,
      layer: c.layer,
      col: c.col,
      row: c.row,
      x: c.x,
      y: c.y,
      w: CARD_W,
      h: CARD_H,
    })),
    routes,
    warnings,
  };
}
