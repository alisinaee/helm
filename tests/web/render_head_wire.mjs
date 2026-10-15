// Render the Head wire-up (H9) in node: the nav badge (nav.js) and the Overview chip (overview.js) from a view model.
// argv: this script, web directory, JSON file with {snapshotList, project snapshot}. Prints one JSON object.
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

const web = process.argv[2];
const input = JSON.parse(readFileSync(process.argv[3], "utf-8"));
const nav = await import(pathToFileURL(web + "/js/views/nav.js").href);

const counts = nav.countsFor({ snapshotList: input.snapshots, meterRows: [] });
const bnavHead = nav.navView({ route: { section: "overview", name: "all" }, ui: { navMini: false },
  snapshotList: input.snapshots, meterRows: [] });
console.log(JSON.stringify({
  headCount: counts.head,
  navHasHead: bnavHead.indexOf('href="#/all/head"') >= 0,
  navBadge: /data-tone="neutral">\d+<span class="sr-only"> open asks/.test(bnavHead),
}));
