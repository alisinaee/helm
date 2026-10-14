// UsageBand: the weekly and five-hour plan meters, reset countdowns, the stale marker and the Sync now button.
// The band is global: it is shown on Home and on every project.

import { bannerHtml, esc, meterHtml, skeletonHtml } from "../dom.js";
import { fmtAge, fmtPercent, fmtResets } from "../format.js";
import { copyButton, refSummary } from "../ref.js";

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

function statusLine(u) {
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

export function usageView(vm) {
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
  const updatedHtml = u.loaded && u.ageNow != null ? '<span class="band-sub">Updated ' +
    esc(fmtAge(u.ageNow)) + "</span>" : "";
  const pid = vm.route && vm.route.name === "project" ? vm.route.id : (vm.projects && vm.projects[0]
    ? vm.projects[0].id : "");
  const copy = copyButton("section", "usage.band", "Usage", { project: pid,
    sum: refSummary("section", u.loaded ? 2 : 0) });
  return '<div class="band' + compact + '">' + body +
    '<div class="band-actions">' + statusLine(u) + updatedHtml +
    '<button type="button" class="btn" data-action="sync-usage" data-focus="sync"' +
    (syncing ? " disabled" : "") + ">" + (syncing ? "Syncing" : "Sync now") + "</button>" + copy +
    syncLine(u.sync) + "</div></div>";
}
