// Extras: the spike board and the real-hardware board. Shown only when the snapshot has them.
// Each item is a chip with a glyph and its id; the glyph and the id carry the state, not the colour alone.

import { esc, sectionHtml } from "../dom.js";
import { fmtCount } from "../format.js";

const GLYPH = { done: "✓", partial: "◐", todo: "○" };
const KIND = { done: "success", partial: "warning", todo: "neutral" };

function passed(items) {
  return items.filter(function (item) {
    return item.state === "done";
  }).length;
}

function boardHtml(label, items) {
  const chips = items.map(function (item) {
    const state = GLYPH[item.state] ? item.state : "todo";
    const tip = item.id + " " + item.label + (item.status ? " - " + item.status : "");
    return '<span class="chip chip-' + KIND[state] + '" title="' + esc(tip) + '">' + GLYPH[state] + " " +
      esc(item.id) + "</span>";
  }).join("");
  return '<div class="board"><p class="sub-head">' + esc(label) + " · " + fmtCount(passed(items)) + "/" +
    fmtCount(items.length) + " passed</p><div class=\"chip-grid\">" + chips + "</div></div>";
}

export function extrasSection(vm) {
  const snap = vm.project.snapshot;
  if (!snap.spikes.length && !snap.rh.length) return "";
  const parts = [];
  if (snap.spikes.length) {
    parts.push("Research spikes: " + fmtCount(passed(snap.spikes)) + "/" + fmtCount(snap.spikes.length));
  }
  if (snap.rh.length) parts.push("Hardware checks: " + fmtCount(passed(snap.rh)) + "/" + fmtCount(snap.rh.length));
  const body = (snap.spikes.length ? boardHtml("Spike board", snap.spikes) : "") +
    (snap.rh.length ? boardHtml("Real-hardware board", snap.rh) : "");
  return sectionHtml({ id: "extras", title: "Extras", summary: parts.join(" · ") + " passed",
    open: vm.open.extras, body: body });
}
