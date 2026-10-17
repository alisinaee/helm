// Render the Limits v2 cards with a stubbed GET /api/v1/limits (used by test_limits_v2_web.py).
import { pathToFileURL } from "node:url";
const web = process.argv[2];
const load = (name) => import(pathToFileURL(web + "/js/" + name).href);
const win = (extra) => ({ on: true, mode: "cap", value: 35, base: 0, once: false, stop: 35, percent: 12, fresh: true,
  resetsAt: "2026-10-17T13:50:00+00:00", ...extra });
const data = { windows: { five_hour: win({ mode: "budget", value: 20, base: 29, stop: 49, percent: 29 }),
  week: win({ on: false, stop: null, percent: 60 }) } };
globalThis.fetch = async () => ({ ok: true, status: 200, headers: { get: () => null }, json: async () => ({ windows: data.windows }),
  text: async () => JSON.stringify(data) });
const v2 = await load("views/limits_v2.js");
const vm = { route: { name: "all" }, projects: [{ id: "a", name: "Alpha" }] };
const before = v2.limitsV2Html(vm);
await new Promise((r) => setTimeout(r, 200));
const html = v2.limitsV2Html(vm);
const rec = v2._lv.recOf("five_hour");
const out = { before, html, label: v2.labelOf(rec, "five_hour"), stop: v2.stopOf(rec) };
v2._lv.setStop("five_hour", 70);
const d = v2._lv.state.draft.five_hour;
out.budgetAfter = { value: d.value, base: d.base };
v2._lv.setStop("week", 40);
const w = v2._lv.state.draft.week;
out.weekAfter = { value: w.value, on: w.on };
v2._lv.setStop("five_hour", 5);
out.clamped = v2._lv.state.draft.five_hour.value;
console.log(JSON.stringify(out));
process.exit(0);
