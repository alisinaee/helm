// Git (R7.29 W1.c, docs/GIT-SPEC.md section 5): the project's repo as the person reads it. Three tabs: Changes (the
// branch line, banners for a merge in progress, a detached HEAD and conflicts, the changed files with a commit form for
// the files ticked), History (the newest commits with their task and job) and Branches. Reads come from the project's
// git routes. Writes are the git.commit and git.push ops through POST /api/v1/cmd; the server decides what is allowed
// and a refusal says why. This page runs no git command itself, and offers no discard, reset, merge, rebase or
// force push. History draws a commit graph with its own SVG lane renderer (gitgraph.js replays commands, so it cannot
// take parent pointers, and it cannot sit in fixed grid rows) and shows a commit's diff with diff2html, both
// vendored in web/vendor and loaded only when this section first renders.

import { getJson, postJson } from "../api.js";
import { bannerHtml, chipHtml, emptyHtml, esc, patch, skeletonHtml } from "../dom.js";
import { relTime } from "../format.js";
import { copyButton } from "../ref.js";
import { projectHash } from "../router.js";
import { showToast } from "./toast.js";

const TABS = [["changes", "Changes"], ["history", "History"], ["branches", "Branches"]];
const NOTE = "No force push, reset, discard, merge or rebase.";

const LANE_W = 12; // px between lanes in the graph SVG
const LANE_MAX = 8; // lanes beyond this share the last column
const ROW_H = 28;
const VENDOR = ["/vendor/diff2html.min.js"];
const detail = new Map(); // sha -> {commit, files} | {error}
const diffs = new Map(); // sha + path -> {diff, skipped, truncated} | {error}
const sel = { sha: null, path: null, wkey: null, mode: window.innerWidth < 640 ? "line-by-line" : "side-by-side" };
const wdiffs = new Map(); // project + "\n" + path -> worktree diff reply | {error}
const wreading = new Set(); // keys with a worktree diff read in flight
let vendorState = "idle"; // idle | loading | ready | failed
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
  Promise.all([getJson(base + "status"), getJson(base + "log?n=100"), getJson(base + "branches")])
    .then(function (replies) {
      store.set(pid, { status: replies[0].data, rows: replies[1].data.rows || [],
        branches: replies[2].data.branches || [], error: null });
      wdiffs.clear(); // the status moved on: the shown diff is read again
      if (sel.wkey && sel.wkey.indexOf(pid + "\n") === 0) fetchWork(pid, sel.wkey.slice(pid.length + 1));
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

// diff2html is loaded once, when the section first renders; a failure leaves the plain patch text.
function loadVendor() {
  if (vendorState !== "idle" || !document.head) return;
  vendorState = "loading";
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = "/vendor/diff2html.min.css";
  document.head.appendChild(link);
  const script = document.createElement("script");
  script.src = VENDOR[0];
  script.onload = function () {
    vendorState = "ready";
    repaint();
  };
  script.onerror = function () {
    vendorState = "failed";
    repaint();
  };
  document.head.appendChild(script);
}

function pickCommit(pid, sha) {
  sel.sha = sha;
  sel.path = null;
  repaint();
  if (detail.has(sha)) return;
  getJson(gitBase(pid) + "show/" + encodeURIComponent(sha)).then(function (reply) {
    detail.set(sha, { commit: reply.data.commit, files: reply.data.files || [] });
  }, function (err) {
    detail.set(sha, { error: err.message || "Commit could not be read." });
  }).finally(repaint);
}

// The uncommitted diff of one changed file. The key holds the project, so a switch of project never shows another's.
function fetchWork(pid, path) {
  const key = pid + "\n" + path;
  wreading.add(key);
  getJson(gitBase(pid) + "diff?path=" + encodeURIComponent(path)).then(function (reply) {
    wdiffs.set(key, reply.data);
  }, function (err) {
    wdiffs.set(key, { error: err.message || "Diff could not be read." });
  }).finally(function () {
    wreading.delete(key);
    repaint();
  });
}

function pickWork(pid, path) {
  const key = pid + "\n" + path;
  const moved = sel.wkey !== key;
  sel.wkey = key;
  if (!wdiffs.has(key) && !wreading.has(key)) fetchWork(pid, path);
  if (moved) repaint();
}

function pickFile(pid, path) {
  sel.path = path;
  repaint();
  const key = sel.sha + "\n" + path;
  if (diffs.has(key)) return;
  const url = gitBase(pid) + "diff/" + encodeURIComponent(sel.sha) + "?path=" + encodeURIComponent(path);
  getJson(url).then(function (reply) {
    diffs.set(key, reply.data);
  }, function (err) {
    diffs.set(key, { error: err.message || "Diff could not be read." });
  }).finally(repaint);
}

// Lane layout. rows are newest first (topo order). Each row gets its column, the lanes passing straight through, the
// lanes that end here (merge into the column) and the lanes it opens toward its parents.
export function layoutGraph(rows) {
  const lanes = []; // lanes[i] = sha that lane i is waiting for, or null
  const out = [];
  for (const row of rows) {
    let col = lanes.indexOf(row.sha);
    if (col < 0) {
      col = lanes.indexOf(null);
      if (col < 0) col = lanes.length;
      lanes[col] = row.sha;
    }
    const before = lanes.slice();
    const merges = [];
    lanes.forEach(function (want, i) {
      if (want === row.sha && i !== col) {
        merges.push(i);
        lanes[i] = null;
      }
    });
    const parents = row.parents || [];
    const links = [];
    if (parents.length) {
      lanes[col] = parents[0];
      links.push(col);
      parents.slice(1).forEach(function (p) {
        let at = lanes.indexOf(p);
        if (at < 0) {
          at = lanes.indexOf(null);
          if (at < 0) at = lanes.length;
          lanes[at] = p;
        }
        links.push(at);
      });
    } else {
      lanes[col] = null;
    }
    while (lanes.length && lanes[lanes.length - 1] === null) lanes.pop();
    out.push({ col: col, before: before, merges: merges, links: links, after: lanes.slice() });
  }
  return out;
}

function laneX(i) {
  return Math.min(i, LANE_MAX - 1) * LANE_W + LANE_W / 2;
}

function graphSvg(g, width) {
  const mid = ROW_H / 2;
  const cx = laneX(g.col);
  const parts = [];
  function line(x1, y1, x2, y2, lane) {
    parts.push('<path class="gl gl-' + (lane % LANE_MAX) + '" d="M' + x1 + " " + y1 + (x1 === x2 ? " L" : " C" + x1 +
      " " + mid + " " + x2 + " " + mid + " ") + x2 + " " + y2 + '"/>');
  }
  g.before.forEach(function (want, i) {
    if (want === null || i === g.col || g.merges.indexOf(i) >= 0) return;
    line(laneX(i), 0, laneX(i), ROW_H, i);
  });
  if (g.before[g.col] !== undefined && g.before[g.col] !== null) line(cx, 0, cx, mid, g.col);
  g.merges.forEach(function (i) {
    line(laneX(i), 0, cx, mid, i);
  });
  g.links.forEach(function (i) {
    line(cx, mid, laneX(i), ROW_H, i);
  });
  parts.push('<circle class="gd gl-' + (g.col % LANE_MAX) + '" cx="' + cx + '" cy="' + mid + '" r="4"/>');
  return '<svg class="git-graph" width="' + width + '" height="' + ROW_H + '" viewBox="0 0 ' + width + " " + ROW_H +
    '" aria-hidden="true">' + parts.join("") + "</svg>";
}

function diffHtml() {
  if (!sel.path) return "";
  const got = diffs.get(sel.sha + "\n" + sel.path);
  if (!got) return skeletonHtml(["w-90", "w-60"]);
  if (got.error) return bannerHtml("warning", "Diff could not be read.", got.error);
  if (got.skipped) return emptyHtml("No diff shown.", got.skipped);
  const note = got.truncated ? bannerHtml("warning", "Diff cut.", "The patch is longer than the size cap.") : "";
  if (vendorState === "ready" && window.Diff2Html) {
    return note + window.Diff2Html.html(got.diff, { drawFileList: false, matching: "lines", outputFormat: sel.mode });
  }
  return note + '<pre class="git-raw">' + esc(got.diff) + "</pre>";
}

const DIFF_KIND = { "+": "add", "-": "del", " ": "ctx" };
const HUNK = /^@@ -(\d+)(?:,\d+)? \+(\d+)/;

// Old and new line numbers for each row, counted from the hunk headers. Hunk rows are muted, not numbered.
function diffRowsHtml(lines) {
  let oldNo = 0;
  let newNo = 0;
  return lines.map(function (row) {
    if (row.t === "@") {
      const m = HUNK.exec(row.text);
      if (m) {
        oldNo = Number(m[1]);
        newNo = Number(m[2]);
      }
      return '<div class="gd-row gd-hunk"><span class="gd-no"></span><span class="gd-no"></span><span class="gd-tx">' +
        esc(row.text) + "</span></div>";
    }
    let o = "";
    let n = "";
    if (row.t !== "+") o = String(oldNo++);
    if (row.t !== "-") n = String(newNo++);
    return '<div class="gd-row gd-' + (DIFF_KIND[row.t] || "ctx") + '"><span class="gd-no">' + o +
      '</span><span class="gd-no">' + n + '</span><span class="gd-tx">' + esc(row.text) + "</span></div>";
  }).join("");
}

// The right pane of Changes: the selected file's name and status, then its diff (or the loading and error state).
function workDiffHtml(pid) {
  if (!sel.wkey || sel.wkey.indexOf(pid + "\n") !== 0) {
    return emptyHtml("Select a file", "Its uncommitted diff shows here.");
  }
  const path = sel.wkey.slice(pid.length + 1);
  const got = wdiffs.get(sel.wkey);
  const cut = path.lastIndexOf("/");
  let pill = "";
  if (got && got.status) {
    const letter = statusLetter(got.status);
    pill = '<span class="git-st git-st-' + esc(letter.toLowerCase()) + '" title="' + esc(got.status) + '">' +
      esc(letter) + "</span>";
  }
  const head = '<div class="git-dhead"><span class="git-dname" title="' + esc(path) + '">' +
    esc(path.slice(cut + 1)) + "</span>" + pill + "</div>";
  if (!got) return head + skeletonHtml(["w-90", "w-60"]);
  if (got.error) return head + bannerHtml("warning", "Diff could not be read.", got.error);
  if (got.skipped) return head + emptyHtml("No diff shown.", got.skipped);
  if (!got.lines || !got.lines.length) return head + emptyHtml("No text changes.", "Nothing to show for this file.");
  const note = got.truncated ? bannerHtml("warning", "Diff cut.", "The diff is longer than the size cap.") : "";
  return head + note + '<div class="git-diff" role="region" tabindex="0" aria-label="Diff of ' + esc(path) + '">' +
    diffRowsHtml(got.lines) + "</div>";
}

function modeButtons() {
  return [["side-by-side", "Side by side"], ["line-by-line", "Inline"]].map(function (m) {
    return '<button type="button" class="btn" data-git="mode" data-mode="' + m[0] + '" aria-pressed="' +
      (sel.mode === m[0] ? "true" : "false") + '" data-focus="git-mode-' + m[0] + '">' + m[1] + "</button>";
  }).join("");
}

function detailHtml() {
  if (!sel.sha) return emptyHtml("Pick a commit.", "Its changed files and diff show here.");
  const got = detail.get(sel.sha);
  if (!got) return skeletonHtml(["w-60", "w-90", "w-40"]);
  if (got.error) return bannerHtml("warning", "Commit could not be read.", got.error);
  const files = got.files.map(function (f) {
    const on = f.path === sel.path;
    return '<li class="row-grid git-file" data-git="file" data-path="' + esc(f.path) + '" aria-current="' + on +
      '"><span class="rg-t" title="' + esc(f.path) + '">' + esc(f.path) + '</span><span class="rg-num num ok">' +
      (f.added == null ? "bin" : "+" + esc(f.added)) + '</span><span class="rg-num num bad">' +
      (f.deleted == null ? "" : "-" + esc(f.deleted)) + "</span></li>";
  }).join("");
  const c = got.commit;
  return '<div class="git-head"><span class="num">' + esc(c.sha.slice(0, 7)) + "</span> " + esc(c.subject) +
    '</div><ul class="git-list" aria-label="Changed files">' + (files || "<li>No file changes.</li>") + "</ul>" +
    '<div class="seg git-modes" role="group" aria-label="Diff layout">' + modeButtons() + "</div>" + diffHtml();
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
  } else if (kind === "pick") {
    pickCommit(pid, el.getAttribute("data-sha"));
  } else if (kind === "file") {
    pickFile(pid, el.getAttribute("data-path"));
  } else if (kind === "wfile") {
    pickWork(pid, el.getAttribute("data-path"));
  } else if (kind === "mode") {
    sel.mode = el.getAttribute("data-mode") === "line-by-line" ? "line-by-line" : "side-by-side";
    repaint();
  } else if (kind === "push") {
    send("git.push", {}, pid, "Pushed.");
  }
}

function onChange(event) {
  const el = event.target;
  const left = el && el.closest ? el.closest(".git-left") : null;
  if (!left) return;
  if (el.getAttribute("data-git") === "all") {
    left.querySelectorAll('input[name="path"]').forEach(function (box) {
      box.checked = el.checked;
    });
  }
  syncForm(left.querySelector('[data-git="commit"] button'));
}

function onInput(event) {
  const el = event.target;
  if (!el || el.id !== "git-msg") return;
  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight, 160) + "px";
  syncForm(el);
}

// Up/Down move between the file buttons; focus loads the diff (onFocus). Cmd/Ctrl+Enter in the message box commits.
function onKey(event) {
  const el = event.target;
  if (el && el.getAttribute && el.getAttribute("data-git") === "wfile" &&
    (event.key === "ArrowDown" || event.key === "ArrowUp")) {
    const list = el.closest(".git-list");
    const files = list ? Array.from(list.querySelectorAll('[data-git="wfile"]')) : [];
    const next = files[files.indexOf(el) + (event.key === "ArrowDown" ? 1 : -1)];
    event.preventDefault();
    if (next) next.focus();
    return;
  }
  if (!el || el.id !== "git-msg" || event.key !== "Enter" || !(event.metaKey || event.ctrlKey)) return;
  event.preventDefault();
  if (lastVm && lastVm.route.name === "project" && el.form) commit(el.form, lastVm.route.id);
}

function onFocus(event) {
  const el = event.target;
  if (!el || !el.getAttribute || el.getAttribute("data-git") !== "wfile") return;
  if (lastVm && lastVm.route.name === "project") pickWork(lastVm.route.id, el.getAttribute("data-path"));
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
document.addEventListener("change", onChange);
document.addEventListener("input", onInput);
document.addEventListener("keydown", onKey);
document.addEventListener("focusin", onFocus);

// The one-letter status a file row shows: "??" is untracked (U), otherwise the first changed side of XY.
function statusLetter(code) {
  if (code === "??") return "U";
  return String(code).replace(/\./g, "").charAt(0) || "M";
}

// A checkbox (for the commit) and a button per file: the button shows the diff; the checkbox never does.
function fileRows(list, pid) {
  return list.map(function (row) {
    const path = typeof row === "string" ? row : row.path;
    const code = typeof row === "string" ? "??" : row.code;
    const letter = statusLetter(code);
    const cut = path.lastIndexOf("/");
    const dir = cut > 0 ? path.slice(0, cut + 1) : "";
    const on = sel.wkey === pid + "\n" + path;
    return '<li class="git-fr"><input type="checkbox" name="path" value="' + esc(path) +
      '" aria-label="Commit file"><button type="button" class="git-fb" data-git="wfile" data-path="' + esc(path) +
      '" aria-current="' + on + '" title="' + esc(path) + '"><span class="git-st git-st-' +
      esc(letter.toLowerCase()) + '" title="' + esc(code) + '">' + esc(letter) + '</span><span class="git-fn"><b>' +
      esc(path.slice(cut + 1)) + "</b>" + (dir ? "<i>" + esc(dir) + "</i>" : "") + "</span></button></li>";
  }).join("");
}

function commitPanel() {
  return '<form class="git-form" data-git="commit" novalidate>' +
    '<textarea id="git-msg" name="message" rows="2" maxlength="4000" placeholder="Summary (required)" ' +
    'aria-label="Commit message"></textarea><div class="git-cr">' +
    '<input id="git-task" name="task" type="text" maxlength="20" autocomplete="off" placeholder="Task id" ' +
    'aria-label="Task id"><button type="submit" class="btn btn-primary" data-focus="git-commit" disabled>' +
    '<span data-git-count>Commit</span></button></div><p class="git-foot">' + esc(NOTE) + "</p></form>";
}

function headerHtml(vm, entry) {
  const s = (entry && entry.status) || null;
  const name = (vm.project && vm.project.name) || vm.route.id;
  const chips = [chipHtml(name, "neutral")];
  let push = "";
  if (s) {
    chips.push('<span class="git-chip git-branch">' + esc(s.detached ? "Detached HEAD" : s.branch || "") + "</span>");
    chips.push('<span class="git-chip">' + esc(s.upstream || "No upstream") + ' <span class="git-ab">↑' +
      esc(s.ahead || 0) + " ↓" + esc(s.behind || 0) + "</span></span>");
    const ahead = s.ahead || 0;
    push = '<button type="button" class="btn' + (ahead > 0 ? " btn-primary" : "") + '" data-git="push" ' +
      'data-focus="git-push"' + (ahead > 0 ? "" : ' disabled title="Nothing to push: no commits ahead."') + ">" +
      (ahead > 0 ? "Push " + esc(ahead) + "↑" : "Push") + "</button>";
  }
  return '<div class="git-bar"><div class="git-chips">' + chips.join("") +
    '</div><div class="git-act"><button type="button" class="btn" data-git="refresh" data-focus="git-refresh" ' +
    'aria-label="Refresh" title="Refresh">Refresh</button>' + push + "</div></div>";
}

function changesHtml(pid, entry) {
  const s = entry.status || {};
  const parts = [];
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
    parts.push(emptyHtml("Working tree clean", "Nothing to commit."));
    return parts.join("");
  }
  const canCommit = !s.detached && !s.in_progress;
  const left = '<div class="git-left"><div class="git-gh"><input type="checkbox" data-git="all" ' +
    'aria-label="Select all files"><span>Changes (' + files.length + ')</span></div>' +
    '<ul class="git-list" aria-label="Changed files">' + fileRows(files, pid) + "</ul>" +
    (canCommit ? commitPanel() : "") + "</div>";
  const right = '<div class="git-right">' + workDiffHtml(pid) + "</div>";
  parts.push('<div class="git-split">' + left + right + "</div>");
  return parts.join("");
}

// Keeps the Commit button's label and enabled state in step with the ticks and the message, without a repaint.
function syncForm(root) {
  const form = root && root.closest ? root.closest('[data-git="commit"]') : null;
  const scope = form ? form.parentNode : null;
  if (!form || !scope) return;
  const ticked = scope.querySelectorAll('input[name="path"]:checked').length;
  const all = scope.querySelector('[data-git="all"]');
  const boxes = scope.querySelectorAll('input[name="path"]').length;
  if (all) {
    all.checked = boxes > 0 && ticked === boxes;
    all.indeterminate = ticked > 0 && ticked < boxes;
  }
  const label = form.querySelector("[data-git-count]");
  if (label) label.textContent = ticked ? "Commit " + ticked + (ticked === 1 ? " file" : " files") : "Commit";
  const btn = form.querySelector('button[type="submit"]');
  if (btn) btn.disabled = !ticked || !form.elements.message.value.trim();
}

function historyHtml(vm, entry) {
  if (!entry.rows.length) return emptyHtml("No commits yet.", "");
  const pid = vm.route.id;
  const layout = layoutGraph(entry.rows);
  const cols = Math.min(LANE_MAX, Math.max(1, layout.reduce(function (n, g) {
    return Math.max(n, g.col + 1, g.after.length);
  }, 1)));
  const width = cols * LANE_W;
  const head = '<li class="row-grid git-log rg-head"><span class="rg-t">Graph</span><span class="rg-t">Commit</span>' +
    '<span class="rg-t">Message</span><span class="rg-t git-au">Author</span>' +
    '<span class="rg-num">Age</span><span></span>' +
    "</li>";
  const rows = entry.rows.map(function (row, i) {
    const when = row.time == null ? { text: "–", title: "" } : relTime(row.time * 1000, vm.now);
    const on = row.sha === sel.sha;
    return '<li class="row-grid git-log" data-git="pick" data-sha="' + esc(row.sha) + '" aria-current="' + on +
      '"><span class="git-gcell">' + graphSvg(layout[i], width) + '</span><span class="rg-t num" title="' +
      esc(row.sha) + '">' + esc(row.sha.slice(0, 7)) + '</span><span class="rg-t" title="' +
      esc([row.task, row.job].filter(Boolean).join(" · ")) + '"><button type="button" class="git-pick" ' +
      'data-focus="git-pick-' + esc(row.sha.slice(0, 7)) + '">' + esc((row.task ? row.task + " " : "") +
      row.subject) + '</button></span><span class="rg-t git-au">' + esc(row.author) +
      '</span><span class="rg-num num" title="' + esc(when.title) + '">' + esc(when.text) + "</span>" +
      copyButton("commit", row.sha, "Copy ref", { project: pid }) + "</li>";
  }).join("");
  return '<div class="git-hist" data-splitter-host="git">' +
    '<ul class="git-list git-commits" aria-label="Commits">' + head + rows + "</ul>" +
    '<div class="spl" role="separator" tabindex="0" aria-orientation="vertical" aria-label="Resize commit detail" ' +
    'data-splitter="git" data-min="320" data-max="720" data-def="416" ' +
    'title="Drag to resize, double-click to reset"></div>' +
    '<section class="git-detail" aria-label="Commit detail">' + detailHtml() + "</section></div>";
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
    return '<button type="button" role="tab" class="git-tab" data-git="tab" data-tab="' + t[0] + '" aria-selected="' +
      (tab === t[0] ? "true" : "false") + '" data-focus="git-tab-' + t[0] + '">' + esc(t[1]) + "</button>";
  }).join("");
  return '<div class="git-tabs" role="tablist" aria-label="Git views">' + buttons + "</div>";
}

// The project's own page. With All projects it lists the projects, each linking to its Git page.
function chooserHtml(vm) {
  const list = (vm.projects || []).map(function (p) {
    return '<li class="row-grid git-br"><a class="rg-t" href="' + esc(projectHash(p.id, "git")) + '">' +
      esc(p.name || p.id) + "</a></li>";
  }).join("");
  return '<div class="page-head"><p class="page-note">Pick a project to see its ' +
    "repo.</p></div>" + '<ul class="git-list" aria-label="Projects">' + list + "</ul>";
}

function sectionHtml(vm) {
  if (vm.route.name !== "project") return chooserHtml(vm);
  const pid = vm.route.id;
  return '<div class="git-page">' + headerHtml(vm, store.get(pid)) + tabsHtml() + bodyHtml(vm, pid) + "</div>";
}

export function sectionView(vm) {
  lastVm = vm;
  loadVendor();
  if (vm.route.name === "project" && !store.has(vm.route.id) && !reading.has(vm.route.id)) load(vm.route.id);
  return sectionHtml(vm);
}
