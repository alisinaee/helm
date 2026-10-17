# System v2 (R11.1): a diagram workspace that fills the screen, knows the work, and draws every useful view

Builds on docs/SYSTEM-VIEWS-SPEC.md (R10.33). Owner: R11.1 lead. Subtasks R11.101..R11.111 below (R11.1a..k; the plan grammar needs numbers).

## 1. Research summary (2026-10-17)
- **C4 model** (c4model.com/diagrams): 4 core static levels (Context, Container, Component, Code) plus supplementary
  System landscape, Dynamic (runtime collaboration, sequence style) and Deployment. "You don't need all four levels";
  Context + Containers serve most teams. Each level is a zoom of the one above, which is exactly our drill-down.
- **Structurizr** (structurizr.com, docs.structurizr.com): views are filtered projections of ONE model (landscape,
  context, container, component, code, dynamic, deployment, filtered); interactive zoom, auto key/legend, quick
  navigation between views; double-click drills from an element to its own view.
- **Mermaid / draw.io** (drawio.com docs): the common diagram vocabulary is flowchart/activity, sequence, class,
  state (composite states, choice, fork/join), ER (crow's foot, PK/FK), C4, deployment, gantt/timeline. draw.io
  containers collapse/expand in place with a +/- toggle; Fit window / Fit page; Ctrl/Cmd+wheel zoom.
- **Backstage** catalog: a graph of entities (System, Component, API, Resource, Group/User) with typed relations
  (dependsOn, providesApi, ownedBy, partOf). Relations, not pictures, are the source; the graph view is a projection.
  Ownership (who/which work is on a part) is first-class.
- **SchemaSpy**: ER is reverse engineered from schema metadata; besides declared FKs it infers "implied relations"
  when a column name/type matches another table's key. We do the same over SQL text, JSON Schema and JSON stores.
- **CodeSee / Sourcegraph**: auto-generated, zoomable maps of folders and services; value comes from overlaying live
  facts (changes, owners, PRs) on the map. We overlay commits, jobs, board tasks and Work items.
- **Timelines** (vis-timeline, IBA, Visual Studio threads view): drag to pan time, Shift+wheel / trackpad horizontal
  to scroll, Ctrl/Cmd+wheel zoom at cursor, a Reset/Now control, preset zoom spans.

Decision: one model, many projections. The backend derives every view it can from the code and data files; each
view has a relevance score so the switcher shows what matters for THIS project first; docs/system.json overrides
or adds any view; "Update diagrams" asks the head (AI) to fill what cannot be derived.

## 2. Diagram catalogue (which, from where)
| id | Family | Diagram | Derived from | Override key in docs/system.json |
|---|---|---|---|---|
| context | Structure | C4 L1 Context | (exists) | external |
| containers | Structure | C4 L2 Containers | (exists) | containers |
| components | Structure | C4 L3 Components | (exists) | components, edges |
| modules | Structure | Modules (code map) | (exists) | - |
| layers | Structure | Layers | (exists) | layers |
| classes | Structure | Class / module (C4 L4 Code) | Python `ast` classes (bases, public methods, attrs); JS/TS `export class` / `export function` per file | classes |
| deployment | Structure | Deployment | Makefile targets, launchd/systemd plists, Dockerfile, docker-compose, Procfile, package.json scripts, bin/*, `serve`/port literals | deployment |
| usecases | Behaviour | Use cases | actors (person, agents, externals) + CLI subcommands (argparse `add_parser`), HTTP routes, UI sections (routes.js SECTIONS) | usecases |
| flows | Behaviour | Sequence (C4 dynamic) | (exists) | flows |
| activity | Behaviour | Activity (per component) | Python `ast` of the component's top entry functions: calls, if (decision), for/while (loop), try (error path), return (end) | activities |
| states | Behaviour | State machines | tuple/list/set constants named `*STATUS*`, `*STATES*`, `*_KINDS` with string members; transitions from `status == "a"` ... `status = "b"` assignments in one function, else listed order marked `guessed` | machines |
| data | Data | Data flow (DFD) | (exists, the Data view) | - |
| er | Data | ER / EER | SQL `CREATE TABLE` text (columns, PK, `REFERENCES` FK), JSON Schema files (`properties`, `$ref`), tracked JSON/JSONL stores (item keys of the first 50 records); implied relations when a field is `<entity>Id`, `<entity>`, `<entity>s` (list = 1..n); EER: `allOf`/`$ref` inheritance and Python dataclass bases become IS-A | entities |

Relevance (`catalog`): `score` 0..100 from how much real content the view has (node count, edge count, declared
overrides +40, empty = 0 and `available:false`). The switcher shows the families in order with views sorted by
score; views with score >= 30 are "recommended" (shown as buttons), the rest sit in the family's "More" menu.
`system.json` `"views": ["components", "er", ...]` pins the order. All views stay reachable (no page scroll).

## 3. Backend contract (GET /api/v1/projects/{id}/system, additive)
`arch` gains:
```
catalog: [{id, family: "structure|behaviour|data", label, score, available, reason, derived: bool}]
diagrams: {
  classes:    {groups, nodes:[{id,label,sub,kind:"class|function|module",group,attrs:[str],methods:[str]}], edges:[{from,to,kind:"extends|uses",label}]},
  deployment: {groups, nodes:[{id,label,sub,kind:"device|process|store|external",group}], edges},
  usecases:   {actors:[{id,label,kind}], cases:[{id,label,group,sub}], links:[{actor,case}], groups:[{id,label}]},
  activity:   {items:[{id, component, name, file, line, steps:[{id,kind:"start|action|decision|loop|merge|end|error",label}], edges:[{from,to,label}]}]},
  states:     {items:[{id, name, file, states:[str], transitions:[{from,to,label,guessed}], initial}]},
  er:         {entities:[{id,label,source,file,attrs:[{name,type,pk,fk,many}],parent}], relations:[{from,to,label,card:"1-1|1-n|n-n",implied}]}
}
```
`arch.details[<node id>]` for components (`c:`) and containers (`k:`) gains:
```
board:    [{id, title, status, phase, model, work}]      // board (agent) tasks bound to the component
work:     [{id, title, status, kind}]                     // Work items bound (human cards)
progress: {done, total, pct}                              // over board tasks; Work items when no tasks
ref:      "rb:<pid>/component/<id>"                       // for copy id
```
**Binding rule (component -> tasks)**, first match wins per task, all rules unioned:
1. Explicit: `components[].tasks: ["R11.1", ...]` and `components[].work: ["W3"]` in docs/system.json.
2. Commits: task ids in subjects of commits touching the component's files (all history up to MAX_COMMITS, not only
   30 days), as heat already does.
3. Refs/paths: a task whose `refs` include `file:<path>` or whose title/note contains a path matched by the
   component's globs, or the component id/name as a whole word.
4. Work items: every Work item that binds one of the component's tasks (work_svc tasks list), plus rule 1.
Groups/containers aggregate their components (union, progress over the union).
Implementation: new `roadmap/services/system_tasks.py` (`bind(mapped, commits, tasks, work, declared) -> {cid: {...}}`),
new `roadmap/services/system_v2.py` (`extend(project_root, mapped, arch, data_dir, commits) -> arch`; calls
system_tasks, `system_data.er/states`, `system_behave.classes/deployment/usecases/activity`, builds `catalog`; each
call guarded so one failure only adds a warning). routes.py `project_system` calls `system_v2.extend` after
`system_arch.analyze`. Same confinement and caps as system_arch (tracked files, 256 KB each, 4000 files); cached by
sha + system.json mtime; tasks.json/work mtime added to the ETag.

## 4. Frontend
### 4.1 Layout (fix of issue 1)
- `.sys` is a flex column with `height:100%`; `.main:has(> .sys)` gets `overflow:hidden`; the canvas wrapper is
  `flex:1;min-height:0`; the SVG is `height:100%` (no `100vh - 190px`). No vertical page scrollbar at 1440x900,
  1024x768, 768x1024, 500x900. Toolbar = one row (wraps to two on phone), legend inline in the same row.
- Fit: on first draw, on view change and on canvas resize (ResizeObserver) while the user has not panned/zoomed:
  true fit (scale = min(w/box.w, h/box.h), clamp 0.2..1.5), centred. "Fit" button and `0`/`f` key always true-fit.
  Zoom -, +, a % readout (button: click resets 100 %), Cmd/Ctrl+wheel and pinch zoom at cursor; plain wheel /
  trackpad pans; drag pans; arrow keys pan.
- Full screen: the toolbar button uses the Fullscreen API on the `.sys` element (`requestFullscreen`), fallback to
  the `#/full/<pid>/system` route; on enter/exit the view refits; Esc exits; the side panel works inside it.
- Side panel docks inside `.sys` (absolute, right, 400 px; overlay on < 1024) and the canvas keeps full width.

### 4.2 Context menu (issue 2) `web/js/views/system-menu.js`
Right-click (or Shift+F10 / the "..." button on a focused box, long-press on touch) on a node or group opens a
menu at the pointer (kept inside the canvas):
header (name, kind chip, progress meter `done/total`), then items: Details (opens panel), Tasks (n) submenu-list
of board tasks + Work items (status chip, id, title; click opens Work/Roadmap), Open in Work, Copy id
(rb:<pid>/component/<id> + summary via ref.js), Ask Head about it (head.log kind=question with refs), Expand /
Collapse (groups and containers), Open sub-diagram (drill), Show in other views. Keyboard: arrows, Enter, Esc;
`role="menu"`/`menuitem`; focus returns to the node. API: `menuHtml(target, details, opts)`, `openMenu(host, at,
target, details, opts)`, `closeMenu()`, actions emitted as `CustomEvent("system:menu", {detail:{action,id}})`.
CSS classes: `.sys-menu`, `.sys-menu-h`, `.sys-menu-i`, `.sys-menu-sep`, `.sys-menu-list` (in system.css).

### 4.3 Expand and drill (issue 5) `web/js/graph/syslayout.js`
- Each group band and container box has a +/- toggle (top-left, 20 px, also in the menu). Collapsed group = one
  node (label + "n parts"), edges re-aggregated with counts; expanded = its members. Layout re-runs; the view keeps
  the toggled box under the pointer (anchor) and then fits only if it no longer fits.
- Drill: "Open sub-diagram" on a container/group shows a sub-view (`subgraph(view, groupId)` = members + one
  boundary node per external neighbour), breadcrumb `System > Containers > HTTP API` above the canvas; Backspace or a
  crumb goes up. Hash: `#/p/<pid>/system?v=<view>&in=<groupId>` so it deep-links.
- API: `layeredLayout(g, {aspect, collapsed:Set})`, `collapseGroups(g, collapsed)`, `subgraph(g, groupId)`.

### 4.4 Panel (issue 8) `web/js/views/system-panel.js`
Adds for components/containers: progress meter, "Board tasks (n)" rows (status chip | id | title | model),
"Work items (n)" rows (status | id | title), each a link (`#/p/<pid>/work/i/<W>` or the task in Roadmap), Copy id
button (`copyButton("component", id, label, {project, sum})`), Ask Head button, Open in Work. Row grid columns per
UI-CHECKLIST rule 0.

### 4.5 New diagrams (issue 3) `web/js/graph/sysdiagrams.js`
Pure renderers to SVG strings, token colours only, focusable nodes `data-sys`/`data-wf-item`:
`erSvg(er)` entity boxes with attribute rows (PK key icon text "PK", FK "FK"), crow's-foot ends, implied relations
dashed; `stateSvg(machine)` rounded states, initial dot, final ring, labelled transitions; `usecaseSvg(uc)` actors
left (stick figure), system boundary, ellipses, association lines; `activitySvg(act)` start dot, action rounded
rects, decision diamonds, merge, end ring, error path red; `deploymentSvg(dep)` nested 3D-ish node boxes with
processes inside; `classSvg(cls)` UML class boxes (name | attrs | methods), extends = hollow triangle. Each returns
`{svg, w, h}` sized to content. Multi-item diagrams (activity, states) get an item picker chip row like Flows.

### 4.6 Toolbar (issues 6, 7)
`[Structure | Behaviour | Data] [recommended view buttons] [More v] | [- 100% + Fit] [Expand all/Collapse all]
[Copy id] [Update diagrams] [Full screen]`. Copy id copies `rb:<pid>/view/system.<view>` + one-line summary, or the
selected node's ref. Update diagrams: `task.add {title:"Update System diagrams and check them (<project>)",
phase:<current open phase>}` then `head.log {text:"Update the System diagrams of <pid> and check them",
kind:"ask", sum:"update System diagrams", refs:["task:<new id>"]}`; toast with the task id and Undo.

### 4.7 Timeline (issue 9) `web/js/views/workflow.js` (timeline code only)
Continuous time axis over all jobs (not clipped to the range: the range picks the visible window); drag pans past
the window edge and loads the earlier/later span; plain horizontal wheel / trackpad and Shift+wheel scroll time;
Ctrl/Cmd+wheel and pinch zoom at the cursor (1 h .. all); zoom buttons -/+ and span presets 2h/Day/Week/All set the
window; "Now" glides to now; the axis labels re-tick for the zoom level (minutes, hours, days). No vertical page
scroll from the timeline; lanes scroll inside the plot.

## 5. Subtasks (phase R11; disjoint files per wave)
| id | Wave | Files (only these) | Done-check |
|---|---|---|---|
| R11.101 | 1 | new roadmap/services/system_tasks.py, new roadmap/services/system_v2.py, roadmap/http/routes.py (project_system + ETag only), roadmap/services/system.py (keep `tasks`/`work`/`views` keys), new tests/unit/test_system_tasks.py, tests/api/schemas/system.json, docs/API.md | fixture: component with commits R1.2 -> board has R1.2 with status; explicit tasks/work; progress; catalog present |
| R11.102 | 1 | new roadmap/services/system_data.py, new tests/unit/test_system_data.py | er from CREATE TABLE + JSON Schema + JSON store with FK and implied relations; states from STATUS tuples |
| R11.103 | 1 | new roadmap/services/system_behave.py, new tests/unit/test_system_behave.py | classes, deployment, usecases (argparse, routes, SECTIONS), activity from ast on a fixture |
| R11.104 | 1 | web/js/views/system.js, web/css/system.css, tests/web/test_system_view.py, tests/web/render_system.mjs | no page scroll, true fit, zoom %, Fullscreen API, panel docks inside, grouped switcher from catalog, Copy id, Update diagrams |
| R11.105 | 1 | new web/js/views/system-menu.js, new tests/web/test_system_menu.py | menuHtml items per kind, keyboard, clamped position, events |
| R11.106 | 1 | web/js/views/system-panel.js, tests/web/test_system_panel.py | board + work rows, progress, copy, ask, open in work |
| R11.107 | 1 | new web/js/graph/sysdiagrams.js, new tests/web/test_sysdiagrams.py | 6 renderers, no overlaps on fixtures, tokens only |
| R11.108 | 1 | web/js/graph/syslayout.js, tests/web/test_syslayout.py | collapse/expand regroup with edge counts, subgraph, perf |
| R11.109 | 1 | web/js/views/workflow.js (timeline functions only), tests/web/test_wf_timeline_ux.py | drag past edge, shift-wheel, zoom presets, Now |
| R11.110 | 2 | web/js/views/system.js, web/css/system.css, tests/web/test_system_view.py | menu + expand/drill + breadcrumb + new diagram kinds wired; check-ui green |
| R11.111 | 2 | docs/system.json, docs/SYSTEM-VIEWS-SPEC.md | seed tasks/work/machines/usecases overrides; `roadmap system check` passes |

New web files (need a service restart to stop 404): web/js/views/system-menu.js, web/js/graph/sysdiagrams.js.
New Python modules load on restart too: system_tasks.py, system_v2.py, system_data.py, system_behave.py.
