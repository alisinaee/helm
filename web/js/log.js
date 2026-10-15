// Browser debug log (R7.16 step 4). Events are batched and POSTed as JSON to /api/v1/log; the server writes them
// to the local debug log. Only WARN/ERROR events and named actions are recorded (the closed list below). Logging is
// fail-quiet: a failed send is retried once after a short backoff and then dropped, nothing here logs its own
// failures, and no UI path awaits it. The phone page carries no CSRF value (the same signal postJson uses), so it
// stays silent.

const ENDPOINT = "/api/v1/log";
const SWITCH_KEY = "rb.logging";
const FLUSH_MS = 2000;
const RETRY_MS = 3000;
const BATCH_MAX = 50;
const BODY_MAX = 14 * 1024;
const BUFFER_MAX = 200;
const RATE_MAX = 300;
const SLOW_API_MS = 1500;
const SLOW_RENDER_MS = 200;
const DATA_MAX = 1024;
const STACK_MAX = 1536;
const FRAMES_MAX = 12;
const SECRET_KEY = /token|cookie|csrf|auth|password|secret/i;
const TARGET_ATTRS = ["data-item", "data-section", "data-project", "data-op", "data-task", "data-id", "data-toast"];
const REF_RE = /^rb:[a-z0-9-]+(\/[a-z]+\/[A-Za-z0-9._-]+)?$/;

// The closed list of event names and the level each one is written at. Unknown names are not recorded.
const EVENTS = new Map([
  ["ui.load", "INFO"],
  ["ui.route", "INFO"],
  ["ui.action", "INFO"],
  ["ui.submit", "INFO"],
  ["ui.mark", "INFO"],
  ["ui.error", "ERROR"],
  ["ui.reject", "ERROR"],
  ["ui.csp", "WARN"],
  ["ui.api", "WARN"],
  ["ui.render", "WARN"],
  ["ui.console", "WARN"],
]);

const buffer = [];
const stats = { sent: 0, dropped: 0 };
const rate = { start: 0, count: 0 };
let sid = newSid();
let enabled = readEnabled();
let installed = false;
let timer = null;

function newSid() {
  try {
    const bytes = new Uint8Array(4);
    crypto.getRandomValues(bytes);
    return Array.from(bytes, function (b) {
      return b.toString(16).padStart(2, "0");
    }).join("");
  } catch (err) {
    return Math.floor(Math.random() * 0x100000000).toString(16).padStart(8, "0");
  }
}

function readEnabled() {
  try {
    return localStorage.getItem(SWITCH_KEY) !== "0";
  } catch (err) {
    return true;
  }
}

// The page's CSRF value from its meta tag, or "" (phone pages carry none, and the placeholder is ignored).
function csrfValue() {
  try {
    for (const meta of document.querySelectorAll('meta[name="csrf"]')) {
      const value = meta.getAttribute("content") || "";
      if (value && value !== "__CSRF__") return value;
    }
  } catch (err) {
    return "";
  }
  return "";
}

function active() {
  return enabled && csrfValue() !== "" && typeof fetch === "function";
}

function cut(value, max) {
  const text = String(value == null ? "" : value);
  return text.length > max ? text.slice(0, Math.max(0, max - 1)) + "…" : text;
}

// Plain text for a log field: no query string or fragment on any URL, no home path (~), no CSRF value, one line.
function scrub(value, max) {
  let text = String(value == null ? "" : value);
  text = text.replace(/([a-z][a-z0-9+.-]*:\/\/[^\s"'<>()]*?)[?#][^\s"'<>()]*/gi, "$1");
  text = text.replace(/\/(Users|home)\/[^\s/"'()]+/g, "~");
  const token = csrfValue();
  if (token) text = text.split(token).join("[redacted]");
  return cut(text.replace(/\s+/g, " ").trim(), max);
}

function validRef(value) {
  const text = String(value || "");
  return REF_RE.test(text) && text.length <= 120 ? text : "";
}

function routeNow() {
  try {
    const hash = window.location.hash || "";
    const at = hash.indexOf("?");
    return cut(at >= 0 ? hash.slice(0, at) : hash, 120) || "#/";
  } catch (err) {
    return "";
  }
}

function stamp(date) {
  const pad = function (n, width) {
    return String(n).padStart(width || 2, "0");
  };
  const offset = -date.getTimezoneOffset();
  const abs = Math.abs(offset);
  return date.getFullYear() + "-" + pad(date.getMonth() + 1) + "-" + pad(date.getDate()) + "T" +
    pad(date.getHours()) + ":" + pad(date.getMinutes()) + ":" + pad(date.getSeconds()) + "." +
    pad(date.getMilliseconds(), 3) + (offset >= 0 ? "+" : "-") + pad(Math.floor(abs / 60)) + ":" +
    pad(abs % 60);
}

// A JSON-safe copy with at most 20 keys, 200-character strings, 10 array items and two levels of nesting.
function shape(value, depth) {
  if (value === null || value === undefined) return null;
  if (typeof value === "string") return scrub(value, 200);
  if (typeof value === "number") return isFinite(value) ? value : null;
  if (typeof value === "boolean") return value;
  if (depth >= 2) return null;
  if (Array.isArray(value)) {
    return value.slice(0, 10).map(function (item) {
      return shape(item, depth + 1);
    });
  }
  if (typeof value !== "object") return null;
  const out = {};
  let count = 0;
  for (const key of Object.keys(value)) {
    if (count >= 20) break;
    if (SECRET_KEY.test(key)) continue;
    out[cut(key, 40)] = shape(value[key], depth + 1);
    count += 1;
  }
  return out;
}

// data, shaped and cut to 1 KB (1.5 KB more when it carries a stack). Keys are dropped from the end until it fits.
function fitData(value, hasStack) {
  const data = shape(value, 0) || {};
  const limit = DATA_MAX + (hasStack ? STACK_MAX : 0);
  const keys = Object.keys(data);
  while (keys.length && JSON.stringify(data).length > limit) {
    delete data[keys.pop()];
  }
  return data;
}

// The top frames of a stack, one line each, cut to 12 frames and 1.5 KB.
function stackText(stack) {
  if (!stack) return "";
  const lines = String(stack).split("\n").slice(0, FRAMES_MAX);
  return cut(lines.map(function (line) {
    return scrub(line, 200);
  }).join(" | "), STACK_MAX);
}

function underRate(now) {
  if (now - rate.start >= 60000) {
    rate.start = now;
    rate.count = 0;
  }
  if (rate.count >= RATE_MAX) return false;
  rate.count += 1;
  return true;
}

// Build one event and queue it. Never throws, never awaits.
function record(ev, lvl, msg, data, ref) {
  try {
    if (!active() || !underRate(Date.now())) {
      if (enabled) stats.dropped += 1;
      return;
    }
    const event = {
      ts: stamp(new Date()),
      sid: sid,
      src: "ui",
      lvl: lvl,
      ev: cut(ev, 32),
      route: routeNow(),
      msg: scrub(msg, 300),
    };
    if (ref) event.ref = ref;
    if (data) {
      const rest = Object.assign({}, data);
      const stack = rest.stack ? stackText(rest.stack) : "";
      delete rest.stack;
      const fitted = fitData(rest, stack !== "");
      if (stack) fitted.stack = stack;
      if (Object.keys(fitted).length) event.data = fitted;
    }
    if (buffer.length >= BUFFER_MAX) {
      buffer.shift();
      stats.dropped += 1;
    }
    buffer.push(event);
    schedule();
  } catch (err) {
    return;
  }
}

function schedule() {
  if (timer !== null) return;
  timer = setTimeout(function () {
    timer = null;
    flush();
  }, FLUSH_MS);
}

// The next batch: at most 50 events and about 14 KB of JSON (the server cap is 16 KB).
function takeBatch() {
  const batch = [];
  let size = 80;
  while (buffer.length && batch.length < BATCH_MAX) {
    const text = JSON.stringify(buffer[0]);
    if (batch.length && size + text.length + 1 > BODY_MAX) break;
    size += text.length + 1;
    batch.push(buffer.shift());
  }
  return batch;
}

function send(batch, attempt) {
  const body = JSON.stringify({ sid: sid, events: batch });
  let pending;
  try {
    pending = fetch(ENDPOINT, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Roadmap-CSRF": csrfValue(),
        Accept: "application/json",
      },
      body: body,
      credentials: "same-origin",
      keepalive: true,
    });
  } catch (err) {
    pending = Promise.reject(err);
  }
  Promise.resolve(pending).then(function (res) {
    if (res && res.ok) {
      stats.sent += batch.length;
    } else {
      failed(batch, attempt);
    }
  }, function () {
    failed(batch, attempt);
  }).catch(function () {});
}

// One retry after RETRY_MS, then the batch is dropped. Nothing is logged about the failure.
function failed(batch, attempt) {
  if (attempt === 0) {
    setTimeout(function () {
      send(batch, 1);
    }, RETRY_MS);
    return;
  }
  stats.dropped += batch.length;
}

function flush() {
  if (timer !== null) {
    clearTimeout(timer);
    timer = null;
  }
  if (!buffer.length) return;
  if (!active()) {
    buffer.length = 0;
    return;
  }
  while (buffer.length) {
    send(takeBatch(), 0);
  }
}

function consoleText(value) {
  if (typeof value === "string") return value;
  if (value && typeof value.message === "string") return value.message;
  try {
    return String(value);
  } catch (err) {
    return "";
  }
}

function hostOf(uri) {
  const text = String(uri || "");
  if (/^[a-z][a-z0-9+.-]*:\/\//i.test(text)) {
    try {
      return new URL(text).host;
    } catch (err) {
      return "";
    }
  }
  return scrub(text, 40);
}

function onError(event) {
  try {
    const err = event.error;
    const msg = event.message || (err && err.message) || "error";
    const at = scrub(event.filename || "", 200) + ":" + (event.lineno || 0) + ":" + (event.colno || 0);
    record("ui.error", "ERROR", msg, { at: at, stack: err && err.stack ? err.stack : undefined });
  } catch (err) {
    return;
  }
}

function onRejection(event) {
  try {
    const reason = event.reason;
    const msg = reason && typeof reason.message === "string" ? reason.message : consoleText(reason);
    record("ui.reject", "ERROR", msg, { stack: reason && reason.stack ? reason.stack : undefined });
  } catch (err) {
    return;
  }
}

function onCsp(event) {
  record("ui.csp", "WARN", "blocked " + scrub(event.violatedDirective, 60), {
    violatedDirective: scrub(event.violatedDirective, 60),
    blocked: hostOf(event.blockedURI),
  });
}

function onSubmit(event) {
  const form = event.target;
  if (!form || form.tagName !== "FORM") return;
  const name = form.id || form.getAttribute("name") || "form";
  record("ui.submit", "INFO", "submit", { form: scrub(name, 60) });
}

// Wrap console.error and console.warn: the original still runs, with the same arguments.
function wrapConsole(name, lvl) {
  const original = console[name];
  if (typeof original !== "function") return;
  console[name] = function () {
    try {
      record("ui.console", lvl, consoleText(arguments[0]), null);
    } catch (err) {
      return;
    }
    return original.apply(console, arguments);
  };
}

function flushNow() {
  try {
    flush();
  } catch (err) {
    return;
  }
}

// Install the page hooks once, at boot. Safe to call on any page; the phone page records nothing.
export function installLog() {
  if (installed) return;
  installed = true;
  try {
    window.addEventListener("error", onError);
    window.addEventListener("unhandledrejection", onRejection);
    document.addEventListener("securitypolicyviolation", onCsp);
    document.addEventListener("submit", onSubmit, true);
    window.addEventListener("pagehide", flushNow);
    document.addEventListener("visibilitychange", function () {
      if (document.hidden) flushNow();
    });
    wrapConsole("error", "ERROR");
    wrapConsole("warn", "WARN");
    const nav = typeof navigator !== "undefined" ? navigator : {};
    record("ui.load", "INFO", "page load", {
      viewport: window.innerWidth + "x" + window.innerHeight,
      theme: document.documentElement.getAttribute("data-theme") || "auto",
      dpr: window.devicePixelRatio,
      ua: cut(nav.userAgent || "", 80),
    });
  } catch (err) {
    return;
  }
}

// logEvent(ev, msg, data): record one event from the closed list. Its level comes from the list.
export function logEvent(ev, msg, data) {
  const lvl = EVENTS.get(ev);
  if (lvl) record(ev, lvl, msg, data || null);
}

// mark(note): a test-session mark. It takes the ref of the focused row (data-ref), and flushes at once.
export function mark(note) {
  try {
    const focus = document.activeElement;
    const row = focus && focus.closest ? focus.closest("[data-ref]") : null;
    const ref = row ? validRef(row.getAttribute("data-ref")) : "";
    record("ui.mark", "INFO", String(note || "mark"), null, ref);
    flushNow();
  } catch (err) {
    return;
  }
}

// A named action: a data-action click (el) or a write op (no el; extra carries the project).
export function logAction(name, el, extra) {
  try {
    const data = Object.assign({}, extra || {});
    let ref = "";
    if (el && el.getAttribute) {
      ref = validRef(el.getAttribute("data-ref"));
      const target = TARGET_ATTRS.map(function (attr) {
        return el.getAttribute(attr);
      }).find(function (value) {
        return value;
      });
      if (target) data.target = target;
      if (el.getAttribute("data-kind")) data.kind = el.getAttribute("data-kind");
    }
    record("ui.action", "INFO", name, Object.keys(data).length ? data : null, ref);
  } catch (err) {
    return;
  }
}

function pathOf(url) {
  return cut(String(url || "").replace(/^[a-z]+:\/\/[^/]+/i, "").split("?")[0].split("#")[0], 120);
}

// One API request from api.js. Only failures (status 0 or non-2xx, other than 304) and replies slower than 1.5 s are
// recorded, with method and path only (never the query or a body).
export function noteRequest(method, url, status, started) {
  try {
    const ms = Date.now() - started;
    const failedReply = status === 0 || (status !== 304 && (status < 200 || status >= 300));
    if (!failedReply && ms <= SLOW_API_MS) return;
    const path = pathOf(url);
    record("ui.api", "WARN", method + " " + path + " " + status, {
      method: method,
      path: path,
      status: status,
      ms: Math.round(ms),
    });
  } catch (err) {
    return;
  }
}

// Render time from app.js; only slow renders (over 200 ms) are recorded.
export function noteRender(view, started) {
  try {
    const ms = Date.now() - started;
    if (ms > SLOW_RENDER_MS) {
      record("ui.render", "WARN", "render " + cut(view, 40) + " " + Math.round(ms) + " ms", {
        view: cut(view, 40),
        ms: Math.round(ms),
      });
    }
  } catch (err) {
    return;
  }
}

// A route change from app.js (the hash route is read when the event is built).
export function noteRoute() {
  record("ui.route", "INFO", "route change", null);
}

// Logging on or off (Settings > Logging stores the switch). Off drops what is queued.
export function setEnabled(on) {
  enabled = !!on;
  if (!enabled) buffer.length = 0;
  try {
    localStorage.setItem(SWITCH_KEY, enabled ? "1" : "0");
  } catch (err) {
    return;
  }
}

export function status() {
  return {
    enabled: enabled,
    active: active(),
    sid: sid,
    buffered: buffer.length,
    sent: stats.sent,
    dropped: stats.dropped,
  };
}
