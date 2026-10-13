// TopBar: title, the project switcher (a native select), the detail toggle, the theme toggle and the live badge.

import { esc } from "../dom.js";
import { fmtClock } from "../format.js";
import { homeHash } from "../router.js";

const THEME_LABEL = { auto: "Auto", dark: "Dark", light: "Light" };

export function themeLabel(theme) {
  return THEME_LABEL[theme] || "Auto";
}

function liveHtml(conn) {
  if (conn.ok === true) {
    return '<span class="live">Live · ' + esc(fmtClock(conn.lastOkAt)) + "</span>";
  }
  if (conn.ok === false) {
    return '<span class="live is-down">Disconnected, retrying</span>';
  }
  return '<span class="live is-wait">Connecting</span>';
}

function switcherHtml(vm) {
  const current = vm.view === "project" ? vm.route.id : "";
  const options = ['<option value=""' + (current ? "" : " selected") + ">All projects (Home)</option>"];
  for (const project of vm.projects || []) {
    options.push('<option value="' + esc(project.id) + '"' + (project.id === current ? " selected" : "") + ">" +
      esc(project.name) + "</option>");
  }
  return '<label class="switcher-label">Project' +
    '<select id="switcher" class="switcher" data-action="switch-project" data-focus="switcher"' +
    '>' + options.join("") + "</select></label>";
}

function modeHtml(vm) {
  const minimal = vm.mode === "minimal";
  return '<div class="seg" role="group" aria-label="Detail level">' +
    '<button type="button" class="btn" aria-pressed="' + minimal + '" data-action="set-mode" ' +
    'data-mode="minimal" data-focus="mode-minimal">Minimal</button>' +
    '<button type="button" class="btn" aria-pressed="' + !minimal + '" data-action="set-mode" ' +
    'data-mode="expanded" data-focus="mode-expanded">Expanded</button></div>';
}

export function topbarView(vm) {
  const theme = vm.theme || "auto";
  return '<div class="topbar">' +
    '<h1 class="topbar-title"><a href="' + esc(homeHash()) + '">roadmap-board</a></h1>' +
    '<div class="topbar-group">' + switcherHtml(vm) + "</div>" +
    '<div class="topbar-group">' + modeHtml(vm) +
    '<button type="button" class="btn" data-action="cycle-theme" data-focus="theme">Theme: ' +
    esc(themeLabel(theme)) + "</button></div>" +
    liveHtml(vm.conn) + "</div>";
}
