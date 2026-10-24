// Section import retry policy (R11.167). Pure helpers, no DOM, so node can test them.
// A failed import after a server restart is a network failure: keep retrying quietly (1 s, 2 s, 4 s, 8 s, then every
// 15 s) and show the red "Could not load" state only after QUIET_MS of failures, or at once for a code error.
export const RETRY_STEPS_MS = [1000, 2000, 4000, 8000];
export const RETRY_MAX_MS = 15000;
export const QUIET_MS = 30000;

// attempt is the number of failures so far (1 for the first).
export function retryDelayMs(attempt) {
  const n = Math.max(1, attempt | 0);
  return n <= RETRY_STEPS_MS.length ? RETRY_STEPS_MS[n - 1] : RETRY_MAX_MS;
}

// A fetch or connection failure of the module URL (Chrome, Firefox, Safari wording). A SyntaxError, ReferenceError or
// any other module error is not one: retrying cannot fix it.
export function isNetworkError(err) {
  if (!err) return true;
  const name = String(err.name || "");
  if (name === "SyntaxError" || name === "ReferenceError" || name === "RangeError") return false;
  const msg = String(err.message || err);
  return /failed to fetch|dynamically imported module|importing a module script failed|network|load failed|connection/i
    .test(msg) || (name === "TypeError" && msg === "");
}

// "quiet" while the failure is a network one younger than QUIET_MS; else "error".
export function importVerdict(err, firstFailAt, now) {
  if (!isNetworkError(err)) return "error";
  return now - firstFailAt >= QUIET_MS ? "error" : "quiet";
}
