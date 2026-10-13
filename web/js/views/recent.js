// Recent progress: the newest rows of the roadmap log. The summary is the newest row, in one line.

import { esc, sectionHtml } from "../dom.js";
import { plainText } from "./next.js";

function dateOf(value) {
  return String(value || "").slice(5);
}

export function recentSection(vm) {
  const log = vm.project.snapshot.log;
  const summary = log.length ? dateOf(log[0].date) + " " + plainText(log[0].text) : "No log rows";
  const body = log.length
    ? '<ul class="log-list">' + log.map(function (row) {
      return '<li class="log-row"><span class="log-date num">' + esc(dateOf(row.date)) + "</span>" +
        "<span>" + esc(plainText(row.text)) + "</span></li>";
    }).join("") + "</ul>"
    : '<p class="placeholder">No log rows.</p>';
  return sectionHtml({ id: "recent", title: "Recent progress", summary: summary, open: vm.open.recent, body: body });
}
