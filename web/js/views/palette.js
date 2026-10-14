// Command palette (WP61b). Cmd+K or Ctrl+K opens a modal search over the project's tasks, issues and questions, and a
// list of commands: ">stop", ">resume", ">go <section>", ">start <task id>", ">done <task id>". Commands go through
// cmd.js run(), the one write path. Rows are escaped with esc() and handled by delegation, with no inline
// handlers or styles.
import { esc, patch } from "../dom.js";
import { run } from "../cmd.js";
import { buildHash, currentRoute, sectionHash } from "../router.js";
import { SECTIONS, SETTINGS } from "../routes.js";

const LIMIT = 10;
const KIND_LABEL = { task: "task", issue: "issue", question: "question", cmd: "command" };
const TYPED = /^>(start|done)\s+(\S+)/i;

let dialog = null, input = null, list = null, status = null;
let results = [], active = 0, opener = null;
let scopeSnap = null, scopePid = null;

// Cmd+K or Ctrl+K (no Alt, no Shift). Case of the key does not matter.
export function isPaletteKey(e) {
  return Boolean(e) && !e.altKey && !e.shiftKey && (e.metaKey || e.ctrlKey) &&
    String(e.key || "").toLowerCase() === "k";
}

// Lower is better; 0 means no match. Ids rank above titles, and a prefix above a substring.
export function rank(item, q) {
  if (!q) return 1;
  const id = String(item.id || "").toLowerCase(), title = String(item.title || "").toLowerCase();
  if (id === q) return 1;
  if (id.startsWith(q)) return 2;
  if (title.startsWith(q)) return 3;
  if (id.indexOf(q) >= 0) return 4;
  return title.indexOf(q) >= 0 ? 5 : 0;
}

function cmd(id, title, fn) {
  return { id: id, title: title, kind: "cmd", run: fn };
}

function go(section) {
  window.location.hash = sectionHash(currentRoute(), section);
}

function openItem(pid, section, item) {
  window.location.hash = buildHash({ name: "project", id: pid, section: section, item: item });
}

// Commands that act on a project need one; in All projects only the navigation commands are listed.
export function commandsFor(snap, pid) {
  const out = [];
  if (pid) {
    out.push(cmd(">stop", "Stop agents in this project",
      () => run("control.stop", {}, { project: pid, key: "control:" + pid, value: true, label: "Stopped" })));
    out.push(cmd(">resume", "Resume agents in this project",
      () => run("control.resume", {}, { project: pid, key: "control:" + pid, value: false, label: "Resumed" })));
  }
  for (const s of SECTIONS.concat([SETTINGS])) {
    out.push(cmd(">go " + s.id, "Go to " + s.label, () => go(s.id)));
  }
  if (pid) {
    for (const t of (snap && snap.tasks) || []) out.push(...taskCommands(pid, t.id, t.title));
  }
  return out;
}

function taskCommands(pid, id, title) {
  return [
    cmd(">start " + id, title || id,
      () => run("task.start", { id: id }, { project: pid, label: id + " queued to run" })),
    cmd(">done " + id, title || id, () => run("task.status", { id: id, status: "done" },
      { project: pid, label: id + " set to Done" })),
  ];
}

export function itemsFor(snap, pid) {
  if (!pid || !snap) return [];
  const items = [];
  for (const t of snap.tasks || []) {
    items.push({ id: t.id, title: t.title, kind: "task", run: () => openItem(pid, "work", t.id) });
  }
  for (const i of snap.issues || []) {
    items.push({ id: i.id, title: i.title, kind: "issue", run: () => openItem(pid, "issues", i.id) });
  }
  for (const q of snap.questions || []) {
    items.push({ id: q.id, title: q.text, kind: "question", run: () => openItem(pid, "inbox", q.id) });
  }
  return items;
}

// The ranked results for the query text. In command mode (text starts with ">") a typed ">start X" or ">done X"
// adds its command even when X is not in the snapshot, so the server can give the answer.
export function searchPalette(text, snap, pid) {
  const raw = String(text || "").trim(), q = raw.toLowerCase();
  if (!raw.startsWith(">")) {
    return rankAll(itemsFor(snap, pid), q);
  }
  const pool = commandsFor(snap, pid);
  const typed = TYPED.exec(raw);
  if (typed && pid) {
    const id = typed[2];
    const known = ((snap && snap.tasks) || []).some(t => t.id === id);
    if (!known) {
      const verb = ">" + typed[1].toLowerCase();
      pool.push(...taskCommands(pid, id, "Task " + id).filter(c => c.id.toLowerCase().startsWith(verb)));
    }
  }
  return rankAll(pool, q);
}

function rankAll(pool, q) {
  return pool.map(item => ({ item, score: rank(item, q) }))
    .filter(e => e.score > 0)
    .sort((a, b) => a.score - b.score)
    .slice(0, LIMIT)
    .map(e => e.item);
}

function renderResults() {
  input.setAttribute("aria-expanded", results.length ? "true" : "false");
  if (!results.length) {
    input.removeAttribute("aria-activedescendant");
    patch("palette-list", "");
    patch("palette-status", "No matching commands or items.");
    return;
  }
  patch("palette-status", "");
  if (active >= results.length) active = 0;
  input.setAttribute("aria-activedescendant", "palette-opt-" + active);
  patch("palette-list", results.map(function (item, i) {
    const on = i === active;
    return '<div class="row-grid palette-opt' + (on ? " is-active" : "") + '" id="palette-opt-' + i +
      '" role="option" aria-selected="' + (on ? "true" : "false") + '" data-index="' + i + '">' +
      '<span class="palette-id">' + esc(item.id) + "</span>" +
      '<span class="rg-t" title="' + esc(item.title) + '">' + esc(item.title) + "</span>" +
      '<span class="rg-num">' + esc(KIND_LABEL[item.kind] || item.kind) + "</span></div>";
  }).join(""));
}

function refresh(snap, pid) {
  results = searchPalette(input.value, snap, pid);
  active = 0;
  renderResults();
}

function runActive() {
  const item = results[active];
  if (!item) return;
  dialog.close();
  item.run();
}

function move(step) {
  if (!results.length) return;
  active = (active + step + results.length) % results.length;
  renderResults();
  const el = document.getElementById("palette-opt-" + active);
  if (el && el.scrollIntoView) el.scrollIntoView({ block: "nearest" });
}

function onKeyDown(event) {
  if (event.isComposing) return;
  if (event.key === "ArrowDown") {
    event.preventDefault(); move(1);
  } else if (event.key === "ArrowUp") {
    event.preventDefault(); move(-1);
  } else if (event.key === "Enter") {
    event.preventDefault(); runActive();
  } else if (event.key === "Escape") {
    event.preventDefault(); dialog.close();
  } else if (event.key === "Tab") {
    // The input is the only focusable control: Tab keeps focus inside the palette.
    event.preventDefault(); input.focus();
  }
}

function ensureDialog() {
  if (dialog) return;
  dialog = document.createElement("dialog");
  dialog.id = "palette";
  dialog.className = "palette";
  dialog.setAttribute("aria-label", "Command palette");
  const body = document.createElement("div");
  body.className = "palette-body";
  input = document.createElement("input");
  input.id = "palette-input";
  input.type = "text";
  input.autocomplete = "off";
  input.spellcheck = false;
  input.setAttribute("role", "combobox");
  input.setAttribute("aria-label", "Search tasks, issues, questions or type > for commands");
  input.setAttribute("aria-autocomplete", "list");
  input.setAttribute("aria-controls", "palette-list");
  input.setAttribute("aria-expanded", "false");
  list = document.createElement("div");
  list.id = "palette-list";
  list.setAttribute("role", "listbox");
  list.setAttribute("aria-label", "Results");
  status = document.createElement("p");
  status.id = "palette-status";
  status.className = "palette-status";
  status.setAttribute("role", "status");
  body.append(input, list, status);
  dialog.appendChild(body);
  document.body.appendChild(dialog);
  input.addEventListener("input", function () { refresh(scopeSnap, scopePid); });
  dialog.addEventListener("keydown", onKeyDown);
  list.addEventListener("click", function (e) {
    const row = e.target.closest ? e.target.closest("[data-index]") : null;
    if (!row) return;
    active = Number(row.getAttribute("data-index"));
    runActive();
  });
  // A click on the backdrop lands on the dialog itself, since its content is wrapped in .palette-body.
  dialog.addEventListener("click", function (e) { if (e.target === dialog) dialog.close(); });
  dialog.addEventListener("close", function () {
    const back = opener;
    opener = null;
    input.blur();
    if (back && back.isConnected && typeof back.focus === "function") back.focus();
  });
}

// Cmd+K toggles. snapshot is the open project's snapshot (null in All projects, where only navigation commands show).
export function openPalette(snapshot) {
  ensureDialog();
  if (dialog.open) {
    dialog.close();
    return;
  }
  scopeSnap = snapshot || null;
  scopePid = scopeSnap ? scopeSnap.id || null : null;
  opener = document.activeElement;
  input.value = "";
  refresh(scopeSnap, scopePid);
  dialog.showModal();
  input.focus();
}
