// Number and time formatting. Mirrors roadmap/core/format.py; both sides are checked against
// tests/fixtures/format_cases.json (web/dev/tests.html runs the JavaScript side).

export const MISSING = "–";

function isNumber(value) {
  return typeof value === "number" && Number.isFinite(value);
}

// Half up, as Python's floor(x + 0.5) in format.py.
function roundHalfUp(x) {
  return Math.floor(x + 0.5);
}

function pad2(n) {
  return n < 10 ? "0" + n : String(n);
}

// Token count given in thousands: "840k" below 1000k, "1.2M" from 1000k.
export function fmtTokens(k) {
  if (!isNumber(k)) return MISSING;
  const n = roundHalfUp(k);
  if (n < 1000) return n + "k";
  return (n / 1000).toFixed(1) + "M";
}

// Percent in 0-100 units: whole numbers, "<1%" for 0 < p < 1.
export function fmtPercent(p) {
  if (!isNumber(p)) return MISSING;
  if (p > 0 && p < 1) return "<1%";
  return roundHalfUp(p) + "%";
}

// Duration in seconds: "45s", "4m 12s", "1h 05m", "1d 3h". Negative values count as 0.
export function fmtDuration(seconds) {
  if (!isNumber(seconds)) return MISSING;
  const total = Math.max(0, roundHalfUp(seconds));
  if (total < 60) return total + "s";
  if (total < 3600) return Math.floor(total / 60) + "m " + pad2(total % 60) + "s";
  if (total < 86400) return Math.floor(total / 3600) + "h " + pad2(Math.floor((total % 3600) / 60)) + "m";
  return Math.floor(total / 86400) + "d " + Math.floor((total % 86400) / 3600) + "h";
}

// Whole count with thousands grouping: "1,234".
export function fmtCount(n) {
  if (!isNumber(n)) return MISSING;
  return String(roundHalfUp(n)).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

function toMs(value) {
  if (value == null || value === "") return NaN;
  if (typeof value === "number") return value;
  return Date.parse(value);
}

// Absolute local time for a title attribute, e.g. "Thu 16 Oct, 08:00".
export function fmtAbs(value) {
  const ms = toMs(value);
  if (Number.isNaN(ms)) return "";
  const d = new Date(ms);
  return d.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" }) + ", " +
    pad2(d.getHours()) + ":" + pad2(d.getMinutes());
}

// Age in seconds as words: "just now", "2 min ago", "3 h ago", "2 d ago".
export function fmtAge(seconds) {
  if (!isNumber(seconds)) return MISSING;
  const diff = Math.max(0, Math.round(seconds));
  if (diff < 45) return "just now";
  if (diff < 3600) return Math.round(diff / 60) + " min ago";
  if (diff < 86400) return Math.floor(diff / 3600) + " h ago";
  return Math.floor(diff / 86400) + " d ago";
}

// Relative time for a timestamp. The absolute time is returned as title.
export function relTime(value, now) {
  const ms = toMs(value);
  if (Number.isNaN(ms)) return { text: MISSING, title: "" };
  const at = isNumber(now) ? now : Date.now();
  return { text: fmtAge((at - ms) / 1000), title: fmtAbs(ms) };
}

// Reset countdown: "resets in 3h 12m (Thu 07:59)". Missing or past times read as "resets soon" or MISSING.
export function fmtResets(value, now) {
  const ms = toMs(value);
  if (Number.isNaN(ms)) return MISSING;
  const at = isNumber(now) ? now : Date.now();
  const left = Math.round((ms - at) / 1000);
  if (left <= 0) return "resets soon (" + fmtAbs(ms) + ")";
  return "resets in " + fmtDuration(left) + " (" + fmtAbs(ms) + ")";
}

// Clock for the live badge: "17:21:04".
export function fmtClock(ms) {
  const d = new Date(ms);
  return pad2(d.getHours()) + ":" + pad2(d.getMinutes()) + ":" + pad2(d.getSeconds());
}

const FUNCTIONS = {
  fmt_tokens: fmtTokens,
  fmt_percent: fmtPercent,
  fmt_duration: fmtDuration,
  fmt_count: fmtCount,
};

// Check the shared fixture cases. Returns a list of failure strings; an empty list means all pass.
export function checkCases(cases) {
  const failures = [];
  for (const item of cases) {
    const fn = FUNCTIONS[item.fn];
    if (!fn) {
      failures.push("unknown function " + item.fn);
      continue;
    }
    const got = fn(item.input);
    if (got !== item.expected) {
      failures.push(item.fn + "(" + JSON.stringify(item.input) + ") = " + JSON.stringify(got) +
        ", expected " + JSON.stringify(item.expected));
    }
  }
  return failures;
}
