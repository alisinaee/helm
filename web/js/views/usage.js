// UsageBand: the weekly and five-hour plan meters, reset countdowns, the stale marker, the Sync now button and the
// manual "Enter usage" form. The band is global: it is shown on Home and on every project. Usage arrives without a
// manual step: the service fetches it (R10.29, docs/USAGE-SOURCES.md) from the OAuth endpoint, Claude Code's status
// line, or an estimate from the local transcripts. Sync now always runs that fetch for real; the band names the
// source and the age. With no usable Claude Code login (no_token, no_item, expired) it names the one-time setup.
// The form stays folded as a fallback; it opens when the reading is old. Writes go through cmd.js run("usage.set").

import { bannerHtml, esc, meterHtml, skeletonHtml } from "../dom.js";
import { fmtAge, fmtPercent, fmtResets } from "../format.js";
import { copyButton, refSummary } from "../ref.js";
import { run } from "../cmd.js";

const NO_AUTO_SYNC = ["no_token", "no_item", "denied", "expired"];
const UNAVAILABLE_CODES = ["no_token", "no_item", "expired"];
const PERCENT = /^\d{1,3}(\.\d{1,2})?$/;
const OLD_TITLE = "Usage is old.";
const OLD_DETAIL = "It updates by itself when the service can read it; see docs/USAGE-SOURCES.md.";
const UNAVAILABLE_DETAIL = "No Claude Code login on this Mac: run claude auth login once (docs/USAGE-SOURCES.md).";

// The typed values survive a redraw; the message is the last validation problem.
let entryDraft = { weekly: "", fiveHour: "" };
let entryMessage = "";
let listening = false;

function toneFor(pct) {
  if (pct == null) return "accent";
  if (pct >= 95) return "danger";
  if (pct >= 80) return "warning";
  return "accent";
}

function meterBlock(label, pct, resetsAt, now, approx) {
  const text = (approx && pct != null ? "~" : "") + fmtPercent(pct);
  return '<div class="band-meter">' +
    '<div class="band-head"><span class="band-label">' + esc(label) + "</span>" +
    '<span class="band-value">' + esc(text) + "</span></div>" +
    meterHtml(pct, toneFor(pct)) +
    '<p class="band-sub">' + esc(fmtResets(resetsAt, now)) + "</p></div>";
}

function noAutoSync(u) {
  return NO_AUTO_SYNC.indexOf(u.syncError) !== -1;
}

// No usable Claude Code login: not an error. The other sources still run; the band names the setup step.
function unavailable(u) {
  return u.status === "unavailable" || UNAVAILABLE_CODES.indexOf(u.syncError) !== -1;
}

function statusLine(u) {
  if (unavailable(u)) return u.stale || u.veryOld ? bannerHtml("warning", OLD_TITLE, UNAVAILABLE_DETAIL) : "";
  if (noAutoSync(u)) return u.stale || u.veryOld ? bannerHtml("warning", OLD_TITLE, OLD_DETAIL) : "";
  if (u.veryOld) {
    const why = u.lastError ? u.lastError : "no reading yet";
    return bannerHtml("danger", "Usage data outdated: " + why, "Click Sync now or check provider.");
  }
  if (u.stale) {
    const minutes = Math.max(1, Math.floor(u.ageNow / 60));
    return '<p class="band-status"><span class="badge badge-warning">Outdated</span> Updated ' +
      esc(minutes) + " min ago</p>";
  }
  return "";
}

function syncLine(sync, u) {
  if (!sync || !sync.message) return "";
  const tone = sync.state === "error" ? " is-danger" : "";
  return '<p class="band-status' + tone + '">' + esc(sync.message) + "</p>";
}

// Where the reading came from, in words: an estimate from the transcripts, the head's push from the app, a Claude
// Code hook or status line, a value typed by hand, or one the endpoint synced.
export function sourceWord(source) {
  const s = String(source || "").toLowerCase();
  if (/estimate/.test(s)) return "estimated from local transcripts";
  if (/push/.test(s)) return "by the head from the app";
  if (/claude code/.test(s)) return "from Claude Code";
  if (/manual|entered/.test(s)) return "entered by you";
  if (/endpoint|sync/.test(s)) return "synced";
  return "";
}

function fieldHtml(label, name, focus) {
  return '<label class="lim-field"><span class="lim-label">' + esc(label) + "</span>" +
    '<input class="lim-num" type="text" inputmode="decimal" autocomplete="off" name="' + esc(name) +
    '" value="' + esc(entryDraft[name]) + '" data-usage-field="' + esc(name) + '" data-focus="' + esc(focus) +
    '"></label>';
}

// The fallback form, folded while the reading is fresh (no manual step is needed then).
function entryHtml(open) {
  const msg = entryMessage ? '<p class="band-status is-danger" role="alert">' + esc(entryMessage) + "</p>" : "";
  return '<details class="usage-more"' + (open || entryMessage ? " open" : "") +
    '><summary class="band-sub">Enter usage by hand</summary>' +
    '<form class="tk-override usage-entry" data-usage-entry novalidate>' +
    fieldHtml("This week %", "weekly", "usage-weekly") +
    fieldHtml("Last 5 hours %", "fiveHour", "usage-five-hour") +
    '<button type="submit" class="btn" data-focus="usage-save">Save usage</button></form>' + msg + "</details>";
}

// Plain-words check of one typed percent. Blank means "leave this window as it is".
function readPercent(text, name) {
  const s = String(text || "").trim().replace(",", ".");
  if (s === "") return { value: null, error: null };
  const n = PERCENT.test(s) ? Number(s) : NaN;
  if (!(n >= 0 && n <= 100)) return { value: null, error: name + " must be a number from 0 to 100." };
  return { value: n, error: null };
}

function redraw() {
  if (typeof document !== "undefined") document.dispatchEvent(new Event("rb:render"));
}

async function submitEntry() {
  const weekly = readPercent(entryDraft.weekly, "This week %");
  const fiveHour = readPercent(entryDraft.fiveHour, "Last 5 hours %");
  const error = weekly.error || fiveHour.error ||
    (weekly.value === null && fiveHour.value === null ? "Enter a number for at least one window." : "");
  if (error) {
    entryMessage = error;
    redraw();
    return;
  }
  entryMessage = "";
  const args = {};
  const parts = [];
  if (weekly.value !== null) {
    args.weekly = weekly.value;
    parts.push("week " + weekly.value + "%");
  }
  if (fiveHour.value !== null) {
    args.fiveHour = fiveHour.value;
    parts.push("5 hours " + fiveHour.value + "%");
  }
  const data = await run("usage.set", args, { label: "Usage entered: " + parts.join(", ") });
  if (data) entryDraft = { weekly: "", fiveHour: "" };
}

// One document-level listener for the form (the band is redrawn often, so it is not bound per render).
function attachEntryListeners() {
  if (listening || typeof document === "undefined") return;
  listening = true;
  document.addEventListener("input", function (event) {
    const t = event.target;
    const name = t && t.getAttribute ? t.getAttribute("data-usage-field") : null;
    if (name && name in entryDraft) entryDraft[name] = t.value;
  });
  document.addEventListener("submit", function (event) {
    const form = event.target;
    if (!form || !form.hasAttribute || !form.hasAttribute("data-usage-entry")) return;
    event.preventDefault();
    submitEntry();
  });
}

export function usageView(vm) {
  attachEntryListeners();
  const u = vm.usage;
  const compact = vm.view === "project" ? " is-compact" : "";
  if (!u.loaded && !u.error) {
    return '<div class="band' + compact + '">' + skeletonHtml(["w-60", "w-40"]) + "</div>";
  }
  const syncing = u.sync && u.sync.state === "running";
  const approx = /estimate/i.test(String(u.source || ""));
  const body = u.loaded ? (
    meterBlock("Week", u.weeklyPercent, u.weeklyResetsAt, vm.now, approx) +
    meterBlock("5 hours", u.fiveHourPercent, u.fiveHourResetsAt, vm.now, approx)
  ) : bannerHtml("danger", "Could not load account usage.", u.error || "");
  const source = sourceWord(u.source);
  const updatedHtml = u.loaded && u.ageNow != null ? '<span class="band-sub">Updated ' +
    esc(fmtAge(u.ageNow)) + (source ? ", " + esc(source) : "") + "</span>" : "";
  const syncButton = '<button type="button" class="btn" data-action="sync-usage" data-focus="sync"' +
    (syncing ? " disabled" : "") + ">" + (syncing ? "Syncing" : "Sync now") + "</button>";
  const pid = vm.route && vm.route.name === "project" ? vm.route.id : (vm.projects && vm.projects[0]
    ? vm.projects[0].id : "");
  const copy = copyButton("section", "usage.band", "Usage", { project: pid,
    sum: refSummary("section", u.loaded ? 2 : 0) });
  const old = !u.loaded || u.stale || u.veryOld;
  return '<div class="band' + compact + '">' + body + entryHtml(old) +
    '<div class="band-actions">' + statusLine(u) + updatedHtml + syncButton + copy +
    syncLine(u.sync, u) + "</div></div>";
}
