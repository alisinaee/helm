// Workflow graph layout (WP71, WP70-A). layout(graph, mode, range, now) places the nodes of buildGraph() and returns
// their boxes, the cubic path of every edge, the lane bands and, in time mode, the tick columns. Pure: no DOM, no clock
// (now is an argument), no randomness, so the same input gives the same JSON.
//
// Left to right. Phases are horizontal bands in phase order. A column is the longest-path rank over dependency and
// handoff edges (mode "dependency") or the time bucket of the range (mode "time"). Inside a lane the nodes stack per
// column. Four barycenter sweeps (forward, backward, forward, backward) order the tasks to cut crossings. Issues sit
// above the tasks they block, the queue pill sits in column 0, and each task's job pills hang under it.
// Cycles: a depth-first search finds the back edges. They are ignored for the rank and reported in `cycles`, and
// their paths are still drawn.
//
// flowLayout(graph, opts) (R7.14 B) is the left-to-right map: Start, one frame per phase, End. It returns the boxes of
// every visible node, the frames, a right-angled polyline (`routes`) for every edge including the sequence edges, the
// parallel brackets, the Now flag and the path order. layout() returns it as `flow`; its other fields are unchanged.

import { NODE_CAP } from "./model.js";

export const NODE_W = 168;
export const NODE_H = 44;
export const PILL_W = 52;
export const PILL_H = 20;

const PILL_STEP = 58;
const PILL_DY = 58;
const SLOT_GAP = 10;
const COL_GAP = 32;
const COL_W = NODE_W + COL_GAP;
const X0 = NODE_W + COL_GAP;
const LANE_PAD = 8;
const LANE_GAP = 8;
const TOP_DEP = 8;
const TOP_TIME = 36;
const MARGIN = 16;
const SWEEPS = 4;
const MIN = 60000;
const HOUR = 60 * MIN;
const DAY = 24 * HOUR;
const BUCKET = { "2h": 15 * MIN, today: HOUR, week: 6 * HOUR, all: DAY };
const MAX_COLS = 200;

// Flow layout sizes (NODE_W, NODE_H, PILL_*, PILL_DY and MARGIN are shared with the layout above).
const CARD_W = 200;
const CARD_H = 56;
const CELL_GAP = 24;
const ROW_GAP = 28;
const STACK_GAP = 12;
const STRIP_GAP = 10;
const STRIP_SEP = 14;
const FRAME_GAP = 28;
const FRAME_PAD = 12;
const TITLE_H = 26;
const CHANNEL = 14;
const FLOW_TOP = 40;
const FLOW_COLS = 4;
const END_W = 132;
const END_H = 44;
const FLAG_W = 96;
const FLAG_H = 20;
const SLOT = 24;
const CORNER = 12;
const LOOP = 12;
const WIDE = 100;

function colX(c) {
  return X0 + c * COL_W;
}

function slotOf(node, pills) {
  if (node.type === "task" && pills > 0) return PILL_DY + PILL_H + SLOT_GAP;
  return NODE_H + SLOT_GAP;
}

// Longest-path rank over the task pairs. Depth-first search finds the back edges, which are dropped before ranking.
function rankTasks(ids, pairList) {
  const succ = new Map(ids.map((id) => [id, new Set()]));
  pairList.forEach(([a, b]) => {
    if (succ.has(a) && succ.has(b)) succ.get(a).add(b);
  });
  const adj = new Map(ids.map((id) => [id, Array.from(succ.get(id)).sort()]));
  const state = new Map();
  const back = new Set();
  ids.forEach((root) => {
    if (state.has(root)) return;
    state.set(root, 1);
    const stack = [[root, 0]];
    while (stack.length) {
      const top = stack[stack.length - 1];
      const out = adj.get(top[0]);
      if (top[1] < out.length) {
        const v = out[top[1]];
        top[1] += 1;
        if (state.get(v) === 1) back.add(top[0] + ">" + v);
        else if (!state.has(v)) {
          state.set(v, 1);
          stack.push([v, 0]);
        }
      } else {
        state.set(top[0], 2);
        stack.pop();
      }
    }
  });
  const indeg = new Map(ids.map((id) => [id, 0]));
  const forward = new Map(ids.map((id) => [id, []]));
  ids.forEach((u) => {
    adj.get(u).forEach((v) => {
      if (back.has(u + ">" + v)) return;
      forward.get(u).push(v);
      indeg.set(v, indeg.get(v) + 1);
    });
  });
  const rank = new Map(ids.map((id) => [id, 0]));
  const queue = ids.filter((id) => indeg.get(id) === 0);
  for (let i = 0; i < queue.length; i += 1) {
    const u = queue[i];
    forward.get(u).forEach((v) => {
      rank.set(v, Math.max(rank.get(v), rank.get(u) + 1));
      indeg.set(v, indeg.get(v) - 1);
      if (indeg.get(v) === 0) queue.push(v);
    });
  }
  return { rank, cycles: Array.from(back).sort() };
}

// The time window of the range and the bucket width. Each column is one bucket. Above MAX_COLS the buckets widen.
function timeWindow(range, now, times) {
  const key = ["2h", "today", "week", "all"].indexOf(range) >= 0 ? range : "today";
  let t0;
  let t1 = now;
  if (key === "2h") t0 = now - 2 * HOUR;
  else if (key === "week") t0 = now - 7 * DAY;
  else if (key === "all") t0 = Math.min(now - 2 * HOUR, ...times);
  else {
    const d = new Date(now);
    t0 = new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
    t1 = t0 + DAY;
  }
  let bucket = BUCKET[key];
  const span = Math.max(1, t1 - t0);
  if (span / bucket > MAX_COLS) bucket = Math.ceil(span / MAX_COLS);
  return { t0, bucket, n: Math.max(1, Math.ceil(span / bucket)) };
}

export function layout(graph, mode, range, now) {
  const g = graph && Array.isArray(graph.nodes) ? graph : { nodes: [], edges: [], lanes: [] };
  const timeMode = mode === "time";
  const nowMs = Number(now) || 0;
  const nodes = g.nodes.filter((n) => n && typeof n.id === "string");
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const edges = (Array.isArray(g.edges) ? g.edges : []).filter((e) => e && byId.has(e.from) && byId.has(e.to));
  const laneOf = (n) => (n.lane === null || n.lane === undefined ? "_" : String(n.lane));

  const laneIds = [];
  const laneSeen = new Set();
  const pushLane = (id) => {
    if (laneSeen.has(id)) return;
    laneSeen.add(id);
    laneIds.push(id);
  };
  (Array.isArray(g.lanes) ? g.lanes : []).forEach((l) => {
    if (l && l.id !== undefined && l.id !== null) pushLane(String(l.id));
  });
  nodes.forEach((n) => pushLane(laneOf(n)));

  // Task pairs (dependency and handoff, seen at task level) drive the rank and the sweeps.
  const taskOf = (n) => (n.type === "task" ? n.id : n.type === "job" ? n.parent : null);
  const pairList = [];
  edges.forEach((e) => {
    if (e.type !== "dependency" && e.type !== "handoff") return;
    const a = taskOf(byId.get(e.from));
    const b = taskOf(byId.get(e.to));
    if (a && b && a !== b) pairList.push([a, b]);
  });
  const taskNodes = nodes.filter((n) => n.type === "task");
  const { rank, cycles } = rankTasks(taskNodes.map((n) => n.id), pairList);

  let win = null;
  if (timeMode) {
    const times = nodes.filter((n) => n.type === "task" && typeof n.time === "number").map((n) => n.time);
    win = timeWindow(range, nowMs, times);
  }
  const hasQueue = nodes.some((n) => n.type === "queue");
  const shift = !timeMode && hasQueue ? 1 : 0;
  const col = new Map();
  taskNodes.forEach((n) => {
    if (timeMode) {
      const t = typeof n.time === "number" ? n.time : null;
      col.set(n.id, t === null ? 0 : Math.min(win.n - 1, Math.max(0, Math.floor((t - win.t0) / win.bucket))));
    } else {
      col.set(n.id, (rank.get(n.id) || 0) + shift);
    }
  });
  nodes.forEach((n) => {
    if (n.type === "queue") col.set(n.id, 0);
  });
  // An issue sits in the column of the first task it blocks.
  const blockTarget = new Map();
  edges.forEach((e) => {
    if (e.type === "blocker" && !blockTarget.has(e.from)) blockTarget.set(e.from, e.to);
  });
  nodes.forEach((n) => {
    if (n.type !== "issue") return;
    const t = blockTarget.get(n.id);
    col.set(n.id, t !== undefined && col.has(t) ? col.get(t) : 0);
  });

  let maxCol = 0;
  col.forEach((c) => {
    if (c > maxCol) maxCol = c;
  });
  if (timeMode) maxCol = Math.max(maxCol, win.n - 1);

  // Cells: per lane and column, the slot nodes at the top (issues, queue) and the tasks, which the sweeps order.
  const slotNodes = nodes.filter((n) => n.type !== "phase" && n.type !== "job");
  const laneCells = new Map(laneIds.map((id) => [id, new Map()]));
  slotNodes.forEach((n) => {
    const cells = laneCells.get(laneOf(n));
    const c = col.get(n.id) || 0;
    if (!cells.has(c)) cells.set(c, { top: [], tasks: [] });
    const cell = cells.get(c);
    if (n.type === "task") cell.tasks.push(n.id);
    else cell.top.push(n.id);
  });
  const preds = new Map(taskNodes.map((n) => [n.id, []]));
  const succs = new Map(taskNodes.map((n) => [n.id, []]));
  pairList.forEach(([a, b]) => {
    if (!preds.has(a) || !preds.has(b) || laneOf(byId.get(a)) !== laneOf(byId.get(b))) return;
    succs.get(a).push(b);
    preds.get(b).push(a);
  });
  const at = new Map();
  laneCells.forEach((cells) => cells.forEach((cell) => {
    cell.tasks.forEach((id, j) => at.set(id, cell.top.length + j));
  }));
  const colKeys = Array.from(new Set(slotNodes.map((n) => col.get(n.id) || 0))).sort((a, b) => a - b);
  for (let s = 0; s < SWEEPS; s += 1) {
    const forward = s % 2 === 0;
    const order = forward ? colKeys : colKeys.slice().reverse();
    order.forEach((c) => {
      laneIds.forEach((lane) => {
        const cell = laneCells.get(lane).get(c);
        if (!cell || cell.tasks.length < 2) return;
        const rows = cell.tasks.map((id) => {
          const near = (forward ? preds : succs).get(id).map((v) => at.get(v)).filter((p) => p !== undefined);
          const cur = at.get(id);
          const bary = near.length ? near.reduce((a, b) => a + b, 0) / near.length : cur;
          return { id, bary, cur };
        });
        rows.sort((a, b) => a.bary - b.bary || a.cur - b.cur || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
        cell.tasks = rows.map((r) => r.id);
        cell.tasks.forEach((id, j) => at.set(id, cell.top.length + j));
      });
    });
  }

  const pillCount = new Map();
  nodes.forEach((n) => {
    if (n.type === "job" && n.parent) pillCount.set(n.parent, (pillCount.get(n.parent) || 0) + 1);
  });
  const pos = {};
  const bands = [];
  const bandOf = new Map();
  let y = timeMode ? TOP_TIME : TOP_DEP;
  laneIds.forEach((lane) => {
    const cells = laneCells.get(lane);
    let inner = 0;
    Array.from(cells.keys()).sort((a, b) => a - b).forEach((c) => {
      const cell = cells.get(c);
      let cy = 0;
      cell.top.concat(cell.tasks).forEach((id) => {
        pos[id] = { x: colX(c), y: y + LANE_PAD + cy, w: NODE_W, h: NODE_H };
        cy += slotOf(byId.get(id), pillCount.get(id) || 0);
      });
      inner = Math.max(inner, cy);
    });
    const h = Math.max(NODE_H + 2 * LANE_PAD, inner > 0 ? inner - SLOT_GAP + 2 * LANE_PAD : 0);
    const band = { id: lane, y, h };
    bands.push(band);
    bandOf.set(lane, band);
    y += h + LANE_GAP;
  });
  nodes.forEach((n) => {
    if (n.type === "phase") {
      const band = bandOf.get(laneOf(n));
      pos[n.id] = { x: 0, y: band.y + LANE_PAD, w: NODE_W, h: NODE_H };
    }
  });
  const pillIndex = new Map();
  nodes.forEach((n) => {
    if (n.type !== "job" || !pos[n.parent]) return;
    const parent = pos[n.parent];
    const k = pillIndex.get(n.parent) || 0;
    pillIndex.set(n.parent, k + 1);
    pos[n.id] = { x: parent.x + k * PILL_STEP, y: parent.y + PILL_DY, w: PILL_W, h: PILL_H };
  });

  const paths = {};
  edges.forEach((e) => {
    const a = pos[e.from];
    const b = pos[e.to];
    if (!a || !b) return;
    const x1 = a.x + a.w;
    const y1 = a.y + a.h / 2;
    const x2 = b.x;
    const y2 = b.y + b.h / 2;
    const d = Math.max(24, Math.round(Math.abs(x2 - x1) / 2));
    paths[e.id] = "M" + x1 + " " + y1 + "C" + (x1 + d) + " " + y1 + " " + (x2 - d) + " " + y2 + " " + x2 + " " + y2;
  });

  const ticks = [];
  let nowX = null;
  if (timeMode) {
    for (let i = 0; i < win.n; i += 1) ticks.push({ x: colX(i), t: win.t0 + i * win.bucket });
    if (nowMs >= win.t0 && nowMs <= win.t0 + win.n * win.bucket) {
      nowX = Math.round(X0 + ((nowMs - win.t0) / win.bucket) * COL_W);
    }
  }
  const width = X0 + (maxCol + 1) * COL_W - COL_GAP + MARGIN;
  const bottom = bands.length ? bands[bands.length - 1].y + bands[bands.length - 1].h : (timeMode ? TOP_TIME : TOP_DEP);
  return {
    mode: timeMode ? "time" : "dependency",
    pos,
    paths,
    lanes: bands,
    width,
    height: bottom + MARGIN,
    cycles,
    ticks,
    nowX,
    flow: flowLayout(g, {}),
  };
}

function laneOf(n) {
  return n.lane === null || n.lane === undefined ? "_" : String(n.lane);
}

function cy(b) {
  return b.y + b.h / 2;
}

function right(b) {
  return b.x + b.w;
}

function bottom(b) {
  return b.y + b.h;
}

// Vertical joins sit on the right corner of a wide box, clear of the job pills that hang under a task.
function anchor(b) {
  return b.w >= WIDE ? b.x + b.w - CORNER : b.x + b.w / 2;
}

function taskHeight(pills) {
  return pills > 0 ? PILL_DY + PILL_H : NODE_H;
}

function cellHeight(cell, pillsOf) {
  let h = 0;
  cell.forEach((t, j) => {
    h += taskHeight((pillsOf.get(t.id) || []).length) + (j ? STACK_GAP : 0);
  });
  return h;
}

function withSlot(b) {
  const out = { x: b.x, y: b.y, w: b.w, h: b.h };
  if (b.w >= WIDE) {
    out.slot = { x: b.x + b.w - SLOT - 4, y: b.y + Math.round((b.h - SLOT) / 2), w: SLOT, h: SLOT };
  }
  return out;
}

// Stable topological order of ids by the [before, after] pairs: the earliest ready id goes next. A cycle falls back to
// file order for the ids it holds back.
function stableOrder(ids, pairs) {
  const known = new Set(ids);
  const succ = new Map(ids.map((id) => [id, []]));
  const indeg = new Map(ids.map((id) => [id, 0]));
  pairs.forEach(([a, b]) => {
    if (a === b || !known.has(a) || !known.has(b)) return;
    succ.get(a).push(b);
    indeg.set(b, indeg.get(b) + 1);
  });
  const done = new Set();
  const out = [];
  while (out.length < ids.length) {
    let pick = ids.find((id) => !done.has(id) && indeg.get(id) === 0);
    if (pick === undefined) pick = ids.find((id) => !done.has(id));
    done.add(pick);
    out.push(pick);
    succ.get(pick).forEach((v) => indeg.set(v, indeg.get(v) - 1));
  }
  return out;
}

// One frame's inner layout, relative to the frame's top-left corner. The cells are the tasks in topological file order:
// one task, or a parallel group whose members stack in one column. Cells fill rows of up to four; odd rows run right to
// left (snake), so consecutive tasks are always neighbours. The strip above holds the issues and the queue.
function laneGeometry(tasks, strip, ctx) {
  const byTask = new Map(tasks.map((t) => [t.id, t]));
  const ordered = stableOrder(tasks.map((t) => t.id), ctx.pairs).map((id) => byTask.get(id));
  const cells = [];
  const taken = new Set();
  ordered.forEach((t) => {
    const grp = ctx.groupOf.get(t.id);
    if (!grp) {
      cells.push([t]);
      return;
    }
    if (taken.has(grp)) return;
    taken.add(grp);
    cells.push(ordered.filter((m) => ctx.groupOf.get(m.id) === grp));
  });
  const boxes = new Map();
  const brackets = [];
  const order = [];
  const top = FRAME_PAD + TITLE_H + 8;
  let cols = 0;
  let bottomY = top;
  if (strip.length) {
    const rows = Math.ceil(strip.length / FLOW_COLS);
    cols = Math.min(FLOW_COLS, strip.length);
    strip.forEach((n, k) => {
      const col = k % FLOW_COLS;
      const row = Math.floor(k / FLOW_COLS);
      boxes.set(n.id, { x: FRAME_PAD + col * (NODE_W + CELL_GAP), y: top + row * (NODE_H + STRIP_GAP),
        w: NODE_W, h: NODE_H });
    });
    bottomY = top + rows * NODE_H + (rows - 1) * STRIP_GAP;
  }
  let y = strip.length ? bottomY + STRIP_SEP : top;
  if (cells.length) {
    const gc = Math.min(FLOW_COLS, cells.length);
    cols = Math.max(cols, gc);
    for (let r = 0; r * gc < cells.length; r += 1) {
      const row = cells.slice(r * gc, r * gc + gc);
      const rowH = Math.max(...row.map((cell) => cellHeight(cell, ctx.pillsOf)));
      row.forEach((cell, k) => {
        const col = r % 2 === 0 ? k : gc - 1 - k;
        const x = FRAME_PAD + col * (NODE_W + CELL_GAP);
        let cyy = y;
        cell.forEach((t) => {
          const pills = ctx.pillsOf.get(t.id) || [];
          boxes.set(t.id, { x, y: cyy, w: NODE_W, h: NODE_H });
          pills.forEach((p, q) => boxes.set(p.id, { x: x + q * PILL_STEP, y: cyy + PILL_DY, w: PILL_W, h: PILL_H }));
          order.push(t.id);
          cyy += taskHeight(pills.length) + STACK_GAP;
        });
        if (cell.length > 1) {
          brackets.push({ x: x - 4, y: y - 4, w: NODE_W + 8, h: cellHeight(cell, ctx.pillsOf) + 8,
            members: cell.map((t) => t.id) });
        }
      });
      bottomY = y + rowH;
      y = bottomY + ROW_GAP;
    }
  }
  const width = 2 * FRAME_PAD + cols * NODE_W + Math.max(0, cols - 1) * CELL_GAP;
  return {
    w: Math.max(CARD_W, width),
    h: bottomY + FRAME_PAD + CHANNEL,
    boxes,
    brackets,
    order,
    count: boxes.size,
  };
}

function loopRoute(a) {
  const r = right(a);
  const m = cy(a);
  return [[r, m - 8], [r + LOOP, m - 8], [r + LOOP, m + 8], [r, m + 8]];
}

// Two boxes in the same frame: straight when they share a row or a column, else one right-angled elbow.
function insideRoute(a, b) {
  if (a === b) return loopRoute(a);
  if (Math.abs(cy(a) - cy(b)) < 1) {
    return b.x > a.x ? [[right(a), cy(a)], [b.x, cy(b)]] : [[a.x, cy(a)], [right(b), cy(b)]];
  }
  if (Math.abs(anchor(a) - anchor(b)) < 1) {
    return b.y > a.y ? [[anchor(a), bottom(a)], [anchor(b), b.y]] : [[anchor(a), a.y], [anchor(b), bottom(b)]];
  }
  if (b.x >= right(a)) {
    const mx = right(a) + CELL_GAP / 2;
    return [[right(a), cy(a)], [mx, cy(a)], [mx, cy(b)], [b.x, cy(b)]];
  }
  if (right(b) <= a.x) {
    const mx = a.x - CELL_GAP / 2;
    return [[a.x, cy(a)], [mx, cy(a)], [mx, cy(b)], [right(b), cy(b)]];
  }
  const down = b.y > a.y;
  const my = down ? (bottom(a) + b.y) / 2 : (bottom(b) + a.y) / 2;
  return [[anchor(a), down ? bottom(a) : a.y], [anchor(a), my], [anchor(b), my],
    [anchor(b), down ? b.y : bottom(b)]];
}

// Two boxes in different frames: down from the source through the frame's bottom channel, across the gap between the
// frames, then into the target from its near side. The channel lies under every row, so it crosses no node.
function crossRoute(S, D, fs, fd) {
  const a = S.box;
  const b = D.box;
  const chan = S.card ? bottom(fs) + 8 : bottom(fs) - 6;
  const toRight = fd.x > fs.x;
  const gx = Math.round(toRight ? (right(fs) + fd.x) / 2 : (right(fd) + fs.x) / 2);
  const entry = toRight ? b.x : right(b);
  const sx = anchor(a);
  return [[sx, bottom(a)], [sx, chan], [gx, chan], [gx, cy(b)], [entry, cy(b)]];
}

// A folded frame sends its one arrow out of its right middle into the left side of the frame to its right.
function cardRoute(S, D, fd) {
  const a = S.box;
  const b = D.box;
  const gx = Math.round((right(a) + fd.x) / 2);
  return [[right(a), cy(a)], [gx, cy(a)], [gx, cy(b)], [b.x, cy(b)]];
}

function routeEdge(S, D, frameBox) {
  if (S.kind === "start" && D.kind === "end") return [[right(S.box), cy(S.box)], [D.box.x, cy(D.box)]];
  if (S.kind === "start") {
    const fd = frameBox.get(D.lane);
    if (!fd) return null;
    const gx = Math.round((right(S.box) + fd.x) / 2);
    return [[right(S.box), cy(S.box)], [gx, cy(S.box)], [gx, cy(D.box)], [D.box.x, cy(D.box)]];
  }
  if (S.kind === "end" || D.kind === "start") return null;
  const fs = frameBox.get(S.lane);
  const fd = D.kind === "end" ? D.box : frameBox.get(D.lane);
  if (!fs || !fd) return null;
  // Tasks inside one folded frame all draw on its card: their edges are hidden inside it, not looped back onto it.
  if (S.lane === D.lane) return S.card ? null : insideRoute(S.box, D.box);
  if (S.card && fd.x > fs.x) return cardRoute(S, D, fd);
  return crossRoute(S, D, fs, fd);
}

export function flowLayout(graph, opts) {
  const g = graph && Array.isArray(graph.nodes) ? graph : { nodes: [], edges: [] };
  const o = opts && typeof opts === "object" ? opts : {};
  const nodes = g.nodes.filter((n) => n && typeof n.id === "string");
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const ends = (id) => id === "start" || id === "end" || byId.has(id);
  const seenEdge = new Set();
  const edges = (Array.isArray(g.edges) ? g.edges : []).concat(Array.isArray(g.sequence) ? g.sequence : [])
    .filter((e) => {
      if (!e || typeof e.id !== "string" || seenEdge.has(e.id) || !ends(e.from) || !ends(e.to)) return false;
      seenEdge.add(e.id);
      return true;
    });

  // Lanes in phase order; a lane some node names but the phase list lacks comes after.
  const phaseOf = new Map();
  const laneIds = [];
  const laneSeen = new Set();
  const addLane = (id) => {
    if (laneSeen.has(id)) return;
    laneSeen.add(id);
    laneIds.push(id);
  };
  (Array.isArray(g.lanes) ? g.lanes : []).forEach((l) => {
    if (l && l.id !== undefined && l.id !== null) addLane(String(l.id));
  });
  nodes.forEach((n) => {
    if (n.type === "phase") {
      phaseOf.set(laneOf(n), n);
      addLane(laneOf(n));
    }
  });
  nodes.forEach((n) => addLane(laneOf(n)));

  const tasksOf = new Map();
  const pillsOf = new Map();
  const stripOf = new Map();
  const push = (map, key, value) => {
    const rows = map.get(key) || [];
    rows.push(value);
    map.set(key, rows);
  };
  nodes.forEach((n) => {
    if (n.type === "task") push(tasksOf, laneOf(n), n);
    else if (n.type === "job" && n.parent) push(pillsOf, n.parent, n);
    else if (n.type === "issue" || n.type === "queue") push(stripOf, laneOf(n), n);
  });
  const groupOf = new Map();
  (Array.isArray(g.parallel) ? g.parallel : []).forEach((grp) => {
    if (!grp || !Array.isArray(grp.members)) return;
    grp.members.forEach((m) => {
      if (byId.has(m) && byId.get(m).type === "task" && !groupOf.has(m)) groupOf.set(m, grp);
    });
  });
  const pairsOf = new Map();
  edges.forEach((e) => {
    if (e.type !== "dependency" || !byId.has(e.from) || !byId.has(e.to)) return;
    const lane = laneOf(byId.get(e.from));
    if (lane !== laneOf(byId.get(e.to))) return;
    push(pairsOf, lane, [e.from, e.to]);
  });

  const geo = new Map();
  laneIds.forEach((lane) => {
    geo.set(lane, laneGeometry(tasksOf.get(lane) || [], stripOf.get(lane) || [],
      { pairs: pairsOf.get(lane) || [], groupOf, pillsOf }));
  });

  // Which frames are cards. Done phases start collapsed; opts.open and opts.close override; expandAll (Show all) turns
  // the defaults off; collapseAll folds every frame.
  const open = new Set(Array.isArray(o.open) ? o.open.map(String) : []);
  const shut = new Set(Array.isArray(o.close) ? o.close.map(String) : []);
  const collapsed = new Set();
  laneIds.forEach((lane) => {
    const ph = phaseOf.get(lane);
    let fold = false;
    if (shut.has(lane)) fold = true;
    else if (!open.has(lane) && o.expandAll !== true) {
      fold = o.collapseAll === true || (ph !== undefined && ph.collapsed === true);
    }
    if (fold) collapsed.add(lane);
  });
  const cur = typeof g.current === "string" ? g.current : "start";
  const curNode = byId.get(cur);
  const curLane = curNode ? laneOf(curNode) : null;
  const curIdx = cur === "start" ? -1 : cur === "end" ? laneIds.length : laneIds.indexOf(curLane);
  const countNodes = () => {
    let c = 2;
    laneIds.forEach((lane) => {
      c += collapsed.has(lane) ? 1 : geo.get(lane).count;
    });
    return c;
  };
  // The cap: done phases are already cards; then todo phases two or more past Now (furthest first); then every frame
  // but Now's (summary). Show all (expandAll) skips it.
  // Start (curIdx -1) keeps the first frame open and End the last; the frame kept open is the one the cap spares.
  let capped = false;
  if (o.expandAll !== true && countNodes() > NODE_CAP) {
    const keep = Math.min(laneIds.length - 1, Math.max(0, curIdx));
    for (let i = laneIds.length - 1; i >= 0 && countNodes() > NODE_CAP; i -= 1) {
      const lane = laneIds[i];
      const ph = phaseOf.get(lane);
      const todo = !ph || ph.done < ph.total;
      if (i >= curIdx + 2 && todo && !open.has(lane)) collapsed.add(lane);
    }
    for (let i = laneIds.length - 1; i >= 0 && countNodes() > NODE_CAP; i -= 1) {
      if (i !== keep) collapsed.add(laneIds[i]);
    }
    // Last resort: one phase alone is over the cap, so Now's frame folds too (its Now point moves to the card).
    if (countNodes() > NODE_CAP && laneIds.length) collapsed.add(laneIds[keep]);
    capped = countNodes() > NODE_CAP;
  }

  // Place the frames left to right.
  const start = { x: MARGIN, y: 0, w: END_W, h: END_H };
  let x = MARGIN + END_W + FRAME_GAP;
  const frameRec = new Map();
  const frames = [];
  laneIds.forEach((lane) => {
    const isCard = collapsed.has(lane);
    const gm = geo.get(lane);
    const box = { x, y: FLOW_TOP, w: isCard ? CARD_W : gm.w, h: isCard ? CARD_H : gm.h };
    const ph = phaseOf.get(lane);
    frameRec.set(lane, { box, collapsed: isCard });
    frames.push({
      id: "phase:" + lane, lane, label: ph ? ph.label : lane, approved: ph ? ph.approved === true : false,
      done: ph ? ph.done : 0, total: ph ? ph.total : 0, tokensK: ph ? ph.tokensK : 0, collapsed: isCard,
      x: box.x, y: box.y, w: box.w, h: box.h,
      title: { x: box.x + FRAME_PAD, y: box.y + FRAME_PAD, w: box.w - 2 * FRAME_PAD, h: TITLE_H },
      slot: { x: box.x + box.w - FRAME_PAD - SLOT, y: box.y + FRAME_PAD + 1, w: SLOT, h: SLOT },
    });
    x += box.w + FRAME_GAP;
  });
  const mainBottom = frames.reduce((m, f) => Math.max(m, f.y + f.h), FLOW_TOP + END_H);
  const endX = x;
  const pillY = Math.round(FLOW_TOP + (mainBottom - FLOW_TOP - END_H) / 2);
  const endBox = { x: endX, y: pillY, w: END_W, h: END_H };
  start.y = pillY;

  const boxes = { start, end: endBox };
  const parallel = [];
  const path = ["start"];
  const frameBox = new Map();
  frames.forEach((f) => {
    frameBox.set(f.lane, { x: f.x, y: f.y, w: f.w, h: f.h });
  });
  frames.forEach((f) => {
    const fb = frameBox.get(f.lane);
    if (f.collapsed) {
      boxes[f.id] = withSlot(fb);
      path.push(f.id);
      return;
    }
    const gm = geo.get(f.lane);
    gm.boxes.forEach((rb, id) => {
      boxes[id] = withSlot({ x: fb.x + rb.x, y: fb.y + rb.y, w: rb.w, h: rb.h });
    });
    gm.brackets.forEach((br) => {
      parallel.push({ lane: f.lane, x: fb.x + br.x, y: fb.y + br.y, w: br.w, h: br.h, members: br.members });
    });
    gm.order.forEach((id) => path.push(id));
  });
  path.push("end");

  // Every node id resolves to the box that draws it: its own box, or its frame's card when the frame is folded.
  const endpoint = (id) => {
    if (id === "start") return { kind: "start", lane: null, box: start };
    if (id === "end") return { kind: "end", lane: null, box: endBox };
    const n = byId.get(id);
    if (!n) return null;
    const lane = laneOf(n);
    const rec = frameRec.get(lane);
    if (!rec) return null;
    // A phase id (Now on a folded task) points at the whole frame: its card when folded, its box when open.
    if (rec.collapsed || n.type === "phase") return { kind: "node", lane, box: rec.box, card: true };
    const b = boxes[id];
    return b ? { kind: "node", lane, box: b, card: false } : null;
  };
  const routes = {};
  edges.forEach((e) => {
    const S = endpoint(e.from);
    const D = endpoint(e.to);
    if (!S || !D) return;
    const pts = routeEdge(S, D, frameBox);
    if (pts) routes[e.id] = pts.map(([px, py]) => [Math.round(px), Math.round(py)]);
  });

  const nowEnd = endpoint(cur);
  const now = {
    node: cur,
    box: nowEnd ? nowEnd.box : null,
    flag: nowEnd ? { x: nowEnd.box.x, y: FLOW_TOP - FLAG_H - 4, w: FLAG_W, h: FLAG_H } : null,
  };
  const mainH = Math.max(mainBottom, endBox.y + END_H);
  return {
    width: endX + END_W + MARGIN,
    height: mainH + MARGIN,
    cap: NODE_CAP,
    count: Object.keys(boxes).length,
    capped,
    collapsed: laneIds.filter((lane) => collapsed.has(lane)),
    frames,
    boxes,
    routes,
    parallel,
    now,
    path,
  };
}
