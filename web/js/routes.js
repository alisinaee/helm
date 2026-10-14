// Section registry (WP28). Each section has an id, a nav label, an icon id in icons.svg and a module path. A section
// whose module is null is not built yet: it shows "Coming soon" and makes no request. A later package sets its path,
// and loadSection() imports it on first visit. A module that fails to load also shows "Coming soon".

export const SECTIONS = [
  { id: "overview", label: "Overview", icon: "overview", module: "./views/overview.js", bottom: true },
  { id: "inbox", label: "Inbox", icon: "inbox", module: "./views/inbox.js", bottom: true },
  { id: "roadmap", label: "Roadmap", icon: "roadmap", module: "./views/roadmap.js", bottom: false },
  { id: "work", label: "Work", icon: "work", module: "./views/work.js", bottom: true },
  { id: "issues", label: "Issues", icon: "issues", module: "./views/issues.js", bottom: true },
  { id: "agents", label: "Agents", icon: "agents", module: "./views/agents.js", bottom: false },
  { id: "workflow", label: "Workflow", icon: "workflow", module: "./views/workflow.js", bottom: false },
  { id: "tokens", label: "Tokens", icon: "tokens", module: "./views/tokens.js", bottom: false },
  { id: "rules", label: "Rules", icon: "rules", module: "./views/rules.js", bottom: false },
  { id: "research", label: "Research", icon: "research", module: "./views/research.js", bottom: false },
  { id: "activity", label: "Activity", icon: "activity", module: "./views/activity.js", bottom: false },
];

export const SETTINGS = { id: "settings", label: "Settings", icon: "settings", module: "./views/settings.js",
  bottom: false };

export const DEFAULT_SECTION = "overview";

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
