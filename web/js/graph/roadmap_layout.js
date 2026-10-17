// Roadmap Map layout (R11.5, docs/ROADMAP-MAP.md). Pure: one normalized project snapshot in, boxes and paths out, so
// node tests can drive it and the same input always gives the same output. The picture is a metro line of phases
// (one station per phase, in plan order, left to right) with a column of task cards under each open station (a story
// map). A folded phase is a narrow column with its station and a summary box. Inside an open phase the done tasks
// fold into one "N done" stub that opens in place. Dependency arrows come from the `after` pairs; the metro line
// itself is the phase flow. "Now" is the phase that owns a running job, else the first phase that is not done.
//
// opts: { status: all|open|doing|blocked|hold|done, model: "" or a model name, open: {pid: bool},
// showDone: {pid: bool}, deps: [[from, to], ...], running: {taskId: true}, blocked: [taskId, ...], spacing: 1 }.
// spacing (R11.115, 0.2 .. no upper limit) scales the gap between columns and between cards; box sizes never change.

import { spacingOf } from "./layout.js";

export const COL_W = 200;
export const FOLD_W = 120;
export const COL_GAP = 28;
export const CARD_W = 184;
export const CARD_H = 46;
export const CARD_GAP = 8;
export const STUB_H = 28;
export const HEAD_H = 76;
export const PAD = 16;
export const LINE_Y = 22;
export const STATUSES = ["all", "open", "doing", "blocked", "hold", "done"];

function phaseOf(task) {
  return task.phase || String(task.id).split(".")[0];
}

// One of done, doing, blocked, hold, defer, todo. A running job or a partial task is doing; an open blocker names a
// blocked task.
export function statusOf(task, running, blocked) {
  const s = String(task.state || "todo");
  if (s === "done") return "done";
  if (blocked && blocked.indexOf(task.id) >= 0) return "blocked";
  if ((running && running[task.id]) || s === "partial" || s === "doing" || s === "active") return "doing";
  if (s === "blocked" || s === "block") return "blocked";
  if (s === "hold") return "hold";
  if (s === "deferred" || s === "defer") return "defer";
  return "todo";
}

function passes(status, want) {
  if (!want || want === "all") return true;
  if (want === "open") return status !== "done";
  return status === want;
}

function phaseOpen(phase, open) {
  const saved = open ? open[phase.id] : undefined;
  return typeof saved === "boolean" ? saved : phase.state !== "done";
}

// The phase that holds "Now": the one with a running job, else the first not-done phase, else null.
export function nowPhase(snap, running) {
  const phases = snap.phases || [];
  const tasks = snap.tasks || [];
  for (const p of phases) {
    if (tasks.some(function (t) {
      return phaseOf(t) === p.id && running && running[t.id];
    })) return p.id;
  }
  const next = phases.find(function (p) {
    return p.state !== "done";
  });
  return next ? next.id : null;
}

function depPath(a, b) {
  const x1 = a.x + a.w;
  const y1 = a.y + a.h / 2;
  if (b.x > a.x) {
    const x2 = b.x;
    const y2 = b.y + b.h / 2;
    const dx = Math.max(16, (x2 - x1) / 2);
    return "M" + x1 + " " + y1 + "C" + (x1 + dx) + " " + y1 + " " + (x2 - dx) + " " + y2 + " " + x2 + " " + y2;
  }
  // Same column (or backwards): a loop on the right side, into the right side of the target.
  const x2 = b.x + b.w;
  const y2 = b.y + b.h / 2;
  const bulge = x1 + 22;
  return "M" + x1 + " " + y1 + "C" + bulge + " " + y1 + " " + bulge + " " + y2 + " " + x2 + " " + y2;
}

export function roadmapLayout(snap, opts) {
  const o = opts || {};
  const k = spacingOf(o.spacing);
  const colGap = Math.round(COL_GAP * k);
  const cardGap = Math.round(CARD_GAP * k);
  const running = o.running || {};
  const blocked = o.blocked || [];
  const phases = Array.isArray(snap && snap.phases) ? snap.phases : [];
  const tasks = Array.isArray(snap && snap.tasks) ? snap.tasks : [];
  const nowId = nowPhase({ phases: phases, tasks: tasks }, running);
  const cols = [];
  const cards = [];
  const stubs = [];
  const boxOf = {};
  let x = PAD;
  let bottom = HEAD_H;
  phases.forEach(function (p) {
    const mine = tasks.filter(function (t) {
      return phaseOf(t) === p.id;
    });
    const open = phaseOpen(p, o.open);
    const w = open ? COL_W : FOLD_W;
    const doing = mine.filter(function (t) {
      return statusOf(t, running, blocked) === "doing";
    }).length;
    const done = typeof p.done === "number" ? p.done : mine.filter(function (t) {
      return t.state === "done";
    }).length;
    const total = typeof p.total === "number" ? p.total : mine.length;
    const pct = total ? Math.round((done / total) * 100) : 0;
    const col = { id: p.id, name: p.name || p.id, state: p.state || "todo", x: x, w: w, open: open, done: done,
      total: total, pct: pct, doing: doing, now: p.id === nowId, cx: x + 12, cy: LINE_Y, shown: 0, hidden: 0 };
    cols.push(col);
    if (open) {
      let y = HEAD_H + cardGap;
      const shown = mine.filter(function (t) {
        const st = statusOf(t, running, blocked);
        return passes(st, o.status) && (!o.model || t.model === o.model);
      });
      const doneRows = shown.filter(function (t) {
        return t.state === "done";
      });
      const fold = doneRows.length > 0 && o.status !== "done" && !(o.showDone && o.showDone[p.id]);
      if (doneRows.length && o.status !== "done") {
        stubs.push({ id: "done:" + p.id, phase: p.id, x: x + (w - CARD_W) / 2, y: y, w: CARD_W, h: STUB_H,
          count: doneRows.length, open: !fold, cx: x + w / 2, cy: y + STUB_H / 2 });
        y += STUB_H + cardGap;
      }
      shown.forEach(function (t) {
        if (fold && t.state === "done") return;
        const c = { id: t.id, key: "task:" + t.id, phase: p.id, x: x + (w - CARD_W) / 2, y: y, w: CARD_W, h: CARD_H,
          status: statusOf(t, running, blocked), title: t.title || "", model: t.model || "",
          tokensK: typeof t.tokensK === "number" ? t.tokensK : null, running: !!running[t.id],
          needsUser: !!t.needsUser && t.state !== "done" };
        c.cx = c.x + c.w / 2;
        c.cy = c.y + c.h / 2;
        cards.push(c);
        boxOf[t.id] = c;
        y += CARD_H + cardGap;
      });
      col.shown = cards.filter(function (c) {
        return c.phase === p.id;
      }).length;
      col.hidden = mine.length - col.shown;
      bottom = Math.max(bottom, y);
    } else {
      col.hidden = mine.length;
    }
    x += w + colGap;
  });
  const edges = [];
  (Array.isArray(o.deps) ? o.deps : []).forEach(function (pair) {
    if (!Array.isArray(pair) || pair.length < 2) return;
    const a = boxOf[pair[0]];
    const b = boxOf[pair[1]];
    if (!a || !b || a === b) return;
    edges.push({ id: "dep:" + a.id + ">" + b.id, from: a.key, to: b.key, d: depPath(a, b) });
  });
  const width = Math.max(x - colGap + PAD, PAD * 2);
  const height = bottom + PAD;
  const first = cols[0];
  const last = cols[cols.length - 1];
  const nowCol = cols.find(function (c) {
    return c.now;
  });
  return {
    cols: cols, cards: cards, stubs: stubs, edges: edges, width: width, height: height,
    line: first ? { x1: first.cx, x2: last.cx, y: LINE_Y } : null,
    now: nowCol ? { phase: nowCol.id, x: nowCol.x - colGap / 2, cx: nowCol.cx, cy: LINE_Y } : null,
  };
}
