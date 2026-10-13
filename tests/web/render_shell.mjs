// Render the shell pieces in node (used by tests/web/test_shell.py). argv: this script, web directory.
// Prints one JSON object: the parsed routes for a set of hashes, and the HTML of the nav, the bottom nav and the top
// bar for a project view with a stopped control and no meters, and for the same view with meter rows.
import { pathToFileURL } from "node:url";

const web = process.argv[2];
const load = (name) => import(pathToFileURL(web + "/js/" + name).href);
const router = await load("router.js");
const nav = await load("views/nav.js");
const top = await load("views/topbar.js");

const hashes = ["", "#/", "#/p/splitnet", "#/p/splitnet/work/board/i/t12?f=state:todo", "#/all/inbox",
  "#/p/BAD!/work", "#/all/nope"];
const routes = {};
for (const hash of hashes) {
  const r = router.parseRoute(hash);
  routes[hash] = { name: r.name, id: r.id, section: r.section, view: r.view, item: r.item, redirect: r.redirect || null };
}

const base = {
  route: router.parseRoute("#/p/splitnet/work"),
  ui: { navMini: false, panelOpen: null, theme: "auto" },
  project: { id: "splitnet", name: "split-net", notFound: false },
  control: { known: true, id: "splitnet", stopped: true, blocked: false, reason: "" },
  conn: { ok: true },
  theme: "auto",
  snapshotList: [{ needUser: 3, runningCount: 1, tasks: [{ needsUser: true }] }],
  meterRows: null,
  mode: "minimal",
};
const withMeters = Object.assign({}, base, {
  meterRows: [
    { id: "L1", scope: "global", window: "day", kind: "pct", used: 4.1, limit: 10, state: "ok", est: false },
    { id: "L2", scope: "global", window: "week", kind: "pct", used: 62, limit: 60, state: "block", est: false },
  ],
});

const out = {
  routes,
  nav: nav.navView(base),
  bnav: nav.bnavView(base),
  topbarStopped: top.topbarView(base),
  topbarMeters: top.topbarView(withMeters),
};
console.log(JSON.stringify(out));
