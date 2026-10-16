// System views layout (R10.33, docs/SYSTEM-VIEWS-SPEC.md). Pure: no DOM, no clock, no randomness.
//
// layeredLayout(view) places a view {groups, nodes, edges} as horizontal bands, one band per group, top to bottom in
// group order. A band holds at most WRAP nodes per row (more wrap into extra rows) and every band spans the full width,
// so the bands read like the layers of an architecture drawing. Four barycentre sweeps order the nodes of each band by
// the mean position of their neighbours in other bands (fewer crossings); ties keep the input order.
// Edges leave the bottom of the upper node and enter the top of the lower one (ports spread along the side by the
// other end's x) as cubic curves; an edge that points up a band leaves the top and enters the bottom and is flagged
// `up`; an edge inside one row arcs above it. Labels sit on the curve where they cover no node and no other label
// (tried at several points along it); a label that fits nowhere is left out (`lx` null) and stays in the tooltip.
//
// sequenceLayout(flow) places a flow {participants, steps} as a sequence diagram: one lifeline per participant, one
// row per step, self calls as a loop. matrixLayout(view) places a data view as a CRUD matrix: rows are the code nodes,
// columns the stores, one cell per edge.

export const NODE_W = 188;
export const NODE_H = 50;
export const GAP_X = 28;
export const ROW_GAP = 26;
export const BAND_GAP = 70;
export const BAND_PAD = 12;
export const BAND_HEAD = 24;
export const WRAP = 6;
export const LABEL_MAX = 30;
// Derived edges with fewer imports than this do not push a node down a row inside its band (they are still drawn).
export const WEAK = 3;

export function weak(e) {
  return e.kind === "import" && (e.count || 0) < WEAK;
}
const CHAR_W = 6.2;
const LABEL_H = 16;
const SWEEPS = 4;
const TRY_T = [0.5, 0.42, 0.58, 0.34, 0.66, 0.26, 0.74, 0.18, 0.82];

function clipText(s, n) {
  const t = String(s || "");
  return t.length > n ? t.slice(0, n - 1) + "…" : t;
}

export function labelWidth(text) {
  return Math.round(clipText(text, LABEL_MAX).length * CHAR_W + 10);
}

function bez(p, t) {
  const u = 1 - t;
  return {
    x: u * u * u * p[0] + 3 * u * u * t * p[2] + 3 * u * t * t * p[4] + t * t * t * p[6],
    y: u * u * u * p[1] + 3 * u * u * t * p[3] + 3 * u * t * t * p[5] + t * t * t * p[7],
  };
}

function hit(a, b) {
  return a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
}

function f1(n) {
  return Math.round(n * 10) / 10;
}

// Orders the nodes of every band (array of arrays of ids) by barycentre; mutates and returns `bands`.
function order(bands, nbr) {
  const pos = new Map();
  const index = () => bands.forEach((b) => b.forEach((id, i) => pos.set(id, b.length > 1 ? i / (b.length - 1) : 0.5)));
  index();
  for (let s = 0; s < SWEEPS; s++) {
    const seq = s % 2 === 0 ? bands.map((_, i) => i) : bands.map((_, i) => bands.length - 1 - i);
    seq.forEach((bi) => {
      const b = bands[bi];
      const key = new Map();
      b.forEach((id, i) => {
        const ns = (nbr.get(id) || []).filter((o) => pos.has(o) && !b.includes(o));
        key.set(id, ns.length ? ns.reduce((a, o) => a + pos.get(o), 0) / ns.length : pos.get(id));
        key.set(id + "\u0000i", i);
      });
      b.sort((x, y) => key.get(x) - key.get(y) || key.get(x + "\u0000i") - key.get(y + "\u0000i"));
      index();
    });
  }
  return bands;
}

// Longest-path depth of each id over the edges between ids of one band (a DFS drops the back edges of a cycle).
function bandDepth(ids, edges) {
  const inside = new Set(ids);
  const out = new Map(ids.map((id) => [id, []]));
  edges.forEach((e) => {
    if (inside.has(e.from) && inside.has(e.to)) out.get(e.from).push(e.to);
  });
  const state = new Map();
  const dag = new Map(ids.map((id) => [id, []]));
  const visit = (id) => {
    state.set(id, 1);
    out.get(id).forEach((t) => {
      if (state.get(t) === 1) return;
      dag.get(id).push(t);
      if (!state.has(t)) visit(t);
    });
    state.set(id, 2);
  };
  ids.forEach((id) => {
    if (!state.has(id)) visit(id);
  });
  const depth = new Map(ids.map((id) => [id, 0]));
  for (let pass = 0; pass < ids.length; pass++) {
    let moved = false;
    ids.forEach((id) => dag.get(id).forEach((t) => {
      if (depth.get(t) < depth.get(id) + 1) {
        depth.set(t, depth.get(id) + 1);
        moved = true;
      }
    }));
    if (!moved) break;
  }
  return depth;
}

export function layeredLayout(view, opts) {
  const wrap = (opts && opts.wrap) || WRAP;
  const groups = (Array.isArray(view.groups) ? view.groups : []).filter((g) => g && g.id);
  const known = new Set(groups.map((g) => g.id));
  const nodes = (Array.isArray(view.nodes) ? view.nodes : []).filter((n) => n && n.id);
  const byId = new Map(nodes.map((n) => [n.id, n]));
  nodes.forEach((n) => {
    if (!known.has(n.group)) {
      known.add(n.group);
      groups.push({ id: n.group, label: String(n.group || "other") });
    }
  });
  const edges = [];
  const seen = new Set();
  (Array.isArray(view.edges) ? view.edges : []).forEach((e) => {
    const k = e && e.from + "\u0000" + e.to;
    if (!e || e.from === e.to || !byId.has(e.from) || !byId.has(e.to) || seen.has(k)) return;
    seen.add(k);
    edges.push(e);
  });
  const nbr = new Map();
  edges.forEach((e) => {
    nbr.set(e.from, (nbr.get(e.from) || []).concat(e.to));
    nbr.set(e.to, (nbr.get(e.to) || []).concat(e.from));
  });
  const used = groups.filter((g) => nodes.some((n) => n.group === g.id));
  // Rows inside a band: the band's own dependency depth (callers above callees), each depth wrapped at `wrap`.
  const rowsOf = used.map((g) => {
    const ids = nodes.filter((n) => n.group === g.id).map((n) => n.id);
    const depth = bandDepth(ids, edges.filter((e) => !weak(e)));
    const max = Math.max(0, ...ids.map((id) => depth.get(id)));
    const rows = [];
    for (let d = 0; d <= max; d++) {
      const level = ids.filter((id) => depth.get(id) === d);
      for (let i = 0; i < level.length; i += wrap) rows.push(level.slice(i, i + wrap));
    }
    return rows;
  });
  const flat = order([].concat(...rowsOf), nbr);
  const cols = Math.min(wrap, Math.max(1, ...flat.map((b) => b.length)));
  const inner = cols * NODE_W + (cols - 1) * GAP_X;
  const width = inner + 2 * BAND_PAD;
  const out = new Map();
  const boxes = [];
  let y = 0;
  let fi = 0;
  rowsOf.forEach((rowList, bi) => {
    const rows = rowList.length;
    const h = BAND_HEAD + rows * NODE_H + (rows - 1) * ROW_GAP + BAND_PAD;
    boxes.push({ id: used[bi].id, label: used[bi].label || used[bi].id, x: 0, y: y, w: width, h: h });
    for (let r = 0; r < rows; r++) {
      const row = flat[fi++];
      const rw = row.length * NODE_W + (row.length - 1) * GAP_X;
      const x0 = BAND_PAD + (inner - rw) / 2;
      row.forEach((id, i) => {
        out.set(id, Object.assign({}, byId.get(id), { x: x0 + i * (NODE_W + GAP_X), y: y + BAND_HEAD + r *
          (NODE_H + ROW_GAP), w: NODE_W, h: NODE_H, band: bi, row: r }));
      });
    }
    y += h + BAND_GAP;
  });
  let height = Math.max(0, y - BAND_GAP);
  let fullW = width;
  // A tall drawing on a wide canvas: the bands flow into columns (in order, top to bottom, then the next column).
  const aspect = (opts && opts.aspect) || 1.8;
  let cols2 = 1;
  let best = Infinity;
  for (let c = 1; c <= Math.min(4, boxes.length); c++) {
    const score = Math.abs(Math.log((c * width + (c - 1) * BAND_GAP) / Math.max(1, height / c) / aspect));
    if (score < best - 0.05) {
      best = score;
      cols2 = c;
    }
  }
  if (cols2 > 1) {
    const target = height / cols2;
    let col = 0;
    let cy = 0;
    let maxH = 0;
    boxes.forEach((b, bi) => {
      if (cy > 0 && cy + b.h / 2 > target && col < cols2 - 1) {
        col += 1;
        cy = 0;
      }
      const dx = col * (width + BAND_GAP);
      const dy = cy - b.y;
      b.x += dx;
      b.y += dy;
      out.forEach((n) => {
        if (n.band === bi) {
          n.x += dx;
          n.y += dy;
        }
      });
      cy += b.h + BAND_GAP;
      maxH = Math.max(maxH, cy - BAND_GAP);
    });
    height = maxH;
    fullW = cols2 * width + (cols2 - 1) * BAND_GAP;
  }
  // Ports: one slot per edge end on a side, sorted by the other end's x.
  const sides = new Map();
  const plan = edges.map((e) => {
    const a = out.get(e.from);
    const b = out.get(e.to);
    const same = Math.abs(a.y - b.y) < 1;
    const down = !same && a.y < b.y;
    const p = { e: e, a: a, b: b, same: same, down: down, up: !same && !down };
    const sa = same ? "t" : down ? "b" : "t";
    const sb = same ? "t" : down ? "t" : "b";
    [[a, sa, b, "s"], [b, sb, a, "t"]].forEach(([n, side, other, end]) => {
      const key = n.id + side;
      if (!sides.has(key)) sides.set(key, []);
      sides.get(key).push({ p: p, end: end, ox: other.x + other.w / 2 });
    });
    return p;
  });
  sides.forEach((list, key) => {
    list.sort((u, v) => u.ox - v.ox);
    const n = out.get(key.slice(0, -1));
    list.forEach((s, i) => {
      s.p[s.end + "x"] = n.x + 14 + ((n.w - 28) * (i + 1)) / (list.length + 1);
    });
  });
  const routes = plan.map((p) => {
    const sx = p.sx;
    const tx = p.tx;
    let pts;
    if (p.same) {
      const sy = p.a.y;
      const lift = 34 + Math.min(40, Math.abs(tx - sx) / 8);
      pts = [sx, sy, sx, sy - lift, tx, sy - lift, tx, sy - 2];
    } else if (p.down) {
      const sy = p.a.y + p.a.h;
      const ty = p.b.y - 2;
      const dy = Math.max(28, (ty - sy) * 0.45);
      pts = [sx, sy, sx, sy + dy, tx, ty - dy, tx, ty];
    } else {
      const sy = p.a.y;
      const ty = p.b.y + p.b.h + 2;
      const dy = Math.max(28, (sy - ty) * 0.45);
      pts = [sx, sy, sx, sy - dy, tx, ty + dy, tx, ty];
    }
    const d = "M" + f1(pts[0]) + " " + f1(pts[1]) + "C" + pts.slice(2).map(f1).join(" ");
    return Object.assign({}, p.e, { d: d, up: p.up, pts: pts, lx: null, ly: null, lw: 0 });
  });
  // Labels: declared edges first, then by count; each takes the first point along its curve that is free.
  const taken = Array.from(out.values()).map((n) => ({ x: n.x - 2, y: n.y - 2, w: n.w + 4, h: n.h + 4 }))
    .concat(boxes.map((b) => ({ x: b.x, y: b.y, w: Math.min(b.w, 12 + b.label.length * CHAR_W), h: 22 })));
  routes.slice().sort((u, v) => (u.derived === v.derived ? 0 : u.derived ? 1 : -1) ||
    (v.count || 0) - (u.count || 0)).forEach((r) => {
    if (!r.label || weak(r)) return;
    const w = labelWidth(r.label);
    for (const t of TRY_T) {
      const c = bez(r.pts, t);
      const box = { x: c.x - w / 2, y: c.y - LABEL_H / 2, w: w, h: LABEL_H };
      if (box.x < 0 || box.x + w > fullW) continue;
      if (taken.some((b) => hit(b, box))) continue;
      taken.push({ x: box.x - 3, y: box.y - 2, w: w + 6, h: LABEL_H + 4 });
      r.lx = f1(c.x);
      r.ly = f1(c.y);
      r.lw = w;
      break;
    }
  });
  routes.forEach((r) => delete r.pts);
  const top = Math.min(0, ...routes.filter((r) => r.label && r.ly !== null).map((r) => r.ly - LABEL_H));
  return { width: fullW, height: height, top: top, groups: boxes, nodes: Array.from(out.values()), edges: routes };
}

export const SEQ_COL = 184;
export const SEQ_HEAD = 40;
export const SEQ_ROW = 38;

export function sequenceLayout(flow) {
  const parts = (Array.isArray(flow.participants) ? flow.participants : []).filter((p) => p && p.id);
  const col = new Map(parts.map((p, i) => [p.id, i]));
  const heads = parts.map((p, i) => ({ id: p.id, label: p.label || p.id, x: i * SEQ_COL + 10, y: 0, w: SEQ_COL - 20,
    h: SEQ_HEAD, cx: i * SEQ_COL + SEQ_COL / 2 }));
  const steps = (Array.isArray(flow.steps) ? flow.steps : []).filter((s) => s && col.has(s.from) && col.has(s.to));
  const rows = steps.map((s, i) => {
    const y = SEQ_HEAD + 34 + i * SEQ_ROW;
    const x1 = heads[col.get(s.from)].cx;
    const x2 = heads[col.get(s.to)].cx;
    const self = x1 === x2;
    const d = self ? "M" + x1 + " " + (y - 6) + "h34v14h-30" : "M" + x1 + " " + y + "H" + (x2 + (x2 > x1 ? -3 : 3));
    const lx = self ? x1 + 40 : (x1 + x2) / 2;
    return { n: i + 1, from: s.from, to: s.to, label: s.label || "", reply: !!s.reply, self: self, d: d, lx: lx,
      ly: y - 6, anchor: self ? "start" : "middle", y: y };
  });
  const height = SEQ_HEAD + 34 + Math.max(0, steps.length - 1) * SEQ_ROW + 24;
  return { width: Math.max(1, parts.length) * SEQ_COL, height: height, heads: heads, rows: rows };
}

export const MX_ROW = 30;
export const MX_COL = 34;
export const MX_LEFT = 200;
export const MX_HEAD = 120;

export function matrixLayout(view) {
  const nodes = Array.isArray(view.nodes) ? view.nodes : [];
  const edges = Array.isArray(view.edges) ? view.edges : [];
  const users = new Set(edges.map((e) => e.from));
  const stores = new Set(edges.map((e) => e.to));
  const rows = nodes.filter((n) => users.has(n.id)).map((n, i) => ({ id: n.id, label: n.label, y: MX_HEAD + i *
    MX_ROW }));
  const cols = nodes.filter((n) => stores.has(n.id) && !users.has(n.id)).map((n, i) => ({ id: n.id, label: n.label,
    sub: n.sub, x: MX_LEFT + i * MX_COL }));
  const ri = new Map(rows.map((r) => [r.id, r]));
  const ci = new Map(cols.map((c) => [c.id, c]));
  const cells = edges.filter((e) => ri.has(e.from) && ci.has(e.to)).map((e) => ({ from: e.from, to: e.to,
    write: /write/.test(e.label || ""), label: e.label || "", x: ci.get(e.to).x + MX_COL / 2,
    y: ri.get(e.from).y + MX_ROW / 2 }));
  return { width: MX_LEFT + cols.length * MX_COL + 8, height: MX_HEAD + rows.length * MX_ROW + 4, rows: rows,
    cols: cols, cells: cells };
}
