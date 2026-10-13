// Overview section (WP28 placeholder): the existing content, under the new shell. In All projects it is the project
// cards and Running now; in a project it is the usage band, the KPI row, Phases and the side sections. The later
// Overview package replaces this file; the Minimal and Expanded toggle stays here until then.

import { esc } from "../dom.js";
import { homeView, projectView } from "./home.js";
import { kpiView } from "./kpi.js";
import { usageView } from "./usage.js";

function modeHtml(vm) {
  const minimal = vm.mode === "minimal";
  return '<div class="seg" role="group" aria-label="Detail level">' +
    '<button type="button" class="btn" aria-pressed="' + minimal + '" data-action="set-mode" ' +
    'data-mode="minimal" data-focus="mode-minimal">Minimal</button>' +
    '<button type="button" class="btn" aria-pressed="' + !minimal + '" data-action="set-mode" ' +
    'data-mode="expanded" data-focus="mode-expanded">Expanded</button></div>';
}

export function sectionView(vm) {
  const inProject = vm.route.name === "project";
  const body = inProject ? projectView(vm) : homeView(vm);
  const kpi = inProject ? kpiView(vm) : "";
  const hint = inProject ? "" :
    '<p class="placeholder">' + esc("Open a project from its card to see its phases.") + "</p>";
  return '<div class="shell-tools">' + modeHtml(vm) + "</div>" +
    '<div class="band-wrap">' + usageView(vm) + "</div>" +
    (kpi ? '<div class="kpi-wrap">' + kpi + "</div>" : "") + body + hint;
}
