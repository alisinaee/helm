// Copy reference (R7.12): the board ref (rb:<project>/<kind>/<id>), the one-line state summary a button carries,
// and the copy itself. Values come from the snapshot already in the browser; nothing is fetched.
// Markup goes through esc().
// The button is a global action: app.js onClick handles data-action="copy-ref", so no inline handler is needed.

import { esc } from "./dom.js";
import { showToast } from "./views/toast.js";

const REF_RE = /^rb:[a-z0-9-]+(\/[a-z]+\/[A-Za-z0-9._-]+)?$/;
const TEXT_MAX = 200;
const TITLE_MAX = 40;

// Collapse white space and cut to max characters, ending in "..." when cut.
function cut(value, max) {
  const text = String(value == null ? "" : value).replace(/\s+/g, " ").trim();
  return text.length > max ? text.slice(0, Math.max(0, max - 3)) + "..." : text;
}

function quoted(title) {
  return '"' + cut(String(title == null ? "" : title).replace(/"/g, "'"), TITLE_MAX) + '"';
}

// The ref string, or "" when the project or an id has a character a ref may not hold (so no path can get in).
export function refOf(project, kind, id) {
  const slug = String(project || "");
  if (!slug) return "";
  const tail = kind === "project" || !kind ? "" : "/" + kind + "/" + String(id == null ? "" : id);
  const ref = "rb:" + slug + tail;
  return REF_RE.test(ref) ? ref : "";
}

// The one-line state of an item, e.g. task "Planner filters" status=doing feature=F7 orphan=no subs=2/5.
// snap is the browser snapshot; it gives the orphan flag for a task (features.orphans) when it is there.
export function refSummary(kind, item, snap) {
  if (!item) return "";
  const feats = Array.isArray(item.feats) ? item.feats : [];
  if (kind === "task") {
    const orphans = snap && snap.features && Array.isArray(snap.features.orphans) ? snap.features.orphans : null;
    const orphan = orphans ? orphans.indexOf(item.id) >= 0 : feats.length === 0;
    const subs = Array.isArray(item.subs) ? item.subs : [];
    const done = subs.filter(function (s) {
      return s.d === true;
    }).length;
    return "task " + quoted(item.title) + " status=" + (item.state || "todo") + " feature=" +
      (feats.join(",") || "none") + " orphan=" + (orphan ? "yes" : "no") + " subs=" + done + "/" + subs.length;
  }
  if (kind === "phase") {
    return "phase " + quoted(item.name || item.title) + " status=" + (item.state || "todo") + " done=" +
      (item.done || 0) + "/" + (item.total || 0);
  }
  if (kind === "feature") {
    const tasks = Array.isArray(item.tasks) ? item.tasks.length : 0;
    return "feature " + quoted(item.title) + " status=" + (item.state || "todo") + " tasks=" + tasks;
  }
  if (kind === "issue") {
    return "issue " + quoted(item.title) + " status=" + (item.status || "open") + " sev=" +
      (item.sev == null ? "none" : item.sev);
  }
  if (kind === "question") {
    return "question " + quoted(item.text) + " status=" + (item.answered ? "answered" : "open");
  }
  if (kind === "job") {
    const tokens = typeof item.tokensK === "number" ? item.tokensK + "K" : "none";
    return "job " + quoted(item.title) + " state=" + (item.status || "none") + " model=" + (item.model || "none") +
      " tokens=" + tokens;
  }
  if (kind === "sub") {
    return "sub " + quoted(item.t) + " done=" + (item.d === true ? "yes" : "no");
  }
  if (kind === "research") {
    return "research " + quoted(item.title || item.text);
  }
  if (kind === "section" || kind === "view") {
    const count = typeof item === "number" ? item : item.count;
    return kind + " count=" + (count == null ? 0 : count);
  }
  return "";
}

// The clipboard text: the ref on line one, the summary on line two, at most 200 characters in all.
export function refText(ref, summary) {
  const head = String(ref || "");
  const line = String(summary || "").replace(/\s+/g, " ").trim();
  if (!line) return head;
  const room = TEXT_MAX - head.length - 1;
  const fitted = line.length > room ? line.slice(0, Math.max(0, room - 3)) + "..." : line;
  return head + "\n" + fitted;
}

// The copy button markup. Its data-ref and data-sum are read back by copyRef(). Keep it a sibling of a toggle button.
export function refButtonHtml(ref, label, summary) {
  return '<button type="button" class="ref-copy" data-action="copy-ref" data-ref="' + esc(ref) +
    '" data-sum="' + esc(summary || "") + '" aria-label="Copy reference to ' + esc(label) +
    '"><svg class="ico" aria-hidden="true" focusable="false"><use href="/icons.svg#i-copy"/></svg></button>';
}

// Button markup for a row or section. opts: { project, sum }. Returns "" when no valid ref can be built.
export function copyButton(kind, id, label, opts) {
  const o = opts || {};
  const ref = refOf(o.project, kind, id);
  return ref ? refButtonHtml(ref, label, o.sum) : "";
}

// Without a clipboard (plain http, an old browser) the text goes in a read-only field inside the toast, selected.
function fallback(text) {
  const id = showToast({ text: "Press and hold to copy" });
  const toast = document.querySelector('[data-toast="' + id + '"]');
  if (!toast) return;
  const field = document.createElement("input");
  field.type = "text";
  field.readOnly = true;
  field.value = text;
  field.className = "ref-text";
  field.setAttribute("aria-label", "Reference text");
  toast.appendChild(field);
  field.focus();
  field.select();
}

// Copy the reference on the button el. Success shows the "Copied" toast.
export function copyRef(el) {
  const text = refText(el.getAttribute("data-ref"), el.getAttribute("data-sum"));
  if (!text) return;
  const nav = typeof navigator !== "undefined" ? navigator : null;
  if (!nav || !nav.clipboard || typeof nav.clipboard.writeText !== "function") {
    fallback(text);
    return;
  }
  nav.clipboard.writeText(text).then(function () {
    showToast({ text: "Copied" });
  }, function () {
    fallback(text);
  });
}
