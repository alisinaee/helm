// Activity markup (R11.4): the filter bar, the time scrubber, the day-grouped rows and the detail pane. Pure string
// builders over the state from activity_data.js; activity.js wires them to the page.

import { esc } from "../dom.js";
import { fmtTokens } from "../format.js";
import { copyButton } from "../ref.js";
import { projectHash } from "../router.js";
import {
  ACTOR_WORD, ACTORS, KIND_WORD, KINDS, PRESETS, localInput, refText, stamp,
} from "./activity_data.js";

const ACTOR_ICON = { user: "inbox", head: "head", agent: "agents", system: "settings" };

export function icon(name) {
  return '<svg class="ico" aria-hidden="true" focusable="false">' +
    '<use href="/icons.svg#i-' + esc(name) + '"></use></svg>';
}

export function num(n) {
  return n == null ? "" : Number(n).toLocaleString("en-US");
}

// A toggle chip: fixed word, count in its own tabular cell.
function chip(group, value, word, count, on) {
  return '<button type="button" class="hx-chip hx-k-' + esc(value) + '" data-hx="' + group + '" data-v="' +
    esc(value) + '" aria-pressed="' + (on ? "true" : "false") + '"><span class="hx-dot" aria-hidden="true">' +
    '</span><span>' + esc(word) + '</span><span class="num hx-cnt">' + num(count || 0) + "</span></button>";
}

export function toolbarHtml(st, opts) {
  const f = st.filt;
  const presets = PRESETS.map(function (p) {
    return '<button type="button" class="hx-seg" data-hx="preset" data-v="' + p[0] + '" aria-pressed="' +
      (f.preset === p[0] ? "true" : "false") + '"><span>' + esc(p[1]) + "</span></button>";
  }).join("");
  const actors = ACTORS.map(function (a) {
    return chip("actor", a, ACTOR_WORD[a], st.actors ? st.actors[a] : null, f.actors.indexOf(a) >= 0);
  }).join("");
  const kinds = KINDS.filter(function (k) {
    return !st.counts || st.counts[k] > 0 || f.kinds.indexOf(k) >= 0;
  }).map(function (k) {
    return chip("kind", k, KIND_WORD[k], st.counts ? st.counts[k] : null, f.kinds.indexOf(k) >= 0);
  }).join("");
  const any = f.kinds.length || f.actors.length || f.q || f.preset !== "all";
  const live = opts.live ? '<span class="hx-live" title="New events appear on their own">' +
    '<span class="hx-pulse" aria-hidden="true"></span>Live</span>' : "";
  return '<div class="hx-bar">' +
    '<h2 class="page-title hx-title">Activity</h2>' +
    '<span class="hx-total num" aria-live="polite">' + esc(opts.totalText) + "</span>" +
    '<label class="hx-search"><span class="sr-only">Search history</span>' +
    '<input type="search" id="hx-q" class="input hx-q" placeholder="Search ids, text, models" ' +
    'autocomplete="off" spellcheck="false" value="' + esc(f.q) + '"></label>' +
    '<div class="hx-segs" role="group" aria-label="Time range">' + presets + "</div>" +
    live +
    '<span class="hx-tools">' +
    (any ? '<button type="button" class="btn btn-small" data-hx="clear">Clear</button>' : "") +
    '<button type="button" class="btn btn-small" data-hx="export" title="Copy the events shown as a Markdown table"' +
    ">Copy as Markdown</button></span></div>" +
    '<div class="hx-filters"><div class="hx-chips" role="group" aria-label="Who">' + actors + "</div>" +
    '<span class="hx-sep" aria-hidden="true"></span>' +
    '<div class="hx-chips" role="group" aria-label="Kinds">' + kinds + "</div></div>";
}

// The custom range inputs (the keyboard path for picking a window); the timeline strip itself is in
// activity_timeline.js.
export function scrubberHtml(st) {
  const f = st.filt;
  if (f.preset !== "custom") return "";
  return '<div class="hx-scrub"><span class="hx-range">' +
    '<label><span class="hx-lbl">From</span><input type="datetime-local" class="input hx-dt" id="hx-from" ' +
    'data-hx="from" value="' + esc(localInput(f.from)) + '"></label>' +
    '<label><span class="hx-lbl">To</span><input type="datetime-local" class="input hx-dt" id="hx-to" ' +
    'data-hx="to" value="' + esc(localInput(f.to)) + '"></label></span></div>';
}

export function actorHtml(a) {
  return '<span class="hx-actor hx-a-' + esc(a) + '">' + icon(ACTOR_ICON[a] || "activity") + "<span>" +
    esc(ACTOR_WORD[a] || a) + "</span></span>";
}

export function kindHtml(e) {
  const bad = /\.(failed|error|stopped)$/.test(e.verb || "");
  return '<span class="hx-kind hx-k-' + esc(e.kind) + (bad ? " hx-bad" : "") + '"><span class="hx-dot" ' +
    'aria-hidden="true"></span>' + esc(KIND_WORD[e.kind] || e.kind) + "</span>";
}

export function hrefOf(e, fallbackPid) {
  const pid = e.project || fallbackPid;
  if (!e.link || !pid) return "";
  const cut = e.link.indexOf("?");
  const path = cut >= 0 ? e.link.slice(0, cut) : e.link;
  const parts = path.split("/");
  return projectHash(pid, parts[0]) + (parts.length > 1 ? "/" + parts.slice(1).map(encodeURIComponent).join("/") :
    "") + (cut >= 0 ? e.link.slice(cut) : "");
}

function field(name, valueHtml) {
  return valueHtml ? "<dt>" + esc(name) + "</dt><dd>" + valueHtml + "</dd>" : "";
}

function textBlock(name, text) {
  return text ? '<h4 class="hx-sub">' + esc(name) + '</h4><pre class="hx-pre">' + esc(text) + "</pre>" : "";
}

// The detail pane of the selected event: every field, the full text and reply of a head item, copy and open.
export function detailHtml(e, ctx) {
  if (!e) return "";
  const d = e.detail || {};
  const ref = refText(e);
  const kindWord = e.subject ? e.subject.split(":")[0] : "";
  const href = hrefOf(e, ctx.pid);
  const copy = ref && e.project ? copyButton(kindWord, ref, ref, { project: e.project, sum: e.summary }) : "";
  const extra = [];
  for (const key of ["task", "status", "effort", "engine", "durationS", "note", "reason", "answer", "headKind",
    "by", "weeklyPct", "dayPts", "author", "sha", "op", "source"]) {
    const v = d[key];
    if (v == null || v === "" || typeof v === "object") continue;
    extra.push(field(key === "durationS" ? "Duration" : key.charAt(0).toUpperCase() + key.slice(1),
      esc(key === "durationS" ? Math.round(v / 60) + " min" : String(v))));
  }
  const links = Array.isArray(d.links) && d.links.length ? field("Links", esc(d.links.join(", "))) : "";
  const options = Array.isArray(d.options) && d.options.length ? field("Options", esc(d.options.join(" · "))) : "";
  return '<aside class="hx-detail" aria-label="Event details"><div class="hx-dhead">' + kindHtml(e) +
    '<span class="hx-dtime num">' + esc(stamp(e.ms)) + "</span>" + copy +
    '<button type="button" class="hx-x" data-hx="close" aria-label="Close details">' +
    '<svg class="ico" aria-hidden="true" focusable="false"><path d="M6 6l12 12M18 6 6 18"/></svg></button></div>' +
    '<p class="hx-dsum">' + esc(e.summary) + "</p>" +
    '<dl class="hx-dl">' + field("Who", actorHtml(e.actor)) +
    (e.pname ? field("Project", esc(e.pname)) : "") +
    field("Ref", ref ? (href ? '<a href="' + esc(href) + '">' + esc(ref) + "</a>" : esc(ref)) : "") +
    field("Model", e.model ? esc(e.model) : "") +
    field("Tokens", e.tokensK == null ? "" : '<span class="num">' + esc(fmtTokens(e.tokensK)) + "</span>") +
    field("Event", esc(e.verb || "")) + extra.join("") + links + options +
    field("Undo", e.undo ? "Available on the row" : "") + "</dl>" +
    textBlock("Text", d.text) + textBlock("Reply", d.reply) +
    '<div class="hx-dact"><button type="button" class="btn btn-small" data-hx="copy-md" data-id="' + esc(e.id) +
    '">Copy as Markdown</button>' + (href ? '<a class="btn btn-small" href="' + esc(href) + '">Open</a>' : "") +
    "</div></aside>";
}
