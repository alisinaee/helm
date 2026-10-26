// R7.82 U2: server pushes. One EventSource on /api/v1/stream tells the page when a project's revision changed;
// the regular poll stays as a slow safety net while the stream is healthy. The helpers below are pure (tested in node).
export const STREAM_URL = "/api/v1/stream";
export const STREAM_SILENCE_MS = 40000;
export const BACKOFF_STEPS = [2000, 4000, 8000, 15000];
export const SAFETY_POLL_MS = 30000;

// A rev event needs a refresh when its rev differs from the cached snapshot rev of that project.
export function refreshNeeded(cachedRev, pushedRev) {
  if (typeof pushedRev !== "string" || !pushedRev) return false;
  return cachedRev !== pushedRev;
}

// Reconnect delay for the nth failed attempt (0-based): 2, 4, 8, then 15 s.
export function backoffDelay(attempt) {
  const n = Math.max(0, Math.floor(attempt) || 0);
  return BACKOFF_STEPS[Math.min(n, BACKOFF_STEPS.length - 1)];
}

// The poll delay: the normal one (fast or slow tab) unless the stream is healthy, then the 30 s safety net.
export function pollInterval(normalMs, streamHealthy) {
  return streamHealthy ? Math.max(normalMs, SAFETY_POLL_MS) : normalMs;
}

// The stream counts as healthy when open and something (event or ping) arrived within STREAM_SILENCE_MS.
export function streamHealthy(open, lastEventAt, now) {
  return !!open && lastEventAt > 0 && now - lastEventAt < STREAM_SILENCE_MS;
}

// Parses one rev event payload; null when malformed.
export function parseRev(text) {
  try {
    const d = JSON.parse(text);
    if (d && typeof d.project === "string" && typeof d.rev === "string") return { project: d.project, rev: d.rev };
  } catch (err) { /* malformed */ }
  return null;
}

// startLive(env): env = { ES, setTimeout, clearTimeout, now, fetchStatus(url) -> Promise<status>, cachedRev(pid),
// onRev(pid), onUp(), onDown() }. Returns { healthy(), stop() }. Without EventSource nothing happens (polling only).
export function startLive(env) {
  const g = globalThis.EventSource;
  const ES = env.ES !== undefined ? env.ES : (typeof g === "function" ? g : null);
  if (typeof ES !== "function") return { healthy: function () { return false; }, stop: function () {} };
  let es = null, open = false, last = 0, attempt = 0, retry = 0, watch = 0, stopped = false, wasUp = false;
  function setDown() {
    if (open || wasUp) { open = false; wasUp = false; env.onDown(); }
    open = false;
  }
  function arm() {
    env.clearTimeout(watch);
    watch = env.setTimeout(function () {
      if (!streamHealthy(open, last, env.now())) fail();
      else arm();
    }, STREAM_SILENCE_MS);
  }
  function alive() {
    last = env.now();
    attempt = 0;
    if (!wasUp) { wasUp = true; open = true; env.onUp(); }
    arm();
  }
  function fail() {
    if (stopped) return;
    if (es) { try { es.close(); } catch (err) { /* closed */ } es = null; }
    env.clearTimeout(watch);
    setDown();
    const d = backoffDelay(attempt++);
    env.clearTimeout(retry);
    // A 404/503 answer means no stream here: stop trying (the poll goes on) unless it is a plain network drop.
    retry = env.setTimeout(function () {
      Promise.resolve(env.fetchStatus(STREAM_URL)).then(function (st) {
        if (stopped) return;
        if (st === 404) return;
        connect();
      }, function () { if (!stopped) connect(); });
    }, d);
  }
  function connect() {
    if (stopped) return;
    try { es = new ES(STREAM_URL); } catch (err) { es = null; return; }
    es.onopen = function () { open = true; last = env.now(); arm(); };
    es.addEventListener("rev", function (ev) {
      const r = parseRev(ev && ev.data);
      alive();
      if (r && refreshNeeded(env.cachedRev(r.project), r.rev)) env.onRev(r.project);
    });
    es.addEventListener("ping", alive);
    es.onmessage = alive;
    es.onerror = function () { fail(); };
  }
  connect();
  return {
    healthy: function () { return streamHealthy(open, last, env.now()); },
    stop: function () {
      stopped = true;
      env.clearTimeout(watch); env.clearTimeout(retry);
      if (es) { try { es.close(); } catch (err) { /* closed */ } es = null; }
    },
  };
}
