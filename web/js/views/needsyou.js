// Needs you: the open tasks whose needsUser flag is set (the same count as the summary's need_user), as task rows.

import { sectionHtml } from "../dom.js";
import { fmtCount } from "../format.js";
import { taskListHtml } from "./tasks.js";

export function needsSection(vm) {
  const tasks = vm.project.snapshot.tasks.filter(function (t) {
    return t.needsUser && t.state !== "done";
  });
  const summary = tasks.length ? fmtCount(tasks.length) + " awaiting action" : "Nothing waiting on you";
  const body = tasks.length
    ? '<div class="needs-list">' + taskListHtml(tasks) + "</div>"
    : '<p class="placeholder">No actions pending.</p>';
  return sectionHtml({ id: "needs", title: "Needs you", summary: summary, open: vm.open.needs, body: body });
}
