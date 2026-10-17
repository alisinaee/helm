// Top bar (WP28, R7.28 W1.d, R11.129): the scope crumb (project name, section, view), the control pill with one Stop or
// Resume button, the 5h and W usage mini bars (stop tick, title with the share and the stop), the connection dot, the
// theme toggle and "?". A stale reading shows its age and an Enter usage link. The client does no limit maths;
// missing values read "unknown".

import { csrfToken } from "../api.js";
import { esc } from "../dom.js";
import { fmtPercent } from "../format.js";
import { mark, status as logStatus } from "../log.js";
import { SECTIONS, SETTINGS, sectionById } from "../routes.js";
import { sectionHash } from "../router.js";
import { panelIsOpen } from "../state.js";
import { showToast } from "./toast.js";
import { weeklyStopRow } from "./limits.js";

const THEME_LABEL = { auto: "Auto", dark: "Dark", light: "Light" };
const MARK_LABEL = "I am seeing a bug here";
const LOCAL_HOST = /^(localhost|127\.0\.0\.1|\[::1\])$/;

// The Mark button, the m key and the palette command exist only on localhost with a CSRF value (the phone has none).
export function markAllowed() {
  if (typeof window === "undefined" || typeof location === "undefined") return false;
  return LOCAL_HOST.test(location.hostname) && Boolean(csrfToken());
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

// Stop for one window from the meter rows, read defensively: a five-hour row (window five_hour / 5h) or, when
// there is none, the weekly stop. Null when no stop is set.
function stopFor(vm, win) {
  const rows = limitRows(vm.meterRows) || [];
  const stops = vm.limits && vm.limits.stops ? vm.limits.stops : (vm.stops || null);
  if (stops && typeof stops[win] === "number") return stops[win];
  if (win === "five") {
    const hit = rows.filter(function (r) {
      return typeof r.limit === "number" && /^(five_hour|5h|five)/.test(String(r.window || ""));
    });
    if (hit.length) return hit.reduce(function (a, b) { return b.limit < a.limit ? b : a; }).limit;
  }
  const row = bindingStopRow(rows);
  return row && typeof row.limit === "number" ? row.limit : null;
}

function clockOf(iso) {
  const at = iso ? new Date(iso) : null;
  if (!at || isNaN(at.getTime())) return "";
  const pad = function (n) { return (n < 10 ? "0" : "") + n; };
  return pad(at.getHours()) + ":" + pad(at.getMinutes());
}

// Tone of a mini bar: danger at the stop, warning from stop - 10, else none.
export function miniTone(pct, stop) {
  if (typeof pct !== "number" || typeof stop !== "number") return "";
  if (pct >= stop) return " tone-danger";
  return pct >= stop - 10 ? " tone-warning" : "";
}

function miniHtml(vm, id, label, long, pct, stop, resets) {
  const known = typeof pct === "number";
  const tone = miniTone(pct, stop);
  const text = known ? fmtPercent(pct) : "unknown";
  const when = clockOf(resets);
  const title = long + " " + text + (stop !== null ? ", stop at " + fmtPercent(stop) : ", no stop") +
    (when ? ", resets " + when : "") + (ageText(vm.usage) ? "; updated " + ageText(vm.usage) : "");
  const tick = stop !== null ? '<span class="mini-tick" data-pct="' + esc(Math.min(100, stop)) + '"></span>' : "";
  return '<span class="mini' + (known ? "" : " is-unknown") + '" data-win="' + id + '" title="' + esc(title) + '">' +
    '<span class="mini-l">' + label + '</span><span class="meter' + tone + '"><span class="meter-fill" data-pct="' +
    (known ? esc(Math.min(100, Math.max(0, pct))) : 0) + '"></span>' + tick + '</span><span class="mini-v">' +
    esc(text) + "</span></span>";
}

// The usage widget: account chip (more than one account only), 5h and W mini bars, one link to Tokens > Limits.
// Stale is the usage view's flag (the 90-minute rule): then the age is written out and Enter usage is offered. The
// weekly share unknown (no reading, or no weekly figure) offers Enter usage too.
function metersHtml(vm) {
  const u = vm.usage || null;
  const stale = Boolean(u && u.stale === true);
  const accts = Array.isArray(vm.accounts) ? vm.accounts : [];
  const chip = accts.length > 1 ? '<span class="chip top-acct" title="Account">' +
    esc(String(accts[0].name || accts[0].id || "account").replace(/(.{2}).*(.{2})/, "$1…$2")) + "</span>" : "";
  const href = sectionHash(vm.route, "tokens") + "/limits";
  const age = stale ? '<span class="top-age chip-warning">' + esc(ageText(Object.assign({}, u, { stale: true }))) +
    "</span>" : "";
  const enter = stale || !u || typeof u.weeklyPercent !== "number" ? enterHtml(vm) : "";
  return chip + '<a class="top-meters' + (stale ? " is-stale" : "") + '" href="' + esc(href) +
    '" data-focus="usage" aria-label="Usage and limits">' +
    miniHtml(vm, "5h", "5h", "5 hours", u ? u.fiveHourPercent : null, stopFor(vm, "five"), u && u.fiveHourResetsAt) +
    miniHtml(vm, "w", "W", "Week", u ? u.weeklyPercent : null, stopFor(vm, "week"), u && u.weeklyResetsAt) +
    (stale ? '<span class="dot top-stale" aria-hidden="true"></span>' : "") + "</a>" + age + enter;
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

// More menu (native details): the theme cycle lives here. Cmd+K and m stay keys and palette commands.
function moreHtml(theme) {
  return '<details class="top-more"><summary class="btn" aria-label="More" title="More">' +
    '<svg class="ico" aria-hidden="true" focusable="false"><use href="/icons.svg#i-more"></use></svg></summary>' +
    '<div class="top-menu"><button type="button" class="btn" data-action="cycle-theme" data-focus="theme"' +
    ' aria-label="Change theme">Theme: ' + esc(themeLabel(theme)) + "</button></div></details>";
}

export function topbarView(vm) {
  const theme = vm.theme || "auto";
  return '<div class="top-row">' + crumbHtml(vm) +
    '<div class="top-tools">' + controlHtml(vm) + metersHtml(vm) + connHtml(vm.conn) +
    '<button type="button" class="btn" data-action="help-open" data-focus="help" aria-haspopup="dialog"' +
    ' aria-label="Keyboard shortcuts">?</button>' + panelToggleHtml(vm) + moreHtml(theme) +
    "</div></div>";
}
