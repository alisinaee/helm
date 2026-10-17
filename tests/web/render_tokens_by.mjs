import { tokensByHtml } from "../../web/js/views/tokens_by.js";
const j = (id, task, model, units, est) => ({ id, task, model, units, estPct: est, tokens: { out: 1000, model } });
const vm = { route: { name: "all" }, snapshotList: [{ id: "p", jobs: [j("1", "R1", "sonnet", 3000, 1.25), j("2", "R1", "haiku", 500, 0.02), j("3", "R2", "sonnet", 100, null)] }] };
console.log(tokensByHtml(vm));
