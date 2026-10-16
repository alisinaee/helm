// System map side panel (R10.24, A6): the facts of the selected component, as a string. system.js docks it at the
// right edge. The API gives the globs, a file count and the heat counts (commits in 30 days, last commit, open Work,
// running jobs, bugs); it does not list files, commits or task ids, so the links go to the Work and Git views.

import { chipHtml, esc } from "../dom.js";

function row(label, value) {
  return "<dt>" + label + "</dt><dd>" + value + "</dd>";
}

function num(v) {
  const n = Number(v);
  return Number.isFinite(n) && n > 0 ? n : 0;
}

export function panelHtml(pid, comp, heat) {
  if (!comp) return "";
  const h = Object.assign({}, comp.heat && typeof comp.heat === "object" ? comp.heat : {}, heat || {});
  const globs = (Array.isArray(comp.files) ? comp.files : []).map((g) => "<li><code class=\"code\">" + esc(g) +
    "</code></li>").join("");
  const base = "#/p/" + encodeURIComponent(pid);
  const last = typeof h.lastAt === "string" ? esc(h.lastAt.slice(0, 10)) : "none";
  return '<aside class="side-body sys-panel" aria-label="Component ' + esc(comp.name || comp.id) + '">' +
    '<h2>' + esc(comp.name || comp.id) + "</h2><p>" + chipHtml(comp.layer || "other") +
    ' <button type="button" class="btn btn-small" data-sys-op="close" aria-label="Close panel (Esc)">Close</button>' +
    "</p>" + (comp.notes ? "<p>" + esc(comp.notes) + "</p>" : "") + "<dl>" +
    row("Files", num(comp.fileCount)) + (comp.entry ? row("Entry", "<code class=\"code\">" + esc(comp.entry) +
      "</code>") : "") + row("Commits (30 days)", num(h.commits30 !== undefined ? h.commits30 : h.commits)) +
    row("Last commit", last) + row("Running jobs", num(h.runningJobs !== undefined ? h.runningJobs : h.jobs)) +
    row("Open Work", num(h.openWork !== undefined ? h.openWork : h.work)) + row("Bugs", num(h.bugs)) + "</dl>" +
    "<h3>Paths</h3><ul>" + (globs || "<li>none</li>") + "</ul>" + '<p><a href="' + base +
    '/work">Work items</a> · <a href="' + base + '/git">Commits in Git</a></p></aside>';
}
