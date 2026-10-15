// Tokens (R7.28 B): one plain page, the same for All projects and a project. Order: usage now (usage.js, with the
// manual form and the honest no-token banner), the weekly stop and the share per project (both from limits.js), one
// sentence about the limit with the one-click 1-hour override, and read-only spend per project. Numbers come from the
// snapshot; the page does no limit maths of its own. Usage comes from the snapshot's usage reading (snap.usage), so
// the usage band, the weekly reset and the top bar agree with the meters on this page.

import { bannerHtml, esc } from "../dom.js";
import { MISSING, fmtPercent, fmtResets, fmtTokens } from "../format.js";
import { copyButton, refSummary } from "../ref.js";
import { pageState } from "./inbox.js";
import { shareRowsHtml, weeklyStopHtml } from "./limits.js";
import { usageView } from "./usage.js";

const LIMIT_SENTENCE = "At the limit, agents stop starting new jobs. Override for 1 hour lets them run again.";

// Which project, if any, has a limit reached. The override applies to one project, so only project rows count.
function blockedPid(snaps, isProject, pid) {
  for (const snap of snaps) {
    const rows = Array.isArray(snap.meters) ? snap.meters : [];
    const hit = rows.some(function (row) {
      return row.state === "block" && (isProject || row.scope === "project");
    });
    if (hit) return isProject ? pid : snap.id;
  }
  return null;
}

function overrideHtml(pid, name) {
  return '<p class="ov-actions"><button type="button" class="btn" data-action="override" data-project="' +
    esc(pid) + '" data-focus="override" aria-label="Override for 1 hour, ' + esc(name) + '">' +
    "Override for 1 hour</button></p>";
}

// Spend per project, read-only: tokens used this week, the estimated share of the weekly allowance, and when the
// weekly window resets. One shared row grid; the numbers sit right-aligned in their own cells.
function spendTableHtml(vm, snaps) {
  const names = {};
  for (const p of vm.projects || []) names[p.id] = p.name;
  const reset = fmtResets(vm.usage ? vm.usage.weeklyResetsAt : null, vm.now);
  const head = '<li class="row-grid tk-spend rg-head"><span class="rg-t">Project</span>' +
    '<span class="rg-num">Tokens used</span><span class="rg-num">Share of weekly</span>' +
    '<span class="rg-num">Resets</span></li>';
  const rows = snaps.map(function (snap) {
    const week = snap.weekUse || {};
    const share = week.estPts == null ? MISSING : "≈ " + fmtPercent(week.estPts);
    return '<li class="row-grid tk-spend"><span class="rg-t">' + esc(names[snap.id] || snap.title || snap.id) +
      '</span><span class="rg-num num">' + esc(fmtTokens(week.tokK)) + '</span><span class="rg-num num">' +
      esc(share) + '</span><span class="rg-num num">' + esc(reset) + "</span></li>";
  }).join("");
  return '<ul class="spend-list" aria-label="Spend per project this week">' + head + rows + "</ul>";
}

function sectionCard(id, title, copy, body) {
  return '<section class="ov-card" aria-labelledby="' + id + '"><div class="lim-bar"><h3 id="' + id +
    '" class="lim-h">' + esc(title) + "</h3>" + copy + "</div>" + body + "</section>";
}

export function sectionView(vm) {
  const state = pageState(vm);
  if (state) return state;
  const isProject = vm.route.name === "project";
  const snaps = isProject ? [vm.project.snapshot] : (vm.snapshotList || []);
  const pid = isProject ? vm.route.id : (vm.projects[0] ? vm.projects[0].id : null);
  // Copy refs name one project: the project view's own. All projects has none, so its section refs are omitted.
  const refPid = isProject ? pid : null;
  const measured = snaps.some(function (s) {
    return Array.isArray(s.meters);
  });
  const notice = (measured ? "" : bannerHtml("warning", "Limits are not measured yet.",
    "Usage data still loading; limits unavailable.")) + (vm.usage && vm.usage.loaded ? "" :
    bannerHtml("warning", "No usage reading in the snapshot yet.", "The usage band fills at the next poll."));
  const title = isProject ? "Tokens for " + vm.project.name : "Tokens for all projects";
  const head = '<div class="page-head"><h2 class="page-title">' + esc(title) + "</h2>" +
    '<p class="page-note">' + esc(isProject ? "This project's limit and spend."
      : "Account-wide weekly stop and every project's spend.") + "</p></div>";
  const usage = '<section class="ov-card" aria-label="Usage now">' + usageView(vm) + "</section>";
  // The weekly stop and the share rows bring their own heading and copy button (limits.js).
  const stop = '<section class="ov-card" aria-label="Weekly stop">' + weeklyStopHtml(vm) + "</section>";
  const share = '<section class="ov-card" aria-label="Share per project">' + shareRowsHtml(vm) + "</section>";
  const blocked = blockedPid(snaps, isProject, pid);
  const blockedName = blocked ? (isProject ? vm.project.name : (vm.projects.find(function (p) {
    return p.id === blocked;
  }) || { name: blocked }).name) : "";
  const limit = '<section class="ov-card" aria-label="At the limit"><p class="page-note">' + esc(LIMIT_SENTENCE) +
    "</p>" + (blocked ? overrideHtml(blocked, blockedName) : "") + "</section>";
  const spend = sectionCard("tk-spend", "Spend", copyButton("section", "tokens.spend", "Spend",
    { project: refPid, sum: refSummary("section", snaps.length) }), spendTableHtml(vm, snaps));
  const accuracy = '<p class="page-note">Percentages are estimates; token counts are exact.</p>';
  return head + notice + usage + stop + share + limit + spend + accuracy;
}
