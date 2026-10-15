// Rules (WP33): the project's rules in tabs by scope group, a delete on each rule, an add form (scope, kind, text
// with a 160-character counter) and Sync to CLAUDE.md. Adds and deletes go through run() in cmd.js. Sync posts
// itself so its toast can say what changed. Rules belong to one project, so All projects shows a pointer instead.

import { postJson } from "../api.js";
import { bannerHtml, chipHtml, emptyHtml, esc } from "../dom.js";
import { run } from "../cmd.js";
import { pageState } from "./inbox.js";
import { copyButton, refSummary } from "../ref.js";
import { showToast } from "./toast.js";

const MAX_TEXT = 160;
const BUDGET_MAX = 100000;  // thousands of tokens, as the server checks it
const TABS = [
  { id: "all", label: "All", test: function (s) { return s === "all"; } },
  { id: "lead", label: "Lead and worker", test: function (s) { return s === "lead" || s === "worker"; } },
  { id: "models", label: "Models", test: function (s) { return s === "haiku" || s === "sonnet" || s === "opus"; } },
  { id: "phase", label: "Phase and task",
    test: function (s) { return s.indexOf("phase:") === 0 || s.indexOf("task:") === 0; } },
  { id: "claude", label: "Claude", test: function (s) { return s === "claude"; } },
];
const SCOPE_OPTIONS = ["all", "lead", "worker", "haiku", "sonnet", "opus", "claude"];
const KIND_OPTIONS = [
  { value: "do", text: "Do" },
  { value: "dont", text: "Don't" },
  { value: "budget", text: "Budget" },
  { value: "done", text: "Done when" },
];
const KIND_KIND = { do: "success", dont: "danger", budget: "warning", done: "neutral" };

let tab = "all";
let listening = false;
let projectNow = null;

function tabOf(id) {
  for (const t of TABS) {
    if (t.id === id) return t;
  }
  return TABS[0];
}

function listHtml(rules, activeTab, project) {
  const group = tabOf(activeTab);
  const shown = rules.filter(function (r) {
    return group.id === "all" ? true : group.test(r.scope);
  });
  if (!shown.length) return emptyGroupHtml(activeTab);
  return '<ul class="rule-list">' + shown.map(function (r) {
    const value = r.kind === "budget" && r.value != null ? esc(r.value) + "k" : "";
    return '<li class="rule-row row-grid"><span class="rule-main rg-main">' +
      chipHtml(kindWord(r.kind), KIND_KIND[r.kind] || "neutral") +
      ' <span class="rule-text" title="' + esc(r.text) + '">' + esc(r.text) + "</span></span>" +
      '<span class="rule-scope rg-t">' + esc(r.scope) + "</span>" +
      '<span class="rg-num num">' + value + "</span>" +
      '<button type="button" class="btn btn-small" data-action="rule-rm" data-id="' + esc(r.id) +
      '" data-focus="rm-' + esc(r.id) + '" aria-label="Delete rule ' + esc(r.id) + '">Delete</button>' +
      copyButton("rule", r.id, "rule " + r.id, { project: project, sum: refSummary("rule", r) }) + "</li>";
  }).join("") + "</ul>";
}

function emptyGroupHtml(activeTab) {
  if (activeTab === "all") return emptyHtml("No rules yet.", "Add the first one in the form below.");
  return emptyHtml("No rules in this group.", '<button type="button" class="btn btn-small" data-action="rule-tab" ' +
    'data-tab="all" data-focus="tab-all">Show all rules</button>');
}

function kindWord(kind) {
  for (const k of KIND_OPTIONS) {
    if (k.value === kind) return k.text;
  }
  return kind;
}

function tabsHtml(active) {
  return '<div class="rule-tabs" role="group" aria-label="Rule groups">' + TABS.map(function (t) {
    return '<button type="button" class="btn btn-small" aria-pressed="' + (t.id === active ? "true" : "false") +
      '" data-action="rule-tab" data-tab="' + esc(t.id) + '" data-focus="tab-' + esc(t.id) + '">' +
      esc(t.label) + "</button>";
  }).join("") + "</div>";
}

function addFormHtml() {
  const scopes = SCOPE_OPTIONS.map(function (s) {
    return '<option value="' + esc(s) + '">' + esc(s) + "</option>";
  }).join("");
  const kinds = KIND_OPTIONS.map(function (k) {
    return '<option value="' + esc(k.value) + '">' + esc(k.text) + "</option>";
  }).join("");
  return '<section class="ov-card rules-form" aria-labelledby="rules-add">' +
    '<h3 id="rules-add" class="lim-h">Add a rule</h3>' +
    '<div class="lim-edit">' +
    '<label class="lim-field"><span class="lim-label">Scope</span><select class="lim-select" data-rule="scope" ' +
    'data-focus="rule-scope">' + scopes + "</select></label>" +
    '<label class="lim-field"><span class="lim-label">Or one task or phase (e.g. task:R8.13)</span>' +
    '<input class="lim-text" type="text" maxlength="60" data-rule="custom" data-focus="rule-custom"></label>' +
    '<label class="lim-field"><span class="lim-label">Kind</span><select class="lim-select" data-rule="kind" ' +
    'data-focus="rule-kind">' + kinds + "</select></label>" +
    '<label class="lim-field" data-rule-budget hidden><span class="lim-label">Budget (thousands of tokens)</span>' +
    '<input class="lim-num" type="number" min="1" max="' + BUDGET_MAX + '" step="1" data-rule="value" ' +
    'data-focus="rule-value" aria-describedby="rule-value-err"></label>' +
    '</div><p class="rule-err" id="rule-value-err" data-err-for="value"></p>' +
    '<label class="lim-field"><span class="lim-label">Rule text</span>' +
    '<textarea class="rule-input" rows="2" maxlength="' + MAX_TEXT + '" data-rule="text" data-focus="rule-text" ' +
    'aria-describedby="rule-text-err rule-count"></textarea></label>' +
    '<p class="rule-err" id="rule-text-err" data-err-for="text"></p>' +
    '<p class="rule-count num" id="rule-count" data-count-for="text">0/' + MAX_TEXT + " characters</p>" +
    '<button type="button" class="btn btn-primary" data-action="rule-add" data-focus="rule-add">Add rule</button>' +
    "</section>";
}

function syncHtml() {
  return '<section class="ov-card" aria-labelledby="rules-sync">' +
    '<h3 id="rules-sync" class="lim-h">Sync to CLAUDE.md</h3>' +
    '<p class="page-note">Writes these rules into the project CLAUDE.md between the roadmap markers. ' +
    "A backup copy of the file is kept first, and text outside the markers is not changed.</p>" +
    '<button type="button" class="btn" data-action="rule-sync" data-focus="rule-sync">' +
    "Sync to CLAUDE.md</button></section>";
}

export function sectionView(vm) {
  if (vm.route.name !== "project") {
    return emptyHtml("Rules belong to one project.", '<a href="#/all/overview">Go to All projects</a>');
  }
  const state = pageState(vm);
  if (state) return state;
  attachRuleListeners();
  projectNow = vm.route.id;
  const snap = vm.project.snapshot;
  const rules = snap.rules;
  const sectionCopy = rules == null ? "" : copyButton("section", "rules.list", "rules",
    { project: vm.route.id, sum: refSummary("section", { count: rules.length }) });
  const head = '<div class="page-head"><h2 class="page-title">Rules</h2><p class="page-note">Rules for agents in ' +
    esc(vm.project.name) + ".</p>" + sectionCopy + "</div>";
  const notice = rules == null ? bannerHtml("warning", "Rules are not in the snapshot yet.",
    "Add and sync still work. The list appears when the snapshot carries rules.") : "";
  const list = rules == null ? "" : listHtml(rules, tab, vm.route.id);
  return head + notice + tabsHtml(tab) + '<section class="ov-card" aria-label="Rules">' + list + "</section>" +
    addFormHtml() + syncHtml();
}

// The text counter and the cancel of an empty add. Attached once to <main>.
export function attachRuleListeners() {
  if (listening || typeof document === "undefined") return;
  const main = document.getElementById("main");
  if (!main) return;
  listening = true;
  main.addEventListener("input", function (event) {
    const t = event.target;
    const name = t && t.getAttribute ? t.getAttribute("data-rule") : null;
    if (!name) return;
    setErr(t.closest(".rules-form"), name, "");
    if (name !== "text") return;
    const count = main.querySelector('[data-count-for="text"]');
    if (count) count.textContent = t.value.length + "/" + MAX_TEXT + " characters";
  });
  // Only a budget rule takes a number, so the budget field appears for that kind alone.
  main.addEventListener("change", function (event) {
    const t = event.target;
    if (!t || t.getAttribute("data-rule") !== "kind") return;
    const budget = t.closest(".rules-form").querySelector("[data-rule-budget]");
    if (budget) budget.hidden = t.value !== "budget";
  });
}

// The inline error under a field (data-err-for), and aria-invalid on the field itself. Empty text clears it.
function setErr(root, name, message) {
  if (!root) return;
  const err = root.querySelector('[data-err-for="' + name + '"]');
  const field = root.querySelector('[data-rule="' + name + '"]');
  if (err) err.textContent = message;
  if (field) field.setAttribute("aria-invalid", message ? "true" : "false");
}

function formValues(el) {
  const root = el.closest(".rules-form");
  const read = function (name) {
    return root ? root.querySelector('[data-rule="' + name + '"]') : null;
  };
  const custom = read("custom");
  const scope = custom && custom.value.trim() ? custom.value.trim() : read("scope").value;
  const valueField = read("value");
  const raw = valueField ? valueField.value.trim() : "";
  const kind = read("kind").value;
  return {
    scope: scope,
    kind: kind,
    text: read("text").value.trim(),
    value: kind === "budget" && raw !== "" ? Number(raw) : null,
  };
}

// Sync posts directly so the toast can report the counts that the op returns.
async function syncRules() {
  try {
    const reply = await postJson("/api/v1/cmd", { op: "rules.sync", args: { dryRun: false }, project: projectNow });
    const result = (reply.data && reply.data.data) || {};
    showToast({ text: syncSummary(result), tone: "success" });
  } catch (err) {
    showToast({ text: "Sync to CLAUDE.md failed: " + (err.message || "unknown error"), tone: "danger" });
  }
}

function syncSummary(result) {
  const added = result.added || 0;
  const changed = result.changed || 0;
  const removed = result.removed || 0;
  if (!added && !changed && !removed) return "CLAUDE.md already matches the rules. Nothing changed.";
  return "Synced to CLAUDE.md: " + added + " added, " + changed + " changed, " + removed + " removed.";
}

// Actions for the rules screen. Returns true when handled (app.js re-renders).
export function ruleAction(action, el) {
  if (action === "rule-tab") {
    tab = el.getAttribute("data-tab") || "all";
    return true;
  }
  if (action === "rule-rm") {
    const id = el.getAttribute("data-id");
    run("rules.rm", { id: id }, { project: projectNow, label: "Rule " + id + " deleted" });
    return true;
  }
  if (action === "rule-add") {
    const form = el.closest(".rules-form");
    const v = formValues(el);
    const badValue = v.kind === "budget" && (!Number.isInteger(v.value) || v.value < 1 || v.value > BUDGET_MAX);
    setErr(form, "text", v.text ? "" : "Write the rule text first.");
    setErr(form, "value", badValue ? "Enter a whole number from 1 to " + BUDGET_MAX + "." : "");
    const firstBad = !v.text ? "text" : badValue ? "value" : "";
    if (firstBad) {
      // false: no re-render, so the inline errors stay on screen.
      const field = form.querySelector('[data-rule="' + firstBad + '"]');
      if (field) field.focus();
      return false;
    }
    run("rules.add", v, { project: projectNow, label: "Rule added" });
    return true;
  }
  if (action === "rule-sync") {
    syncRules();
    return true;
  }
  return false;
}
