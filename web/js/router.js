// Hash routes (WP28). "#/all/<section>" is the global scope. "#/p/<id>/<section>[/<view>][/i/<item>]" is one project.
// Filters ride in the hash query: "#/all/work?f=state:todo&g=phase". Old "#/" and "#/p/<id>" links are redirected.
// currentRoute() returns the parsed route; when the hash is not in canonical form it also carries "redirect", and
// app.js replaces the hash with it.

import { DEFAULT_SECTION, sectionById } from "./routes.js";

const PROJECT_ID = /^[a-z0-9][a-z0-9-]{0,39}$/;
const SEGMENT = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,59}$/;
const FILTER_KEYS = ["f", "g"];
const FILTER_MAX = 200;

function splitHash(hash) {
  const raw = String(hash || "").replace(/^#/, "");
  const at = raw.indexOf("?");
  const path = at >= 0 ? raw.slice(0, at) : raw;
  const query = at >= 0 ? raw.slice(at + 1) : "";
  const parts = path.split("/").filter(function (part) {
    return part.length > 0;
  });
  return { parts: parts, query: query };
}

function filtersFrom(query) {
  const filters = {};
  const params = new URLSearchParams(query);
  for (const key of FILTER_KEYS) {
    const value = params.get(key);
    if (value && value.length <= FILTER_MAX) filters[key] = value;
  }
  return filters;
}

function queryFrom(filters) {
  const params = new URLSearchParams();
  for (const key of FILTER_KEYS) {
    if (filters[key]) params.set(key, filters[key]);
  }
  const text = params.toString();
  return text ? "?" + text : "";
}

// The canonical hash for a route, for example "#/p/rb-site/work/board/i/t12?f=state:todo".
export function buildHash(route) {
  const base = route.name === "project" ? "#/p/" + route.id : "#/all";
  const section = route.section || DEFAULT_SECTION;
  const view = route.view ? "/" + route.view : "";
  const item = route.item ? "/i/" + route.item : "";
  return base + "/" + section + view + item + queryFrom(route.filters || {});
}

export function parseRoute(hash) {
  const split = splitHash(hash);
  const parts = split.parts;
  const filters = filtersFrom(split.query);
  let name = "home";
  let id = null;
  let rest = [];
  if (parts[0] === "p" && PROJECT_ID.test(parts[1] || "")) {
    name = "project";
    id = parts[1];
    rest = parts.slice(2);
  } else if (parts.length === 0 || parts[0] === "all") {
    rest = parts.slice(1);
  } else if (parts[0] === "p") {
    rest = [];
  } else {
    rest = parts;
  }
  // Old "#/p/<id>" links have no section: they go to that project's overview.
  let section = rest[0] || DEFAULT_SECTION;
  if (!sectionById(section)) section = DEFAULT_SECTION;
  let view = null;
  let item = null;
  const at = rest.indexOf("i");
  if (at >= 0) {
    item = rest[at + 1] || null;
    view = at >= 2 ? rest[1] : null;
  } else {
    view = rest[1] || null;
  }
  if (view && !SEGMENT.test(view)) view = null;
  if (item && !SEGMENT.test(item)) item = null;
  const route = { name: name, id: id, section: section, view: view, item: item, filters: filters };
  const canonical = buildHash(route);
  const current = String(hash || "");
  if (current !== canonical && current.replace(/^#\/?/, "#/") !== canonical) {
    route.redirect = canonical;
  }
  return route;
}

export function currentRoute() {
  return parseRoute(window.location.hash);
}

export function homeHash() {
  return "#/all/" + DEFAULT_SECTION;
}

export function projectHash(id, section) {
  return "#/p/" + id + "/" + (section || DEFAULT_SECTION);
}

// The same scope as the route, pointing at another section.
export function sectionHash(route, section) {
  if (route && route.name === "project" && route.id) return projectHash(route.id, section);
  return "#/all/" + section;
}

export function onRouteChange(handler) {
  window.addEventListener("hashchange", handler);
}
