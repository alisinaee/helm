// Keyboard map (WP28). Keys are ignored while a text field or select has focus, and while Ctrl, Meta or Alt is down.
// Single-character keys are ignored when Settings turns "Single-key shortcuts" off (singleKeysOn).
// Shell keys: "?" help, "[" collapse the nav, "]" show or hide the panel, "z" undo the newest undoable toast,
// "Esc" closes the help dialog or the panel sheet, "g" then a letter goes to a section (g h is All projects), and
// "m" marks a bug here (localhost only, R8.21). The top bar Mark and palette buttons are clicks, handled in initKeys.
// Views add their own keys with bindKey(); the per-item keys (j k Enter s x d h c and so on) arrive with their views.

import { sectionHash, currentRoute, homeHash } from "./router.js";
import { SECTIONS, SETTINGS } from "./routes.js";
import { isSheetWidth, loadUi, panelIsOpen, updateUi } from "./state.js";
import { triggerUndo } from "./views/toast.js";
import { isPaletteKey } from "./views/palette.js";
import { markAllowed, markBug } from "./views/topbar.js";

// Single-key shortcuts (WCAG 2.1.4) can be turned off in Settings > Keyboard shortcuts. The choice lives under its
// own localStorage key (like the log switch); the default is on. Blocked storage keeps the choice until reload.
const SINGLE_KEY_SWITCH = "rb.keys.single";
let singleKeysMemo = null;

export function singleKeysOn() {
  if (singleKeysMemo !== null) return singleKeysMemo;
  try {
    return window.localStorage.getItem(SINGLE_KEY_SWITCH) !== "0";
  } catch (err) {
    return true;
  }
}

export function setSingleKeys(on) {
  singleKeysMemo = Boolean(on);
  try {
    window.localStorage.setItem(SINGLE_KEY_SWITCH, singleKeysMemo ? "1" : "0");
  } catch (err) {
    // Blocked or full storage: the choice lasts until reload.
  }
}

const CHORD_MS = 1000;
const CHORD_KEYS = { h: "home", o: "overview", i: "inbox", r: "roadmap", w: "work", u: "issues", a: "agents",
  t: "tokens", e: "rules", n: "research", v: "activity", ",": "settings" };
const extra = new Map();
let chordAt = 0;
let hooks = {
  rerender: function () {},
  openHelp: function () {},
  closeHelp: function () {},
  openPalette: function () {},
  helpOpen: function () {
    return false;
  },
};

export function bindKey(key, handler) {
  extra.set(key, handler);
}

export function setKeyHooks(next) {
  hooks = Object.assign(hooks, next);
}

function isTyping(target) {
  return Boolean(target) && (target.isContentEditable || /^(INPUT|SELECT|TEXTAREA)$/.test(target.tagName));
}

export function togglePanel() {
  updateUi(function (ui) {
    ui.panelOpen = !panelIsOpen(ui);
  });
  hooks.rerender();
}

export function toggleNav() {
  updateUi(function (ui) {
    ui.navMini = !ui.navMini;
  });
  hooks.rerender();
}

export function closePanel() {
  updateUi(function (ui) {
    ui.panelOpen = false;
  });
  hooks.rerender();
}

// Escape closes the panel sheet; focus goes back to the panel toggle (the render replaces the button, so it is found
// again by its data-focus name).
function focusPanelToggle() {
  const btn = document.querySelector('[data-focus="panel-toggle"]');
  if (btn && typeof btn.focus === "function") btn.focus();
}

function goToSection(key) {
  const name = CHORD_KEYS[key];
  const route = currentRoute();
  const section = name === "home" ? "overview" : name;
  if (name === "home") {
    window.location.hash = homeHash();
    return;
  }
  const known = SECTIONS.concat([SETTINGS]).some(function (s) {
    return s.id === section;
  });
  if (known) window.location.hash = sectionHash(route, section);
}

function onKeydown(event) {
  // Cmd+K or Ctrl+K opens the command palette, also while its own search field has focus (it then closes).
  if (isPaletteKey(event)) {
    event.preventDefault();
    hooks.openPalette();
    return;
  }
  // Alt+arrow bindings (WP32, roadmap cards) are the only Alt keys; they are not used while typing.
  if (event.altKey && !event.ctrlKey && !event.metaKey && !isTyping(event.target) && extra.has("Alt+" + event.key)) {
    event.preventDefault();
    extra.get("Alt+" + event.key)(event);
    return;
  }
  if (event.defaultPrevented || event.ctrlKey || event.metaKey || event.altKey || isTyping(event.target)) {
    return;
  }
  const key = event.key;
  if (key === "Escape") {
    if (hooks.helpOpen()) {
      hooks.closeHelp();
    } else if (isSheetWidth() && panelIsOpen(loadUi())) {
      closePanel();
      focusPanelToggle();
    }
    chordAt = 0;
    return;
  }
  // A single character key (letters, ?, [, ], per-item keys) does nothing while the Settings switch is off.
  if (key.length === 1 && !singleKeysOn()) {
    chordAt = 0;
    return;
  }
  if (event.shiftKey && key !== "?") {
    chordAt = 0;
    return;
  }
  if (chordAt && Date.now() - chordAt < CHORD_MS && CHORD_KEYS[key]) {
    chordAt = 0;
    event.preventDefault();
    goToSection(key);
    return;
  }
  chordAt = key === "g" ? Date.now() : 0;
  if (key === "g") return;
  if (key === "?") {
    event.preventDefault();
    hooks.openHelp();
  } else if (key === "[") {
    toggleNav();
  } else if (key === "]") {
    togglePanel();
  } else if (key === "z") {
    if (triggerUndo()) event.preventDefault();
  } else if (key === "m") {
    if (markAllowed()) markBug();
  } else if (extra.has(key)) {
    extra.get(key)(event);
  }
}

export function helpRows() {
  return [
    ["?", "Show this list"],
    ["Ctrl+K or Cmd+K", "Open the command palette: find a task, issue or question, or type > for commands"],
    ["[", "Collapse or expand the navigation"],
    ["]", "Show or hide the side panel"],
    ["z", "Undo the last change"],
    ["m", "Mark a bug here: notes this screen in the debug log (on this Mac only)"],
    ["Esc", "Close this list, or the panel sheet"],
    ["g then o i r w u a t e n v ,", "Go to a section: Overview, Inbox, Roadmap, Work, Issues, Agents, " +
      "Tokens, Rules, Research, Activity, Settings"],
    ["g then h", "Go to All projects"],
  ];
}

// Top bar buttons that are not app.js actions: the Mark button and the Cmd+K button.
function onShellClick(event) {
  const el = event.target && event.target.closest ? event.target.closest("[data-action]") : null;
  if (!el) return;
  const action = el.getAttribute("data-action");
  if (action === "mark-bug") {
    markBug();
  } else if (action === "palette-open") {
    hooks.openPalette();
  }
}

export function initKeys() {
  document.addEventListener("keydown", onKeydown);
  document.addEventListener("click", onShellClick);
}
