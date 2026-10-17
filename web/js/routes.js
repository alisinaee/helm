// Section registry (WP28). Each section has an id, a nav label, an icon id in icons.svg and a module path. A section
// whose module is null is not built yet: it shows "Coming soon" and makes no request. A later package sets its path,
// and loadSection() imports it on first visit. A module that fails to load also shows "Coming soon".

export const SECTIONS = [
  { id: "overview", label: "Overview", icon: "overview", module: "./views/overview.js", bottom: true },
  { id: "inbox", label: "Inbox", icon: "inbox", module: "./views/inbox.js", bottom: true },
  // Head (HEAD-SPEC section 5): head.js exports sectionView(vm) and reads the snapshot's head key
  // (vm.project.snapshot.head). The nav badge and the Overview chip read the same key.
  { id: "head", label: "Head", icon: "head", module: "./views/head.js", bottom: false },
  { id: "roadmap", label: "Roadmap", icon: "roadmap", module: "./views/roadmap.js", bottom: false },
  { id: "work", label: "Work", icon: "work", module: "./views/work.js", bottom: true },
  { id: "agents", label: "Agents", icon: "agents", module: "./views/agents.js", bottom: false },
  { id: "workflow", label: "Workflow", icon: "workflow", module: "./views/workflow.js", bottom: false },
  { id: "system", label: "System", icon: "system", module: "./views/system.js", bottom: false },
  { id: "tokens", label: "Tokens", icon: "tokens", module: "./views/tokens.js", bottom: false },
  { id: "rules", label: "Rules", icon: "rules", module: "./views/rules.js", bottom: false },
  { id: "activity", label: "Activity", icon: "activity", module: "./views/activity.js", bottom: false },
  // Git (R7.29 W1.c). The sprite has no branch glyph yet, so it reuses the workflow icon.
  { id: "git", label: "Git", icon: "workflow", module: "./views/git.js", bottom: false },
];

export const SETTINGS = { id: "settings", label: "Settings", icon: "settings", module: "./views/settings.js",
  bottom: false };

export const DEFAULT_SECTION = "overview";

// R7.97: the Issues section is gone; issues live on Work with Kind=Issue. Old links (#/p/<id>/issues[/i/<I>][?f=]) map
// to Work; f=blockers becomes the Blocked filter on issues. Returns the new hash, or null when the hash is not old.
const LEGACY_ISSUES = /^#\/p\/([a-z0-9][a-z0-9-]{0,39})\/issues(?:\/i\/([A-Za-z0-9][A-Za-z0-9._-]{0,59}))?(?:\?(.*))?$/;

export function legacyIssuesHash(hash) {
  const m = LEGACY_ISSUES.exec(String(hash || ""));
  if (!m) return null;
  const blockers = new URLSearchParams(m[3] || "").get("f") === "blockers";
  return "#/p/" + m[1] + "/work" + (m[2] ? "/i/" + m[2] : "") + "?f=kind:issue" + (blockers ? ",blocked" : "");
}

// R10.7: the Planner is a view inside Work. Old "#/p/<id>/planner[?f=F5]" links map to "#/p/<id>/work/planner[?f=F5]"
// (the focus item rides along); the global "#/all/planner" maps to "#/all/work". Returns the new hash, or null.
const LEGACY_PLANNER = /^#\/(?:p\/([a-z0-9][a-z0-9-]{0,39})|all)\/planner(?:\/[^?]*)?(?:\?(.*))?$/;

export function legacyPlannerHash(hash) {
  const m = LEGACY_PLANNER.exec(String(hash || ""));
  if (!m) return null;
  const f = new URLSearchParams(m[2] || "").get("f");
  const focus = f && /^F[1-9][0-9]?$/.test(f) ? "?f=" + f : "";
  return m[1] ? "#/p/" + m[1] + "/work/planner" + focus : "#/all/work";
}

// R7.30: "#/full/<pid>/workflow" is the Map alone in its own tab (app.js mounts it). Returns the project id, or null.
const FULL_ROUTE = /^#\/full\/([a-z0-9][a-z0-9-]{0,39})\/workflow(?:\?.*)?$/;

export function fullRouteOf(hash) {
  const m = FULL_ROUTE.exec(String(hash || ""));
  return m ? m[1] : null;
}

// A7: "#/full/<pid>/system" is the System diagram alone, in the same tab. Returns the project id, or null.
const FULL_SYS = /^#\/full\/([a-z0-9][a-z0-9-]{0,39})\/system(?:\?.*)?$/;

export function fullSystemOf(hash) {
  const m = FULL_SYS.exec(String(hash || ""));
  return m ? m[1] : null;
}

function redirectLegacyIssues() {
  const next = legacyIssuesHash(window.location.hash) || legacyPlannerHash(window.location.hash);
  if (next) window.location.replace(next);
}

if (typeof window !== "undefined") {
  redirectLegacyIssues();
  window.addEventListener("hashchange", redirectLegacyIssues);
}

export function sectionById(id) {
  if (id === SETTINGS.id) return SETTINGS;
  for (const section of SECTIONS) {
    if (section.id === id) return section;
  }
  return null;
}

// Resolves to the module that exports sectionView(vm). Rejects when the section has no module or the import fails.
export function loadSection(section) {
  if (!section || !section.module) {
    return Promise.reject(new Error("not built yet"));
  }
  return import(section.module);
}
