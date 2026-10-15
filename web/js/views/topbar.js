// Top bar (WP28): the scope crumb (project name, section, view), the control pill with one Stop or Resume button,
// the Today and Week mini meters, the connection dot, the theme toggle and "?". The meters read only
// snapshot meters.limits (WP27); when that is missing they show grey "unknown". The client does no limit maths.

import { csrfToken } from "../api.js";
import { esc, meterHtml } from "../dom.js";
import { mark, status as logStatus } from "../log.js";
import { SECTIONS, SETTINGS, sectionById } from "../routes.js";
import { panelIsOpen } from "../state.js";
import { showToast } from "./toast.js";

const THEME_LABEL = { auto: "Auto", dark: "Dark", light: "Light" };
const STATE_RANK = { ok: 0, unknown: 1, warn: 2, block: 3 };
const MARK_LABEL = "I am seeing a bug here";
const LOCAL_HOST = /^(localhost|127\.0\.0\.1|\[::1\])$/;

// The Mark button, the m key and the palette command exist only on localhost with a CSRF value (the phone has none).
export function markAllowed() {
  if (typeof window === "undefined" || typeof location === "undefined") return false;
  return LOCAL_HOST.test(location.hostname) && Boolean(csrfToken());
}

// Phone width (under 600 px): the top bar has no room for Mark or Cmd+K, and a phone keyboard has no Cmd key.
function phoneWidth() {
  return typeof window !== "undefined" && typeof window.matchMedia === "function" &&
    window.matchMedia("(max-width: 599px)").matches;
}

// Mark this moment in the debug log (R7.16 step 5b). mark() records the route and the ref of the focused row.
export function markBug() {
  if (!markAllowed()) return;
  if (!logStatus().active) {
    showToast({ text: "Logging is off. Turn it on in Settings > Logging." });
    return;
  }
  mark(MARK_LABEL);
  showToast({ text: "Marked" });
}

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

// The side panel toggle, always last: it shows the panel again after its Close button hid it. Same handler as the
// project crumb. The "]" key is the shortcut (keys.js), named in the title.
// Without a window (a node render), an unset panel state reads as closed.
function sideOpen(ui) {
  if (!ui) return false;
  if (typeof ui.panelOpen === "boolean") return ui.panelOpen;
  return typeof window !== "undefined" && panelIsOpen(ui);
}

function panelToggleHtml(vm) {
  const open = sideOpen(vm.ui);
  const label = open ? "Hide side panel" : "Show side panel";
  return '<button type="button" class="btn" data-action="panel-toggle" data-focus="panel-toggle"' +
    ' aria-pressed="' + (open ? "true" : "false") + '" aria-label="' + label +
    '" title="' + label + ' (])"><svg class="ico" aria-hidden="true" focusable="false">' +
    '<use href="/icons.svg#i-panel"></use></svg></button>';
}

// The command palette button (Cmd+K or Ctrl+K opens it too; keys.js handles data-action="palette-open").
function paletteHtml() {
  if (phoneWidth()) return "";
  return '<button type="button" class="btn" data-action="palette-open" data-focus="palette" aria-haspopup="dialog"' +
    ' aria-label="Command palette (Cmd+K or Ctrl+K)" title="Command palette (Cmd+K or Ctrl+K)">⌘K</button>';
}

// The Mark button (localhost only): flag icon and the word, with the full sentence in the name (keys.js handles it).
function markHtml() {
  if (!markAllowed() || phoneWidth()) return "";
  return '<button type="button" class="btn" data-action="mark-bug" data-focus="mark-bug"' +
    ' aria-label="Mark: ' + MARK_LABEL + '" title="' + MARK_LABEL + ' (m)">' +
    '<svg class="ico" aria-hidden="true" focusable="false"><use href="/icons.svg#i-flag"></use></svg>Mark</button>';
}

export function topbarView(vm) {
  const theme = vm.theme || "auto";
  return '<div class="top-row">' + crumbHtml(vm) +
    '<div class="top-tools">' + controlHtml(vm) + metersHtml(vm) + connHtml(vm.conn) + markHtml() + paletteHtml() +
    '<button type="button" class="btn" data-action="cycle-theme" data-focus="theme" aria-label="Theme: ' +
    esc(themeLabel(theme)) + '. Change theme">' + esc(themeLabel(theme)) + "</button>" +
    '<button type="button" class="btn" data-action="help-open" data-focus="help" aria-haspopup="dialog"' +
    ' aria-label="Keyboard shortcuts">?</button>' + panelToggleHtml(vm) +
    "</div></div>";
}
