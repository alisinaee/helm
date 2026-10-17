// Tokens by task and by model (R10.32 step 5): two read-only tables summed from the jobs that carry measured tokens.
// Units are the cost-weighted units of the server (core/parsers.py weighted_units); out is the output tokens.
// Both tables use the shared .row-grid with fixed tracks; numbers are right-aligned.

import { esc } from "../dom.js";
import { MISSING } from "../format.js";

const TOP = 15;

// The estimated weekly points of a row as "≈ 1.2%"; "≈ <0.1%" for a sliver, a dash for none.
export function fmtEst(n) {
  if (typeof n !== "number" || !isFinite(n) || n <= 0) return MISSING;
  return n < 0.05 ? "≈ <0.1%" : "≈ " + n.toFixed(1) + "%";
}

// A count as 12.3k or 4.5M; 0 stays "0".
export function fmtCount(n) {
  if (typeof n !== "number" || !isFinite(n)) return MISSING;
  if (n >= 1e6) return (n / 1e6).toFixed(1) + "M";
  if (n >= 1e3) return (n / 1e3).toFixed(1) + "k";
  return String(Math.round(n));
}

// Sum the jobs by key(job): {key, jobs, units, out}, biggest units first. Jobs without measured tokens are skipped.
export function sumBy(jobs, key) {
  const map = new Map();
  for (const j of jobs) {
    if (!j.tokens || typeof j.units !== "number") continue;
    const k = key(j);
    if (!k) continue;
    let row = map.get(k);
    if (!row) {
      row = { key: k, jobs: 0, units: 0, out: 0, est: 0 };
      map.set(k, row);
    }
    row.jobs += 1;
    row.units += j.units;
    row.out += typeof j.tokens.out === "number" ? j.tokens.out : 0;
    row.est += typeof j.estPct === "number" ? j.estPct : 0;
  }
  return Array.from(map.values()).sort(function (a, b) {
    return b.units - a.units;
  });
}

function tableHtml(id, title, first, rows, more) {
  const head = '<li class="row-grid tk-by rg-head"><span class="rg-t">' + esc(first) +
    '</span><span class="rg-num">Jobs</span><span class="rg-num">Out tokens</span>' +
    '<span class="rg-num">Units</span><span class="rg-num" title="Estimate, weekly limit">≈ Weekly</span></li>';
  const body = rows.length ? rows.map(function (r) {
    return '<li class="row-grid tk-by"><span class="rg-t" title="' + esc(r.key) + '">' + esc(r.key) +
      '</span><span class="rg-num num">' + r.jobs + '</span><span class="rg-num num">' + esc(fmtCount(r.out)) +
      '</span><span class="rg-num num">' + esc(fmtCount(r.units)) + '</span><span class="rg-num num">' +
      esc(fmtEst(r.est)) + "</span></li>";
  }).join("") : '<li class="page-note">No measured jobs yet.</li>';
  return '<h4 class="lim-h" id="' + id + '">' + esc(title) + '</h4><ul class="spend-list" aria-labelledby="' + id +
    '">' + head + body + "</ul>" + (more > 0 ? '<p class="page-note">+ ' + more + " more</p>" : "");
}

// The two tables for the view in vm: the project's jobs, or every project's jobs on the All view.
export function tokensByHtml(vm) {
  const snaps = (vm.snapshotList || []).filter(function (s) {
    return !(vm.route && vm.route.name === "project") || s.id === vm.route.id;
  });
  const jobs = [];
  for (const s of snaps) for (const j of s.jobs || []) jobs.push(j);
  const tasks = sumBy(jobs, function (j) {
    return j.task;
  });
  const models = sumBy(jobs, function (j) {
    return j.tokens.model || j.model;
  });
  const note = '<p class="page-note">Estimate: share of weekly usage by weighted tokens</p>';
  return '<div class="tk-by-wrap">' + note + tableHtml("tk-by-task", "By task", "Task", tasks.slice(0, TOP),
    tasks.length - TOP) + tableHtml("tk-by-model", "By model", "Model", models, 0) + "</div>";
}
