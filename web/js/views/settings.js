// Settings (WP33): theme, density, what a phone may change, keyboard help and where the data lives. Theme and density
// are kept in the UI preferences (state.js); nothing here writes to the project files.

import { esc } from "../dom.js";
import { loadUi, saveTheme, updateUi } from "../state.js";

const THEMES = [
  { id: "auto", label: "Match system" },
  { id: "dark", label: "Dark" },
  { id: "light", label: "Light" },
];
const DENSITIES = [
  { id: "comfortable", label: "Comfortable" },
  { id: "compact", label: "Compact" },
];
const DENSITY_IDS = DENSITIES.map(function (d) {
  return d.id;
});

function choiceHtml(name, options, current, action) {
  return '<div class="rule-tabs" role="group" aria-label="' + esc(name) + '">' + options.map(function (o) {
    return '<button type="button" class="btn btn-small" aria-pressed="' + (o.id === current ? "true" : "false") +
      '" data-action="' + esc(action) + '" data-value="' + esc(o.id) + '" data-focus="' + esc(action) + "-" +
      esc(o.id) + '">' + esc(o.label) + "</button>";
  }).join("") + "</div>";
}

function applyDensity(value) {
  if (typeof document === "undefined") return;
  document.documentElement.setAttribute("data-density", value);
}

export function sectionView() {
  const ui = loadUi();
  applyDensity(ui.density);
  return '<div class="page-head"><h2 class="page-title">Settings</h2>' +
    '<p class="page-note">Preferences for this browser. Project settings live in the project files.</p></div>' +
    '<section class="ov-card" aria-labelledby="set-look"><h3 id="set-look" class="lim-h">Appearance</h3>' +
    '<p class="lim-label">Theme</p>' + choiceHtml("Theme", THEMES, ui.theme, "set-theme") +
    '<p class="lim-label">Density</p>' + choiceHtml("Density", DENSITIES, ui.density, "set-density") +
    "</section>" +
    '<section class="ov-card" aria-labelledby="set-phone"><h3 id="set-phone" class="lim-h">Phone</h3>' +
    '<p class="page-note">Read only on a phone: it can see every project and answer questions. It cannot change ' +
    "limits, overrides, rules, caps or approvals.</p></section>" +
    '<section class="ov-card" aria-labelledby="set-keys"><h3 id="set-keys" class="lim-h">Keyboard</h3>' +
    '<p class="page-note">Press ? for the list of shortcuts.</p>' +
    '<button type="button" class="btn" data-action="help-open" data-focus="help-open">Keyboard shortcuts</button>' +
    "</section>" +
    '<section class="ov-card" aria-labelledby="set-data"><h3 id="set-data" class="lim-h">Data</h3>' +
    '<p class="page-note">Global limits, the usage ledger and the global config live in the roadmap home folder. ' +
    "Each project keeps its rules in docs/rules.txt and its budget in budget.json. Run roadmap doctor to see the " +
    "exact paths.</p></section>";
}

// Theme and density actions. Returns true when handled (app.js re-renders).
export function settingsAction(action, el) {
  if (action === "set-theme") {
    const value = el.getAttribute("data-value");
    saveTheme(value);
    if (value === "auto") {
      document.documentElement.removeAttribute("data-theme");
    } else {
      document.documentElement.setAttribute("data-theme", value);
    }
    return true;
  }
  if (action === "set-density") {
    const value = el.getAttribute("data-value");
    if (DENSITY_IDS.indexOf(value) < 0) return true;
    updateUi(function (ui) {
      ui.density = value;
    });
    applyDensity(value);
    return true;
  }
  return false;
}
