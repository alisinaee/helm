// Workflow (WP48, W2): the job spans and task edges of each project's snapshot (the workflow key, WP47), drawn as
// swimlanes (Timeline), a left-to-right flow of phase frames (Map) or one row per job (Table). layout() builds
// the model and the renderers return markup. Bars and cards carry data-focus (patch() restores focus with it) and
// data-lane / data-x, which the arrow keys use. Writes go through cmd.js. There are no inline handlers or styles:
// geometry is SVG attributes and colour comes from classes on the tokens.
//
// The view URL is #/p/<id>/workflow/<timeline|map|table>, the range is filter f=range:<2h|today|week|all>.

import { getJson } from "../api.js";
import { run } from "../cmd.js";
import { bannerHtml, chipHtml, emptyHtml, esc, setHtml, skeletonHtml } from "../dom.js";
import { MISSING, fmtDuration, fmtTokens } from "../format.js";
import { buildHash, currentRoute, projectHash } from "../router.js";
import { pageState } from "./inbox.js";

const LANE_H = 44;
const PLOT_W = 960;
const AXIS_H = 28;
const HOUR = 3600000;
const DAY = 24 * HOUR;
const RANGES = [["2h", "2 h"], ["today", "Today"], ["week", "Week"], ["all", "All"]];
const VIEWS = [["timeline", "Timeline"], ["map", "Map"], ["table", "Table"]];
const RANGE_STEP = { "2h": 1800000, today: 3 * HOUR, week: DAY, all: DAY };
const SCOPE_MAX = 8;
const FRESH_MS = 5000;
const QUEUE_W = 112;
const QUEUE_GAP = 8;
const OPEN_K = 0.75;
const TICK_MAX = 200;
const WORD = { running: "running", done: "done", failed: "failed" };
const CHIP = { doing: "neutral", done: "success", blocked: "danger", queued: "neutral" };
const DEFS = '<marker id="wf-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" ' +
  'orient="auto-start-reverse"><path class="wf-arrow" d="M0 0L8 4L0 8z"/></marker>' +
  '<pattern id="wf-hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">' +
  '<rect class="wf-hatch-bg" width="6" height="6"/><path class="wf-hatch-line" d="M0 0V6"/></pattern>';

const cache = new Map();
const bound = new WeakSet();
let lastModel = null;
let selectedKey = null;
let scrollLeft = 0;

function isObj(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function list(value) {
  return Array.isArray(value) ? value.filter(isObj) : [];
}

function spansOf(raw) {
  const wf = raw && raw.workflow;
  return wf && Array.isArray(wf.spans) ? wf.spans.filter(Array.isArray) : [];
}

function pairsOf(raw, name) {
  const wf = raw && raw.workflow;
  const edges = wf && wf.edges;
  return edges && Array.isArray(edges[name]) ? edges[name].filter(Array.isArray) : [];
}

function pad(n) {
  return n < 10 ? "0" + n : String(n);
}

function clock(ms) {
  const d = new Date(ms);
  return pad(d.getHours()) + ":" + pad(d.getMinutes());
}

function monthDay(ms) {
  const d = new Date(ms);
  return (d.getMonth() + 1) + "/" + d.getDate();
}

function clip(text, max) {
  const s = String(text || "");
  return s.length <= max ? s : s.slice(0, Math.max(1, max - 1)) + "…";
}

function phone() {
  return typeof window !== "undefined" && typeof window.matchMedia === "function" &&
    window.matchMedia("(max-width: 767px)").matches;
}

// The clock for rendering. Floored to 30 s so the markup changes at most twice a minute between polls.
function nowMs() {
  return Math.floor(Date.now() / 30000) * 30000;
}

// The lane of a job: the head (opus, or role head), a worker model lane, or other.
export function laneKeyOf(model, role) {
  if (model === "opus" || role === "head") return "head";
  if (model === "haiku" || model === "sonnet" || model === "agy") return model;
  return "other";
}

function statusOf(status) {
  if (status === "running") return "doing";
  if (status === "done") return "done";
  if (status === "failed") return "blocked";
  return "queued";
}

// The class of a task card from its state word (todo, doing, done, block, deferred and so on).
function cardClass(state) {
  if (state === "done") return "done";
  if (state === "doing" || state === "active" || state === "running") return "doing";
  if (state === "block" || state === "blocked") return "blocked";
  if (state === "deferred" || state === "defer") return "defer";
  return "todo";
}

// Snapshots are fetched by this view (normalizeSnapshot in state.js does not keep the workflow key). One request per
// project per FRESH_MS at most. The next app render picks up the result, so nothing here re-renders by itself.
function fetchSnapshot(pid) {
  const now = Date.now();
  const entry = cache.get(pid) || { raw: null, at: 0, error: null, pending: false };
  cache.set(pid, entry);
  if (entry.pending || now - entry.at < FRESH_MS) return;
  entry.pending = true;
  getJson("/api/v1/projects/" + encodeURIComponent(pid) + "/snapshot").then(function (res) {
    entry.raw = res.data || {};
    entry.error = null;
  }, function (err) {
    entry.error = err;
  }).then(function () {
    entry.at = Date.now();
    entry.pending = false;
  });
}

// The range window in ms. 2 h and Week end now; Today is the local day; All starts at the earliest job.
function windowOf(range, now, starts) {
  if (range === "2h") return { key: range, t0: now - 2 * HOUR, t1: now };
  if (range === "week") return { key: range, t0: now - 7 * DAY, t1: now };
  if (range === "today") {
    const d = new Date(now);
    const t0 = new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
    return { key: range, t0: t0, t1: t0 + DAY };
  }
  return { key: "all", t0: Math.min.apply(null, [now - 2 * HOUR].concat(starts)), t1: now };
}

// The model for one project (a raw snapshot) or for several (an array: one lane per project, the global view).
// Bars are jobs, queued tasks and blocked tasks; cards are the tasks for the Map; marks are task status times.
export function layout(snap, range, now) {
  const multi = Array.isArray(snap);
  const raws = (multi ? snap : [snap]).filter(isObj);
  const starts = [];
  raws.forEach(function (raw) {
    spansOf(raw).forEach(function (row) {
      starts.push(Number(row[5]) * 1000);
    });
  });
  const key = RANGES.some(function (r) {
    return r[0] === range;
  }) ? range : "today";
  const win = windowOf(key, now, starts);
  const t0 = win.t0;
  const t1 = win.t1;
  const projects = raws.map(function (raw, i) {
    const project = isObj(raw.project) ? raw.project : {};
    const pid = String(project.id || "project-" + (i + 1));
    return { pid: pid, name: String(project.title || project.id || pid), raw: raw };
  });
  const single = multi ? null : projects[0] || null;
  let total = 0;
  const jobs = [];
  projects.forEach(function (p) {
    const titles = new Map(list(p.raw.jobs).map(function (j) {
      return [String(j.id), String(j.title || "")];
    }));
    spansOf(p.raw).forEach(function (row) {
      total += 1;
      const start = Number(row[5]) * 1000;
      const end = row[6] == null ? null : Number(row[6]) * 1000;
      if ((end == null ? now : end) < t0 || start > t1) return;
      const model = row[2] ? String(row[2]) : "";
      const role = row[3] ? String(row[3]) : "";
      jobs.push({ pid: p.pid, pname: p.name, job: String(row[0]), task: row[1] ? String(row[1]) : null,
        model: model, role: role, parent: row[4] ? String(row[4]) : null, start: start, end: end,
        status: String(row[7] || ""), tokensK: row[8] == null ? null : Number(row[8]),
        title: titles.get(String(row[0])) || "", lane: multi ? p.pid : laneKeyOf(model, role) });
    });
  });

  const lanes = [];
  const laneAt = new Map();
  const addLane = function (laneKey, label, kind, pid) {
    laneAt.set(laneKey, lanes.length);
    lanes.push({ key: laneKey, label: label, kind: kind, pid: pid || null });
  };
  if (multi) {
    projects.forEach(function (p) {
      addLane(p.pid, p.name, "project", p.pid);
    });
  } else {
    addLane("head", "Head", "head");
    const used = new Set(jobs.map(function (j) {
      return j.lane;
    }));
    ["haiku", "sonnet", "agy", "other"].forEach(function (k) {
      if (used.has(k)) addLane(k, k, "model");
    });
    addLane("queue", "Queue", "queue");
    addLane("blocked", "Blocked", "blocked");
  }

  const items = [];
  const byJob = new Map();
  jobs.forEach(function (j) {
    const item = { key: "j:" + j.pid + ":" + j.job, kind: "job", pid: j.pid, pname: j.pname, job: j.job,
      task: j.task, model: j.model, role: j.role, parent: j.parent, lane: laneAt.get(j.lane), start: j.start,
      end: j.end, live: j.end == null, status: statusOf(j.status), word: WORD[j.status] || (j.status || "unknown"),
      tokensK: j.tokensK, title: j.title };
    items.push(item);
    byJob.set(j.pid + "|" + j.job, item);
  });

  const cards = [];
  const cardAt = new Map();
  const phases = [];
  const phaseAt = new Map();
  projects.forEach(function (p) {
    const phaseRows = list(p.raw.phases);
    phaseRows.forEach(function (ph) {
      const id = String(ph.id);
      const phase = { key: p.pid + ":" + id, pid: p.pid, label: (multi ? p.name + " · " : "") +
        String(ph.title || ph.name || id), approved: ph.approved === true, cards: [] };
      phases.push(phase);
      phaseAt.set(phase.key, phase);
    });
    list(p.raw.tasks).forEach(function (t) {
      if (!t.id) return;
      const phaseId = String(t.phase || "");
      const card = { key: "t:" + p.pid + ":" + t.id, kind: "task", pid: p.pid, pname: p.name, task: String(t.id),
        title: String(t.title || ""), phase: phaseId, state: String(t.state || "todo"), cls: cardClass(t.state),
        model: t.model ? String(t.model) : "", tokensK: t.tokensK == null ? null : Number(t.tokensK),
        at: isObj(t.at) ? t.at : {}, approved: false, job: null, jobKey: null };
      let phase = phaseAt.get(p.pid + ":" + phaseId);
      if (!phase) {
        phase = { key: p.pid + ":", pid: p.pid, label: (multi ? p.name + " · " : "") + "Other", approved: true,
          cards: [] };
        phaseAt.set(phase.key, phase);
        phases.push(phase);
      }
      card.approved = phase.approved;
      phase.cards.push(card);
      cards.push(card);
      cardAt.set(p.pid + "|" + card.task, card);
    });
  });
  const cardKeys = new Set(cards.map(function (c) {
    return c.key;
  }));
  items.forEach(function (it) {
    if (it.kind !== "job" || !it.live || !it.task) return;
    const card = cardAt.get(it.pid + "|" + it.task);
    if (card) {
      card.job = it.job;
      card.jobKey = it.key;
    }
  });
  const titleOf = function (pid, task) {
    const card = cardAt.get(pid + "|" + task);
    return card ? card.title : "";
  };

  if (single) {
    list(single.raw.queue).forEach(function (q, i) {
      if (!q.task) return;
      const task = String(q.task);
      items.push({ key: "q:" + single.pid + ":" + i, kind: "queue", pid: single.pid, pname: single.name, job: null,
        task: task, model: "", role: "", parent: null, lane: laneAt.get("queue"), start: null, end: null,
        live: false, status: "queued", word: "queued", tokensK: null, title: titleOf(single.pid, task), qi: i });
    });
    (Array.isArray(single.raw.blocked) ? single.raw.blocked : []).forEach(function (id) {
      if (typeof id !== "string" || !id) return;
      const task = id;
      const card = cardAt.get(single.pid + "|" + task);
      const at = card ? Date.parse(card.at.blocked || "") : NaN;
      const start = Number.isNaN(at) ? t0 : Math.max(t0, at);
      if (start > t1) return;
      items.push({ key: "b:" + single.pid + ":" + task, kind: "blocked", pid: single.pid, pname: single.name,
        job: null, task: task, model: "", role: "", parent: null, lane: laneAt.get("blocked"), start: start,
        end: now, live: false, status: "blocked", word: "blocked", tokensK: null, title: titleOf(single.pid, task) });
    });
  }
  const itemKeys = new Set(items.map(function (it) {
    return it.key;
  }));

  const marks = [];
  if (single) {
    cards.forEach(function (card) {
      ["doing", "done", "blocked"].forEach(function (st) {
        const at = Date.parse(card.at[st] || "");
        if (Number.isNaN(at) || at < t0 || at > t1) return;
        marks.push({ key: "m:" + card.pid + ":" + card.task + ":" + st, kind: "mark", pid: card.pid,
          task: card.task, status: st, lane: laneAt.get("head"), t: at,
          label: "Task " + card.task + (card.title ? " " + card.title : "") + " moved to " + st + " at " + clock(at) });
      });
    });
  }

  const edges = { handoff: [], after: [], block: [] };
  items.forEach(function (it) {
    if (it.kind !== "job" || !it.parent) return;
    const parent = byJob.get(it.pid + "|" + it.parent);
    if (parent) edges.handoff.push({ from: parent.key, to: it.key });
  });
  projects.forEach(function (p) {
    pairsOf(p.raw, "after").forEach(function (pair) {
      const a = "t:" + p.pid + ":" + pair[0];
      const b = "t:" + p.pid + ":" + pair[1];
      if (cardKeys.has(a) && cardKeys.has(b)) edges.after.push({ from: a, to: b });
    });
    pairsOf(p.raw, "block").forEach(function (pair) {
      const task = String(pair[1]);
      const card = cardAt.get(p.pid + "|" + task);
      if (!card) return;
      const blockKey = "b:" + p.pid + ":" + task;
      let latest = null;
      items.forEach(function (it) {
        if (it.kind === "job" && it.pid === p.pid && it.task === task && (!latest || it.start > latest.start)) {
          latest = it;
        }
      });
      edges.block.push({ issue: String(pair[0]), pid: p.pid, task: task, cardKey: card.key,
        blockKey: itemKeys.has(blockKey) ? blockKey : null, jobKey: latest ? latest.key : null });
    });
  });

  const byKey = new Map();
  items.forEach(function (it) {
    byKey.set(it.key, it);
  });
  cards.forEach(function (c) {
    byKey.set(c.key, c);
  });
  return { now: now, range: win, multi: multi, lanes: lanes, items: items, cards: cards, marks: marks,
    phases: phases, edges: edges, byKey: byKey, empty: total === 0,
    jobCount: items.filter(function (it) {
      return it.kind === "job";
    }).length };
}

function ticksOf(range) {
  const step = RANGE_STEP[range.key] || RANGE_STEP.today;
  const out = [];
  for (let t = Math.ceil(range.t0 / step) * step; t <= range.t1 && out.length < TICK_MAX; t += step) {
    out.push(t);
  }
  return out;
}

function tickText(t, key) {
  return key === "2h" || key === "today" ? clock(t) : monthDay(t);
}

function durationText(it, now) {
  if (it.kind !== "job") return MISSING;
  return fmtDuration(((it.end == null ? now : it.end) - it.start) / 1000);
}

function modelText(it) {
  if (it.kind !== "job") return MISSING;
  return (it.model || "model") + (it.role ? " · " + it.role : "");
}

function barTitle(it) {
  if (it.kind === "queue") return "Task " + it.task + " queued, waiting for agent";
  if (it.kind === "blocked") return "Task " + it.task + " blocked since " + clock(it.start);
  const who = "Job " + it.job + " " + (it.model || "model") + (it.role ? " " + it.role : "") +
    (it.task ? ", task " + it.task : "");
  const when = clock(it.start) + "–" + (it.end == null ? "now" : clock(it.end));
  const tokens = it.tokensK == null ? "unknown token count" : fmtTokens(it.tokensK) + " tokens";
  const pre = it.pname && it.pname !== it.pid ? it.pname + ": " : "";
  return pre + who + ", " + it.word + ", " + when + ", " + tokens;
}

function hashFor(route, view, range, item) {
  const filters = Object.assign({}, route.filters || {});
  filters.f = "range:" + range;
  return buildHash({ name: route.name, id: route.id, section: "workflow", view: view, item: item || null,
    filters: filters });
}

// The view of the route. The Map is the default for a project at 768 px and wider; the phone default is the Table.
function viewOf(route) {
  if (VIEWS.some(function (v) {
    return v[0] === route.view;
  })) return route.view;
  if (phone()) return "table";
  return route.name === "project" ? "map" : "timeline";
}


function rangeOf(route) {
  const f = route.filters && route.filters.f ? String(route.filters.f) : "";
  const m = /(?:^|,)range:(2h|today|week|all)(?:,|$)/.exec(f);
  return m ? m[1] : "today";
}

// The hash that opens an item's Details: the task in its project's Workflow view.
function itemHref(model, pid, task) {
  const route = model.route || { filters: {} };
  return buildHash({ name: "project", id: pid, section: "workflow", view: model.view || null, item: task,
    filters: Object.assign({}, route.filters || {}) });
}

function laneLabelHtml(lane) {
  return '<div class="wf-lbl" title="' + esc(lane.label) + '"><span class="wf-sw wf-sw-' + esc(lane.kind === "model" ?
    lane.key : lane.kind) + '" aria-hidden="true"></span><span>' + esc(lane.label) + "</span></div>";
}

function gutterHtml(model) {
  return model.lanes.map(function (lane, i) {
    const mine = model.items.filter(function (it) {
      return it.kind === "job" && it.lane === i;
    });
    const known = mine.filter(function (it) {
      return it.tokensK != null;
    });
    const sum = known.reduce(function (acc, it) {
      return acc + it.tokensK;
    }, 0);
    return '<div class="wf-g"><span class="num wf-gn">' + mine.length + '</span><span class="num wf-gt">' +
      esc(known.length ? fmtTokens(sum) : MISSING) + "</span></div>";
  }).join("");
}

function barHtml(it, g, now) {
  const w = Math.max(6, g.x1 - g.x0);
  const y = g.cy - 13;
  const label = it.kind === "job" ? (it.task ? it.task + " " : "") + (it.title || it.job) : it.task || "";
  const title = barTitle(it);
  const live = it.live ? '<rect class="wf-pulse" x="' + (g.x1 - 3) + '" y="' + y + '" width="3" height="26"/>' : "";
  return '<g class="wf-bar wf-b-' + esc(it.status) + (it.live ? " wf-live" : "") + '" tabindex="0" role="button" ' +
    'aria-label="' + esc(title) + '" data-focus="' + esc(it.key) + '" data-wf-item="' + esc(it.key) +
    '" data-wf-task="' + esc(it.task || "") + '" data-wf-pid="' + esc(it.pid) + '" data-lane="' + esc(g.lane) +
    '" data-x="' + g.x0 + '" data-y="' + g.cy + '"><title>' + esc(title) + '</title><rect x="' + g.x0 + '" y="' + y +
    '" width="' + w + '" height="26" rx="4"/>' + live + '<text x="' + (g.x0 + 6) + '" y="' + (g.cy + 4) + '">' +
    esc(clip(label, Math.floor((w - 10) / 6.6))) + "</text></g>";
}

// The Timeline: a fixed label column, the swimlane plot (one SVG, so arrows can cross lanes) and a fixed gutter.
export function timelineSvg(model) {
  const r = model.range;
  const span = r.t1 - r.t0 || 1;
  const X = function (t) {
    return Math.min(PLOT_W, Math.max(0, ((t - r.t0) / span) * PLOT_W));
  };
  const H = model.lanes.length * LANE_H;
  const xNow = X(model.now);
  const geo = new Map();
  let queued = 0;
  model.items.forEach(function (it) {
    const lane = it.lane;
    const cy = lane * LANE_H + LANE_H / 2;
    let x0;
    let x1;
    if (it.kind === "queue") {
      x0 = Math.min(xNow + QUEUE_GAP + queued * (QUEUE_W + QUEUE_GAP), PLOT_W - QUEUE_W);
      queued += 1;
      x1 = x0 + QUEUE_W;
    } else {
      x0 = Math.min(X(it.start), PLOT_W - 6);
      x1 = Math.min(PLOT_W, Math.max(X(it.end == null ? model.now : it.end), x0 + 6));
    }
    geo.set(it.key, { x0: x0, x1: x1, cy: cy, lane: lane });
  });
  const bg = model.lanes.map(function (lane, i) {
    return '<rect class="wf-lane' + (i % 2 ? " wf-lane-alt" : "") + '" x="0" y="' + i * LANE_H + '" width="' +
      PLOT_W + '" height="' + LANE_H + '"/>';
  }).join("");
  const grid = ticksOf(r).map(function (t) {
    return '<line class="wf-tickline" x1="' + X(t) + '" y1="0" x2="' + X(t) + '" y2="' + H + '"/>';
  }).join("");
  const ticks = ticksOf(r).map(function (t) {
    const x = Math.min(PLOT_W - 16, Math.max(16, X(t)));
    return '<text class="wf-tick" x="' + x + '" y="' + (AXIS_H - 8) + '" text-anchor="middle">' +
      esc(tickText(t, r.key)) + "</text>";
  }).join("");
  const paths = [];
  model.edges.handoff.forEach(function (e) {
    const p = geo.get(e.from);
    const c = geo.get(e.to);
    if (!p || !c) return;
    const sx = Math.min(Math.max(c.x0, p.x0), p.x1);
    const mid = (p.cy + c.cy) / 2;
    paths.push('<path class="wf-edge wf-e-handoff" d="M ' + sx + " " + p.cy + " C " + sx + " " + mid + ", " +
      (c.x0 - 10) + " " + mid + ", " + c.x0 + " " + c.cy + '" marker-end="url(#wf-arrow)"/>');
  });
  model.edges.block.forEach(function (e) {
    const b = e.blockKey ? geo.get(e.blockKey) : null;
    const j = e.jobKey ? geo.get(e.jobKey) : null;
    if (!b || !j) return;
    paths.push('<path class="wf-edge wf-e-block" d="M ' + b.x0 + " " + b.cy + " C " + (b.x0 - 12) + " " + b.cy +
      ", " + (j.x0 - 12) + " " + j.cy + ", " + j.x0 + " " + j.cy + '" marker-end="url(#wf-arrow)"/>');
  });
  const bars = model.items.map(function (it) {
    return barHtml(it, geo.get(it.key), model.now);
  }).join("");
  const marks = model.marks.map(function (m) {
    const x = X(m.t);
    const cy = m.lane * LANE_H + LANE_H / 2;
    return '<g class="wf-mark wf-m-' + esc(m.status) + '" role="img" aria-label="' + esc(m.label) + '"><title>' +
      esc(m.label) + '</title><path d="M ' + x + " " + (cy - 6) + " L " + (x + 6) + " " + cy + " L " + x + " " +
      (cy + 6) + " L " + (x - 6) + " " + cy + ' Z"/></g>';
  }).join("");
  const plot = '<svg class="wf-plot" width="' + PLOT_W + '" height="' + H + '" viewBox="0 0 ' + PLOT_W + " " + H +
    '" role="group" aria-label="Swimlanes">' + bg + grid + paths.join("") + bars + marks +
    '<line class="wf-now" x1="' + xNow + '" y1="0" x2="' + xNow + '" y2="' + H + '"/></svg>';
  const axis = '<svg class="wf-axis" width="' + PLOT_W + '" height="' + AXIS_H + '" viewBox="0 0 ' + PLOT_W + " " +
    AXIS_H + '" aria-hidden="true" focusable="false"><defs>' + DEFS + "</defs>" + ticks +
    '<text class="wf-now-t" x="' + xNow + '" y="10" text-anchor="middle">now</text></svg>';
  const labels = model.lanes.map(laneLabelHtml).join("");
  return '<div class="wf-scroll"><div class="wf-grid">' + '<div class="wf-corner"></div>' + axis +
    '<div class="wf-g wf-corner wf-gh"><span class="wf-gn">Jobs</span><span class="wf-gt">Tokens</span></div>' +
    '<div class="wf-labels">' + labels + "</div>" + plot + '<div class="wf-gutters">' + gutterHtml(model) +
    "</div></div></div>";
}

// The Map (WP72). R7.14 E: the left-to-right flow of graph/model.js, laid out by flowLayout() in graph/layout.js
// and drawn by graph/render.js. The minimap (graph/minimap.js) sits in the stage corner above 640 px; at 640 px and
// below, the phase chips are the overview instead. The four graph modules load on the first visit to the Map, so no
// other view requests them. mapSvg() returns the controls and an empty host; mountMaps() puts the SVG in the host
// after the patch.
// Map state rides in the f param as st:, ag:, ph:, all: and x: tokens (the router keeps only f and g), with "|" between
// the values of one token. x: lists the phases the reader opened (+id) or closed (-id); a done phase starts closed.
const MAP_STATUS = ["doing", "blocked", "todo", "done", "defer"];
const MAP_AGENT = ["opus", "sonnet", "haiku", "agy"];
const NARROW_Q = "(max-width: 640px)";
const mapStates = new Map();
let graphKit = null;
let graphFailed = false;
let loadingGraph = false;
let pendingMap = null;
let activeMap = null;
let lastView = null;
let mapKinds = null;
let mapHasNow = false;

function mapStateFor(pid) {
  let st = mapStates.get(pid);
  if (!st) {
    st = { view: null, fitted: false, focus: null, taps: { last: null } };
    mapStates.set(pid, st);
  }
  return st;
}

// The graph modules are imported once. A synthetic hashchange then makes the app re-render the section.
function loadGraph() {
  if (graphKit || graphFailed || loadingGraph) return;
  loadingGraph = true;
  Promise.all([import("../graph/model.js"), import("../graph/layout.js"), import("../graph/render.js"),
    import("../graph/minimap.js")]).then(function (mods) {
    graphKit = { model: mods[0], layout: mods[1], render: mods[2], minimap: mods[3] };
    loadingGraph = false;
    if (typeof window !== "undefined") window.dispatchEvent(new Event("hashchange"));
  }, function () {
    graphFailed = true;
    loadingGraph = false;
    if (typeof window !== "undefined") window.dispatchEvent(new Event("hashchange"));
  });
}

function narrow() {
  return typeof window !== "undefined" && typeof window.matchMedia === "function" &&
    window.matchMedia(NARROW_Q).matches;
}

function mapOpts(route) {
  const out = {};
  const f = route.filters && route.filters.f ? String(route.filters.f) : "";
  f.split(",").forEach(function (tok) {
    const m = /^(st|ag|ph|all|x):(.*)$/.exec(tok);
    if (m) out[m[1]] = m[2];
  });
  return out;
}

function mapList(value) {
  return value ? String(value).split("|").filter(function (s) {
    return s !== "";
  }) : [];
}

// The phases the reader opened (+id) or closed (-id) through x:.
function foldsOf(value) {
  const out = { open: [], shut: [] };
  mapList(value).forEach(function (tok) {
    if (tok.charAt(0) === "+") out.open.push(tok.slice(1));
    else if (tok.charAt(0) === "-") out.shut.push(tok.slice(1));
  });
  return out;
}

function countOf(graph) {
  return graph.nodes.filter(function (n) {
    return n.type !== "phase";
  }).length;
}

// The hash of the Map with some map options changed (a value of "" removes the option).
function mapHash(route, range, changes) {
  const opts = Object.assign(mapOpts(route), changes);
  const parts = ["range:" + range];
  Object.keys(opts).forEach(function (k) {
    if (opts[k]) parts.push(k + ":" + opts[k]);
  });
  const filters = Object.assign({}, route.filters || {}, { f: parts.join(",") });
  return buildHash({ name: route.name, id: route.id, section: "workflow", view: "map", filters: filters });
}

function toggled(list, value) {
  return list.indexOf(value) < 0 ? list.concat([value]) : list.filter(function (v) {
    return v !== value;
  });
}

function chipsHtml(route, range, label, key, values, selected) {
  const chips = values.map(function (v) {
    const on = selected.indexOf(v) >= 0;
    const change = {};
    change[key] = toggled(selected, v).join("|");
    return '<a class="wfg-chip" href="' + esc(mapHash(route, range, change)) + '"' +
      (on ? ' aria-current="true"' : "") + ">" + esc(v) + "</a>";
  }).join("");
  return '<div class="wfg-chips" role="group" aria-label="' + esc(label) + '"><span class="wfg-chips-lbl">' +
    esc(label) + "</span>" + chips + "</div>";
}

function ctlHtml(label, op, text, pressed) {
  const press = pressed === undefined ? "" : ' aria-pressed="' + (pressed ? "true" : "false") + '"';
  return '<button type="button" class="btn btn-small" data-wf-map-op="' + op + '" aria-label="' + esc(label) +
    '"' + press + ">" + esc(text) + "</button>";
}

function frameOf(id) {
  const frames = activeMap && activeMap.flow ? activeMap.flow.frames || [] : [];
  return frames.find(function (f) {
    return f.id === id;
  }) || null;
}

// Opens or closes one phase frame. The choice goes to x: in the hash, so a reload keeps it.
function toggleFrame(id) {
  const f = frameOf(id);
  if (!f) return;
  const route = currentRoute();
  const keep = mapList(mapOpts(route).x).filter(function (tok) {
    return tok.slice(1) !== f.lane;
  });
  keep.push((f.collapsed ? "+" : "-") + f.lane);
  window.location.hash = mapHash(route, rangeOf(route), { x: keep.join("|") });
}

function toggleAll() {
  const route = currentRoute();
  const on = mapOpts(route).all === "1";
  window.location.hash = mapHash(route, rangeOf(route), { all: on ? "" : "1" });
}

// The phase chips of the narrow layout centre the view on their frame. The view keeps its zoom.
function centerFrame(id) {
  const f = frameOf(id);
  if (f && activeMap) activeMap.api.centerOn({ x: f.x + f.w / 2, y: f.y + f.h / 2 }, false);
}

function mapOp(op) {
  if (!activeMap) return;
  const api = activeMap.api;
  if (op === "out") api.zoom(0.8);
  else if (op === "in") api.zoom(1.25);
  else if (op === "fit") api.fit();
  else if (op === "now") api.centerOn("now", false);
  else if (op === "start") api.centerOn("start", false);
  else if (op === "all") toggleAll();
  else if (op === "focus-off") setFocus(activeMap.pid, null);
}

// Focus mode: the closure of the node is drawn at full strength, the rest dims. Classes only; no re-render.
function syncFocus(pid, key, graph) {
  if (!activeMap || activeMap.pid !== pid || !graphKit) return;
  activeMap.focus = key;
  if (graph) activeMap.graph = graph;
  graphKit.render.applyFocus(activeMap.svg, graphKit.render.closureOf(activeMap.graph, key), key);
}

function setFocus(pid, key) {
  mapStateFor(pid).focus = key;
  syncFocus(pid, key, null);
}

function mapSvg(kit, ctx) {
  const route = ctx.route;
  const range = ctx.range;
  const opts = mapOpts(route);
  const showAll = opts.all === "1";
  const folds = foldsOf(opts.x);
  const st = mapStateFor(ctx.pid);
  pendingMap = null;
  const all = kit.model.buildGraph(ctx.raw, { expand: true });
  const total = countOf(all);
  if (!total) {
    return emptyHtml("No tasks or jobs yet.", "<span>Agents record work with <code class=\"code\">roadmap job start" +
      '</code>.</span> <a href="' + esc(projectHash(ctx.pid, "agents")) + '">Open Agents</a>');
  }
  // With no filter the filtered graph is the expanded one, so it is built once; a filter needs its own build.
  const filtered = mapList(opts.st).length + mapList(opts.ag).length + mapList(opts.ph).length > 0;
  const graph = filtered ? kit.model.buildGraph(ctx.raw, { status: mapList(opts.st), agent: mapList(opts.ag),
    phase: mapList(opts.ph), expand: true }) : all;
  const matched = countOf(graph);
  const flow = kit.layout.flowLayout(graph, { expandAll: showAll, open: folds.open, close: folds.shut });
  const shown = graph.nodes.filter(function (n) {
    return n.type !== "phase" && flow.boxes[n.id];
  }).length;
  // The legend lists the edge kinds this flow actually draws (a route exists and both ends are on screen).
  mapKinds = new Set();
  graph.edges.concat(graph.sequence || []).forEach(function (e) {
    if (flow.routes && flow.routes[e.id]) mapKinds.add(e.type);
  });
  mapHasNow = !!(flow.now && flow.now.flag);
  const phases = all.lanes.map(function (l) {
    return l.id;
  });
  const filters = '<div class="wfg-chips-row">' +
    chipsHtml(route, range, "Status", "st", MAP_STATUS, mapList(opts.st)) +
    chipsHtml(route, range, "Agent", "ag", MAP_AGENT, mapList(opts.ag)) +
    chipsHtml(route, range, "Phase", "ph", phases, mapList(opts.ph)) + "</div>";
  const count = '<div class="wfg-bar"><span class="wfg-count" aria-live="polite">' + matched + " of " + total +
    " items</span></div>";
  if (!matched) {
    return count + filters + '<p class="wf-hint">No tasks match these filters.<a href="' +
      esc(mapHash(route, range, { st: "", ag: "", ph: "" })) + '">Clear filters</a></p>';
  }
  // Folded phases hide their tasks: the note says how many are drawn, and Show all draws every phase (slow).
  const note = matched > shown && !showAll
    ? '<p class="wfg-note">Showing ' + shown + " of " + matched + " items" +
      (flow.capped ? " (the view caps at " + flow.cap + ")" : "") + ". Expand phases to see the rest. " +
      '<a href="' + esc(mapHash(route, range, { all: "1" })) + '">Show all (slow)</a></p>' : "";
  const crumbs = narrow() ? '<nav class="wfg-chips" aria-label="Phases">' + (flow.frames || []).map(function (f) {
    const nb = flow.now && flow.now.box;
    const here = !!nb && nb.x >= f.x && nb.x < f.x + f.w;
    return '<button type="button" class="wfg-chip" data-wf-frame="' + esc(f.id) + '"' +
      (here ? ' aria-current="true"' : "") + ">" +
      esc(f.label && f.label !== f.lane ? f.lane + " " + f.label : f.lane) + " " + f.done + "/" + f.total +
      "</button>";
  }).join("") + "</nav>" : "";
  const ctl = '<div class="wfg-ctl" role="toolbar" aria-label="Diagram controls">' +
    ctlHtml("Zoom out", "out", "−") + ctlHtml("Zoom in", "in", "+") + ctlHtml("Fit to screen", "fit", "Fit") +
    ctlHtml("Centre on Now (N)", "now", "Now") + ctlHtml("Go to Start (S)", "start", "Start") +
    ctlHtml("Show all phases", "all", "Show all", showAll) + ctlHtml("Clear focus", "focus-off", "Reset focus") +
    "</div>";
  // Focus mode lasts while its node's Details is open: Escape goes back to Projects (panel.js), which drops it here.
  st.focus = route.item ? st.focus : null;
  if (activeMap && activeMap.focus !== st.focus) syncFocus(ctx.pid, st.focus, graph);
  pendingMap = { graph: graph, flow: flow, lay: flow, pid: ctx.pid, focus: st.focus, view: st.view,
    taps: st.taps,
    onTap: function (node) {
      const fold = node.getAttribute("data-wf-fold");
      if (fold) {
        toggleFrame(fold);
        return;
      }
      const key = node.getAttribute("data-wf-item");
      if (key.indexOf("phase:") === 0) {
        toggleFrame(key);
        return;
      }
      setFocus(ctx.pid, key);
      navigate(node);
    },
    onClear: function () {
      setFocus(ctx.pid, null);
      const fold = activeMap ? activeMap.fold : null;
      if (activeMap) activeMap.fold = null;
      if (fold) toggleFrame(fold);
    },
    onView: function (v) {
      mapStateFor(ctx.pid).view = v;
    } };
  return count + filters + note + crumbs + '<div class="wfg-stage">' + ctl +
    '<div class="wfg-host" data-wf-map-host></div></div>';
}

// Opens the map centred on Now, fitted to its height but never below OPEN_K (so the card titles stay readable). Later
// renders keep the reader's own zoom and pan.
function openAtNow(api, flow) {
  const k = Math.min(1, Math.max(OPEN_K, (api.size().h - 32) / Math.max(1, flow.height)));
  api.zoom(k / api.view().k);
  api.centerOn("now", true);
}

// Puts the pending diagram into the host the last patch rendered, with the minimap beside it. Runs after every patch.
function mountMaps() {
  if (!pendingMap || !graphKit || typeof document === "undefined") return;
  const host = document.querySelector("[data-wf-map-host]");
  if (!host || host.firstChild) return;
  const st = pendingMap;
  pendingMap = null;
  const store = mapStateFor(st.pid);
  const opening = !store.fitted;
  store.fitted = true;
  if (activeMap && activeMap.mini) activeMap.mini.stop();
  // The old viewport stops first (its glide may still write a view); then the live view is read, not the one the
  // render captured.
  if (activeMap && activeMap.api) activeMap.api.destroy();
  const view = opening ? undefined : store.view;
  const api = graphKit.render.mountMap(host, Object.assign({}, st, { fit: false, view: view }));
  activeMap = { pid: st.pid, api: api, graph: st.graph, flow: st.flow, svg: host.querySelector("svg"),
    focus: st.focus, fold: null, mini: null };
  if (opening) openAtNow(api, st.flow);
  host.addEventListener("pointerdown", function (e) {
    const fold = closestEl(e.target, "[data-wf-fold]");
    if (activeMap) activeMap.fold = fold ? fold.getAttribute("data-wf-fold") : null;
  });
  host.addEventListener("pointerup", function () {
    if (activeMap) activeMap.fold = null;
  });
  if (!narrow()) activeMap.mini = graphKit.minimap.mountMinimap(host.parentNode, { flow: st.flow, viewport: api });
}

function mapBody(route, raw, range) {
  mapKinds = null;
  mapHasNow = false;
  if (route.name !== "project") {
    return '<p class="wf-hint">Select a project to view diagram.</p>';
  }
  if (graphFailed) return bannerHtml("danger", "Diagram failed to load.", "");
  if (!graphKit) {
    loadGraph();
    return '<div aria-busy="true">' + skeletonHtml(["w-60", "w-90"]) + "</div>";
  }
  return mapSvg(graphKit, { pid: route.id, raw: raw, route: route, range: range, now: nowMs() });
}

function statusChip(word, status) {
  return chipHtml(word, CHIP[status] || "neutral");
}

function actionHtml(it, model) {
  if (it.kind !== "job" || !it.task) return MISSING;
  if (it.live) {
    return '<button type="button" class="btn btn-small" data-wf-op="task.stop" data-wf-pid="' + esc(it.pid) +
      '" data-wf-task="' + esc(it.task) + '" aria-label="Stop task ' + esc(it.task) + '">Stop</button>';
  }
  return '<a class="btn btn-small" href="' + esc(itemHref(model, it.pid, it.task)) + '" aria-label="Open task ' +
    esc(it.task) + '">Open</a>';
}

// The Table: one row per job bar, with the same tracks as the detail strip (.wf-cols and .row-grid).
export function tableHtml(model) {
  const rows = model.items.filter(function (it) {
    return it.kind === "job";
  });
  const head = "<tr><th scope=\"col\">Status</th><th scope=\"col\">Job</th><th scope=\"col\">Task</th>" +
    "<th scope=\"col\">Model</th><th scope=\"col\" class=\"rg-num\">Start</th><th scope=\"col\" class=\"rg-num\">" +
    "Duration</th><th scope=\"col\" class=\"rg-num\">Tokens (thousands)</th><th scope=\"col\">Action</th></tr>";
  const body = rows.map(function (it) {
    const task = it.task ? esc(it.task) + (model.multi ? " · " + esc(it.pname) : "") : MISSING;
    return "<tr>" + "<td>" + statusChip(it.word, it.status) + "</td>" + '<td class="wf-id">' + esc(it.job) + "</td>" +
      "<td>" + task + "</td>" + "<td>" + esc(modelText(it)) + "</td>" +
      '<td class="rg-num num">' + clock(it.start) + "</td>" +
      '<td class="rg-num num">' + esc(durationText(it, model.now)) + "</td>" +
      '<td class="rg-num num">' + esc(it.tokensK == null ? MISSING : fmtTokens(it.tokensK)) + "</td>" +
      "<td>" + actionHtml(it, model) + "</td></tr>";
  }).join("");
  return '<div class="wf-scroll"><table class="wf-table"><caption class="sr-only">Jobs in this range</caption>' +
    "<thead>" + head + "</thead><tbody>" + body + "</tbody></table></div>";
}

// The detail strip for the selected bar, card or mark. Its tracks are the same as the Table's.
function detailHtml(model, key) {
  const it = key && model ? model.byKey.get(key) : null;
  if (!it) {
    return '<span class="wf-hint">Select an item to view details.</span>';
  }
  if (it.kind === "task") {
    const approve = it.approved ? "" : '<a class="btn btn-small" href="' + esc(projectHash(it.pid, "roadmap")) + '">' +
      "Approve in Roadmap</a>";
    const start = it.cls === "todo" && it.approved
      ? '<button type="button" class="btn btn-small btn-primary" data-wf-op="task.start" data-wf-pid="' +
        esc(it.pid) + '" data-wf-task="' + esc(it.task) + '" aria-label="Start task ' +
        esc(it.task) + '">Start</button>'
      : approve || MISSING;
    return statusChip(it.state, it.cls === "todo" ? "queued" : it.cls === "doing" ? "doing" : it.cls === "done"
      ? "done" : "blocked") + '<span class="wf-id">' + esc(it.job || MISSING) + "</span>" +
      "<span>" + esc(it.task) + "</span><span>" + esc(it.model || MISSING) + "</span>" +
      '<span class="rg-num num">' + esc(it.at.doing ? clock(Date.parse(it.at.doing)) : MISSING) + "</span>" +
      '<span class="rg-num num">' + MISSING + "</span>" +
      '<span class="rg-num num">' + esc(it.tokensK == null ? MISSING : fmtTokens(it.tokensK)) + "</span>" + start;
  }
  const kind = it.kind === "job" ? it.status : it.status;
  const action = it.kind === "job" && it.task ? (it.live
    ? '<button type="button" class="btn btn-small" data-wf-op="task.stop" data-wf-pid="' + esc(it.pid) +
      '" data-wf-task="' + esc(it.task) + '" aria-label="Stop task ' + esc(it.task) + '">Stop</button>'
    : '<a class="btn btn-small" href="' + esc(itemHref(model, it.pid, it.task)) + '">Open</a>')
    : it.task ? '<a class="btn btn-small" href="' + esc(itemHref(model, it.pid, it.task)) + '">Open</a>' : MISSING;
  return statusChip(it.word, kind) + '<span class="wf-id">' + esc(it.job || MISSING) + "</span>" +
    "<span>" + esc(it.task || MISSING) + "</span><span>" + esc(modelText(it)) + "</span>" +
    '<span class="rg-num num">' + (it.start == null ? MISSING : clock(it.start)) + "</span>" +
    '<span class="rg-num num">' + esc(durationText(it, model.now)) + "</span>" +
    '<span class="rg-num num">' + esc(it.tokensK == null ? MISSING : fmtTokens(it.tokensK)) + "</span>" + action;
}

function viewLinks(route, view, range) {
  return VIEWS.map(function (v) {
    const on = v[0] === view;
    return '<a href="' + esc(hashFor(route, v[0], range, null)) + '"' + (on ? ' aria-current="page"' : "") + ">" +
      esc(v[1]) + "</a>";
  }).join("");
}

function rangeLinks(route, view, range) {
  return RANGES.map(function (r) {
    const on = r[0] === range;
    return '<a href="' + esc(hashFor(route, view, r[0], null)) + '"' + (on ? ' aria-current="page"' : "") + ">" +
      esc(r[1]) + "</a>";
  }).join("");
}

function mapKey(cls) {
  return '<svg class="wf-edge-svg" width="22" height="8" viewBox="0 0 22 8" aria-hidden="true" focusable="false">' +
    '<path class="' + cls + '" d="M1 4H21"/></svg>';
}

function keyItem(key, text) {
  return "<li>" + key + esc(text) + "</li>";
}

// The legend names only what is drawn. The Map shows the edge kinds it drew (kinds) and the Now flag when it has one;
// the Timeline draws handoff and blocker bars; the Table draws only the status words, so it gets the status keys.
function legendHtml(view, kinds, hasNow) {
  const dot = function (cls) {
    return '<span class="wf-key ' + cls + '" aria-hidden="true"></span>';
  };
  const states = [keyItem(dot("wf-k-done"), "Done"), keyItem(dot("wf-k-doing"), "Running"),
    keyItem(dot("wf-k-blocked"), "Blocked or failed"),
    keyItem(dot("wf-k-queued"), view === "map" ? "Todo" : "Queued")];
  let extra = [];
  if (view === "map") {
    const names = [["sequence", "Sequence", "wfg-e"], ["dependency", "Dependency", "wfg-e wfg-e-dependency"],
      ["handoff", "Handoff", "wfg-e wfg-e-handoff"], ["blocker", "Blocker", "wfg-e wfg-e-blocker"]];
    extra = names.filter(function (n) {
      return kinds && kinds.has(n[0]);
    }).map(function (n) {
      return keyItem(mapKey(n[2]), n[1]);
    });
    if (hasNow) extra.push(keyItem(dot("wf-k-doing"), "You are here (Now)"));
  } else if (view === "timeline") {
    extra = [keyItem('<span class="wf-edge-key wf-e-handoff" aria-hidden="true"></span>', "Handoff"),
      keyItem('<span class="wf-edge-key wf-e-block" aria-hidden="true"></span>', "Blocker")];
  }
  return '<ul class="wf-legend" id="wf-legend" aria-label="Legend">' + states.concat(extra).join("") + "</ul>";
}

export function sectionView(vm) {
  const state = pageState(vm);
  if (state) return state;
  const route = vm.route;
  const pids = route.name === "project" ? [route.id] : (vm.projects || []).slice(0, SCOPE_MAX).map(function (p) {
    return p.id;
  });
  pids.forEach(function (pid) {
    fetchSnapshot(pid);
  });
  const entries = pids.map(function (pid) {
    return cache.get(pid);
  }).filter(function (e) {
    return e && e.raw;
  });
  if (!entries.length) {
    const failed = pids.map(function (pid) {
      return cache.get(pid);
    }).find(function (e) {
      return e && e.error;
    });
    if (failed) {
      return bannerHtml("danger", "Could not load the workflow. Retrying.", failed.error.message || "Unknown error");
    }
    return '<div aria-busy="true">' + skeletonHtml(["w-60", "w-90"]) + "</div>";
  }
  const range = rangeOf(route);
  const view = viewOf(route);
  // Entering the Map from another view opens it again at Now; re-renders of the Map keep the reader's view.
  if (view === "map" && lastView !== "map" && route.name === "project") mapStateFor(route.id).fitted = false;
  lastView = view;
  const raws = entries.map(function (e) {
    return e.raw;
  });
  // The Map draws from graph/model.js, so it skips the Timeline model; only its view, route and empty flags are kept.
  const model = view === "map" ? { empty: false, jobCount: 0, byKey: new Map() }
    : layout(route.name === "project" ? raws[0] : raws, range, nowMs());
  model.view = view;
  model.route = route;
  lastModel = model;
  const head = '<div class="page-head"><h2 class="page-title">Workflow</h2><p class="page-note">Live. ' +
    (view === "map" ? "Tasks flow left to right from Start to Now, one frame per phase. Select a task to see its " +
      "details." : "Each bar is a job from start to end, in lanes by role and model. Hover or focus a bar for its " +
      "details, and press Enter to open its task.") + "</p></div>";
  const controls = '<div class="wf-controls"><nav class="seg plan-views" aria-label="View">' +
    viewLinks(route, view, range) +
    '</nav><nav class="seg plan-views" aria-label="Range">' + rangeLinks(route, view, range) + "</nav></div>";
  let body;
  if (model.empty && view !== "map") {
    const agents = route.name === "project" ? projectHash(route.id, "agents") : "#/all/agents";
    body = emptyHtml("No jobs recorded yet.", "<span>Agents record work with <code class=\"code\">roadmap job start" +
      '</code>.</span> <a href="' + esc(agents) + '">Open Agents</a>');
  } else if (view === "table") {
    body = model.jobCount ? tableHtml(model) : '<p class="wf-hint">No jobs in this range.</p>';
  } else if (view === "map") {
    body = mapBody(route, raws[0], range);
  } else {
    body = (model.jobCount ? "" : '<p class="wf-hint">No jobs in this range.</p>') + timelineSvg(model);
  }
  return '<div class="wf-page">' + head + controls + '<div class="wf" data-wf-view="' + esc(view) + '">' + body +
    // The Map has no strip: a tap opens the right panel's Details (navigate), so a strip would repeat it.
    (view === "map" ? "" : '<div class="wf-detail row-grid wf-cols">' + detailHtml(model, selectedKey) + "</div>") +
    legendHtml(view, mapKinds, mapHasNow) +
    "</div></div>";
}

// Operations from the strip or a row: Stop a running job's task, Start a todo task. Both go through cmd.js.
function runOp(el) {
  const op = el.getAttribute("data-wf-op");
  const task = el.getAttribute("data-wf-task");
  if (!op || !task) return;
  const pid = el.getAttribute("data-wf-pid");
  const label = (op === "task.stop" ? "Stop requested for " : "Start requested for ") + task;
  run(op, { id: task }, { project: pid, label: label });
}

// Details for an item: the task in its project's Workflow view, so the right panel opens on Details.
function navigate(el) {
  const task = el.getAttribute("data-wf-task");
  const pid = el.getAttribute("data-wf-pid");
  if (!task || !pid) return;
  const route = currentRoute();
  const view = lastModel && lastModel.view ? lastModel.view : route.view;
  window.location.hash = buildHash({ name: "project", id: pid, section: "workflow", view: view, item: task,
    filters: route.filters || {} });
}

function closestEl(target, selector) {
  return target && typeof target.closest === "function" ? target.closest(selector) : null;
}

function select(e) {
  const el = closestEl(e.target, "[data-wf-item]");
  if (!el || !lastModel || lastModel.view === "map") return;
  const key = el.getAttribute("data-wf-item");
  if (key === selectedKey) return;
  selectedKey = key;
  const strip = closestEl(el, ".wf");
  const detail = strip ? strip.querySelector(".wf-detail") : null;
  if (detail) setHtml(detail, detailHtml(lastModel, key));
}

function onClick(e) {
  const mop = closestEl(e.target, "[data-wf-map-op]");
  if (mop) {
    mapOp(mop.getAttribute("data-wf-map-op"));
    return;
  }
  const crumb = closestEl(e.target, "[data-wf-frame]");
  if (crumb) {
    centerFrame(crumb.getAttribute("data-wf-frame"));
    return;
  }
  const op = closestEl(e.target, "[data-wf-op]");
  if (op) {
    runOp(op);
    return;
  }
  const item = closestEl(e.target, "[data-wf-item]");
  if (item) navigate(item);
}

// The next bar or card for an arrow key. In Timeline the arrows move along a lane (left and right) and between
// lanes (up and down). In Map the axes swap: left and right move between phase columns, up and down along one.
function neighbour(el, key, view) {
  const dir = key === "ArrowLeft" || key === "ArrowUp" ? -1 : key === "ArrowRight" || key === "ArrowDown" ? 1 : 0;
  if (!dir) return null;
  const root = closestEl(el, ".wf");
  if (!root) return null;
  const horizontal = key === "ArrowLeft" || key === "ArrowRight";
  const along = view === "map" ? !horizontal : horizontal;
  const lane = Number(el.getAttribute("data-lane"));
  const x = Number(el.getAttribute("data-x"));
  const all = Array.from(root.querySelectorAll("[data-wf-item][data-lane]"));
  if (along) {
    const row = all.filter(function (e) {
      return Number(e.getAttribute("data-lane")) === lane;
    }).sort(function (a, b) {
      return Number(a.getAttribute("data-x")) - Number(b.getAttribute("data-x"));
    });
    const at = row.indexOf(el);
    return at < 0 ? null : row[at + dir] || null;
  }
  let best = null;
  let bestGap = Infinity;
  all.forEach(function (e) {
    if (Number(e.getAttribute("data-lane")) !== lane + dir) return;
    const gap = Math.abs(Number(e.getAttribute("data-x")) - x);
    if (gap < bestGap) {
      best = e;
      bestGap = gap;
    }
  });
  return best;
}

function onKey(e) {
  // N and S centre the Map on Now and Start from anywhere in the view, except the diagram (its viewport handles them).
  const typing = e.target && /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName || "");
  if (activeMap && lastModel && lastModel.view === "map" && !typing && !closestEl(e.target, ".wfg-host") &&
    /^[nNsS]$/.test(e.key) && !e.ctrlKey && !e.metaKey && !e.altKey) {
    e.preventDefault();
    mapOp(e.key === "n" || e.key === "N" ? "now" : "start");
    return;
  }
  const fold = closestEl(e.target, "[data-wf-fold]");
  if (fold && (e.key === "Enter" || e.key === " ")) {
    e.preventDefault();
    toggleFrame(fold.getAttribute("data-wf-fold"));
    return;
  }
  const el = closestEl(e.target, "[data-wf-item]");
  if (!el || !lastModel) return;
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    const key = el.getAttribute("data-wf-item") || "";
    if (key.indexOf("phase:") === 0) toggleFrame(key);
    else navigate(el);
    return;
  }
  // The Map's arrows, + - 0 and Escape are handled by graph/viewport.js on its SVG.
  if (lastModel.view === "map") return;
  const next = neighbour(el, e.key, lastModel.view);
  if (next) {
    e.preventDefault();
    next.focus();
  }
}

function onScroll(e) {
  if (e.target && e.target.classList && e.target.classList.contains("wf-scroll")) scrollLeft = e.target.scrollLeft;
}

// Event wiring, once per element (the main section is patched in place, so one set of listeners serves every render).
// MutationObserver puts the horizontal scroll back after a patch, because the scroller is a new element then.
export function bind(el) {
  if (!el || bound.has(el)) return;
  bound.add(el);
  el.addEventListener("click", onClick);
  el.addEventListener("focusin", select);
  el.addEventListener("pointerover", select);
  el.addEventListener("keydown", onKey);
  el.addEventListener("scroll", onScroll, true);
  if (typeof MutationObserver === "function") {
    new MutationObserver(function () {
      const scroller = el.querySelector(".wf-scroll");
      if (scroller && scrollLeft && scroller.scrollLeft !== scrollLeft) scroller.scrollLeft = scrollLeft;
      mountMaps();
    }).observe(el, { childList: true });
  }
  // Crossing the 640 px line swaps the minimap for the phase chips, so the Map renders again.
  if (typeof window !== "undefined" && typeof window.matchMedia === "function") {
    const mq = window.matchMedia(NARROW_Q);
    if (mq && typeof mq.addEventListener === "function") {
      mq.addEventListener("change", function () {
        window.dispatchEvent(new Event("hashchange"));
      });
    }
  }
  if (typeof window !== "undefined") {
    window.addEventListener("hashchange", function () {
      scrollLeft = 0;
    });
  }
}

// Loaded by the section router on first visit, after <main> exists. Node tests have no such element.
if (typeof document !== "undefined" && typeof document.getElementById === "function") {
  const main = document.getElementById("main");
  if (main) bind(main);
}
