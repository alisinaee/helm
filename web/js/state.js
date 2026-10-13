// The client store and the view-model. Snapshots and usage are normalized here, so the views only read plain
// fields. Preferences (detail level and section open state, per project) and the theme live in localStorage;
// every access is wrapped in try/catch because storage can be blocked.

export const VIEW_SECTIONS = {
  home: [
    { id: "projects", openByDefault: true },
    { id: "running", openByDefault: true },
  ],
  project: [
    { id: "phases", openByDefault: true, keepInMinimal: true },
    { id: "running", openByDefault: true },
    { id: "needs", openByDefault: false },
    { id: "next", openByDefault: false },
    { id: "recent", openByDefault: false },
    { id: "extras", openByDefault: false },
    { id: "legend", openByDefault: false },
  ],
};

export const VIEW_DEFAULT_MODE = { home: "expanded", project: "minimal" };
export const THEME_ORDER = ["auto", "dark", "light"];
export const STALE_AFTER_S = 240;
export const OLD_AFTER_S = 3600;
const PREFS_PREFIX = "roadmap-board.prefs.";

export function createStore() {
  return {
    projects: null,
    projectsError: null,
    snapshots: {},
    snapshotErrors: {},
    usage: null,
    usageError: null,
    usageFetchedAt: 0,
    sync: { state: "idle", message: "" },
    conn: { ok: null, lastOkAt: null, error: null },
  };
}

function sanitizePrefs(raw) {
  const prefs = { mode: null, open: {} };
  if (!raw || typeof raw !== "object") return prefs;
  if (raw.mode === "minimal" || raw.mode === "expanded") prefs.mode = raw.mode;
  if (raw.open && typeof raw.open === "object") {
    for (const key of Object.keys(raw.open)) {
      if (typeof raw.open[key] === "boolean") prefs.open[key] = raw.open[key];
    }
  }
  return prefs;
}

export function loadPrefs(key) {
  try {
    return sanitizePrefs(JSON.parse(window.localStorage.getItem(PREFS_PREFIX + key)));
  } catch (err) {
    return sanitizePrefs(null);
  }
}

export function savePrefs(key, prefs) {
  try {
    window.localStorage.setItem(PREFS_PREFIX + key, JSON.stringify(prefs));
  } catch (err) {
    // Storage is blocked or full: the choice lasts until reload.
  }
}

// UI preferences (WP28) live under one localStorage key. Every read and write is wrapped in try/catch: storage can be
// blocked, and then the defaults apply for this page view only.
const UI_KEY = "rb.ui.v2";
const PANEL_TABS = ["projects", "details"];
const WORK_VIEWS = ["board", "list", "tree"];
const DENSITIES = ["comfortable", "compact"];
const PROJECT_ID_RE = /^[a-z0-9][a-z0-9-]{0,39}$/;

export function defaultUi() {
  return {
    navMini: false,
    panelOpen: null,
    panelTab: "projects",
    workView: "board",
    filters: {},
    density: "comfortable",
    theme: "auto",
    lastProject: null,
  };
}

function sanitizeUi(raw) {
  const ui = defaultUi();
  if (!raw || typeof raw !== "object") return ui;
  if (typeof raw.navMini === "boolean") ui.navMini = raw.navMini;
  if (typeof raw.panelOpen === "boolean") ui.panelOpen = raw.panelOpen;
  if (PANEL_TABS.indexOf(raw.panelTab) >= 0) ui.panelTab = raw.panelTab;
  if (WORK_VIEWS.indexOf(raw.workView) >= 0) ui.workView = raw.workView;
  if (DENSITIES.indexOf(raw.density) >= 0) ui.density = raw.density;
  if (THEME_ORDER.indexOf(raw.theme) >= 0) ui.theme = raw.theme;
  if (typeof raw.lastProject === "string" && PROJECT_ID_RE.test(raw.lastProject)) ui.lastProject = raw.lastProject;
  if (raw.filters && typeof raw.filters === "object") {
    for (const key of Object.keys(raw.filters).slice(0, 20)) {
      if (typeof raw.filters[key] === "string" && raw.filters[key].length <= 200) {
        ui.filters[key] = raw.filters[key];
      }
    }
  }
  return ui;
}

// panelOpen null means "not chosen yet": the panel is docked open on wide screens and hidden where it floats.
export function isSheetWidth() {
  return window.matchMedia("(max-width: 1199px)").matches;
}

export function panelIsOpen(ui) {
  return ui.panelOpen === null ? !isSheetWidth() : ui.panelOpen;
}

export function loadUi() {
  try {
    return sanitizeUi(JSON.parse(window.localStorage.getItem(UI_KEY)));
  } catch (err) {
    return defaultUi();
  }
}

export function saveUi(ui) {
  try {
    window.localStorage.setItem(UI_KEY, JSON.stringify(sanitizeUi(ui)));
  } catch (err) {
    // Blocked or full storage: the choice lasts until reload.
  }
}

// Change one or more preferences and save. change() receives a copy and may edit it.
export function updateUi(change) {
  const ui = loadUi();
  change(ui);
  saveUi(ui);
  return ui;
}

export function loadTheme() {
  return loadUi().theme;
}

export function saveTheme(value) {
  updateUi(function (ui) {
    ui.theme = THEME_ORDER.indexOf(value) >= 0 ? value : "auto";
  });
}

export function nextTheme(value) {
  const at = THEME_ORDER.indexOf(value);
  return THEME_ORDER[(at + 1) % THEME_ORDER.length];
}

function num(value) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function list(value) {
  return Array.isArray(value) ? value : [];
}

function idList(value) {
  return list(value).map(String);
}

function normalizeJob(j, fetchedAt) {
  const started = Date.parse(j.started);
  const ended = Date.parse(j.ended);
  return {
    id: j.id,
    task: j.task || null,
    title: j.title || "",
    model: j.model || null,
    status: j.status || "",
    elapsedS: num(j.elapsed_s),
    tokensK: num(j.tokensK),
    note: j.note || "",
    startedMs: Number.isNaN(started) ? null : started,
    endedMs: Number.isNaN(ended) ? null : ended,
    fetchedAt: fetchedAt,
  };
}

function normalizeTask(t) {
  return {
    id: t.id,
    title: t.title || "",
    phase: t.phase || "",
    state: t.state || "todo",
    model: t.model || null,
    thinking: t.thinking || "",
    tokensK: num(t.tokensK),
    check: t.check || "none",
    checkK: num(t.checkK),
    needsUser: Boolean(t.needsUser),
    note: t.note || "",
    // WP29 keys: subtasks [{t, d}], the token cap (thousands) and the definition of done when the file has them.
    subs: list(t.subs).map(function (s) {
      return { t: String(s.t || ""), d: s.d === true };
    }),
    capK: num(t.capK),
    dod: typeof t.dod === "string" && t.dod ? t.dod : null,
  };
}

function normalizeBoard(b) {
  return { id: b.id || "", label: b.label || "", state: b.state || "todo", status: b.status || "",
    date: b.date || "" };
}

export function normalizeSnapshot(raw, fetchedAt) {
  const project = raw.project || {};
  const summary = raw.summary || {};
  const overall = (raw.overall && raw.overall.project) || {};
  const phases = Array.isArray(raw.phases) ? raw.phases : [];
  const jobs = Array.isArray(raw.jobs) ? raw.jobs : [];
  const errors = Array.isArray(raw.errors) ? raw.errors : [];
  return {
    id: project.id || null,
    title: project.title || project.id || "Project",
    fetchedAt: fetchedAt,
    tasksLeft: num(summary.tasks_left),
    tasksTotal: num(summary.tasks_total),
    needUser: num(summary.need_user),
    runningCount: num(summary.running_count),
    tokensLeftK: num(summary.tokens_left_k),
    tokensDoneK: num(summary.tokens_done_k),
    tokensPartialK: num(summary.tokens_partial_k),
    tokensRoadmapK: num(summary.tokens_roadmap_k),
    progress: num(overall.progress),
    done: num(overall.done),
    total: num(overall.total),
    phases: phases.map(function (p) {
      const running = idList(p.running);
      return {
        id: p.id,
        name: p.name || p.id,
        done: num(p.done),
        total: num(p.total),
        progress: num(p.progress),
        state: p.state || "todo",
        onlyDeferred: Boolean(p.only_deferred),
        deferred: num(p.deferred) || 0,
        remainingK: num(p.remaining_k),
        runningCount: running.length,
        running: running,
        recent: idList(p.recent),
      };
    }),
    jobs: jobs.map(function (j) {
      return normalizeJob(j, fetchedAt);
    }),
    running: jobs.filter(function (j) {
      return j.status === "running";
    }).map(function (j) {
      return normalizeJob(j, fetchedAt);
    }),
    // The task cap lives in the snapshot's budget (budget.tasks[id].limit), so it is read from there.
    tasks: list(raw.tasks).map(function (t) {
      const row = raw.budget && raw.budget.tasks ? raw.budget.tasks[t.id] : null;
      return normalizeTask(Object.assign({}, t, { capK: t.capK != null ? t.capK : row ? row.limit : null }));
    }),
    spikes: list(raw.spikes).map(normalizeBoard),
    rh: list(raw.rh).map(normalizeBoard),
    next: list(raw.next).map(String),
    log: list(raw.log).map(function (row) {
      return { date: row.date || "", text: row.text || "" };
    }),
    errors: errors.map(function (e) {
      return { file: e.file || "file", message: e.error || "could not be read" };
    }),
    tasksUpdated: raw.tasks_updated || null,
    control: normalizeControl(raw.control),
    meters: normalizeMeters(raw.meters),
    dayUse: normalizeUse(raw.meters, "today", "pts"),
    weekUse: normalizeUse(raw.meters, "week", "pct"),
    questions: list(raw.questions).map(normalizeQuestion),
    needsYou: list(raw.needsYou).map(normalizeNeedsYou),
    activity: list(raw.activity).map(normalizeActivity),
    blocked: idList(raw.blocked),
    issues: list(raw.issues).map(normalizeIssue),
    // WP29 keys: comments by target (newest last), the queue, and project rules when the snapshot has them.
    comments: normalizeComments(raw.comments),
    queue: list(raw.queue).map(function (q) {
      return { task: String(q.task || ""), by: String(q.by || "") };
    }),
    rules: Array.isArray(raw.rules) ? raw.rules.map(function (r) {
      return { id: String(r.id || ""), scope: String(r.scope || ""), text: String(r.text || "") };
    }) : null,
  };
}

function normalizeComments(raw) {
  const out = Object.create(null);
  if (!raw || typeof raw !== "object") return out;
  for (const target of Object.keys(raw)) {
    out[target] = list(raw[target]).map(function (c) {
      return { by: String(c.by || ""), at: typeof c.at === "string" ? c.at : null, t: String(c.t || "") };
    });
  }
  return out;
}

// The control key: stopped and blocked flags, the reason text and the warnings. An error marker reads as not stopped.
function normalizeControl(raw) {
  const c = raw && typeof raw === "object" ? raw : {};
  return { stopped: c.stopped === true, blocked: c.blocked === true, reason: String(c.reason || ""),
    warn: list(c.warn).map(String) };
}

// WP30 snapshot keys: open questions, needs-you rows, the activity lines (newest 15), open blockers and open issues.
// Times are parsed once here; a missing or bad time is null.
function timeMs(value) {
  const ms = Date.parse(value);
  return Number.isNaN(ms) ? null : ms;
}

function normalizeQuestion(q) {
  return {
    id: String(q.id || ""),
    task: String(q.task || ""),
    text: String(q.text || ""),
    opts: list(q.opts).map(String),
    def: q.def ? String(q.def) : null,
    block: q.block === true,
    timeoutS: num(q.timeoutS),
    askedMs: timeMs(q.asked),
  };
}

function normalizeNeedsYou(row) {
  return { kind: String(row.kind || ""), id: String(row.id || ""), title: String(row.title || row.text || "") };
}

function normalizeActivity(a) {
  return { id: String(a.id || ""), atMs: timeMs(a.at), src: String(a.src || ""), op: String(a.op || ""),
    sum: String(a.sum || ""), undo: a.undo === true };
}

function normalizeIssue(i) {
  return { id: String(i.id || ""), title: String(i.title || ""), kind: String(i.kind || ""),
    status: String(i.status || ""), tasks: idList(i.tasks) };
}

// Today's or this week's usage from meters: the day's points, or the weekly percent, with tracked tokens (K).
function normalizeUse(raw, key, field) {
  if (!raw || typeof raw !== "object" || !raw[key] || typeof raw[key] !== "object") return null;
  const part = raw[key];
  return { value: num(part[field]), tokK: num(part.tokK), estPts: num(part.estPts) };
}

// meters.limits rows (WP27). Null when the snapshot has no meters, so the top bar can show "unknown".
const LIMIT_STATES = ["ok", "warn", "block", "unknown"];

function normalizeMeters(raw) {
  if (!raw || !Array.isArray(raw.limits)) return null;
  return raw.limits.map(function (row) {
    return {
      id: String(row.id || ""),
      scope: row.scope === "project" ? "project" : "global",
      window: row.window === "week" ? "week" : row.window === "total" ? "total" : "day",
      kind: String(row.kind || "pct"),
      used: num(row.used),
      limit: num(row.limit),
      state: LIMIT_STATES.indexOf(row.state) >= 0 ? row.state : "unknown",
      est: row.est === true,
      paceAt: typeof row.paceAt === "string" ? row.paceAt : null,
      src: typeof row.src === "string" ? row.src : null,
    };
  });
}

export function normalizeUsage(raw, fetchedAt) {
  return {
    weeklyPercent: num(raw.weeklyPercent),
    fiveHourPercent: num(raw.fiveHourPercent),
    weeklyResetsAt: raw.weeklyResetsAt || null,
    fiveHourResetsAt: raw.fiveHourResetsAt || null,
    updated: raw.updated || null,
    source: raw.source || null,
    lastError: raw.lastError || null,
    ageS: num(raw.ageS),
    fetchedAt: fetchedAt,
  };
}

// The effective open state of each section for a view. An explicit choice wins. Otherwise expanded mode opens
// everything, and a view with no saved mode opens its openByDefault sections.
// Minimal (chosen) keeps only the sections marked keepInMinimal open; the default view opens openByDefault ones.
export function sectionOpenState(view, prefs) {
  const mode = prefs.mode || VIEW_DEFAULT_MODE[view];
  const open = {};
  for (const section of VIEW_SECTIONS[view]) {
    if (typeof prefs.open[section.id] === "boolean") {
      open[section.id] = prefs.open[section.id];
    } else if (mode === "expanded") {
      open[section.id] = true;
    } else if (prefs.mode) {
      open[section.id] = Boolean(section.keepInMinimal);
    } else {
      open[section.id] = Boolean(section.openByDefault);
    }
  }
  return open;
}

function usageView(store, now) {
  const u = store.usage;
  const sync = store.sync;
  const base = { loaded: Boolean(u), error: store.usageError, sync: sync };
  if (!u) return base;
  const elapsed = (now - u.fetchedAt) / 1000;
  const ageNow = u.ageS == null ? null : u.ageS + elapsed;
  return Object.assign(base, u, {
    ageNow: ageNow,
    stale: ageNow == null || ageNow > STALE_AFTER_S,
    veryOld: ageNow == null || ageNow > OLD_AFTER_S,
  });
}

export function buildViewModel(store, route, prefs, now) {
  const view = route.name;
  const open = sectionOpenState(view, prefs);
  const vm = {
    view: view,
    route: route,
    now: now,
    mode: prefs.mode || VIEW_DEFAULT_MODE[view],
    modeChosen: Boolean(prefs.mode),
    open: open,
    prefsOpen: prefs.open,
    conn: store.conn,
    usage: usageView(store, now),
    projects: null,
    projectsError: store.projectsError,
    project: null,
    home: null,
    title: "roadmap-board",
  };
  const rows = store.projects;
  if (Array.isArray(rows)) {
    vm.projects = rows.map(function (row) {
      return {
        id: row.id,
        name: row.name,
        progress: num(row.progress),
        tasksLeft: num(row.tasks_left),
        running: num(row.running),
        needUser: num(row.need_user),
        errorsCount: num(row.errors_count) || 0,
        stale: Boolean(row.stale),
      };
    });
  }
  if (view === "project") {
    const found = vm.projects ? vm.projects.find(function (p) {
      return p.id === route.id;
    }) : null;
    const snap = store.snapshots[route.id] || null;
    vm.project = {
      id: route.id,
      name: found ? found.name : route.id,
      notFound: Boolean(vm.projects) && !found,
      error: store.snapshotErrors[route.id] || null,
      snapshot: snap,
      running: snap ? snap.running.map(function (job) {
        return Object.assign({}, job, { elapsedNow: runningElapsed(job, now) });
      }) : [],
    };
    if (vm.project.name) vm.title = vm.project.name + " · roadmap-board";
  } else {
    const running = [];
    for (const id of Object.keys(store.snapshots)) {
      const snap = store.snapshots[id];
      const name = vm.projects ? (vm.projects.find(function (p) {
        return p.id === id;
      }) || { name: id }).name : id;
      for (const job of snap.running) {
        const elapsedNow = runningElapsed(job, now);
        running.push(Object.assign({}, job, { projectId: id, projectName: name, elapsedNow: elapsedNow }));
      }
    }
    vm.home = { running: running, loading: !Array.isArray(store.projects) && !store.projectsError };
  }
  return vm;
}

function runningElapsed(job, now) {
  if (job.elapsedS == null) return null;
  return job.elapsedS + (now - job.fetchedAt) / 1000;
}
