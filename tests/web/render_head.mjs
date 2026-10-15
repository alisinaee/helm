// Render the Head screen (web/js/views/head.js, R7.31 H8) in node from a view model, used by tests/web/test_head_view.py.
// argv: this script, web directory, JSON file with the view model (head: {now, prev, counts, rows, full}).
// Prints one JSON object with the HTML for each case.
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

const web = process.argv[2];
const vm = JSON.parse(readFileSync(process.argv[3], "utf-8"));
// The row ages are counted from Date.now(): a pinned clock (vm.pinNow, an ISO time) keeps them fixed.
const pinned = typeof vm.pinNow === "string" ? Date.parse(vm.pinNow) : NaN;
if (Number.isFinite(pinned)) Date.now = () => pinned;
const head = await import(pathToFileURL(web + "/js/views/head.js").href);

const base = { project: "alpha", view: "cards" };
const empty = { head: { now: vm.head.now, prev: [], counts: {}, rows: [] } };

console.log(JSON.stringify({
  screen: head.headHtml(vm, Object.assign({ f: "all" }, base)),
  unhandled: head.headHtml(vm, Object.assign({ f: "unhandled" }, base)),
  done: head.headHtml(vm, Object.assign({ f: "done" }, base)),
  open: head.headHtml(vm, Object.assign({ f: "open", open: ["H1"] }, base)),
  readOnly: head.headHtml(vm, Object.assign({ f: "all", readOnly: true }, base)),
  empty: head.headHtml(empty, Object.assign({ f: "open" }, base)),
  unclaimed: head.headHtml({ head: { counts: {}, rows: [] } }, Object.assign({ f: "open" }, base)),
  noMatch: head.headHtml(vm, Object.assign({ f: "open", q: "zzz-none" }, base)),
  noReply: head.headHtml(Object.assign({}, vm, { head: Object.assign({}, vm.head, { full: { id: "H1", text: "x", history: [] } }) }), Object.assign({ f: "open", open: ["H1"] }, base)),
  hash: head.hashOf({ f: "unhandled", q: "a b", kind: "bug" }),
  oldest: head.headHtml(vm, Object.assign({ f: "all", sort: "old" }, base)),
  hashOld: head.hashOf({ f: "all", sort: "old" }),
  hashNew: head.hashOf({ f: "all", sort: "new" }),
  list: head.headHtml(vm, { f: "all", project: "alpha", view: "list" }),
  listDefault: head.headHtml(vm, { f: "all", project: "alpha" }),
  listOpen: head.headHtml(vm, { f: "open", open: ["H1"], project: "alpha", view: "list" }),
  listReadOnly: head.headHtml(vm, { f: "all", project: "alpha", view: "list", readOnly: true }),
  listEmpty: head.headHtml(empty, { f: "open", project: "alpha", view: "list" }),
  listOldest: head.headHtml(vm, { f: "all", sort: "old", project: "alpha", view: "list" }),
  hashList: head.hashOf({ f: "all", view: "list" }),
  hashCards: head.hashOf({ f: "all", view: "cards" }),
  shortSum: head.headHtml({ head: Object.assign({}, vm.head, { rows: vm.head.rows.map(function (r) {
    return r.id === "H1" ? Object.assign({}, r, { sum: "<img src=x" }) : r;
  }) }) }, Object.assign({ f: "all" }, base)),
}));
