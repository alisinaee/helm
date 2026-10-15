// Research (WP34): the project's research notes (read only, from GET /api/v1/projects/{id}/notes) with a plain-text
// reader, and the onboarding checklist for a project. Note text is shown escaped and preformatted, never as markup.
// Requests are made here; when one finishes, the view asks app.js to draw again with a "rb:render" event.

import { getJson } from "../api.js";
import { chipHtml, emptyHtml, esc } from "../dom.js";
import { MISSING, fmtCount } from "../format.js";
import { copyButton, refSummary } from "../ref.js";
import { pageState } from "./inbox.js";
import { projectHash } from "../router.js";

const lists = new Map();   // project id -> {state: loading|ready|error, notes, message}
const texts = new Map();   // "project/name" -> {state, text, message}
let selected = null;       // {pid, name} of the note open in the reader

function requestRender() {
  document.dispatchEvent(new Event("rb:render"));
}

function notesUrl(pid) {
  return "/api/v1/projects/" + encodeURIComponent(pid) + "/notes";
}

async function loadList(pid) {
  lists.set(pid, { state: "loading" });
  try {
    const reply = await getJson(notesUrl(pid));
    lists.set(pid, { state: "ready", notes: Array.isArray(reply.data.notes) ? reply.data.notes : [] });
  } catch (err) {
    lists.set(pid, { state: "error", message: err.message || "The notes could not be loaded." });
  }
  requestRender();
}

async function loadText(pid, name) {
  const key = pid + "/" + name;
  texts.set(key, { state: "loading" });
  try {
    const response = await fetch(notesUrl(pid) + "/" + encodeURIComponent(name),
      { headers: { Accept: "text/plain" }, credentials: "same-origin" });
    if (!response.ok) throw new Error("The note could not be read (HTTP " + response.status + ").");
    texts.set(key, { state: "ready", text: await response.text() });
  } catch (err) {
    texts.set(key, { state: "error", message: err.message || "The note could not be read." });
  }
  requestRender();
}

// The onboarding steps for a project, each ticked from its snapshot when the snapshot shows it.
export function onboardingSteps(snap) {
  const phase = snap.phases && snap.phases[0];
  return [
    { title: "Register the project", done: true, hint: "roadmap project add <path>" },
    { title: "Import the plan", done: snap.tasks.length > 0, hint: "roadmap plan import <file>" },
    { title: "Set the rules", done: Array.isArray(snap.rules) && snap.rules.length > 0,
      hint: "Rules section: add at least one rule" },
    { title: "Approve phase 1", done: Boolean(phase && phase.approved),
      hint: "Roadmap section: approve the first phase" },
  ];
}

function checklistHtml(steps) {
  const doneCount = steps.filter(function (s) {
    return s.done;
  }).length;
  return '<section class="ov-card" aria-label="Onboarding checklist"><h3 class="ov-h">Onboarding ' +
    esc(fmtCount(doneCount)) + " of " + steps.length + "</h3><ol class=\"act-list\">" + steps.map(function (s) {
      return '<li class="act-row"><span>' + chipHtml(s.done ? "Done" : "To do", s.done ? "success" : "neutral") +
        '</span><span class="act-main"><span class="act-sum">' + esc(s.title) + "</span><br>" +
        '<span class="ov-sum">' + esc(s.hint) + "</span></span></li>";
    }).join("") + "</ol></section>";
}

function noteRowHtml(note, pid) {
  const isOpen = selected !== null && selected.pid === pid && selected.name === note.name;
  const lines = note.lines == null ? MISSING : fmtCount(note.lines) + " lines";
  return '<li class="note-row row-grid"><button type="button" class="btn" aria-pressed="' +
    (isOpen ? "true" : "false") +
    '" data-action="note-open" data-project="' + esc(pid) + '" data-name="' + esc(note.name) +
    '" data-focus="note-' + esc(pid) + "-" + esc(note.name) + '">' +
    '<span class="note-main"><span class="act-sum rg-t">' + esc(note.title || note.name) + '</span>' +
    '<span class="ov-sum rg-t">' + esc(note.name) + "</span></span>" +
    '<span class="ov-sum rg-num">' + esc(note.size == null ? MISSING : fmtCount(note.size) + " bytes") + "</span>" +
    '<span class="ov-sum rg-num">' + esc(lines) + "</span></button>" +
    copyButton("research", note.name, note.title || note.name, { project: pid, sum: refSummary("research", note) }) +
    "</li>";
}

function readerHtml(pid) {
  if (selected === null || selected.pid !== pid) return "";
  const key = pid + "/" + selected.name;
  const entry = texts.get(key) || { state: "loading" };
  let body;
  if (entry.state === "ready") {
    body = '<pre class="note-text" tabindex="0">' + esc(entry.text) + "</pre>";
  } else if (entry.state === "error") {
    body = '<p class="ov-sum" role="alert">' + esc(entry.message) + "</p>";
  } else {
    body = '<p class="ov-sum">Loading the note.</p>';
  }
  return '<section class="ov-card" aria-label="Note text"><h3 class="ov-h">' + esc(selected.name) + "</h3>" + body +
    "</section>";
}

// The section copy button for the note list, once the list has loaded (its count is then known).
function notesCopy(pid) {
  const entry = lists.get(pid);
  if (!entry || entry.state !== "ready") return "";
  return copyButton("section", "research.list", "research notes",
    { project: pid, sum: refSummary("section", { count: entry.notes.length }) });
}

function notesHtml(pid) {
  const entry = lists.get(pid);
  if (!entry || entry.state === "loading") return '<p class="ov-sum" aria-live="polite">Loading the notes.</p>';
  if (entry.state === "error") return '<p class="ov-sum" role="alert">' + esc(entry.message) + "</p>";
  if (!entry.notes.length) {
    return emptyHtml("No research notes yet.", "Start one with <code class=\"code\">roadmap research new landscape " +
      "&quot;Title&quot; --project " + esc(pid) + "</code>, then reload this page.");
  }
  return '<ul class="nz-list" aria-label="Research notes">' + entry.notes.map(function (note) {
    return noteRowHtml(note, pid);
  }).join("") + "</ul>";
}

export function sectionView(vm) {
  const state = pageState(vm);
  if (state) return state;
  if (vm.route.name !== "project") {
    const links = (vm.projects || []).map(function (p) {
      return '<li><a href="' + esc(projectHash(p.id, "research")) + '">' + esc(p.name) + "</a></li>";
    }).join("");
    return '<div class="page-head"><h2 class="page-title">Research</h2><p class="page-note">Research notes belong ' +
      "to one project. Choose a project.</p></div>" + (links ? '<ul class="nz-list">' + links + "</ul>"
        : emptyHtml("No projects yet."));
  }
  const pid = vm.route.id;
  if (!lists.has(pid)) loadList(pid);
  const snap = vm.project.snapshot;
  return '<div class="page-head"><h2 class="page-title">Research</h2><p class="page-note">Read only. Notes are ' +
    "written with roadmap research, at most 6 per project.</p></div>" + checklistHtml(onboardingSteps(snap)) +
    '<section class="ov-card" aria-label="Research notes list"><h3 class="ov-h">Notes</h3>' + notesCopy(pid) +
    notesHtml(pid) +
    '<p><button type="button" class="btn btn-small" data-action="note-refresh" data-project="' + esc(pid) +
    '" data-focus="note-refresh">Reload notes</button></p></section>' + readerHtml(pid);
}

// Click entry point (app.js sends note-open and note-refresh here).
export function pageAction(action, el) {
  const pid = el.getAttribute("data-project");
  if (action === "note-open") {
    const name = el.getAttribute("data-name");
    selected = { pid: pid, name: name };
    if (!texts.has(pid + "/" + name)) loadText(pid, name);
    requestRender();
  } else if (action === "note-refresh") {
    lists.delete(pid);
    requestRender();
  }
}
