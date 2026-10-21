// Boot, the poll loop and the shell. Snapshots refresh every 2 s; the usage reading rides in each snapshot
// (snap.usage). While the tab is hidden everything refreshes every 30 s. The shell (nav, top bar, toasts, help)
// renders on every pass; the section in <main> is a module loaded on first visit (routes.js), and a section that
// fails renders its own error without taking the shell down. Writes go through cmd.js, the one write path.

import { getJson, postJson, sinceUrl } from "./api.js";
import { bannerHtml, emptyHtml, esc, patch, setHidden, skeletonHtml } from "./dom.js";
import { buildViewModel, createStore, isSheetWidth, loadMode, loadPrefs, loadTheme, loadUi, normalizeSnapshot,
  panelIsOpen, resolveMode, saveMode, savePrefs, sectionOpenState, updateUi } from "./state.js";
import { currentRoute, onRouteChange } from "./router.js";
import { fullRouteOf, fullSystemOf, loadSection, sectionById } from "./routes.js";
import { configureCommands, pendingValue, run } from "./cmd.js";
import { withBusy } from "./busy.js";
import { initKeys, setKeyHooks } from "./keys.js";
import { featureLinkChange } from "./views/details.js";
import { bnavView, navView, toggleMore } from "./views/nav.js";
import { pageAction } from "./views/inbox.js";
import { openPalette } from "./views/palette.js";
import { limitAction } from "./views/limits.js";
import { ruleAction } from "./views/rules.js";
import { settingsAction } from "./views/settings.js";
import { initPanel, panelView } from "./views/panel.js";
import { initResize } from "./resize.js";
import { initSplitters } from "./splitter.js";
import { initToolbars } from "./toolbar.js";
import { isLightNow, topbarView } from "./views/topbar.js";
import { dismissToast, setToastHold, setToastListener, toastsHtml, undoToast } from "./views/toast.js";
import { copyRef } from "./ref.js";
import { installLog, logAction, noteRender, noteRoute } from "./log.js";

const FAST_MS = 2000;
const SLOW_MS = 30000;

const root = document.getElementById("app");
const liveRegion = document.getElementById("live-status");
const helpDialog = document.getElementById("help");
const store = createStore();
const prefsCache = new Map();
const failedSections = new Set();
const loadedSections = new Map();
// A failed section import is not cached: its rejected promise is dropped, the error is kept here for the inline
// "Could not load" state, and a retry imports again. autoRetried allows one automatic retry per section.
const importErrors = new Map();
const importTries = new Map();
const autoRetried = new Set();
const AUTO_RETRY_MS = 1000;
const loadingSections = new Set();
let timer = null;
let busy = false;
let followUp = false;
// A pass that found nothing new skips the render, but at least this often one renders anyway (clock-driven labels).
const SKIP_RENDER_MAX_MS = 10000;
let lastRenderAt = 0;
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

// data-theme is the palette; data-mode is always dark or light (auto is resolved here, see resolveMode).
function applyTheme(theme, mode) {
  const html = document.documentElement;
  html.setAttribute("data-theme", theme);
  html.setAttribute("data-mode", resolveMode(mode));
}

// While the mode is auto, a change of the system preference re-applies the look.
function watchSystemMode() {
  if (typeof matchMedia !== "function") return;
  const query = matchMedia("(prefers-color-scheme: light)");
  const onChange = () => {
    if (loadMode() !== "auto") return;
    applyTheme(loadTheme(), "auto");
    render();
  };
  if (query.addEventListener) query.addEventListener("change", onChange);
}

// The sun/moon button flips the mode (dark <-> light). The new mode spreads out as a circle from the switch button
// (View Transitions API). Browsers without it, and reduced-motion users, get the change at once.
function switchMode(next, origin) {
  const apply = () => {
    saveMode(next);
    applyTheme(loadTheme(), next);
    render();
  };
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (!document.startViewTransition || reduce) {
    apply();
    return;
  }
  const box = origin ? origin.getBoundingClientRect() : null;
  const x = box ? box.left + box.width / 2 : window.innerWidth - 40;
  const y = box ? box.top + box.height / 2 : 40;
  const radius = Math.hypot(Math.max(x, window.innerWidth - x), Math.max(y, window.innerHeight - y));
  const transition = document.startViewTransition(apply);
  transition.ready.then(() => {
    document.documentElement.animate(
      { clipPath: ["circle(0px at " + x + "px " + y + "px)", "circle(" + radius + "px at " + x + "px " + y + "px)"] },
      { duration: 620, easing: "cubic-bezier(.2,.8,.2,1)", pseudoElement: "::view-transition-new(root)" });
  });
}

function errorHtml(sectionId, err) {
  return bannerHtml("danger", "This section could not be shown.",
    (err && err.message ? err.message : "Unknown error") + " (" + sectionId + ")");
}

function comingSoonHtml(section) {
  return emptyHtml("Coming soon", "<span>" + esc(section.label) + " is not built yet.</span>");
}

// A section whose import failed: a small inline state with a Retry button (data-action section-retry).
function importErrorHtml(section) {
  return '<div class="empty" role="alert"><p>Could not load this section · ' +
    '<button type="button" class="btn btn-small" data-action="section-retry" data-section="' + esc(section.id) +
    '">Retry</button></p></div>';
}

// The section in <main>. A module loads once; until it is in, a skeleton shows and the next render picks it up.
// A failed import is retried once after AUTO_RETRY_MS, then only by the Retry button.
function ensureLoaded(section) {
  if (loadingSections.has(section.id)) return;
  loadingSections.add(section.id);
  // The browser caches a failed module URL for good, so every attempt after the first adds a query to the URL.
  const tries = (importTries.get(section.id) || 0) + 1;
  importTries.set(section.id, tries);
  const target = tries > 1 ? Object.assign({}, section, { module: section.module + "?retry=" + tries }) : section;
  loadSection(target).then(function (mod) {
    importErrors.delete(section.id);
    loadedSections.set(section.id, mod);
    // The Planner binds its delegated listeners once, on the <main> element that stays in place across renders.
    if (section.id === "planner" && typeof mod.bind === "function") mod.bind(document.getElementById("main"));
  }, function (err) {
    importErrors.set(section.id, err || new Error("import failed"));
    if (!autoRetried.has(section.id)) {
      autoRetried.add(section.id);
      setTimeout(function () {
        if (importErrors.has(section.id)) retrySection(section.id);
      }, AUTO_RETRY_MS);
    }
  }).then(function () {
    loadingSections.delete(section.id);
    render();
  });
}

// Retry button and the automatic retry: the error clears, a skeleton shows, and the import runs again.
function retrySection(sectionId) {
  const section = sectionById(sectionId);
  if (!section || !section.module || loadedSections.has(sectionId)) return;
  importErrors.delete(sectionId);
  ensureLoaded(section);
  render();
}

function mainHtml(vm) {
  const section = sectionById(vm.route.section);
  if (!section) return comingSoonHtml({ label: "This section" });
  if (loadedSections.has(section.id)) return loadedSections.get(section.id).sectionView(vm);
  if (!section.module) return comingSoonHtml(section);
  if (importErrors.has(section.id)) return importErrorHtml(section);
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
    ["g, then o i r w u a t e v ,", "Go to a section: Overview, Inbox, Roadmap, Work, Issues, Agents, " +
      "Tokens, Rules, Activity, Settings"],
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

// Limits windows (stop per window) for the top bar ticks, from /api/v1/limits; refreshed at most every 10 s.
let topLimits = { windows: null, at: 0 };
function topLimitsFor() {
  if (!document.hidden && Date.now() - topLimits.at > 10000) {
    topLimits.at = Date.now();
    getJson("/api/v1/limits").then(function (res) {
      if (res && res.status === 200 && res.data && res.data.windows) {
        const prev = JSON.stringify(topLimits.windows);
        topLimits.windows = res.data.windows;
        if (JSON.stringify(topLimits.windows) !== prev) document.dispatchEvent(new Event("rb:render"));
      }
    }).catch(function () {});
  }
  return topLimits.windows ? { windows: topLimits.windows } : null;
}

function buildShellVm(route, now) {
  const vm = buildViewModel(store, route, prefsFor(route), now);
  const snapshots = snapshotsInScope(route);
  vm.ui = loadUi();
  vm.theme = vm.ui.theme;
  vm.mode = vm.ui.mode;
  vm.snapshotList = snapshots;
  vm.meterRows = meterRowsFor(snapshots);
  vm.limits = topLimitsFor();
  vm.control = controlFor(route, route.name === "project" ? store.snapshots[route.id] : null, now);
  return vm;
}

function applyLayout(ui) {
  // Below 1200 px the CSS draws the nav as a rail, so the rail's badge rules must apply there too.
  root.setAttribute("data-nav", ui.navMini || isSheetWidth() ? "mini" : "full");
  const open = panelIsOpen(ui);
  root.setAttribute("data-panel", open ? "open" : "closed");
  setHidden("scrim", !(isSheetWidth() && open));
}

// The full-screen Map (#/full/<pid>/workflow) replaces the shell: #app is hidden and #full-view holds the diagram.
function renderFull(pid) {
  root.hidden = true;
  let host = document.getElementById("full-view");
  if (!host) {
    host = document.createElement("div");
    host.id = "full-view";
    document.body.appendChild(host);
  }
  host.hidden = false;
  document.title = "Workflow map";
  import("./views/workflow.js").then(function (mod) {
    mod.mountFull(host, pid);
  });
}

let sysFull = false;
function renderFullSystem(pid) {
  sysFull = true;
  root.hidden = true;
  let host = document.getElementById("full-view");
  if (!host) {
    host = document.createElement("div");
    host.id = "full-view";
    document.body.appendChild(host);
  }
  host.hidden = false;
  document.title = "System";
  import("./views/system.js").then(function (mod) {
    mod.mountFull(host, pid);
  });
}

function render() {
  const started = Date.now();
  if (sysFull && !fullSystemOf(window.location.hash)) {
    sysFull = false;
    const fh = document.getElementById("full-view");
    if (fh) {
      fh.textContent = "";
      fh.style.cssText = "";
    }
    import("./views/system.js").then(function (mod) {
      mod.leaveFull();
    });
  }
  const fullPid = fullRouteOf(window.location.hash);
  if (fullPid) {
    renderFull(fullPid);
    return;
  }
  const sysPid = fullSystemOf(window.location.hash);
  if (sysPid) {
    renderFullSystem(sysPid);
    return;
  }
  root.hidden = false;
  const fullHost = document.getElementById("full-view");
  if (fullHost) fullHost.hidden = true;
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
  noteRender(route.name === "project" ? route.section || "project" : "home", started);
}

function announce(ok) {
  if (ok === lastOk) return;
  lastOk = ok;
  if (ok === true) liveRegion.textContent = "Connected.";
  if (ok === false) liveRegion.textContent = "Disconnected, retrying.";
}

// The rev of a project's stored snapshot, or null when none is stored.
function storedRev(id) {
  const snap = store.snapshots[id];
  return snap && snap.rev ? snap.rev : null;
}

// The projects whose snapshot this poll reads: the open project always, and every other project whose summary rev
// differs from the stored snapshot (or whose summary carries no rev). A project whose rev is unchanged is not read.
function idsToRead(route) {
  const ids = route.name === "project" ? [route.id] : [];
  for (const row of store.projects || []) {
    if (ids.indexOf(row.id) >= 0) continue;
    const rev = typeof row.rev === "string" ? row.rev : null;
    if (!rev || storedRev(row.id) !== rev) ids.push(row.id);
  }
  return ids;
}

// One refresh pass. Resolves to true when something on the page may have changed (a new reply, an error, a
// connection change) and false when every read answered unchanged: the caller then skips the render.
async function refresh() {
  const route = currentRoute();
  const now = Date.now();
  let changed = false;
  const wasOk = store.conn.ok;
  try {
    const res = await getJson("/api/v1/projects");
    if (res.changed) changed = true;
    store.projects = res.data.projects || [];
    store.projectsError = null;
    store.conn = { ok: true, lastOkAt: now, error: null };
  } catch (err) {
    changed = true;
    store.projectsError = err;
    store.conn = { ok: false, lastOkAt: store.conn.lastOkAt, error: err.message };
  }
  if (!wasOk || !store.conn.ok) changed = true;
  announce(store.conn.ok);
  await Promise.all(idsToRead(route).map(async function (id) {
    try {
      // ?since=<stored rev>: the server answers 304 (unchanged, no body) when the stored snapshot is current.
      const url = sinceUrl("/api/v1/projects/" + encodeURIComponent(id) + "/snapshot", storedRev(id));
      const res = await getJson(url);
      // 304: the stored body is still current. Keep it and its fetch time; nothing is re-normalized.
      if (res.changed) {
        store.snapshots[id] = normalizeSnapshot(res.data, now);
        changed = true;
      }
      if (store.snapshotErrors[id]) changed = true;
      delete store.snapshotErrors[id];
    } catch (err) {
      changed = true;
      store.snapshotErrors[id] = err;
    }
  }));
  return changed;
}

async function loop() {
  // A refresh requested while one is in flight (a write, a route change) is queued once, not dropped.
  if (busy) {
    followUp = true;
    return;
  }
  busy = true;
  let changed = true;
  try {
    changed = await refresh();
  } catch (err) {
    // refresh() handles its own failures; anything else must not stop the loop.
    store.conn = { ok: false, lastOkAt: store.conn.lastOkAt, error: String(err) };
  } finally {
    busy = false;
  }
  // Nothing new from the server: keep the page as it is. A render still runs at least every SKIP_RENDER_MAX_MS.
  // The next pass is always scheduled, also when a view throws while rendering: one bad render must not end the
  // live updates (the page would then only change after a manual reload).
  const due = Date.now() - lastRenderAt >= SKIP_RENDER_MAX_MS;
  topLimitsFor();
  try {
    if (changed || followUp || due) {
      render();
      lastRenderAt = Date.now();
    }
  } catch (err) {
    store.conn = { ok: store.conn.ok, lastOkAt: store.conn.lastOkAt, error: String(err) };
    if (typeof console !== "undefined") console.error("render failed", err);
  } finally {
    const again = followUp;
    followUp = false;
    schedule(again ? 0 : document.hidden ? SLOW_MS : FAST_MS);
  }
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
    // render() drew the sync button again: mark that new node busy while the sync request runs.
    await withBusy(document.querySelector('[data-action="sync-usage"]'), postJson("/api/v1/usage/sync", {}));
    store.sync = { state: "ok", message: "Usage synced." };
    render();
    // The new reading and meters come in the next snapshot (snap.usage, snap.meters): read it now.
    schedule(0);
    return;
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
  logAction(action, el, null);
  if (action === "toggle-section") {
    toggleSection(route, el.getAttribute("data-section"));
  } else if (action === "toggle-item") {
    toggleItem(route, el);
  } else if (action === "set-mode") {
    setMode(route, el.getAttribute("data-mode"));
  } else if (action === "theme-toggle") {
    switchMode(isLightNow(loadMode()) ? "dark" : "light", el);
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
  } else if (action === "copy-ref") {
    // Copy reference (ref.js refButtonHtml). The button is a SIBLING of any toggle button, never nested in one:
    // closest() returns the copy button itself, so a row or section toggle does not fire too.
    // No render: copying changes nothing on the page.
    copyRef(el);
  } else if (action === "section-retry") {
    retrySection(el.getAttribute("data-section"));
  } else if (action === "inbox-answer" || action === "undo-line" || action === "override" ||
    action === "rule-accept" || action === "rule-reject" || action === "head-dismiss") {
    pageAction(action, el);
  } else if (limitAction(action, el) || ruleAction(action, el) || settingsAction(action, el)) {
    render();
  } else if (action === "plan-move" || action === "phase-approve") {
    sectionAction("./views/roadmap.js", action, el);
  } else if (action === "agent-stop") {
    sectionAction("./views/agents.js", action, el);
  }
}

// Roadmap buttons (WP32) are handled by their section modules, which are loaded already when the button
// was drawn; the import only fetches the module's exports.
function sectionAction(path, action, el) {
  import(path).then(function (mod) {
    mod.pageAction(action, el);
  });
}

// The Work drawer's "Link to feature" picker (WP55). details.js owns the write; this only routes the change event.
function onChange(event) {
  const el = event.target;
  if (el && el.getAttribute && el.getAttribute("data-side") === "feat-link") featureLinkChange(el);
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
  installLog();
  applyTheme(loadTheme(), loadMode());
  watchSystemMode();
  setKeyHooks({
    rerender: render,
    openHelp: openHelp,
    closeHelp: closeHelp,
    helpOpen: function () {
      return helpDialog.open;
    },
    openPalette: function () {
      const route = currentRoute();
      openPalette(route.name === "project" ? store.snapshots[route.id] || null : null);
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
    rev: storedRev,
  });
  setToastListener(function () {
    patch("toasts", toastsHtml());
  });
  initKeys();
  initPanel({ render: render });
  initResize();
  initSplitters();
  initToolbars();
  document.addEventListener("click", onClick);
  document.addEventListener("change", onChange);
  document.addEventListener("rb:render", render);
  document.addEventListener("rb:limits", function (e) {
    if (!e.detail || typeof e.detail !== "object") return;
    const prev = JSON.stringify(topLimits.windows);
    topLimits.windows = e.detail;
    topLimits.at = Date.now();
    if (JSON.stringify(topLimits.windows) !== prev) document.dispatchEvent(new Event("rb:render"));
  });
  document.addEventListener("pointerover", onPointerOver);
  document.addEventListener("pointerout", onPointerOut);
  document.addEventListener("focusin", onPointerOver);
  document.addEventListener("focusout", onPointerOut);
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) schedule(0);
  });
  helpDialog.addEventListener("close", render);
  onRouteChange(function () {
    noteRoute();
    render();
    schedule(0);
  });
  render();
  schedule(0);
}

boot();
