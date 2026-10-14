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

export const NODE_W = 168;
export const NODE_H = 44;
export const PILL_W = 36;
export const PILL_H = 20;

const PILL_STEP = 40;
const PILL_DY = 50;
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
  };
}
