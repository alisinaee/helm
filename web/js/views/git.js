// Git (R7.29 W1.c, docs/GIT-SPEC.md section 5): the project's repo as the person reads it. Three tabs: Changes (the
// branch line, banners for a merge in progress, a detached HEAD and conflicts, the changed files with a commit form for
// the files ticked), History (the newest commits with their task and job) and Branches. Reads come from the project's
// git routes. Writes are the git.commit and git.push ops through POST /api/v1/cmd; the server decides what is allowed
// and a refusal says why. This page runs no git command itself, and offers no discard, reset, merge, rebase or
// force push.

import { getJson, postJson } from "../api.js";
import { bannerHtml, chipHtml, emptyHtml, esc, patch, skeletonHtml } from "../dom.js";
import { relTime } from "../format.js";
import { copyButton } from "../ref.js";
import { projectHash } from "../router.js";
import { showToast } from "./toast.js";

const TABS = [["changes", "Changes"], ["history", "History"], ["branches", "Branches"]];
const NOTE = "Commit takes only the files ticked. Force push, reset, discard, merge and rebase are never offered.";

const store = new Map(); // project id -> {status, rows, branches, error}
const reading = new Set(); // project ids with a read in flight
let tab = "changes";
let lastVm = null;

function gitBase(pid) {
  return "/api/v1/projects/" + encodeURIComponent(pid) + "/git/";
}

function repaint() {
  if (lastVm) patch("main", sectionHtml(lastVm));
}

function toast(text, tone) {
  showToast({ text: text, tone: tone });
}

// Reads status, the newest 30 commits and the branches. A failure (no repo, git missing) is kept as the error.
function load(pid) {
  if (reading.has(pid)) return;
  reading.add(pid);
  const base = gitBase(pid);
  Promise.all([getJson(base + "status"), getJson(base + "log?n=30"), getJson(base + "branches")])
    .then(function (replies) {
      store.set(pid, { status: replies[0].data, rows: replies[1].data.rows || [],
        branches: replies[2].data.branches || [], error: null });
    }, function (err) {
      store.set(pid, { status: null, rows: [], branches: [],
        error: { code: err.code || "", message: err.message || "Git could not be read." } });
    })
    .finally(function () {
      reading.delete(pid);
      repaint();
    });
}

async function send(op, args, pid, okText) {
  try {
    await postJson("/api/v1/cmd", { op: op, args: args, project: pid });
    toast(okText, "success");
    load(pid);
  } catch (err) {
    toast(op + " failed: " + (err.message || "unknown error"), "danger");
  }
}

function commit(form, pid) {
  const paths = Array.from(form.querySelectorAll('input[name="path"]:checked')).map(function (el) {
    return el.value;
  });
  const message = form.elements.message.value.trim();
  const task = form.elements.task.value.trim();
  if (!paths.length) return toast("Tick at least one file to commit.", "warning");
  if (!message) return toast("Write a commit message first.", "warning");
  const args = { paths: paths, message: message };
  if (task) args.task = task;
  return send("git.commit", args, pid, "Committed " + paths.length + (paths.length === 1 ? " file." : " files."));
}

function onClick(event) {
  const el = event.target && event.target.closest ? event.target.closest("[data-git]") : null;
  if (!el || !lastVm || lastVm.route.name !== "project") return;
  const pid = lastVm.route.id;
  const kind = el.getAttribute("data-git");
  if (kind === "tab") {
    tab = el.getAttribute("data-tab") || "changes";
    repaint();
  } else if (kind === "refresh") {
    load(pid);
  } else if (kind === "push") {
    send("git.push", {}, pid, "Pushed.");
  }
}

function onSubmit(event) {
  const form = event.target;
  if (!form || !form.getAttribute || form.getAttribute("data-git") !== "commit") return;
  event.preventDefault();
  if (lastVm && lastVm.route.name === "project") commit(form, lastVm.route.id);
}

// Listeners are bound once, on the document: the section's markup is replaced on every render.
document.addEventListener("click", onClick);
document.addEventListener("submit", onSubmit);

function fileRows(list) {
  return list.map(function (row) {
    const path = typeof row === "string" ? row : row.path;
    const code = typeof row === "string" ? "??" : row.code;
    return '<li class="row-grid git-files"><input type="checkbox" name="path" value="' + esc(path) +
      '" aria-label="Commit ' + esc(path) + '"><span class="rg-t" title="' + esc(path) + '">' + esc(path) +
      '</span><span class="rg-num num">' + esc(code) + "</span></li>";
  }).join("");
}

function changesHtml(pid, entry) {
  const s = entry.status || {};
  const parts = [];
  const where = s.detached ? "Detached HEAD" : "Branch " + (s.branch || "");
  parts.push('<p class="page-note">' + esc(where) + " · " + esc(s.upstream ? "Upstream " + s.upstream :
    "No upstream") + " · " + chipHtml("ahead " + (s.ahead || 0), "neutral") + " " +
    chipHtml("behind " + (s.behind || 0), "neutral") + "</p>");
  if (s.in_progress) {
    parts.push(bannerHtml("warning", "A " + s.in_progress + " is unfinished.", "Finish it in a terminal. " +
      "Commits are paused."));
  }
  if (s.detached) {
    parts.push(bannerHtml("warning", "Detached HEAD.", "Commits are refused here. Switch to a branch in a terminal."));
  }
  if (s.conflicts && s.conflicts.length) {
    parts.push(bannerHtml("danger", s.conflicts.length + " conflicting file(s).", s.conflicts.join(", ")));
  }
  const files = [].concat(s.staged || [], s.changed || [], s.untracked || []);
  if (!files.length) {
    parts.push(emptyHtml("Nothing to commit.", "The working tree is clean."));
    return parts.join("");
  }
  parts.push('<ul class="git-list" aria-label="Changed files">' + fileRows(files) + "</ul>");
  if (!s.detached && !s.in_progress) {
    parts.push('<form class="git-form" data-git="commit" novalidate>' +
      '<label for="git-msg">Commit message</label><textarea id="git-msg" name="message" rows="2" maxlength="4000">' +
      "</textarea><label>Task (optional) " +
      '<input id="git-task" name="task" type="text" maxlength="20" autocomplete="off"></label>' +
      '<button type="submit" class="btn btn-primary" data-focus="git-commit">Commit selected</button></form>');
  }
  parts.push('<div class="git-form"><button type="button" class="btn" data-git="push" data-focus="git-push">' +
    "Push</button><p class=\"page-note\">Push runs only when the project's policy allows it. A refusal says why." +
    "</p></div>");
  return parts.join("");
}

function historyHtml(vm, entry) {
  if (!entry.rows.length) return emptyHtml("No commits yet.", "");
  const pid = vm.route.id;
  const head = '<li class="row-grid git-log rg-head"><span class="rg-t">Commit</span>' +
    '<span class="rg-t">Subject</span><span class="rg-num">When</span></li>';
  const rows = entry.rows.map(function (row) {
    const meta = [row.task, row.job, row.author].filter(Boolean).join(" · ");
    const when = row.time == null ? { text: "–", title: "" } : relTime(row.time * 1000, vm.now);
    return '<li class="row-grid git-log"><span class="rg-t num" title="' + esc(row.sha) + '">' +
      esc(row.sha.slice(0, 7)) + '</span><span class="rg-t" title="' + esc(meta) + '">' +
      esc((row.task ? row.task + " " : "") + row.subject) + '</span><span class="rg-num num" title="' +
      esc(when.title) + '">' + esc(when.text) + "</span>" +
      copyButton("commit", row.sha, "Copy ref", { project: pid }) + "</li>";
  }).join("");
  return '<ul class="git-list" aria-label="Commits">' + head + rows + "</ul>";
}

function branchesHtml(vm, entry) {
  if (!entry.branches.length) return emptyHtml("No branches.", "");
  const rows = entry.branches.map(function (b) {
    const when = b.time == null ? "–" : relTime(b.time * 1000, vm.now).text;
    const current = b.current ? chipHtml("current", "success") : "";
    return '<li class="row-grid git-br"><span class="rg-t" title="' + esc(b.name) + '">' + esc(b.name) + " " +
      current + '</span><span class="rg-num num">↑' + esc(b.ahead) + " ↓" + esc(b.behind) +
      '</span><span class="rg-num num">' + esc(when) + "</span></li>";
  }).join("");
  return '<ul class="git-list" aria-label="Branches">' + rows + "</ul>";
}

function bodyHtml(vm, pid) {
  const entry = store.get(pid);
  if (!entry) return skeletonHtml(["w-60", "w-90", "w-40"]);
  if (entry.error) {
    if (entry.error.code === "not_a_repo") {
      return emptyHtml("Not a git repo", "Run <code>git init</code> in the project folder. roadmap never runs it.");
    }
    return bannerHtml("warning", "Git could not be read.", entry.error.message);
  }
  if (tab === "history") return historyHtml(vm, entry);
  if (tab === "branches") return branchesHtml(vm, entry);
  return changesHtml(pid, entry);
}

function tabsHtml() {
  const buttons = TABS.map(function (t) {
    return '<button type="button" class="btn" data-git="tab" data-tab="' + t[0] + '" aria-pressed="' +
      (tab === t[0] ? "true" : "false") + '" data-focus="git-tab-' + t[0] + '">' + esc(t[1]) + "</button>";
  }).join("");
  return '<div class="seg" role="group" aria-label="Git views">' + buttons +
    '<button type="button" class="btn" data-git="refresh" data-focus="git-refresh">Refresh</button></div>';
}

// The project's own page. With All projects it lists the projects, each linking to its Git page.
function chooserHtml(vm) {
  const list = (vm.projects || []).map(function (p) {
    return '<li class="row-grid git-br"><a class="rg-t" href="' + esc(projectHash(p.id, "git")) + '">' +
      esc(p.name || p.id) + "</a></li>";
  }).join("");
  return '<div class="page-head"><h2 class="page-title">Git</h2><p class="page-note">Pick a project to see its ' +
    "repo.</p></div>" + '<ul class="git-list" aria-label="Projects">' + list + "</ul>";
}

function sectionHtml(vm) {
  if (vm.route.name !== "project") return chooserHtml(vm);
  const pid = vm.route.id;
  const name = (vm.project && vm.project.name) || pid;
  return '<div class="page-head"><h2 class="page-title">Git: ' + esc(name) + '</h2><p class="page-note">' +
    esc(NOTE) + "</p></div>" + tabsHtml() + bodyHtml(vm, pid);
}

export function sectionView(vm) {
  lastVm = vm;
  if (vm.route.name === "project" && !store.has(vm.route.id) && !reading.has(vm.route.id)) load(vm.route.id);
  return sectionHtml(vm);
}
