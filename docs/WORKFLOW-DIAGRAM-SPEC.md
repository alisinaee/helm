# Workflow diagram engine + design (Opus WP70). Decisions: own SVG engine (nothing vendored), default order Dependency, job pills under tasks

I recommend option (a): our own SVG renderer, a small pan/zoom/pinch controller built on pointer events, and our own lane-aware layered layout. Nothing gets vendored, and the CSP and static allowlist stay exactly as they are.

I read WORKFLOW-SPEC sections 1, 2 and 4, the `web` folder listings, the `<link>`/`<script>` lines in `index.html`, `static.py` and the CSP strings in `security.py`.

**Facts that drive the choice**
- **CSP:** `style-src 'self'` with no `'unsafe-inline'`. That blocks `<style>` elements and `setAttribute('style', …)`, including the `style=` attributes that libraries write into SVG markup. Setting `el.style.x` through the CSSOM and SVG presentation attributes (`transform`, `x`, `fill`) are still allowed. `script-src 'self'` blocks `eval`, `new Function` and blob workers.
- **Static allowlist:** extensions are limited to `CONTENT_TYPES`, and `.mjs` is not in it. Any vendored ESM file would have to be renamed to `.js`. A new `web/vendor/` folder would be picked up automatically at startup.
- **CSS budget:** `web/css` totals 59,798 B against the 65,536 B cap, so about 5.7 KB is free.
- **WP48:** `web/js/views/workflow.js` already exists, and `tests/web/test_workflow_view.py` exists.

## 1. Engine comparison

| | Touch/mouse | Size (min) | CSP risk | Licence / maintained | Styled by our tokens | Keyboard + aria | DAG + swimlanes | Haiku effort |
|---|---|---|---|---|---|---|---|---|
| **(a) Own SVG + pointer controller + layered layout** | Good if built on Pointer Events (one code path for mouse, pen and touch) | ~25 KB, our code | None, we control every attribute | Ours | Native: classes on tokens, dark/light for free | Full: real `<g tabindex role aria-label>` | Best fit: phases as lane bands are first-class | Medium, well bounded |
| (b) Cytoscape.js | Excellent built in | ~370 KB, plus dagre ~60 KB and an adapter | Low, but the adapter is UMD and needs a global | MIT, active | Poor: its own style JSON, needs `getComputedStyle` re-sync on theme change | **Canvas, so no DOM nodes.** We would need a parallel hidden list to be accessible | Its dagre support for compound nodes is weak, so no real swimlanes | Low to wire, high to make accessible and on-brand |
| (c) d3-zoom/selection + dagre | Very good | ~45 KB + ~60 KB | `selection.style` uses the CSSOM, which is fine | ISC/MIT, d3 active, dagre barely maintained | Native SVG | Full | No swimlane constraint, so we must post-process anyway | Medium, plus vendoring several ESM files |
| (d) elkjs + our SVG | Ours | **~1.5 MB** (GWT bundle) | Bundle runs on the main thread, worker build is blob-prone | EPL-2.0 | Native | Full | Best layout quality (partitions = lanes) | High: async API, large file |
| (e) vis-network | Good | ~500 KB | **Injects a `<style>` element, which our CSP blocks** | Apache/MIT, slow | Poor (canvas) | Poor | Hierarchical layout, no lanes | Medium |
| (f) mermaid | Pan/zoom not included | ~2–3 MB | **Inline `<style>` in the SVG output, which our CSP blocks**; static text-to-diagram | MIT | Theme variables only | Poor | No interaction model | Rejected |

**Why (a) wins.** Accessibility, our token colours and swimlanes are the hard requirements here. Every library either loses accessibility (canvas), breaks the CSP (e, f), or still needs our own lane step afterwards (b, c).

At 300 nodes or fewer, SVG is fast, and a layered layout with fixed lanes is about 150 lines of well-understood algorithm:
1. Longest-path ranking.
2. Four barycenter sweeps to reduce crossings within each lane.

So this option needs no vendor folder, no change to the allowlist or CSP, and no `eval` risk. If layout quality ever falls short, we can still vendor dagre later as `web/vendor/dagre-1.1.x.min.js` (MIT, licence header kept); it would replace only `layout.js`.

## 2. Diagram design

**Layout**
- Left to right.
- Each **phase is a horizontal swimlane band**, in phase order, with a sticky label on the left and a right gutter showing done/total and tokens K. Number columns are right-aligned with tabular numbers (rule 0).
- The column is the dependency rank over `after` edges plus handoff edges.
- A toggle **Order: Dependency | Time** sets the column instead from the task's earliest `at.doing` or job `start`, bucketed by the range (2 h, Today, Week, All). In Time mode there is a top tick axis and an accent now-line, which gives the timeline feel.
- Placement is deterministic, with no force layout.

**Node types (all `<g class="n n-<type> s-<status>">`)**

| Node | Shape and content |
|---|---|
| Phase group | Lane band rect plus header (name, approved badge) |
| Task node | 168×44 rounded card: status dot, id, title (ellipsis), and a corner badge for the `after` count |
| Job node | Small pill hanging under its task: model/role chip (opus, sonnet, haiku, agy), job id, running pulse. More than 3 jobs collapse into "+n" |
| Issue/blocker node | Danger-outlined hexagon placed in the lane above the task it blocks |
| Queue node | One aggregate pill, "Queue (n)", at the far left of the lane of its first task |

**Edges (SVG cubic paths with `marker-end`)**
- Handoff: job → job, solid, `--accent-2`.
- Dependency: dotted, `--muted`.
- Blocker: solid `--danger`, thicker.

**Status colours:** done `--success`, doing `--accent`, todo `--unknown`, blocked `--danger` (hatched pattern defined once in `<defs>`).

**Focus mode**
- Tap or click selects a node and dims everything except its upstream and downstream closure (BFS over all edge types).
- Esc or a tap on the background clears it.
- The right panel's Details tab shows the node. Its lists have fixed columns: Status | Id | Title | Model | Start | Dur→ | Tok K→ | [Action], with the action always last.

**Controls (top-right overlay)**
- Buttons: −, +, Fit, 100%, Focus off.
- Wheel zooms around the cursor; Ctrl+wheel and trackpad pinch work too.
- Drag on the background pans.
- On touch: one-finger pan, two-finger pinch, double-tap to zoom.
- Keyboard: `+`/`-`, `0` to fit, Shift+arrows to pan. Arrows move focus to the nearest node in that direction, and Enter opens Details.

**Tap vs drag**
- `pointerdown` captures the pointer. Movement over 6 px, or more than one pointer, means pan or pinch, and click is suppressed. Otherwise `pointerup` counts as a tap.
- `touch-action: none` applies only on the SVG. Zoom is limited to 0.25–3×, and the transform is written as an SVG `transform` attribute on the viewport `<g>`.

**Minimap:** skipped. Instead, a Fit button plus an "n of m nodes" chip.

**Filters:** chips for status, agent/model and phase, saved in the URL (`?st=doing,blocked&ag=haiku&ph=P2`).

**Legend:** one row using the `legend.js` pattern: four status swatches plus the three edge styles.

**Performance cap:** 300 nodes. Above that, done tasks in completed phases collapse into a single "Phase P1: 24 done" node, with a banner offering "Show all (slow)". Rendering is a single `innerHTML`-free build with `createElementNS`, and re-render happens only when the snapshot hash changes.

**Empty state:** "No tasks or jobs yet. Agents record work with `roadmap job start`." plus a link to Agents.

**Mobile (under 768 px):** the default view is Table. The Map still works: lane labels collapse to phase ids, Fit is applied on open, and the panel becomes a bottom sheet.

**Accessibility**
- Every node is `<g tabindex="0" role="button" aria-label="Task P2.3, doing, after P2.1, job J41 haiku">`.
- The SVG has `role="group"` and `aria-describedby` pointing at the legend.
- The Table is the full equivalent.

**Views:** a segmented control **Map | Timeline | Table** saved as `?v=`, with Map as the desktop default. Timeline and Table stay WP48's functions.

## 3. Package plan

**Message to the WP48 worker (send now):** "Keep and finish the Timeline, Table, segmented control, routes, legend and empty state. Stop work on `mapSvg` / the phase-column Map. Leave `mapSvg(model)` as a stub that returns the empty-state markup, so the Map slot exists. Do not add Map CSS. Keep `map.css` at Timeline and Table rules only."

**WP70-A: graph model and layout (Haiku, about 60k, after WP48 lands)**
- Files:
  - New `web/js/graph/model.js`: `buildGraph(snap, filters) → {nodes, edges, lanes}`, including the 300-node collapse.
  - New `web/js/graph/layout.js`: `layout(graph, mode, range, now) → positions`, covering rank, lanes, barycenter sweeps and edge paths.
  - New `tests/web/test_workflow_graph.py`, following the existing tests/web pattern, with fixtures for empty, chain, cycle-free fan-in, and 350 tasks.
- Acceptance:
  1. Pure and deterministic: the same input gives byte-identical output.
  2. No overlapping nodes within a lane.
  3. Every edge has a path.
  4. The 350-task fixture comes down to 300 nodes or fewer.

**WP70-B: renderer, viewport and integration (Haiku, about 120k, after A)**
- Files:
  - New `web/js/graph/viewport.js` (about 200 lines): pointers, pinch, wheel, keys, fit, tap-vs-drag.
  - New `web/js/graph/render.js`: SVG build, focus-mode dimming, aria.
  - `web/js/views/workflow.js`: real `mapSvg`, filters, controls, Details.
  - New `web/css/graph.css` (3.5 KB or less, tokens only) plus its `<link>` in `index.html`.
- Lazy loading: `await import('../graph/render.js')` only when `v=map`.
- Acceptance:
  1. No `style=`, `on*=`, `eval` or `new Function` (grep test).
  2. The CSS budget test passes.
  3. Keyboard: Tab, arrows, Enter, `+`, `-` and `0` all work.

**WP70-C: review and real interaction tests (Sonnet, about 40k)**
- Load the page with the Browser pane at the desktop size and the `mobile` preset.
- Touch: dispatch `PointerEvent`s with `pointerType:'touch'` through `javascript_tool`:
  - One pointer moving 40 px must change the viewport transform and must **not** select a node.
  - Two pointers moving apart must increase the scale.
  - A down/up within 6 px on a node must open Details.
- Mouse: wheel zoom, background drag, Fit.
- CSP: `read_console_messages` with pattern `Content Security Policy` must return zero entries, and the network log must show no `/vendor` requests.
- Check that only the Map view triggers the `graph/*.js` requests.
- Screenshots in dark and light.

**Total:** about 220k across the three packages; each one is under 200k.

## 4. Decisions for the person
1. **Default order for the Map:** Dependency (clean DAG, best for planning) or Time (a timeline feel, but edges can run backwards when work started out of order)? I recommend Dependency by default, with the Time toggle kept.
2. **Job nodes:** show them as pills hanging under their task (compact, which I recommend), or as separate nodes in an "Agents" lane so handoff chains read as their own flow (clearer handoffs, and the graph roughly doubles in size)?

### Critical Files for Implementation
- ~/Works/roadmap-board/web/js/views/workflow.js
- ~/Works/roadmap-board/web/js/graph/layout.js (new)
- ~/Works/roadmap-board/web/js/graph/viewport.js (new)
- ~/Works/roadmap-board/roadmap/http/security.py (CSP; unchanged, used for the check)
- ~/Works/roadmap-board/tests/web/test_workflow_view.py