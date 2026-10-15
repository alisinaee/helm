// Render the Git section (web/js/views/git.js, R7.29 W1.c) in node, used by tests/web/test_git_view.py. The page's
// reads are answered by a stub fetch (two projects: alpha is a repo with changes and commits, beta is not a repo), and
// the document is a stub that keeps the click handler so the tabs can be switched. argv: this script, web directory.
// Prints one JSON object with the HTML of each state.
import { pathToFileURL } from "node:url";

const web = process.argv[2];
const handlers = {};
globalThis.document = {
  addEventListener(type, fn) {
    handlers[type] = fn;
  },
  getElementById() {
    return null;
  },
  querySelectorAll() {
    return [];
  },
};
globalThis.window = globalThis;
globalThis.window.location = { hash: "" };
globalThis.window.addEventListener = () => {};

const NOW = 1800000000;
const ALPHA = {
  status: {
    branch: "main", oid: "abc", detached: false, upstream: "origin/main", ahead: 2, behind: 0,
    staged: [{ path: "web/a.js", code: "M." }], changed: [{ path: "docs/x.md", code: ".M" }],
    untracked: ["notes/new.txt"], conflicts: [], in_progress: null,
  },
  log: {
    n: 30,
    rows: [
      { sha: "1a2b3c4d5e6f", author: "roadmap-board", time: NOW - 3600, subject: "api: retry", task: "R7.61",
        job: null },
      { sha: "9f8e7d6c5b4a", author: "roadmap-board", time: null, subject: "tokens: simple", task: null, job: "j12" },
    ],
  },
  branches: {
    branches: [
      { name: "main", current: true, upstream: "origin/main", ahead: 2, behind: 0, gone: false, time: NOW - 60 },
      { name: "agent/R7.29", current: false, upstream: null, ahead: 0, behind: 0, gone: false, time: null },
    ],
  },
};

function reply(status, body) {
  return { ok: status < 400, status: status, json: async () => body, headers: { get: () => null } };
}

globalThis.fetch = async function (url) {
  if (url.includes("/projects/beta/")) {
    return reply(409, { error: { code: "not_a_repo", message: "Not a git repo" } });
  }
  if (url.includes("/git/status")) return reply(200, ALPHA.status);
  if (url.includes("/git/log")) return reply(200, ALPHA.log);
  if (url.includes("/git/branches")) return reply(200, ALPHA.branches);
  return reply(404, { error: { code: "not_found", message: "no such route" } });
};

const git = await import(pathToFileURL(web + "/js/views/git.js").href);

const alpha = { id: "alpha", name: "alpha" };
const beta = { id: "beta", name: "beta" };
const projects = [alpha, beta];

function view(pid) {
  const project = projects.find((p) => p.id === pid);
  return { route: pid ? { name: "project", id: pid } : { name: "all" }, project: project, projects: projects,
    now: NOW * 1000 };
}

function clickOn(attrs) {
  const el = { getAttribute: (name) => (name in attrs ? attrs[name] : null) };
  handlers.click({ target: { closest: () => el } });
}

async function settle() {
  for (let i = 0; i < 5; i++) await new Promise((resolve) => setTimeout(resolve, 5));
}

// First visit starts the reads; once they are in, the page renders from the stored replies.
git.sectionView(view("alpha"));
git.sectionView(view("beta"));
await settle();
const changes = git.sectionView(view("alpha"));
const notRepo = git.sectionView(view("beta"));
clickOn({ "data-git": "tab", "data-tab": "history" });
const history = git.sectionView(view("alpha"));
clickOn({ "data-git": "tab", "data-tab": "branches" });
const branches = git.sectionView(view("alpha"));
const all = git.sectionView(view(null));

console.log(JSON.stringify({ changes, notRepo, history, branches, all }));
