// Next up: the queued items from the roadmap, as plain text (the markdown bold and code marks are removed).

import { esc, sectionHtml } from "../dom.js";
import { copyButton, refSummary } from "../ref.js";

export function plainText(value) {
  return String(value == null ? "" : value).replace(/\*\*/g, "").replace(/`/g, "");
}

// Adds a section copy-reference button to a sectionHtml() header, after the toggle (a sibling, never nested in it).
// refId is "<module>.<section>"; count is the number of items the section lists. No project slug, no button.
export function sectionRef(html, project, refId, title, count) {
  const button = copyButton("section", refId, title, { project: project, sum: refSummary("section", count) });
  return html.replace("</button></h2>", "</button>" + button + "</h2>");
}

export function nextSection(vm) {
  const items = vm.project.snapshot.next.map(plainText);
  const body = items.length
    ? '<ol class="next-list">' + items.map(function (item) {
      return "<li>" + esc(item) + "</li>";
    }).join("") + "</ol>"
    : '<p class="placeholder">Nothing is queued. <a href="#/p/' + esc(vm.route.id) +
      '/roadmap">Open Roadmap</a> to see the open tasks.</p>';
  const html = sectionHtml({
    id: "next",
    title: "Next up",
    summary: items.length ? items[0] : "Nothing queued",
    open: vm.open.next,
    body: body,
  });
  return sectionRef(html, vm.project.snapshot.id, "next.next", "Next up", items.length);
}
