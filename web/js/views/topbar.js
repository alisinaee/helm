// Top bar (WP28): the scope crumb (project name, section, view), the control pill with one Stop or Resume button,
// the Today and Week mini meters, the connection dot, the theme toggle and "?". The meters read only
// snapshot meters.limits (WP27); when that is missing they show grey "unknown". The client does no limit maths.

import { esc, meterHtml } from "../dom.js";
import { SECTIONS, SETTINGS, sectionById } from "../routes.js";

const THEME_LABEL = { auto: "Auto", dark: "Dark", light: "Light" };
const STATE_RANK = { ok: 0, unknown: 1, warn: 2, block: 3 };

export function themeLabel(theme) {
  return THEME_LABEL[theme] || "Auto";
}

function crumbHtml(vm) {
  const route = vm.route;
  const section = sectionById(route.section) || SECTIONS[0];
  const label = section === SETTINGS ? SETTINGS.label : section.label;
  let scope;
  if (route.name === "project") {
    const name = vm.project ? vm.project.name : route.id;
    scope = '<button type="button" class="crumb-proj" data-action="panel-toggle" data-focus="crumb">' +
      esc(name) + ' <span aria-hidden="true">▾</span><span class="sr-only"> show or hide the panel</span></button>';
  } else {
    scope = '<span class="crumb-proj">All projects</span>';
  }
  const view = route.view ? '<span class="crumb-sep" aria-hidden="true">›</span>' +
    '<span class="crumb-part">' + esc(route.view) + "</span>" : "";
  return '<h1 class="crumb">' + scope + '<span class="crumb-sep" aria-hidden="true">›</span>' +
    '<span class="crumb-part">' + esc(label) + "</span>" + view + "</h1>";
}

function controlHtml(vm) {
  if (vm.route.name !== "project") {
    return '<span class="pill is-wait">Choose a project to stop or resume it</span>';
  }
  const c = vm.control;
  if (!c || !c.known) {
    return '<span class="pill is-wait">Connecting</span>';
  }
  const offline = vm.conn.ok === false ? " disabled" : "";
  if (c.stopped) {
    return '<span class="pill is-stop" role="status"><span class="dot" aria-hidden="true"></span>Stopped</span>' +
      '<button type="button" class="btn" data-action="control" data-op="control.resume" data-project="' +
      esc(c.id) + '" data-focus="control"' + offline + ">Resume</button>";
  }
  const blocked = c.blocked ? " is-blocked" : " is-run";
  const word = c.blocked ? "Blocked" : "Running";
  const title = c.blocked && c.reason ? ' title="' + esc(c.reason) + '"' : "";
  return '<span class="pill' + blocked + '"' + title + '><span class="dot" aria-hidden="true"></span>' +
    word + "</span>" +
    '<button type="button" class="btn" data-action="control" data-op="control.stop" data-project="' +
    esc(c.id) + '" data-focus="control"' + offline + ">Stop</button>";
}

// The tightest row for a window: the highest state, then the highest used share.
function tightest(rows) {
  let best = null;
  let bestShare = -1;
  for (const row of rows) {
    const share = row.limit > 0 && row.used != null ? row.used / row.limit : 0;
    if (!best || STATE_RANK[row.state] > STATE_RANK[best.state] ||
        (STATE_RANK[row.state] === STATE_RANK[best.state] && share > bestShare)) {
      best = row;
      bestShare = share;
    }
  }
  return best;
}

function unit(row) {
  return row.kind === "pct" || row.kind === "acct" ? "%" : "k tok";
}

function miniHtml(label, rows, win) {
  if (rows === null) {
    return '<span class="mini is-unknown"><span class="mini-l">' + esc(label) + "</span>" +
      meterHtml(null, "unknown") + '<span class="mini-v">unknown</span></span>';
  }
  const row = tightest(rows.filter(function (r) {
    return r.window === win;
  }));
  if (!row) {
    return '<span class="mini"><span class="mini-l">' + esc(label) +
      '</span><span class="mini-v">no limit</span></span>';
  }
  if (row.state === "unknown" || row.used == null || row.limit == null) {
    return '<span class="mini is-unknown"><span class="mini-l">' + esc(label) + "</span>" +
      meterHtml(null, "unknown") + '<span class="mini-v">unknown</span></span>';
  }
  const share = row.limit > 0 ? (row.used / row.limit) * 100 : 0;
  const tone = row.state === "block" ? "danger" : row.state === "warn" ? "warning" : "accent";
  const text = (row.est ? "≈" : "") + String(Math.round(row.used * 10) / 10) + "/" +
    String(row.limit) + unit(row);
  return '<span class="mini"><span class="mini-l">' + esc(label) + "</span>" + meterHtml(share, tone) +
    '<span class="mini-v">' + esc(text) + "</span></span>";
}

function metersHtml(vm) {
  return '<div class="top-meters" aria-label="Usage limits">' + miniHtml("Today", vm.meterRows, "day") +
    miniHtml("Week", vm.meterRows, "week") + "</div>";
}

function connHtml(conn) {
  if (conn.ok === true) {
    return '<span class="conn" data-state="ok"><span class="dot" aria-hidden="true"></span>Live</span>';
  }
  if (conn.ok === false) {
    return '<span class="conn" data-state="down"><span class="dot" aria-hidden="true"></span>Offline</span>';
  }
  return '<span class="conn" data-state="wait"><span class="dot" aria-hidden="true"></span>Connecting</span>';
}

export function topbarView(vm) {
  const theme = vm.theme || "auto";
  return '<div class="top-row">' + crumbHtml(vm) +
    '<div class="top-tools">' + controlHtml(vm) + metersHtml(vm) + connHtml(vm.conn) +
    '<button type="button" class="btn" data-action="cycle-theme" data-focus="theme" aria-label="Theme: ' +
    esc(themeLabel(theme)) + '. Change theme">' + esc(themeLabel(theme)) + "</button>" +
    '<button type="button" class="btn" data-action="help-open" data-focus="help"' +
    ' aria-label="Keyboard shortcuts">?</button>' +
    "</div></div>";
}
