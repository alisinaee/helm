# System section + Workflow fixes (R7.113, design only)

Part B (Workflow fixes) is built first; Part A (new "System" section) after. Every package lists its own files
(disjoint across packages in one wave), a done-check, and fits one Haiku worker. Line refs are from 2026-10-15.

## Part B: Workflow fixes

**B-1 "You are here" follows live jobs only.** Now `currentOf()` (web/js/graph/model.js ~104) takes the first task
with status `doing`, and `taskStatus()` (~72) maps `partial`/`active` to `doing`, so a stale partial R3.7 got the
flag. Fix: `current` = the task that owns a job with `status === "running"` (first in lane order); if there is none,
`current = null` and render.js draws no flag/halo (and the legend line "You are here (Now)" in workflow.js ~1044
hides). Partial stays as a "doing" colour only. If 2+ tasks run, flag the first and keep the parallel bracket.
**B-2 Map in a new tab, full screen, details in a side panel (R7.30, never built).** Add a "Open full screen"
button in the Map toolbar: `window.open(hash, "_blank", "noopener")` with the route `#/full/<pid>/workflow`. The
full route renders only the canvas (100vw x 100vh; viewport.js pan/zoom, minimap) plus a right side panel
(360 px, slides over on phone). Tapping a node opens the panel with: title, status, phase, Work item, jobs
(model, tokens, time), last commits, Ask/Accept actions (reuse details.js). Esc closes the panel, not the tab.
The same full route serves System (A-7), so it is built once here.
**B-3 Timeline UI/UX issues (found by reading `timelineSvg`, workflow.js ~478-585; verify in the browser):**
1. Fixed `PLOT_W = 960` x zoom: not full width (breaks UI rule 0); should fill the scroller width at zoom 1.
2. Overflow rows: past `MAX_ROWS = 4` a bar goes to row 3 and is drawn over another bar (the comment says none is).
3. Queue bars are clamped to `W - QUEUE_W`, so many queued tasks pile on top of each other at the right edge.
4. Bars that start before the range clamp to x=0 with no "continues" cue; ended-after-range likewise.
5. Labels are the task id only and vanish when the bar is narrow, so most short jobs are unlabeled boxes.
6. Edges are drawn before bars, so bars hide handoff/blocker arrows; marks sit on lane centre over row-0 bars.
7. Tick labels are clamped to 16..W-16 and can overlap their neighbour; no day boundary line in `week`/`all`.
8. Default range `today` is often empty (the empty card) though older jobs exist; default should be the latest
   range that has jobs. No "jump to now" control after panning.
Fix list per item: fit width (ResizeObserver on the scroller), add rows up to the lane's real need (cap 8, then a
"+N" chip), queue as a stacked count chip, edge-of-range chevrons, label = `id · model` when it fits else nothing,
draw edges above bars at 60% opacity, de-overlap ticks, smart default range, a "Now" button.
**B-4 Table mode.** A job-per-row log answers nothing the person asks. Replace it with **Tasks**: one row per task
that had activity in the range, grid columns: status chip | task id + title | Work item | jobs (running/total) |
last result (done, failed, waiting on you) | tokens | time spent | next action button. Sorted: waiting on you,
running, failed, then done. It answers "what moved, what is stuck, what costs most, what needs me". It stays the
phone default. The raw job log already lives in Agents, so the job table is removed.

## Part A: System section

**Goals.** One live, interactive architecture map for ANY registered project (not only roadmap-board): what the
parts are, which files belong to each, how data flows, and where work is happening now (heat). Light: no new
dependency, one JSON fetch, SVG via the existing graph engine. Works with zero setup (auto baseline) and gets
better when the head/agents keep `docs/system.json`.

**Data sources (cheap, reliable, in this order):**
1. `docs/system.json` (optional, hand/agent kept). Authoritative names, layers, edges, notes.
2. Auto baseline (server, cached by HEAD sha): top-level dirs and second-level packages become components;
   language from extensions; entry points from `Makefile`, `package.json` scripts/bin, `pyproject`/`__main__.py`,
   `bin/*`, `index.html`, `Dockerfile`. Edges only from system.json (no import parsing in v1; see Risks).
3. Heat: `git log --since=30.days --name-only` (one call, cached by sha) mapped to components by globs; commit
   subjects with task ids (`R7.108`) link commits -> tasks -> Work items; jobs link via their task id. Bugs = open
   Issues/Work items of kind bug whose files or task touch the component.

**Schema `docs/system.json` (version 1):**
```
{ "version": 1,
  "layers": ["ui", "service", "cli", "data", "external"],          // order = left-to-right columns
  "components": [ { "id": "web-ui", "name": "Web UI", "layer": "ui", "kind": "module|store|tool|agent|service",
      "files": ["web/js/**", "web/css/**"], "entry": "web/index.html", "notes": "SPA, hash router",
      "owner": "head" } ],
  "edges": [ { "from": "web-ui", "to": "http-api", "label": "GET snapshot, POST cmd", "kind": "call|data|event" } ] }
```
Rules: ids `[a-z0-9-]+`, unique; globs relative to repo; a file belongs to the first matching component; files
matched by none go to an auto "other" component per top-level dir. Unknown keys ignored. Invalid file -> baseline
plus a warning chip "system.json: <error>", never a crash.

**API.** `GET /api/v1/projects/{id}/system` -> `{source: "file|baseline|merged", warnings, layers, components:
[{..., fileCount, heat: {commits30, lastAt, openWork, runningJobs, bugs}}], edges, sha}`. ETag = sha + mtime of
system.json + jobs.json; read-only, no writes, path-confined to the project root (SECURITY.md rules).

**UI sketch.** Nav entry "System" (after Workflow). Toolbar: layer filter chips | heat mode (changes / bugs /
running / off) | search | "Open full screen". Canvas: one column per layer, component cards (name, kind icon,
file count, heat bar on the left edge, a pulse dot when a job runs on it), orthogonal labelled edges. Pan/zoom/
minimap from viewport.js and minimap.js. Tap a card -> side panel: notes, entry, file globs and top 10 files by
change count, last 5 commits, open Work items, running/recent agent jobs, issues; each row links to its section.
Selecting a Work item elsewhere (`?focus=W12`) highlights the components it touches and dims the rest.
Empty state (no git, no dirs): "No structure found" + how to add docs/system.json.

**Risks.** Glob matching cost on big repos (cap 20k files, cache by sha); baseline too coarse for flat repos (fall
back to second-level dirs, max 24 cards, then group); system.json drifting (A-8 check command + head rule);
layout.js is workflow-shaped (phases/lanes), so System needs its own small layered layout; edges without import
parsing are only as good as system.json (v2 may add a Python/JS import scan); heat from commit subjects misses
untagged commits (count them as heat without task link).

## Build packages (ordered; Part B first)

| # | Package | Files (only these) | Done-check |
|---|---|---|---|
| B0 | Split workflow.js: move Timeline and Table code out, pure move | web/js/views/workflow.js, new web/js/views/wf-timeline.js, new web/js/views/wf-table.js | all existing tests and `make check-ui` pass unchanged |
| B1 | Now = running jobs only, hide flag when none | web/js/graph/model.js, web/js/graph/render.js, new tests/web/test_wf_now.py | partial task w/o running job -> no flag; running job -> flag on its task |
| B2 | Full-screen route + side panel for Map | web/js/routes.js, web/js/router.js, new web/js/views/fullmap.js, new web/css/fullmap.css, tests/web/test_fullmap.py | `#/full/<pid>/workflow` renders canvas only; tap node opens panel; Esc closes |
| B3 | Timeline fixes 1-8 | web/js/views/wf-timeline.js, its CSS block, tests/web/test_wf_timeline.py | no overlapping bars at 10 parallel jobs; fills width; queue chip; smart range |
| B4 | Tasks table replaces job table | web/js/views/wf-table.js, tests/web/test_wf_table.py | rows per task, sort order, grid columns aligned |
| A1 | system.json load/validate + baseline | new roadmap/services/system.py, new tests/unit/test_system_service.py | fixture repo -> components; bad JSON -> baseline + warning |
| A2 | Heat from git log + jobs + work | new roadmap/services/systemheat.py, new tests/unit/test_system_heat.py | commits map to components by glob; cached by sha |
| A3 | API endpoint + schema + docs | roadmap/http/routes.py, docs/API.md, new tests/api/schemas/system.json, new tests/api/test_system_api.py | 200 + schema valid, ETag/304, path confinement |
| A4 | Layered layout for components | new web/js/graph/syslayout.js, new tests/web/test_syslayout.py | no card overlap, edges orthogonal, 24 cards < 50 ms |
| A5 | System view (toolbar, canvas, heat modes) | new web/js/views/system.js, new web/css/system.css, web/js/routes.js (nav entry; after B2 merged) | renders for roadmap-board and fixture demo; `make check-ui` |
| A6 | Side panel content | new web/js/views/system-panel.js, tests/web/test_system_panel.py | files, commits, Work, jobs, issues lists; links route correctly |
| A7 | Full-screen System via B2 route | web/js/views/fullmap.js | `#/full/<pid>/system` works with panel |
| A8 | CLI `roadmap system show|check` + seed docs/system.json for roadmap-board + head rule "update system.json when adding a module" | new roadmap/commands/system.py, roadmap/cli.py, docs/system.json, docs/HEAD-RUNBOOK.md | `check` exits 0 on seed, 1 on bad globs |

Waves: {B0} -> {B1, B2, B4, A1, A4} -> {B3, A2, A6} -> {A3} -> {A5} -> {A7, A8}. Head reviews B3 and A5 in the
browser (UI checklist), Opus review on A1/A3 (security: path confinement, git call arguments).
