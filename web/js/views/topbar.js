// Top bar (WP28, R7.28 W1.d): the scope crumb (project name, section, view), the control pill with one Stop or Resume
// button, one text line "Week 63% · stop 95%" (the weekly share from snap.usage and the weekly stop row), the
// connection dot, the theme toggle and "?". The client does no limit maths; missing values read "unknown".

import { csrfToken } from "../api.js";
import { esc } from "../dom.js";
import { fmtPercent } from "../format.js";
import { mark, status as logStatus } from "../log.js";
import { SECTIONS, SETTINGS, sectionById } from "../routes.js";
import { sectionHash } from "../router.js";
import { panelIsOpen } from "../state.js";
import { showToast } from "./toast.js";
import { weekKnown, weeklyStopRow } from "./limits.js";

const THEME_LABEL = { auto: "Auto", dark: "Dark", light: "Light" };
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

// The weekly stop shown in the top bar: the lowest weekly stop row, the project's own (autonomy.json
// limit.stopAtPercent, an acct row, also when its action is warn) or the global percent on the week. The lower one is
// the real stop (R7.77). A warn-only stop still has a value, so it shows as "stop 15%". Else the Tokens rule.
export function bindingStopRow(rows) {
  if (!Array.isArray(rows)) return null;
  const weekly = rows.filter(function (r) {
    const isWeekly = r.kind === "acct" || (r.scope === "global" && r.kind === "pct" && r.window === "week");
    return isWeekly && typeof r.limit === "number";
  });
  if (!weekly.length) return weeklyStopRow(rows);
  return weekly.reduce(function (a, b) { return b.limit < a.limit ? b : a; });
}

// The limit rows of a snapshot's meters: the snapshot carries {limits, today, week}, a plain list is taken as is.
// Null when there are no meters at all (unknown).
function limitRows(meters) {
  if (Array.isArray(meters)) return meters;
  if (meters && Array.isArray(meters.limits)) return meters.limits;
  return null;
}

// The weekly stop from the meter rows: "stop 85%", "stop off", or unknown when the snapshot has no meters at all.
function stopText(meters) {
  const rows = limitRows(meters);
  if (rows === null) return "stop unknown";
  const row = bindingStopRow(rows);
  return row ? "stop " + fmtPercent(row.limit) : "stop off";
}

// The age of the reading in short words: "3m", "2h". Used by ageText.
function shortAge(s) {
  return s < 3600 ? Math.floor(s / 60) + "m" : Math.round(s / 3600) + "h";
}

// The reading age: "just now", "3m ago" when fresh; "stale 2h" when older than maxUsageAgeMin (the stale flag from
// the usage view, which reads the limit from docs/autonomy.json or 90 minutes). Empty when the age is not known.
export function ageText(usage) {
  if (!usage) return "";
  const s = typeof usage.ageNow === "number" ? Math.max(0, usage.ageNow) : null;
  if (usage.stale === true) return s === null ? "stale" : "stale " + shortAge(s);
  if (s === null) return "";
  return s < 60 ? "just now" : shortAge(s) + " ago";
}

// The clock time of the last reading (HH:MM, local time), or "" when the stored time cannot be read.
export function readingTime(usage) {
  const at = usage && usage.updated ? new Date(usage.updated) : null;
  if (!at || isNaN(at.getTime())) return "";
  const pad = function (n) { return (n < 10 ? "0" : "") + n; };
  return pad(at.getHours()) + ":" + pad(at.getMinutes());
}

// The chip tooltip: the 5-hour share, and where the usage comes from and when it was last read.
export function meterTitle(usage) {
  const five = usage && typeof usage.fiveHourPercent === "number" ? fmtPercent(usage.fiveHourPercent) : "unknown";
  const when = readingTime(usage);
  const last = when ? "usage is pushed by the head; last reading at " + when : "usage is pushed by the head";
  return "5-hour " + five + " · " + last;
}

// "Week 63% · stop 95% · 3m ago": the weekly share (snap.usage), the weekly stop and the reading age. Pure, so the
// render test can check it. A missing weekly share reads "Week unknown". A stale reading keeps its last share and
// says "stale 2h" (the chip shows in warning style, see metersHtml).
export function meterText(usage, rows) {
  const pct = usage && typeof usage.weeklyPercent === "number" ? fmtPercent(usage.weeklyPercent) : null;
  const week = pct !== null ? "Week " + pct : "Week unknown";
  const age = ageText(usage);
  return week + " · " + stopText(rows) + (age ? " · " + age : "");
}

// The one action when the weekly share is unknown or stale: open the Tokens screen, where the usage entry form is.
function enterHtml(vm) {
  return '<a class="btn top-enter" href="' + esc(sectionHash(vm.route, "tokens")) + '" data-focus="enter-usage">' +
    "Enter usage</a>";
}

function metersHtml(vm) {
  const stale = Boolean(vm.usage && vm.usage.stale === true);
  return '<span class="top-meters' + (stale ? " chip-warning" : "") + '" title="' +
    esc(meterTitle(vm.usage)) + '">' + esc(meterText(vm.usage, vm.meterRows)) + "</span>" +
    (weekKnown(vm.usage) ? "" : enterHtml(vm));
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
