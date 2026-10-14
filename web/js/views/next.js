// Next up: the queued items from the roadmap, as plain text (the markdown bold and code marks are removed).

import { esc, sectionHtml } from "../dom.js";

export function plainText(value) {
  return String(value == null ? "" : value).replace(/\*\*/g, "").replace(/`/g, "");
}

export function nextSection(vm) {
  const items = vm.project.snapshot.next.map(plainText);
  const body = items.length
    ? '<ol class="next-list">' + items.map(function (item) {
      return "<li>" + esc(item) + "</li>";
    }).join("") + "</ol>"
    : '<p class="placeholder">Queue is empty.</p>';
  return sectionHtml({
    id: "next",
    title: "Next up",
    summary: items.length ? items[0] : "Nothing queued",
    open: vm.open.next,
    body: body,
  });
}
