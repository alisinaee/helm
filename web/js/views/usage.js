// UsageBand: the weekly and five-hour plan meters, reset countdowns, the stale marker, the Sync now button and the
// manual "Enter usage" form. The band is global: it is shown on Home and on every project. When the Mac cannot sync
// usage by itself (syncError no_token, no_item or denied) the band says so in plain words, hides Sync now and offers
// the form. Writes go through cmd.js run("usage.set").

import { bannerHtml, esc, meterHtml, skeletonHtml } from "../dom.js";
import { fmtAge, fmtPercent, fmtResets } from "../format.js";
import { copyButton, refSummary } from "../ref.js";
import { run } from "../cmd.js";

const NO_AUTO_SYNC = ["no_token", "no_item", "denied"];
const PERCENT = /^\d{1,3}(\.\d{1,2})?$/;
const NO_AUTO_TITLE = "Usage is not synced automatically on this Mac.";
const NO_AUTO_DETAIL = "Enter your numbers below, or sign in once with `claude` then `/login` in a terminal " +
  "to turn on auto sync.";

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

function meterBlock(label, pct, resetsAt, now) {
  const text = fmtPercent(pct);
  return '<div class="band-meter">' +
    '<div class="band-head"><span class="band-label">' + esc(label) + "</span>" +
    '<span class="band-value">' + esc(text) + "</span></div>" +
    meterHtml(pct, toneFor(pct)) +
    '<p class="band-sub">' + esc(fmtResets(resetsAt, now)) + "</p></div>";
}

function noAutoSync(u) {
  return NO_AUTO_SYNC.indexOf(u.syncError) !== -1;
}

function statusLine(u) {
  if (noAutoSync(u)) return bannerHtml("warning", NO_AUTO_TITLE, NO_AUTO_DETAIL);
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

function syncLine(sync) {
  if (!sync || !sync.message) return "";
  const tone = sync.state === "error" ? " is-danger" : "";
  return '<p class="band-status' + tone + '">' + esc(sync.message) + "</p>";
}

// Where the reading came from, in words: a value the person typed or pushed by hand, or one the endpoint synced.
function sourceWord(source) {
  const s = String(source || "").toLowerCase();
  if (/manual|entered|push/.test(s)) return "entered by you";
  if (/endpoint|sync/.test(s)) return "synced";
  return "";
}

function fieldHtml(label, name, focus) {
  return '<label class="lim-field"><span class="lim-label">' + esc(label) + "</span>" +
    '<input class="lim-num" type="text" inputmode="decimal" autocomplete="off" name="' + esc(name) +
    '" value="' + esc(entryDraft[name]) + '" data-usage-field="' + esc(name) + '" data-focus="' + esc(focus) +
    '"></label>';
}

function entryHtml() {
  const msg = entryMessage ? '<p class="band-status is-danger" role="alert">' + esc(entryMessage) + "</p>" : "";
  return '<form class="tk-override usage-entry" data-usage-entry novalidate>' +
    '<p class="lim-h2">Enter usage</p>' +
    fieldHtml("This week %", "weekly", "usage-weekly") +
    fieldHtml("Last 5 hours %", "fiveHour", "usage-five-hour") +
    '<button type="submit" class="btn" data-focus="usage-save">Save usage</button></form>' + msg;
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
  const body = u.loaded ? (
    meterBlock("Week", u.weeklyPercent, u.weeklyResetsAt, vm.now) +
    meterBlock("5 hours", u.fiveHourPercent, u.fiveHourResetsAt, vm.now)
  ) : bannerHtml("danger", "Could not load account usage.", u.error || "");
  const source = sourceWord(u.source);
  const updatedHtml = u.loaded && u.ageNow != null ? '<span class="band-sub">Updated ' +
    esc(fmtAge(u.ageNow)) + (source ? ", " + esc(source) : "") + "</span>" : "";
  const syncButton = noAutoSync(u) ? "" :
    '<button type="button" class="btn" data-action="sync-usage" data-focus="sync"' +
    (syncing ? " disabled" : "") + ">" + (syncing ? "Syncing" : "Sync now") + "</button>";
  const pid = vm.route && vm.route.name === "project" ? vm.route.id : (vm.projects && vm.projects[0]
    ? vm.projects[0].id : "");
  const copy = copyButton("section", "usage.band", "Usage", { project: pid,
    sum: refSummary("section", u.loaded ? 2 : 0) });
  return '<div class="band' + compact + '">' + body + entryHtml() +
    '<div class="band-actions">' + statusLine(u) + updatedHtml + syncButton + copy +
    syncLine(u.sync) + "</div></div>";
}
