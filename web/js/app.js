// Boot and the poll loop. Snapshots refresh every 2 s and plan usage every 30 s. While the tab is hidden everything
// refreshes every 30 s. Each view renders inside its own try/catch: a failing view shows its section's error and
// sets data-render-error on #app, and the other sections keep working.

import { getJson, postJson } from "./api.js";
import { bannerHtml, patch, setHidden } from "./dom.js";
import { buildViewModel, createStore, loadPrefs, loadTheme, nextTheme, normalizeSnapshot, normalizeUsage,
  saveTheme, savePrefs, sectionOpenState, VIEW_SECTIONS } from "./state.js";
import { currentRoute, homeHash, onRouteChange, projectHash } from "./router.js";
import { topbarView } from "./views/topbar.js";
import { usageView } from "./views/usage.js";
import { kpiView } from "./views/kpi.js";
import { homeView, projectView } from "./views/home.js";

const FAST_MS = 2000;
const SLOW_MS = 30000;
const USAGE_MS = 30000;

const root = document.getElementById("app");
const liveRegion = document.getElementById("live-status");
const store = createStore();
const prefsCache = new Map();
const failedSections = new Set();
let timer = null;
let busy = false;
let pendingG = 0;
let lastOk = null;

function prefsKey(route) {
  return route.name === "project" ? "project:" + route.id : "home";
}

function prefsFor(route) {
  const key = prefsKey(route);
  if (!prefsCache.has(key)) prefsCache.set(key, loadPrefs(key));
  return prefsCache.get(key);
}

function updatePrefs(route, change) {
  const prefs = prefsFor(route);
  change(prefs);
  savePrefs(prefsKey(route), prefs);
}

function applyTheme(theme) {
  const html = document.documentElement;
  if (theme === "auto") {
    html.removeAttribute("data-theme");
  } else {
    html.setAttribute("data-theme", theme);
  }
}

function errorHtml(sectionId, err) {
  return bannerHtml("danger", "This section could not be shown.",
    (err && err.message ? err.message : "Unknown error") + " (" + sectionId + ")");
}

function render() {
  const route = currentRoute();
  const vm = buildViewModel(store, route, prefsFor(route), Date.now());
  vm.theme = loadTheme();
  document.title = vm.title;
  setHidden("kpi", route.name !== "project");
  const sections = [
    ["topbar", function () {
      return topbarView(vm);
    }],
    ["usage", function () {
      return usageView(vm);
    }],
    ["kpi", function () {
      return route.name === "project" ? kpiView(vm) : "";
    }],
    ["main", function () {
      return route.name === "project" ? projectView(vm) : homeView(vm);
    }],
  ];
  for (const entry of sections) {
    try {
      patch(entry[0], entry[1]());
      failedSections.delete(entry[0]);
    } catch (err) {
      failedSections.add(entry[0]);
      patch(entry[0], errorHtml(entry[0], err));
    }
  }
  if (failedSections.size) {
    root.setAttribute("data-render-error", Array.from(failedSections).join(","));
  } else {
    root.removeAttribute("data-render-error");
  }
}

function announce(ok) {
  if (ok === lastOk) return;
  lastOk = ok;
  if (ok === true) liveRegion.textContent = "Connected.";
  if (ok === false) liveRegion.textContent = "Disconnected, retrying.";
}

async function refreshUsage(now) {
  try {
    const res = await getJson("/api/v1/usage");
    store.usage = normalizeUsage(res.data, now);
    store.usageError = null;
    store.usageFetchedAt = now;
  } catch (err) {
    store.usageError = err.message;
  }
}

async function refresh() {
  const route = currentRoute();
  const now = Date.now();
  try {
    const res = await getJson("/api/v1/projects");
    store.projects = res.data.projects || [];
    store.projectsError = null;
    store.conn = { ok: true, lastOkAt: now, error: null };
  } catch (err) {
    store.projectsError = err;
    store.conn = { ok: false, lastOkAt: store.conn.lastOkAt, error: err.message };
  }
  announce(store.conn.ok);
  let ids;
  if (route.name === "project") {
    ids = [route.id];
  } else {
    ids = (store.projects || []).map(function (p) {
      return p.id;
    });
  }
  await Promise.all(ids.map(async function (id) {
    try {
      const res = await getJson("/api/v1/projects/" + encodeURIComponent(id) + "/snapshot");
      store.snapshots[id] = normalizeSnapshot(res.data, now);
      delete store.snapshotErrors[id];
    } catch (err) {
      store.snapshotErrors[id] = err;
    }
  }));
  if (now - store.usageFetchedAt >= USAGE_MS) {
    await refreshUsage(now);
  }
}

async function loop() {
  if (!busy) {
    busy = true;
    try {
      await refresh();
    } catch (err) {
      // refresh() handles its own failures; anything else must not stop the loop.
      store.conn = { ok: false, lastOkAt: store.conn.lastOkAt, error: String(err) };
    } finally {
      busy = false;
    }
  }
  render();
  schedule(document.hidden ? SLOW_MS : FAST_MS);
}

function schedule(delay) {
  if (timer) window.clearTimeout(timer);
  timer = window.setTimeout(loop, delay);
}

async function syncUsage() {
  if (store.sync.state === "running") return;
  store.sync = { state: "running", message: "Syncing usage." };
  render();
  try {
    const res = await postJson("/api/v1/usage/sync", {});
    const now = Date.now();
    store.usage = normalizeUsage(res.data || {}, now);
    store.usageFetchedAt = now;
    store.usageError = null;
    store.sync = { state: "ok", message: "Usage synced." };
  } catch (err) {
    store.sync = { state: "error", message: "Sync failed: " + err.message };
  }
  render();
}

function setMode(route, mode) {
  updatePrefs(route, function (prefs) {
    prefs.mode = mode;
    prefs.open = {};
  });
  render();
}

function toggleSection(route, id) {
  const open = sectionOpenState(route.name, prefsFor(route));
  updatePrefs(route, function (prefs) {
    prefs.open[id] = !open[id];
  });
  render();
}

// Phase rows and deferred lists: flip the state the button shows (aria-expanded) and remember it per project.
function toggleItem(route, el) {
  const key = el.getAttribute("data-item");
  const expanded = el.getAttribute("aria-expanded") === "true";
  updatePrefs(route, function (prefs) {
    prefs.open[key] = !expanded;
  });
  render();
}

function setAllSections(route, value) {
  updatePrefs(route, function (prefs) {
    for (const section of VIEW_SECTIONS[route.name]) {
      prefs.open[section.id] = value;
    }
  });
  render();
}

function onClick(event) {
  const el = event.target.closest ? event.target.closest("[data-action]") : null;
  if (!el) return;
  const route = currentRoute();
  const action = el.getAttribute("data-action");
  if (action === "toggle-section") {
    toggleSection(route, el.getAttribute("data-section"));
  } else if (action === "toggle-item") {
    toggleItem(route, el);
  } else if (action === "set-mode") {
    setMode(route, el.getAttribute("data-mode"));
  } else if (action === "cycle-theme") {
    const next = nextTheme(loadTheme());
    saveTheme(next);
    applyTheme(next);
    render();
  } else if (action === "sync-usage") {
    syncUsage();
  }
}

function onChange(event) {
  const el = event.target;
  if (el && el.getAttribute && el.getAttribute("data-action") === "switch-project") {
    const value = el.value;
    window.location.hash = value ? projectHash(value) : homeHash();
  }
}

function isTyping(target) {
  return Boolean(target) && (target.isContentEditable || /^(INPUT|SELECT|TEXTAREA)$/.test(target.tagName));
}

function onKeydown(event) {
  if (event.defaultPrevented || event.ctrlKey || event.metaKey || event.altKey || isTyping(event.target)) {
    return;
  }
  const key = event.key;
  if (key === "g") {
    pendingG = Date.now();
    return;
  }
  if (key === "h" && pendingG && Date.now() - pendingG < 1000) {
    pendingG = 0;
    window.location.hash = homeHash();
    return;
  }
  pendingG = 0;
  if (key === "/") {
    event.preventDefault();
    const switcher = document.getElementById("switcher");
    if (switcher) switcher.focus();
  } else if (key === "[" || key === "]") {
    setAllSections(currentRoute(), key === "]");
  }
}

function boot() {
  applyTheme(loadTheme());
  document.addEventListener("click", onClick);
  document.addEventListener("change", onChange);
  document.addEventListener("keydown", onKeydown);
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) schedule(0);
  });
  onRouteChange(function () {
    render();
    schedule(0);
  });
  render();
  schedule(0);
}

boot();
