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

async function failure(response) {
  const body = await readJson(response);
  const error = body && body.error;
  if (error && typeof error.message === "string") {
    return new ApiError(response.status, String(error.code || "http"), error.message);
  }
  return new ApiError(response.status, "http", "The server answered with status " + response.status + ".");
}

export function csrfToken() {
  const metas = document.querySelectorAll('meta[name="csrf"]');
  for (const meta of metas) {
    const value = meta.getAttribute("content") || "";
    if (value && value !== PLACEHOLDER) return value;
  }
  return "";
}

// GET a JSON resource. Resolves to {status, data, etag}. A 304 resolves with the body kept from the last 200.
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
  if (response.status === 304 && cached) {
    return { status: 304, data: cached.data, etag: cached.etag };
  }
  if (!response.ok) throw await failure(response);
  const data = await readJson(response);
  if (data === null) throw new ApiError(response.status, "bad_body", "The server sent an unreadable reply.");
  const etag = response.headers.get("ETag");
  if (etag) etagCache.set(url, { etag: etag, data: data });
  return { status: response.status, data: data, etag: etag };
}

// POST a JSON body with the CSRF header. Resolves to {status, data}.
export async function postJson(url, body) {
  const token = csrfToken();
  if (!token) throw new ApiError(0, "no_token", "This page has no security token. Reload the page.");
  let response;
  const started = Date.now();
  try {
    response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Roadmap-CSRF": token,
        Accept: "application/json",
      },
      body: JSON.stringify(body || {}),
      credentials: "same-origin",
    });
  } catch (err) {
    noteRequest("POST", url, 0, started);
    throw new ApiError(0, "network", "Could not reach the server. Retrying.");
  }
  noteRequest("POST", url, response.status, started);
  if (!response.ok) throw await failure(response);
  const data = await readJson(response);
  return { status: response.status, data: data };
}
