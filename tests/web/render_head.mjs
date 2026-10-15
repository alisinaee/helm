// Render the Head screen (web/js/views/head.js, R7.31 H8) in node from a view model, used by tests/web/test_head_view.py.
// argv: this script, web directory, JSON file with the view model (head: {now, prev, counts, rows, full}).
// Prints one JSON object with the HTML for each case.
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

const web = process.argv[2];
const vm = JSON.parse(readFileSync(process.argv[3], "utf-8"));
const head = await import(pathToFileURL(web + "/js/views/head.js").href);

const base = { project: "alpha" };
const empty = { head: { now: vm.head.now, prev: [], counts: {}, rows: [] } };

console.log(JSON.stringify({
  screen: head.headHtml(vm, Object.assign({ f: "all" }, base)),
  unhandled: head.headHtml(vm, Object.assign({ f: "unhandled" }, base)),
  done: head.headHtml(vm, Object.assign({ f: "done" }, base)),
  open: head.headHtml(vm, Object.assign({ f: "open", id: "H1" }, base)),
  readOnly: head.headHtml(vm, Object.assign({ f: "all", readOnly: true }, base)),
  empty: head.headHtml(empty, Object.assign({ f: "open" }, base)),
  noMatch: head.headHtml(vm, Object.assign({ f: "open", q: "zzz-none" }, base)),
  hash: head.hashOf({ f: "unhandled", q: "a b", kind: "bug" }),
}));
