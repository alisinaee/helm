// Render the Tokens Overview and History tabs with a stubbed history endpoint (used by test_tokens_charts.py).
import { pathToFileURL } from "node:url";
const web = process.argv[2];
const load = (name) => import(pathToFileURL(web + "/js/" + name).href);
const day = (d, m, jobs, out, units) => ({ d, m: { [m]: { jobs, in: 5, out, cacheRead: 100, cacheWrite: 10, units } } });
const z = { jobs: 0, in: 0, out: 0, cacheRead: 0, cacheWrite: 0, units: 0 };
const data = {
  today: "2026-10-17", firstDay: "2026-10-15", models: ["haiku", "sonnet", "opus", "other"],
  days: [day("2026-10-15", "haiku", 3, 900, 5000), day("2026-10-16", "sonnet", 2, 400, 90000), day("2026-10-17", "opus", 1, 100, 40000)],
  totals: { today: { ...z, jobs: 1, out: 100, units: 40000 }, d7: { ...z, jobs: 6, out: 1400, units: 135000 }, all: { ...z, jobs: 6, out: 1400, units: 135000 } },
  projects: [{ id: "a", name: "Alpha", today: z, d7: z, all: { ...z, jobs: 3 } }, { id: "b", name: "Beta", today: z, d7: z, all: { ...z, jobs: 3 } }],
  tasks: [{ id: "R1.1", project: "a", phase: "R1", jobs: 2, out: 10, units: 9000, in: 0, cacheRead: 0, cacheWrite: 0 }],
  phaseUse: [{ id: "R1", project: "a", jobs: 2, out: 10, units: 9000, in: 0, cacheRead: 0, cacheWrite: 0 }],
  phases: [{ project: "a", projectName: "Alpha", id: "R1", name: "One", open: 2, estK: 140, spentK: 50, remainingK: 90 }],
  remainingK: 90, estimatedK: 140, samples: [{ t: Date.parse("2026-10-16T10:00:00") / 1000, wk: 20 }, { t: Date.parse("2026-10-17T10:00:00") / 1000, wk: 31 }],
};
globalThis.fetch = async () => ({ ok: true, status: 200, headers: { get: () => null }, json: async () => data, text: async () => JSON.stringify(data) });
const hist = await load("views/tokens_history.js");
const before = hist.historyHtml("");
await new Promise((r) => setTimeout(r, 300));
const out = { before, overview: hist.overviewHtml(""), history: hist.historyHtml("") };
console.log(JSON.stringify(out));
process.exit(0);
