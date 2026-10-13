// KpiRow: six tiles for the project view. One number per tile; the total or context goes in the sub-line.

import { esc, skeletonHtml } from "../dom.js";
import { fmtCount, fmtPercent, fmtTokens } from "../format.js";

function tile(label, value, sub) {
  return '<div class="kpi"><p class="kpi-label">' + esc(label) + '</p><p class="kpi-value">' + esc(value) +
    '</p><p class="kpi-sub">' + esc(sub) + "</p></div>";
}

export function kpiView(vm) {
  const project = vm.project;
  const snap = project && project.snapshot;
  if (!snap) {
    return '<div class="kpi-row" aria-busy="true">' + skeletonHtml(["w-40", "w-60"]) + "</div>";
  }
  const done = snap.done == null ? "–" : fmtCount(snap.done);
  const total = snap.total == null ? "–" : fmtCount(snap.total);
  const progressPct = snap.progress == null ? null : snap.progress * 100;
  return '<div class="kpi-row">' +
    tile("Running", fmtCount(snap.runningCount), "jobs in progress") +
    tile("Tasks left", fmtCount(snap.tasksLeft), "of " + fmtCount(snap.tasksTotal) + " tasks") +
    tile("Needs you", fmtCount(snap.needUser), "waiting for you") +
    tile("Tokens left", fmtTokens(snap.tokensLeftK), "of " + fmtTokens(snap.tokensRoadmapK) + " planned") +
    tile("Tokens used", fmtTokens(snap.tokensDoneK), fmtTokens(snap.tokensPartialK) + " partly done") +
    tile("Done", fmtPercent(progressPct), done + " of " + total + " items") +
    "</div>";
}
