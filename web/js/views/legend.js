// Legend: what the glyphs, chips and token figures mean. Collapsed by default.

import { chipHtml, esc, sectionHtml } from "../dom.js";
import { STATE_GLYPH, STATE_WORD } from "./tasks.js";

const ROWS = [
  [STATE_GLYPH.done + " " + STATE_WORD.done, "finished and proven"],
  [STATE_GLYPH.partial + " " + STATE_WORD.partial, "Built; verification pending"],
  [STATE_GLYPH.todo + " " + STATE_WORD.todo, "not started"],
  [STATE_GLYPH.hold + " " + STATE_WORD.hold, "waiting on a decision"],
  [STATE_GLYPH.deferred + " " + STATE_WORD.deferred, "Deferred; excluded from task count"],
  ["▶ running", "a job is working on this phase or task"],
  ["~40k", "Estimated tokens; dash indicates unestimated"],
  ["✓ model ~15k", "Verification step, model, and estimate"],
  ["needs you", "Task waiting for your input"],
];

function legendHtml() {
  const rows = ROWS.map(function (row) {
    return "<dt>" + esc(row[0]) + "</dt><dd>" + esc(row[1]) + "</dd>";
  }).join("");
  const models = ["haiku", "sonnet", "opus", "cursor", "agy"].map(function (m) {
    return chipHtml(m, m);
  }).join(" ");
  return '<dl class="legend-list">' + rows + "</dl>" +
    '<p class="sub-head">Execution models</p><div class="chip-grid">' + models + "</div>";
}

export function legendSection(vm) {
  return sectionHtml({
    id: "legend",
    title: "Legend",
    summary: "Icons, badges, and token estimates",
    open: vm.open.legend,
    body: legendHtml(),
  });
}
