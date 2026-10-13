// Self-test for web/dev/tests.html: runs the shared format cases through js/format.js and checks that the page has
// no sideways scroll. Writes PASS or FAIL into #result. Builds the list with textContent only.

import { checkCases } from "../js/format.js";

const report = document.getElementById("report");
const result = document.getElementById("result");
const outcomes = [];

function record(name, failures) {
  const ok = failures.length === 0;
  outcomes.push(ok);
  const item = document.createElement("li");
  item.textContent = (ok ? "ok    " : "FAIL  ") + name + (ok ? "" : ": " + failures.slice(0, 5).join("; "));
  report.appendChild(item);
}

function run() {
  const raw = document.getElementById("format-cases");
  const cases = raw ? JSON.parse(raw.textContent) : [];
  record("format cases match format.py (" + cases.length + " cases)", cases.length ? checkCases(cases) : ["no cases"]);
  const root = document.documentElement;
  const wide = root.scrollWidth > root.clientWidth ? ["scrollWidth " + root.scrollWidth +
    " is wider than clientWidth " + root.clientWidth] : [];
  record("no horizontal scroll at " + window.innerWidth + " px", wide);
  const pass = outcomes.every(Boolean);
  result.textContent = pass ? "PASS" : "FAIL";
  result.className = pass ? "badge" : "badge badge-danger";
}

run();
