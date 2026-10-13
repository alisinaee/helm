// Boot, the poll loop and the shell. Snapshots refresh every 2 s and plan usage every 30 s. While the tab is hidden
// everything refreshes every 30 s. The shell (nav, top bar, toasts, help) renders on every pass; the section in
// <main> is a module loaded on first visit (routes.js), and a section that fails renders its own error without taking
// the shell down. Writes go through cmd.js, the one write path.

import { getJson, postJson } from "./api.js";
import { bannerHtml, emptyHtml, esc, patch, setHidden, skeletonHtml } from "./dom.js";
import { buildViewModel, createStore, isSheetWidth, loadPrefs, loadTheme, loadUi, nextTheme, normalizeSnapshot,
  normalizeUsage, panelIsOpen, saveTheme, savePrefs, sectionOpenState, updateUi } from "./state.js";
import { currentRoute, onRouteChange } from "./router.js";
import { loadSection, sectionById } from "./routes.js";
import { configureCommands, pendingValue, run } from "./cmd.js";
import { initKeys, setKeyHooks } from "./keys.js";
import { bnavView, navView, toggleMore } from "./views/nav.js";
import { pageAction } from "./views/inbox.js";
import { initPanel, panelView } from "./views/panel.js";
import { topbarView } from "./views/topbar.js";
import { dismissToast, setToastHold, setToastListener, toastsHtml, undoToast } from "./views/toast.js";

const FAST_MS = 2000;
const SLOW_MS = 30000;
const USAGE_MS = 30000;

const root = document.getElementById("app");
const liveRegion = document.getElementById("live-status");
const helpDialog = document.getElementById("help");
const store = createStore();
const prefsCache = new Map();
const failedSections = new Set();
const loadedSections = new Map();
const missingSections = new Set();
const loadingSections = new Set();
let timer = null;
let busy = false;
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

function comingSoonHtml(section) {
  return emptyHtml("Coming soon", "<span>" + esc(section.label) + " is not built yet.</span>");
}

// The section in <main>. A module loads once; until it is in, a skeleton shows and the next render picks it up.
function ensureLoaded(section) {
  if (loadingSections.has(section.id)) return;
  loadingSections.add(section.id);
  loadSection(section).then(function (mod) {
    loadedSections.set(section.id, mod);
  }, function () {
    missingSections.add(section.id);
  }).then(function () {
    loadingSections.delete(section.id);
    render();
  });
}

function mainHtml(vm) {
  const section = sectionById(vm.route.section);
  if (!section) return comingSoonHtml({ label: "This section" });
  if (loadedSections.has(section.id)) return loadedSections.get(section.id).sectionView(vm);
  if (!section.module || missingSections.has(section.id)) return comingSoonHtml(section);
  ensureLoaded(section);
  return '<div aria-busy="true">' + skeletonHtml(["w-60", "w-90"]) + "</div>";
}

function helpHtml() {
  const rows = [
    ["?", "Show this list"],
    ["[", "Collapse or expand the navigation"],
    ["]", "Show or hide the side panel"],
    ["z", "Undo the newest change"],
    ["Esc", "Close this list, or the panel sheet"],
    ["g, then o i r w u a t e n v ,", "Go to a section: Overview, Inbox, Roadmap, Work, Issues, Agents, " +
      "Tokens, Rules, Research, Activity, Settings"],
    ["g, then h", "Go to All projects"],
  ];
  return '<dl class="help-rows">' + rows.map(function (row) {
    return '<dt><span class="kbd">' + esc(row[0]) + '</span></dt><dd class="help-desc">' + esc(row[1]) + "</dd>";
  }).join("") + "</dl>";
}

// The snapshots in scope: the project's, or every project's in All projects, in registry order.
function snapshotsInScope(route) {
  if (route.name === "project") {
    const snap = store.snapshots[route.id];
    return snap ? [snap] : [];
  }
  return (store.projects || []).map(function (p) {
    return store.snapshots[p.id];
  }).filter(Boolean);
}

// The control state of the project in scope, with a pending value from a write still in flight.
function controlFor(route, snap, now) {
  if (route.name !== "project") return null;
  if (!snap) return { known: false, id: route.id };
  const pending = pendingValue("control:" + route.id, snap.fetchedAt, now);
  return {
    known: true,
    id: route.id,
    stopped: pending !== undefined ? pending === true : snap.control.stopped,
    blocked: snap.control.blocked,
    reason: snap.control.reason,
  };
}

// The limit rows for the top bar: the project's, else the first snapshot that has meters. Null means unknown.
function meterRowsFor(snapshots) {
  for (const snap of snapshots) {
    if (snap.meters) return snap.meters;
  }
  return null;
}

function buildShellVm(route, now) {
  const vm = buildViewModel(store, route, prefsFor(route), now);
  const snapshots = snapshotsInScope(route);
  vm.ui = loadUi();
  vm.theme = vm.ui.theme;
  vm.snapshotList = snapshots;
  vm.meterRows = meterRowsFor(snapshots);
  vm.control = controlFor(route, route.name === "project" ? store.snapshots[route.id] : null, now);
  return vm;
}

function applyLayout(ui) {
  root.setAttribute("data-nav", ui.navMini ? "mini" : "full");
  const open = panelIsOpen(ui);
  root.setAttribute("data-panel", open ? "open" : "closed");
  setHidden("scrim", !(isSheetWidth() && open));
}

function render() {
  const route = currentRoute();
  if (route.redirect) {
    window.location.replace(route.redirect);
    return;
  }
  const vm = buildShellVm(route, Date.now());
  document.title = vm.title;
  applyLayout(vm.ui);
  if (route.name === "project" && vm.ui.lastProject !== route.id) {
    updateUi(function (ui) {
      ui.lastProject = route.id;
    });
  }
  const sections = [
    ["nav", function () {
      return navView(vm);
    }],
    ["topbar", function () {
      return topbarView(vm);
    }],
    ["main", function () {
      return mainHtml(vm);
    }],
    ["side", function () {
      return panelView(vm);
    }],
    ["bnav", function () {
      return bnavView(vm);
    }],
    ["toasts", function () {
      return toastsHtml();
    }],
    ["help-body", function () {
      return helpHtml();
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

// Stop or Resume the project in scope. The pill shows the new state at once; cmd.js keeps it until a later snapshot.
function controlOp(el) {
  const op = el.getAttribute("data-op");
  const project = el.getAttribute("data-project");
  const stopping = op === "control.stop";
  run(op, {}, {
    project: project,
    key: "control:" + project,
    value: stopping,
    label: stopping ? "Stopped" : "Resumed",
  });
}

function openHelp() {
  if (!helpDialog.open) helpDialog.showModal();
}

function closeHelp() {
  if (helpDialog.open) helpDialog.close();
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
  } else if (action === "control") {
    controlOp(el);
  } else if (action === "nav-mini") {
    updateUi(function (ui) {
      ui.navMini = !ui.navMini;
    });
    render();
  } else if (action === "panel-toggle") {
    updateUi(function (ui) {
      ui.panelOpen = !panelIsOpen(ui);
    });
    render();
  } else if (action === "panel-close") {
    updateUi(function (ui) {
      ui.panelOpen = false;
    });
    render();
  } else if (action === "toggle-more") {
    toggleMore();
    render();
  } else if (action === "help-open") {
    openHelp();
  } else if (action === "help-close") {
    closeHelp();
  } else if (action === "toast-undo") {
    undoToast(el.getAttribute("data-toast"));
  } else if (action === "toast-close") {
    dismissToast(el.getAttribute("data-toast"));
  } else if (action === "inbox-answer" || action === "undo-line" || action === "override") {
    pageAction(action, el);
  }
}

// A toast holds its timer while the pointer or the keyboard focus is on it.
function toastIdOf(target) {
  const el = target && target.closest ? target.closest("[data-toast]") : null;
  return el ? el.getAttribute("data-toast") : null;
}

function onPointerOver(event) {
  const id = toastIdOf(event.target);
  if (id) setToastHold(id, true);
}

function onPointerOut(event) {
  const id = toastIdOf(event.target);
  if (!id) return;
  const next = toastIdOf(event.relatedTarget);
  if (next !== id) setToastHold(id, false);
}

function boot() {
  applyTheme(loadTheme());
  setKeyHooks({
    rerender: render,
    openHelp: openHelp,
    closeHelp: closeHelp,
    helpOpen: function () {
      return helpDialog.open;
    },
  });
  configureCommands({
    writable: function () {
      return store.conn.ok !== false;
    },
    refresh: function () {
      schedule(0);
    },
    render: render,
    project: function () {
      const route = currentRoute();
      return route.name === "project" ? route.id : null;
    },
  });
  setToastListener(function () {
    patch("toasts", toastsHtml());
  });
  initKeys();
  initPanel({ render: render });
  document.addEventListener("click", onClick);
  document.addEventListener("pointerover", onPointerOver);
  document.addEventListener("pointerout", onPointerOut);
  document.addEventListener("focusin", onPointerOver);
  document.addEventListener("focusout", onPointerOut);
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) schedule(0);
  });
  helpDialog.addEventListener("close", render);
  onRouteChange(function () {
    render();
    schedule(0);
  });
  render();
  schedule(0);
}

boot();
