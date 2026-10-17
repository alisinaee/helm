// Seen by head (R11.2, docs/PANEL-TO-HEAD.md): the person's newest board actions and whether the head agent got them.
// sent = logged, no head session has read it yet; seen = handed to a head session by a hook or roadmap watch;
// acted = the head acked it, or a later head write names its ref. One collapsed line; it opens to the rows.
// The data comes from GET /api/v1/projects/{pid}/panel, read at most every REFRESH_MS, and patched in place.

import { chipHtml, esc, setHtml } from "../dom.js";
import { getJson } from "../api.js";

const REFRESH_MS = 5000;
const SHOWN = 8;
const TONE = { sent: "warning", seen: "neutral", acted: "success" };
const HEAD_WORD = { watching: "head watching", open: "head session open", none: "no head session" };
const cache = new Map();

function rowHtml(row) {
  const when = String(row.ts || "").slice(11, 16);
  return '<li class="nz-row">' + chipHtml(row.state, TONE[row.state] || "neutral") + ' <span class="nz-kind">' +
    esc(row.id) + "</span> " + esc(when) + " " + esc(row.sum || "") + "</li>";
}

function bodyHtml(data) {
  if (!data || !Array.isArray(data.rows) || !data.rows.length) return "";
  const c = data.counts || {};
  const line = "Sent to head: " + (c.sent || 0) + " sent · " + (c.seen || 0) + " seen · " + (c.acted || 0) +
    " acted (" + (HEAD_WORD[data.head] || "head unknown") + ")";
  return '<details class="hs"><summary>' + esc(line) + '</summary><ul class="nz-list">' +
    data.rows.slice(0, SHOWN).map(rowHtml).join("") + "</ul></details>";
}

async function refresh(pid) {
  const entry = cache.get(pid);
  entry.at = Date.now();
  try {
    const res = await getJson("/api/v1/projects/" + encodeURIComponent(pid) + "/panel");
    if (res.data) entry.data = res.data;
  } catch (err) {
    return;
  }
  if (typeof document === "undefined") return;
  const node = document.querySelector('[data-headseen="' + pid + '"]');
  if (!node) return;
  const open = node.querySelector("details[open]");
  setHtml(node, bodyHtml(entry.data));
  if (open && node.querySelector("details")) node.querySelector("details").open = true;
}

// The strip for one project: the last known rows now, a fresh read in the background.
export function headSeenHtml(pid) {
  if (!pid) return "";
  if (!cache.has(pid)) cache.set(pid, { at: 0, data: null });
  const entry = cache.get(pid);
  if (Date.now() - entry.at > REFRESH_MS) refresh(pid);
  return '<div data-headseen="' + esc(pid) + '">' + bodyHtml(entry.data) + "</div>";
}
