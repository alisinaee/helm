// Legend: what the glyphs, chips and token figures mean. Collapsed by default.

import { chipHtml, esc, sectionHtml } from "../dom.js";
import { STATE_GLYPH, STATE_WORD } from "./tasks.js";

const ROWS = [
  [STATE_GLYPH.done + " " + STATE_WORD.done, "finished and proven"],
  [STATE_GLYPH.partial + " " + STATE_WORD.partial, "built, not fully proven yet"],
  [STATE_GLYPH.todo + " " + STATE_WORD.todo, "not started"],
  [STATE_GLYPH.hold + " " + STATE_WORD.hold, "waiting on a decision"],
  [STATE_GLYPH.deferred + " " + STATE_WORD.deferred, "parked; not counted in tasks left"],
  ["▶ running", "a job is working on this phase or task"],
  ["~40k", "estimated tokens for the work; – means no value"],
  ["✓ model ~15k", "the check after the work, with its own model and estimate"],
  ["needs you", "this task waits for the person"],
];

function legendHtml() {
  const rows = ROWS.map(function (row) {
    return "<dt>" + esc(row[0]) + "</dt><dd>" + esc(row[1]) + "</dd>";
  }).join("");
  const models = ["haiku", "sonnet", "opus", "cursor", "agy"].map(function (m) {
    return chipHtml(m, m);
  }).join(" ");
  return '<dl class="legend-list">' + rows + "</dl>" +
    '<p class="sub-head">Models that do the work</p><div class="chip-grid">' + models + "</div>";
}

export function legendSection(vm) {
  return sectionHtml({
    id: "legend",
    title: "Legend",
    summary: "Glyphs, chips and token estimates",
    open: vm.open.legend,
    body: legendHtml(),
  });
}
