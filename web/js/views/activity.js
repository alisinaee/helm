// Activity (WP30): the activity lines, newest first. In a project it is that project's lines; in All projects the lines
// of every project are merged by time (50 at most). Each line that can be undone has an Undo button (op undo). Source
// filters are LATER. The snapshot keeps the newest 15 lines per project, so that is what this page can show.

import { chipHtml, emptyHtml, esc } from "../dom.js";
import { MISSING, relTime } from "../format.js";
import { pageState, scopeSnapshots } from "./inbox.js";

const ALL_MAX = 50;

// One activity line as a list item. The Undo button is shown only when the line says it can be undone.
export function activityRowHtml(line, pid, pname, now, showProject) {
  const when = relTime(line.atMs, now);
  const undo = line.undo
    ? '<button type="button" class="btn btn-small" data-action="undo-line" data-project="' + esc(pid) +
      '" data-activity="' + esc(line.id) + '" data-focus="undo-' + esc(pid) + "-" + esc(line.id) + '">Undo</button>'
    : "";
  return '<li class="act-row"><span class="act-time num" title="' + esc(when.title) + '">' +
    esc(when.text || MISSING) + "</span>" +
    '<span class="act-main"><span class="act-sum">' + esc(line.sum || line.op || "Change") + "</span> " +
    chipHtml(line.src || "source", "neutral") +
    (showProject ? " " + chipHtml(pname, "neutral") : "") + "</span>" + undo + "</li>";
}

// The lines in view, newest first: [{line, pid, pname}].
export function mergedLines(scopes, limit) {
  const all = [];
  for (const s of scopes) {
    for (const line of s.snap.activity) all.push({ line: line, pid: s.id, pname: s.name });
  }
  all.sort(function (a, b) {
    return (b.line.atMs == null ? -Infinity : b.line.atMs) - (a.line.atMs == null ? -Infinity : a.line.atMs);
  });
  return limit ? all.slice(0, limit) : all;
}

export function sectionView(vm) {
  const state = pageState(vm);
  if (state) return state;
  const scopes = scopeSnapshots(vm);
  const showProject = vm.route.name !== "project";
  const now = Date.now();
  const lines = mergedLines(scopes, showProject ? ALL_MAX : 0);
  const note = showProject ? "Newest first. Each project keeps its last 15 lines." : "Newest first, 50 at most.";
  const body = lines.length
    ? '<ol class="act-list">' + lines.map(function (entry) {
      return activityRowHtml(entry.line, entry.pid, entry.pname, now, showProject);
    }).join("") + "</ol>"
    : emptyHtml("No activity yet.");
  return '<div class="page-head"><h2 class="page-title">Activity</h2><p class="page-note">' + esc(note) + "</p></div>" +
    '<section class="ov-card" aria-label="Activity lines">' + body + "</section>";
}
