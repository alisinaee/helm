// Shared section toolbar (R11.7, docs/TOOLBAR-PATTERN.md). One compact row: view switcher (segmented), optional search,
// one "Filters" button with an active-count badge, up to two primary actions, and a "More" (...) overflow menu. The
// filter groups live in a popover that is collapsed by default; applied filters show as removable chips in one wrapped
// line only when at least one is active. toolbarHtml(cfg) returns an HTML string (no DOM); initToolbars() wires every
// toolbar through document-level delegation, so re-rendered views need no re-binding. Each user choice is sent as a
// bubbling CustomEvent "rb:toolbar" from the toolbar root with detail {key, type, value}; the section listens and
// re-renders. type: "view" | "token" (checkbox on/off, value = token) | "remove" | "clear" | "search" | "action".
// Open/closed state persists per key in localStorage "rb.toolbar" (try/catch); a closed popover is the default.
import { esc } from "./dom.js";

const STORE = "rb.toolbar";

function load() {
  try {
    const o = JSON.parse(window.localStorage.getItem(STORE) || "{}");
    return o && typeof o === "object" ? o : {};
  } catch (e) {
    return {};
  }
}

function save(key, open) {
  try {
    const o = load();
    if (open) o[key] = { open: true }; else delete o[key];
    window.localStorage.setItem(STORE, JSON.stringify(o));
  } catch (e) { /* storage unavailable */ }
}

export function isOpen(key) {
  const s = load()[key];
  return Boolean(s && s.open);
}

function safeKey(key) {
  return String(key || "x").toLowerCase().replace(/[^a-z0-9-]/g, "-");
}

// Every option that is on, in group order: [{group, label, token}].
export function activeFilters(cfg) {
  const out = [];
  (cfg.groups || []).forEach(function (g) {
    (g.options || []).forEach(function (o) {
      if (o.on) out.push({ group: g.label, label: o.label, token: o.token });
    });
  });
  return out;
}

export function activeCount(cfg) {
  return activeFilters(cfg).length;
}

// Comma-joined token list helpers, the same shape the Work route keeps in f= ("status:todo,model:haiku").
export function toggleToken(list, token) {
  const parts = String(list || "").split(",").filter(Boolean);
  const i = parts.indexOf(token);
  if (i >= 0) parts.splice(i, 1); else parts.push(token);
  return parts.join(",");
}

function viewsHtml(cfg, k) {
  if (!cfg.views || cfg.views.length < 2) return "";
  // More than 4 views do not fit as segments: they become one select (docs/TOOLBAR-PATTERN.md, Slot 1).
  if (cfg.views.length > 4) {
    return '<select class="tb-view-select" data-tb-view-select data-focus="tb-' + k + '-views" aria-label="View">' +
      cfg.views.map(function (v) {
        return '<option value="' + esc(v.id) + '"' + (v.current ? " selected" : "") + ">" + esc(v.label) + "</option>";
      }).join("") + "</select>";
  }
  return '<div class="tb-seg" role="group" aria-label="View">' + cfg.views.map(function (v) {
    // data-focus keeps focus on the same segment after dom.patch re-renders the section (view switch).
    return '<button type="button" class="tb-seg-btn" aria-pressed="' + (v.current ? "true" : "false") +
      '" data-tb-view="' + esc(v.id) + '" data-focus="tb-' + k + "-v-" + esc(v.id) + '">' + esc(v.label) + "</button>";
  }).join("") + "</div>";
}

function searchHtml(cfg, k) {
  if (!cfg.search) return "";
  const label = cfg.search.label || "Search";
  return '<input type="search" class="tb-search" id="tb-' + k + '-q" data-tb-search value="' +
    esc(cfg.search.value || "") + '" placeholder="' + esc(cfg.search.placeholder || label) +
    '" aria-label="' + esc(label) + '">';
}

function filtersButtonHtml(cfg, k, open) {
  if (!cfg.groups || !cfg.groups.length) return "";
  const n = activeCount(cfg);
  const badge = n ? ' <span class="tb-count">' + n + "</span>" : "";
  const label = n ? "Filters, " + n + " active" : "Filters";
  return '<button type="button" class="btn btn-small tb-filters" data-tb-toggle="pop" aria-haspopup="dialog" ' +
    'aria-expanded="' + (open ? "true" : "false") + '" aria-controls="tb-' + k + '-pop" aria-label="' + label +
    '">Filters' + badge + "</button>";
}

function actionsHtml(cfg) {
  return (cfg.actions || []).slice(0, 2).map(function (a) {
    return '<button type="button" class="btn btn-small' + (a.primary ? " btn-primary" : "") + '" data-tb-act="' +
      esc(a.id) + '">' + esc(a.label) + "</button>";
  }).join("");
}

function moreHtml(cfg, k) {
  const items = cfg.overflow || [];
  if (!items.length) return "";
  return '<div class="tb-more-wrap"><button type="button" class="btn btn-small tb-more" data-tb-toggle="menu"' +
    ' aria-haspopup="menu" aria-expanded="false" aria-controls="tb-' + k + '-menu" aria-label="More actions">' +
    "&hellip;</button>" + '<div class="tb-menu" id="tb-' + k + '-menu" role="menu" hidden>' + items.map(function (a) {
    return '<button type="button" role="menuitem" class="tb-menu-item" data-tb-act="' + esc(a.id) + '">' +
      esc(a.label) + "</button>";
  }).join("") + "</div></div>";
}

function popoverHtml(cfg, k, open) {
  if (!cfg.groups || !cfg.groups.length) return "";
  const groups = cfg.groups.map(function (g, gi) {
    return '<fieldset class="tb-grp"><legend>' + esc(g.label) + "</legend>" + (g.options || []).map(function (o, oi) {
      const count = o.count == null ? "" : '<span class="tb-opt-n">' + esc(o.count) + "</span>";
      return '<label class="tb-opt"><input type="checkbox" id="tb-' + k + "-o" + gi + "-" + oi + '" data-tb-token="' +
        esc(o.token) + '"' +
        (o.on ? " checked" : "") + "><span>" + esc(o.label) + "</span>" + count + "</label>";
    }).join("") + "</fieldset>";
  }).join("");
  return '<div class="tb-pop" id="tb-' + k + '-pop" role="dialog" aria-label="Filters"' + (open ? "" : " hidden") +
    '><div class="tb-grps">' + groups + '</div><div class="tb-pop-foot">' +
    '<button type="button" class="btn btn-small" data-tb-clear>Clear all</button>' +
    '<button type="button" class="btn btn-small" data-tb-close>Done</button></div></div>';
}

function appliedHtml(cfg) {
  const act = activeFilters(cfg);
  if (!act.length) return "";
  return '<div class="tb-applied" role="group" aria-label="Active filters">' + act.map(function (a) {
    const text = a.group + ": " + a.label;
    return '<button type="button" class="tb-chip" data-tb-remove="' + esc(a.token) + '" aria-label="Remove filter ' +
      esc(text) + '">' + esc(text) + '<span class="tb-x" aria-hidden="true">&times;</span></button>';
  }).join("") + '<button type="button" class="tb-clear-link" data-tb-clear>Clear</button></div>';
}

// cfg: {key, label, views:[{id,label,current}], search:{value,placeholder,label}, groups:[{id,label,
// options:[{token,label,on,count}]}], actions:[{id,label,primary}] (max 2 shown), overflow:[{id,label}], open}.
// open overrides the stored state (tests and deep links); otherwise the popover is closed unless the person left it
// open for this key.
export function toolbarHtml(cfg) {
  const k = safeKey(cfg.key);
  const open = typeof cfg.open === "boolean" ? cfg.open : isOpen(k);
  // The popover sits right after Filters inside the row (focus order follows the trigger; it anchors to the row).
  return '<div class="tb" data-tb="' + k + '" role="group" aria-label="' + esc(cfg.label || "Section toolbar") + '">' +
    '<div class="tb-row">' + viewsHtml(cfg, k) + searchHtml(cfg, k) + filtersButtonHtml(cfg, k, open) +
    popoverHtml(cfg, k, open) + '<span class="tb-gap"></span><div class="tb-acts">' + actionsHtml(cfg) +
    moreHtml(cfg, k) + "</div></div>" + appliedHtml(cfg) + "</div>";
}

// ---- DOM wiring (browser only) ----

function emit(root, type, value) {
  root.dispatchEvent(new CustomEvent("rb:toolbar", { bubbles: true,
    detail: { key: root.getAttribute("data-tb"), type: type, value: value } }));
}

function panelOf(btn) {
  const id = btn.getAttribute("aria-controls");
  return id ? document.getElementById(id) : null;
}

function setPanel(btn, open, focusInside) {
  const panel = panelOf(btn);
  if (!panel) return;
  panel.hidden = !open;
  btn.setAttribute("aria-expanded", open ? "true" : "false");
  if (btn.getAttribute("data-tb-toggle") === "pop") save(btn.closest("[data-tb]").getAttribute("data-tb"), open);
  if (open && focusInside) {
    const first = panel.querySelector("input, button");
    if (first) first.focus();
  }
}

// Close open menus, and open filter popovers of other toolbars (root null = a click outside every toolbar).
function closeAll(except, root) {
  document.querySelectorAll('[data-tb-toggle][aria-expanded="true"]').forEach(function (b) {
    if (b === except) return;
    if (b.getAttribute("data-tb-toggle") === "menu" || b.closest("[data-tb]") !== root) setPanel(b, false, false);
  });
}

// Open the Filters popover of the first toolbar on screen (for a later "f" key in keys.js).
export function openFilters() {
  const btn = document.querySelector('[data-tb] [data-tb-toggle="pop"]');
  if (btn) setPanel(btn, true, true);
  return Boolean(btn);
}

export function initToolbars() {
  document.addEventListener("click", function (e) {
    const t = e.target && e.target.closest ? e.target : null;
    if (!t) return;
    const root = t.closest("[data-tb]");
    if (!root) { closeAll(null, null); return; }
    const toggle = t.closest("[data-tb-toggle]");
    if (toggle) {
      const open = toggle.getAttribute("aria-expanded") !== "true";
      closeAll(toggle, root);
      setPanel(toggle, open, open);
      return;
    }
    // A click outside an open popover or menu (anywhere, including other parts of this toolbar) closes it.
    if (!t.closest(".tb-pop, .tb-menu")) closeAll(null, null);
    const view = t.closest("[data-tb-view]");
    if (view) return emit(root, "view", view.getAttribute("data-tb-view"));
    const rm = t.closest("[data-tb-remove]");
    if (rm) return emit(root, "remove", rm.getAttribute("data-tb-remove"));
    if (t.closest("[data-tb-clear]")) return emit(root, "clear", "");
    if (t.closest("[data-tb-close]")) {
      const b = root.querySelector('[data-tb-toggle="pop"]');
      if (b) { setPanel(b, false, false); b.focus(); }
      return;
    }
    const act = t.closest("[data-tb-act]");
    if (act) {
      closeAll(null, root);
      emit(root, "action", act.getAttribute("data-tb-act"));
    }
  });
  document.addEventListener("change", function (e) {
    const sel = e.target && e.target.closest ? e.target.closest("[data-tb-view-select]") : null;
    if (sel) return emit(sel.closest("[data-tb]"), "view", sel.value);
    const box = e.target && e.target.closest ? e.target.closest("[data-tb-token]") : null;
    const root = box ? box.closest("[data-tb]") : null;
    if (root) emit(root, "token", box.getAttribute("data-tb-token"));
  });
  document.addEventListener("input", function (e) {
    const q = e.target && e.target.closest ? e.target.closest("[data-tb-search]") : null;
    const root = q ? q.closest("[data-tb]") : null;
    if (root) emit(root, "search", q.value);
  });
  document.addEventListener("keydown", function (e) {
    const t = e.target && e.target.closest ? e.target : null;
    // Escape on the open Filters button itself (focus never left the trigger) closes the popover.
    if (e.key === "Escape" && t && t.matches('[data-tb-toggle="pop"][aria-expanded="true"]')) {
      setPanel(t, false, false);
      e.preventDefault();
      return;
    }
    const panel = t ? t.closest(".tb-pop, .tb-menu") : null;
    if (!panel) return;
    const btn = Array.prototype.find.call(document.querySelectorAll("[aria-controls]"),
      (b) => b.getAttribute("aria-controls") === panel.id) || null;
    if (e.key === "Escape") {
      if (btn) { setPanel(btn, false, false); btn.focus(); }
      e.preventDefault();
      e.stopPropagation();
      return;
    }
    const items = Array.prototype.slice.call(panel.querySelectorAll("input, button"));
    if (!items.length) return;
    const i = items.indexOf(t);
    if (e.key === "Tab" && panel.classList.contains("tb-pop")) {
      // Focus trap: Tab past the last control wraps to the first, Shift+Tab before the first wraps to the last.
      if (!e.shiftKey && i === items.length - 1) { items[0].focus(); e.preventDefault(); }
      if (e.shiftKey && i <= 0) { items[items.length - 1].focus(); e.preventDefault(); }
    } else if ((e.key === "ArrowDown" || e.key === "ArrowUp") && panel.classList.contains("tb-menu")) {
      const n = e.key === "ArrowDown" ? (i + 1) % items.length : (i - 1 + items.length) % items.length;
      items[n].focus();
      e.preventDefault();
    }
  });
}
