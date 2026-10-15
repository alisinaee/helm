// Render the simple limits blocks (web/js/views/limits.js, R7.28 A) in node from two synthetic view models, used by
// tests/web/test_limits_simple.py. argv: this script, web directory. Prints one JSON object with the HTML.
import { pathToFileURL } from "node:url";

const web = process.argv[2];
const limits = await import(pathToFileURL(web + "/js/views/limits.js").href);

const meter = (over) => Object.assign({ id: "X", scope: "project", window: "week", kind: "pct", used: null,
  limit: null, state: "ok", est: false, paceAt: null, src: "limits", action: "block" }, over);

const snap = (id, meters, estPts) => ({ id: id, title: id, meters: meters, weekUse: { estPts: estPts } });

const alpha = snap("alpha", [
  meter({ id: "L4", scope: "global", window: "week", kind: "pct", used: 62, limit: 95, src: "config" }),
  meter({ id: "L5", scope: "project", window: "day", kind: "pct", used: 4.1, limit: 30, state: "warn" }),
  meter({ id: "L6", scope: "project", window: "week", kind: "tok", used: 12, limit: 500 }),
  meter({ id: "AUTO", scope: "project", window: "week", kind: "acct", limit: 80, state: "unknown", src: "autonomy" }),
], 3.2);
const beta = snap("beta", [
  meter({ id: "L4", scope: "global", window: "week", kind: "pct", used: 62, limit: 95, src: "config" }),
], 1.1);

const vm = { projects: [{ id: "alpha", name: "alpha" }, { id: "beta", name: "beta" }],
  snapshotList: [alpha, beta] };
const off = { projects: vm.projects, snapshotList: [snap("alpha", [], 0), snap("beta", [], 0)] };

console.log(JSON.stringify({
  weekly: limits.weeklyStopHtml(vm),
  weeklyOff: limits.weeklyStopHtml(off),
  share: limits.shareRowsHtml(vm),
  shareOff: limits.shareRowsHtml(off),
}));
