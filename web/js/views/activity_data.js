// Activity data (R11.4, docs/ACTIVITY-V2.md): the per-scope state of the history feed, the reads of
// GET /api/v1/projects/{pid}/history (or /api/v1/history in All projects), the filters, and pure helpers (the event
// shape of a snapshot activity line, day grouping, the Markdown export). No DOM here, so node tests can import it.

import { getJson } from "../api.js";

export const KINDS = ["head", "question", "job", "commit", "task", "rule", "feature", "issue", "setting", "usage",
  "session", "other"];
export const KIND_WORD = { head: "Head", question: "Question", job: "Job", commit: "Commit", task: "Task",
  rule: "Rule", feature: "Feature", issue: "Issue", setting: "Setting", usage: "Usage", session: "Session",
  other: "Other" };
export const ACTORS = ["user", "head", "agent", "system"];
export const ACTOR_WORD = { user: "You", head: "Head", agent: "Agent", system: "System" };
export const PRESETS = [["all", "All"], ["today", "Today"], ["24h", "24h"], ["7d", "7d"], ["30d", "30d"],
  ["custom", "Custom"]];
const PAGE = 150;
const DAY_MS = 86400000;
const OP_KIND = { task: "task", queue: "task", plan: "task", backlog: "task", subtask: "task", phase: "task",
  comment: "task", head: "head", question: "question", rules: "rule", rule: "rule", feature: "feature",
  issue: "issue", limit: "setting", budget: "setting", control: "setting", usage: "setting", settings: "setting",
  autonomy: "setting", job: "job", git: "commit" };
const ID_RE = /\b(RP\d+|R\d+(?:\.\d+)+[a-z]?|H\d+|Q\d+|F\d+|I\d+|j\d+)\b/;
const ID_TYPE = [["RP", "rule"], ["R", "task"], ["H", "head"], ["Q", "question"], ["F", "feature"], ["I", "issue"],
  ["j", "job"]];
const STORE_KEY = "rb.activity.filters";

const scopes = new Map(); // scope key ("p:<pid>" | "all") -> state

export function defaultFilters() {
  return { kinds: [], actors: [], q: "", preset: "all", from: null, to: null };
}

function loadFilters(key) {
  try {
    const raw = JSON.parse(localStorage.getItem(STORE_KEY) || "{}")[key];
    if (raw && typeof raw === "object") return Object.assign(defaultFilters(), raw);
  } catch (err) {
    // no storage (private window, node): the defaults
  }
  return defaultFilters();
}

export function saveFilters(key, filt) {
  try {
    const all = JSON.parse(localStorage.getItem(STORE_KEY) || "{}");
    all[key] = filt;
    localStorage.setItem(STORE_KEY, JSON.stringify(all));
  } catch (err) {
    // per-viewer convenience only
  }
}

export function scopeKey(route) {
  return route.name === "project" ? "p:" + route.id : "all";
}

export function stateFor(route) {
  const key = scopeKey(route);
  if (!scopes.has(key)) {
    scopes.set(key, { key: key, pid: route.name === "project" ? route.id : null, filt: loadFilters(key), sel: null,
      sig: null, status: "idle", events: [], next: null, total: 0, counts: null, actors: null, hist: null,
      error: null, older: false, fresh: new Map(), inflight: null });
  }
  return scopes.get(key);
}

// The [from, to] epoch ms of the filters at now (null ends are open). Preset ends are rounded to the minute so a
// poll a few seconds later asks the same URL (and gets a 304).
export function rangeOf(filt, now) {
  const minute = Math.floor(now / 60000) * 60000;
  if (filt.preset === "today") {
    const d = new Date(now);
    d.setHours(0, 0, 0, 0);
    return [d.getTime(), null];
  }
  if (filt.preset === "24h") return [minute - DAY_MS, null];
  if (filt.preset === "7d") return [minute - 7 * DAY_MS, null];
  if (filt.preset === "30d") return [minute - 30 * DAY_MS, null];
  if (filt.preset === "custom") return [filt.from, filt.to];
  return [null, null];
}

export function queryOf(filt, now, before) {
  const parts = [];
  const range = rangeOf(filt, now);
  if (filt.kinds.length) parts.push("kind=" + encodeURIComponent(filt.kinds.join(",")));
  if (filt.actors.length) parts.push("actor=" + encodeURIComponent(filt.actors.join(",")));
  if (filt.q) parts.push("q=" + encodeURIComponent(filt.q));
  if (range[0] != null) parts.push("from=" + range[0]);
  if (range[1] != null) parts.push("to=" + range[1]);
  parts.push("limit=" + PAGE);
  if (before) parts.push("before=" + encodeURIComponent(before));
  return "?" + parts.join("&");
}

function baseUrl(st) {
  return st.pid ? "/api/v1/projects/" + encodeURIComponent(st.pid) + "/history" : "/api/v1/history";
}

// Read the newest page for the current filters. A new filter set replaces the list; the same set (a live poll)
// puts only the new events on top, marked fresh so they slide in. onDone repaints.
export function loadFirst(st, now, onDone) {
  const qkey = queryOf(st.filt, now, null);
  if (st.inflight === qkey) return;
  const sig = JSON.stringify(st.filt);
  st.tried = sig;
  const replace = st.sig !== sig || st.status !== "ready";
  st.inflight = qkey;
  if (replace && st.status !== "ready") st.status = "loading";
  getJson(baseUrl(st) + qkey).then(function (reply) {
    if (st.inflight !== qkey) return;
    const data = reply.data || {};
    const rows = Array.isArray(data.events) ? data.events : [];
    if (replace) {
      st.events = rows;
      st.next = data.next || null;
      st.fresh.clear();
    } else {
      const known = new Set(st.events.map(function (e) { return e.id; }));
      const top = st.events.length ? st.events[0].ms : -Infinity;
      const added = rows.filter(function (e) { return !known.has(e.id) && e.ms >= top; });
      const at = Date.now();
      for (const e of added) st.fresh.set(e.id, at);
      st.events = added.concat(st.events);
      if (!st.events.length) st.next = data.next || null;
    }
    st.total = data.total || 0;
    st.counts = data.counts || null;
    st.actors = data.actors || null;
    st.hist = data.hist || null;
    st.status = "ready";
    st.error = null;
    st.sig = sig;
  }, function (err) {
    if (st.inflight !== qkey) return;
    st.status = st.events.length ? "ready" : "error";
    st.error = err && err.message ? err.message : "The history could not be read.";
  }).finally(function () {
    if (st.inflight === qkey) st.inflight = null;
    onDone();
  });
}

// The next older page, appended. Does nothing when there is none or one is on its way.
export function loadOlder(st, now, onDone) {
  if (!st.next || st.older) return;
  st.older = true;
  getJson(baseUrl(st) + queryOf(st.filt, now, st.next)).then(function (reply) {
    const data = reply.data || {};
    const known = new Set(st.events.map(function (e) { return e.id; }));
    st.events = st.events.concat((data.events || []).filter(function (e) { return !known.has(e.id); }));
    st.next = data.next || null;
  }, function (err) {
    st.error = err && err.message ? err.message : "Older events could not be read.";
  }).finally(function () {
    st.older = false;
    onDone();
  });
}

export function subjectOf(text) {
  const m = ID_RE.exec(String(text || ""));
  if (!m) return null;
  for (const pair of ID_TYPE) {
    if (m[1].startsWith(pair[0])) return pair[1] + ":" + m[1];
  }
  return null;
}

export function kindOfOp(op) {
  return OP_KIND[String(op || "").split(".")[0]] || "other";
}

// A snapshot activity line ({id, atMs, src, op, sum, undo}) in the history event shape. The snapshot keeps the
// newest lines only; they fill the page until the full history arrives (and in node renders, which never fetch).
export function eventFromLine(line, pid, pname) {
  const kind = kindOfOp(line.op);
  const family = String(line.op || "").split(".")[0];
  const actor = line.src === "agent" ? (family === "head" || family === "question" || family === "rules" ?
    "head" : "agent") : "user";
  const subject = subjectOf(line.sum);
  return { id: "activity:" + line.id, ms: line.atMs, kind: kind, verb: line.op || "change", actor: actor,
    subject: subject, summary: line.sum || line.op || "change", link: linkOf(subject), model: null, tokensK: null,
    src: "activity", undo: line.undo === true, activity: line.id, project: pid, pname: pname,
    detail: { source: line.src, op: line.op } };
}

export function linkOf(subject) {
  if (!subject) return null;
  const parts = subject.split(":");
  const map = { task: "work/i/" + parts[1], head: "head?id=" + parts[1], job: "agents", commit: "git",
    question: "inbox", rule: "rules", feature: "work", issue: "work" };
  return map[parts[0]] || null;
}

// The filters applied in the browser (the snapshot fallback rows; the server applies them to fetched pages).
export function matches(e, filt, now) {
  if (filt.kinds.length && filt.kinds.indexOf(e.kind) < 0) return false;
  if (filt.actors.length && filt.actors.indexOf(e.actor) < 0) return false;
  const range = rangeOf(filt, now);
  if (range[0] != null && !(e.ms >= range[0])) return false;
  if (range[1] != null && !(e.ms <= range[1])) return false;
  if (filt.q) {
    const hay = [e.summary, e.subject, e.model, e.verb, e.project].join(" ").toLowerCase();
    return filt.q.toLowerCase().split(/\s+/).every(function (w) { return hay.indexOf(w) >= 0; });
  }
  return true;
}

const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function pad(n) {
  return n < 10 ? "0" + n : String(n);
}

export function dayStart(ms) {
  const d = new Date(ms);
  d.setHours(0, 0, 0, 0);
  return d.getTime();
}

export function dayLabel(start, now) {
  const today = dayStart(now);
  const d = new Date(start);
  const plain = DAYS[d.getDay()] + " " + d.getDate() + " " + MONTHS[d.getMonth()];
  if (start === today) return "Today · " + plain;
  if (start === dayStart(today - 1)) return "Yesterday · " + plain;
  return plain + (d.getFullYear() !== new Date(now).getFullYear() ? " " + d.getFullYear() : "");
}

export function clock(ms) {
  const d = new Date(ms);
  return pad(d.getHours()) + ":" + pad(d.getMinutes());
}

export function stamp(ms) {
  const d = new Date(ms);
  return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()) + " " + clock(ms) + ":" +
    pad(d.getSeconds());
}

// "2026-10-17T08:42" for a datetime-local input.
export function localInput(ms) {
  if (ms == null) return "";
  return stamp(ms).slice(0, 16).replace(" ", "T");
}

// Events newest first in day groups: [{start, events}].
export function groupByDay(events) {
  const groups = [];
  for (const e of events) {
    const start = dayStart(e.ms);
    const last = groups[groups.length - 1];
    if (last && last.start === start) last.events.push(e);
    else groups.push({ start: start, events: [e] });
  }
  return groups;
}

export function refText(e) {
  return e.subject ? e.subject.split(":")[1] : "";
}

function cell(text) {
  return String(text == null ? "" : text).replace(/\|/g, "\\|").replace(/\s+/g, " ").trim();
}

// The events as a Markdown table (the export).
export function toMarkdown(events, title) {
  const lines = ["## " + title, "", "| Time | Actor | Kind | Summary | Ref | Model | Tokens |",
    "| --- | --- | --- | --- | --- | --- | ---: |"];
  for (const e of events) {
    lines.push("| " + [stamp(e.ms), ACTOR_WORD[e.actor] || e.actor, KIND_WORD[e.kind] || e.kind,
      (e.pname ? "[" + e.pname + "] " : "") + e.summary, refText(e), e.model || "",
      e.tokensK == null ? "" : e.tokensK + "k"].map(cell).join(" | ") + " |");
  }
  return lines.join("\n") + "\n";
}

export function modelTone(model) {
  const m = String(model || "").toLowerCase();
  for (const name of ["haiku", "sonnet", "opus", "cursor", "agy"]) {
    if (m.indexOf(name) >= 0) return name;
  }
  return "neutral";
}

export function modelShort(model) {
  const tone = modelTone(model);
  return tone === "neutral" ? String(model || "") : tone;
}
