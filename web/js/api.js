// Fetch helpers for API v1. GET requests keep the last body per URL and send If-None-Match, so a 304 reuses it.
// Every failure becomes an ApiError with a status, a code and a plain message. Writes send the CSRF token from the
// page's <meta name="csrf"> (the server adds the real value; the literal placeholder is ignored).

import { noteRequest } from "./log.js";

const etagCache = new Map();
const PLACEHOLDER = "__CSRF__";

export class ApiError extends Error {
  constructor(status, code, message) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

async function readJson(response) {
  try {
    return await response.json();
  } catch (err) {
    return null;
  }
}

function failure(status, body) {
  const error = body && body.error;
  if (error && typeof error.message === "string") {
    return new ApiError(status, String(error.code || "http"), error.message);
  }
  return new ApiError(status, "http", "The server answered with status " + status + ".");
}

// The CSRF value re-read after a refused write (R7.61). Used only when the server refuses a write with 403 for CSRF.
let freshToken = "";

export function csrfToken() {
  if (freshToken) return freshToken;
  const metas = document.querySelectorAll('meta[name="csrf"]');
  for (const meta of metas) {
    const value = meta.getAttribute("content") || "";
    if (value && value !== PLACEHOLDER) return value;
  }
  return "";
}

// The URL with ?since=<rev> added: the server answers 304 when the revision still matches (no body). A null or empty
// rev gives the URL unchanged.
export function sinceUrl(url, rev) {
  if (!rev) return url;
  return url + (url.indexOf("?") >= 0 ? "&" : "?") + "since=" + encodeURIComponent(rev);
}

// GET a JSON resource. Resolves to {status, data, etag, changed}. A 304 resolves with the body kept from the last 200
// and changed:false, so the caller keeps what it stored (no re-normalize, no new fetch time). A 304 with no kept body
// (a since= request whose URL was never fetched here) resolves with data:null and changed:false, so the caller
// keeps its own stored copy.
export async function getJson(url) {
  const cached = etagCache.get(url);
  const headers = { Accept: "application/json" };
  if (cached) headers["If-None-Match"] = cached.etag;
  let response;
  const started = Date.now();
  try {
    response = await fetch(url, { headers: headers, credentials: "same-origin" });
  } catch (err) {
    noteRequest("GET", url, 0, started);
    throw new ApiError(0, "network", "Could not reach the server. Retrying.");
  }
  noteRequest("GET", url, response.status, started);
  if (response.status === 304) {
    if (cached) return { status: 304, data: cached.data, etag: cached.etag, changed: false };
    return { status: 304, data: null, etag: null, changed: false };
  }
  if (!response.ok) throw failure(response.status, await readJson(response));
  const data = await readJson(response);
  if (data === null) throw new ApiError(response.status, "bad_body", "The server sent an unreadable reply.");
  const etag = response.headers.get("ETag");
  if (etag) etagCache.set(url, { etag: etag, data: data });
  return { status: response.status, data: data, etag: etag, changed: true };
}

async function sendPost(url, body, token) {
  const started = Date.now();
  try {
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Roadmap-CSRF": token,
        Accept: "application/json",
      },
      body: JSON.stringify(body || {}),
      credentials: "same-origin",
    });
    noteRequest("POST", url, response.status, started);
    return response;
  } catch (err) {
    noteRequest("POST", url, 0, started);
    throw new ApiError(0, "network", "Could not reach the server. Retrying.");
  }
}

// After a server restart a tab holds the old CSRF value. The served page (GET /, same origin) carries the current one.
// Resolves to true when a different value was read into freshToken. Never throws.
async function rereadToken(sent) {
  try {
    const res = await fetch("/", { credentials: "same-origin", cache: "no-store" });
    if (!res.ok) return false;
    const html = await res.text();
    const found = /<meta name="csrf" content="([^"]+)"/g;
    let match = found.exec(html);
    while (match && match[1] === PLACEHOLDER) match = found.exec(html);
    if (!match || match[1] === sent) return false;
    freshToken = match[1];
    return true;
  } catch (err) {
    return false;
  }
}

// POST a JSON body with the CSRF header. Resolves to {status, data}. A 403 that names the CSRF token is retried once
// with the value re-read from the page; any other failure, or a second refusal, is thrown as an ApiError.
export async function postJson(url, body) {
  const token = csrfToken();
  if (!token) throw new ApiError(0, "no_token", "This page has no security token. Reload the page.");
  let response = await sendPost(url, body, token);
  if (response.ok) {
    return { status: response.status, data: await readJson(response) };
  }
  let refusal = await readJson(response);
  const named = refusal && refusal.error && String(refusal.error.message || "");
  if (response.status === 403 && /CSRF/i.test(named || "") && (await rereadToken(token))) {
    response = await sendPost(url, body, freshToken);
    if (response.ok) {
      return { status: response.status, data: await readJson(response) };
    }
    refusal = await readJson(response);
  }
  throw failure(response.status, refusal);
}
