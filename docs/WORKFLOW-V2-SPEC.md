# R7.14 Workflow map v2: one path from Start to Now

## 1. What is wrong now

- **Opens on Timeline:** a Gantt of 3 job bars, a Blocked bar, an empty Queue row (1440 shots). The legend lists edges never drawn.
- **Map phases are stacked swimlanes.** The project reads top to bottom, not left to right.
- **Almost no arrows.** Columns rank only over `after` and handoff edges. Alpha (40 tasks) and the real board (68) have 0 `after` and 0 `at`, so every task ranks 0. Each phase is one tall column.
- **No Start, no "you are here", no jump to current.**
- **Bug:** `taskStatus` in model.js maps `partial` and `hold` to todo, so in-progress work is invisible.
- **Keep:** pan, zoom, pinch, tap vs drag, focus, aria, CSP (passed R6.34).

## 2. Visual model

- **Flow, left to right:** Start pill (project, first date) → phase frames → Now → todo tail → End pill ("n left").
- **Frame (one per phase):**
  - Title tab: id, name, done/total, tokens K.
  - Tasks snake inside it in file order, at most 4 columns wide.
  - ▸/▾ collapses it to a 200×56 progress card (state in hash `?x=`).
- **Nodes:**
  - Task: 168×44: glyph, id, title clipped at 22 (full in `<title>`), 24 px R7.12 copy slot.
  - Job pills, issue hexagons: unchanged.
- **Edges:** orthogonal, 8 px rounded corners, `marker-end`, classes only (no inline style), one marker per class.
  - **Sequence** (synthetic): task to next task, and last task of a phase to first task of the next phase. Solid `--muted`, but `--success` from Start to Now.
  - **Dependency** (`after`): dashed `--accent-2`.
  - **Handoff:** thin `--accent-2`.
  - **Blocker:** thick `--danger`.
- **Parallel work:** tasks that are doing at the same time become stacked branches, with a fork arrow in and a join arrow out.
- **States** (always glyph plus aria, never colour alone):
  - done: `--success`
  - doing: `--accent`, with a pulse except under reduced motion
  - todo: `--unknown` outline
  - blocked/hold: `--danger` with a hatch
  - defer: dimmed
- **Now:** an accent bar with a "You are here" flag and a 2 px halo on the current node. After Now: 0.6 opacity.
- **Labels:** below zoom 0.5, ids and frame titles only.

## 3. Layout (layout.js: own, deterministic, O(n+e))

1. **Order:** file order. `after` can reorder tasks only within a phase (stable topological sort).
2. **Current point:** the first doing task. Else the first todo after the last done. Else End.
3. **Frame grid:**
   - `ceil(n/4)` × `min(n,4)` grid; a parallel block takes one column; frames 64 px apart.
   - Cross-frame `after` edges run in a channel above, lanes assigned greedily.
4. **Cap:** 300 visible nodes, with a collapsed frame counting as 1. Over it, done frames collapse, then todo frames 2+ past Now; banner "Show all (slow)".
5. **Modes:** the Time toggle stays. Dependency mode is renamed Path.

## 4. Interaction

- **Default view:** Map at 768 px and wider; Table stays the phone default. On open, the map fits its height and centres on Now.
- **Controls** (fixed 32 px grid): −, zoom %, +, Fit, Now (`n`), Start (`s`), Collapse all / Expand all.
- **Minimap:** 160×90 at the bottom right. Frames plus viewport rect; click/drag moves the view. Under 768 px it becomes a breadcrumb of phase chips.
- **Selection:** tap opens Details plus focus mode; Esc clears.
- **Keyboard:**
  - Tab: the canvas, then nodes in path order.
  - Left / Right: along the path.
  - Up / Down: branch siblings.
  - `[` `]`: previous / next phase.
  - Enter: Details.
  - Space: toggle the frame.
  - `+` `-` `0` `n` `s`.
- **Touch:** unchanged; targets ≥ 44 px on phone.

## 5. Files, budget, data

- **graph/model.js:** status fix; start, end and frame nodes; `sequence` edges; `current`; parallel groups.
- **graph/layout.js:** core rewritten (same signature). Bands removed. Adds `frames`, `current`, `nowX` and orthogonal paths.
- **graph/render.js:** frames, pills, Now flag, per-class markers, an empty `<g class="wfg-ref">` copy slot, zoom-level classes.
- **graph/viewport.js:** `centerOn`, the new keys, path-order arrows, a minimap callback.
- **graph/minimap.js (new):** 120 lines or fewer.
- **views/workflow.js:** Map as default, controls, `x=` in the hash, mobile breadcrumb.
- **css/graph.css:** rewritten, 6 KB or less.
- **CSS:** 64,883 B of 73,728 B now; about 6 KB stays free after.
- **Data:** no backend change. Uses phases, tasks, `workflow.spans`, `edges.after`, `edges.block`, and `at` when present.

## 6. Packages (Haiku, in order A→E, file lists do not overlap)

- **A. Model:** graph/model.js and tests/web/test_workflow_graph.py.
  - Tests: status map, sequence chain, current point (all done / none done / doing), parallel group, determinism.
- **B. Layout:** graph/layout.js and the new tests/web/test_workflow_layout.py.
  - Tests: frames left to right, no overlaps, snake order, every edge has a path, 350 tasks → ≤ 300 nodes, 100 tasks < 50 ms, byte-identical.
- **C. Render:** graph/render.js, css/graph.css, and the markup tests in tests/web/test_graph_keys.py.
  - Tests: no `style=`/`on*`, markers, Now flag, `wfg-ref` slot, CSS budget.
- **D. Viewport:** graph/viewport.js, graph/minimap.js (new) and the new tests/web/test_graph_viewport.py.
  - Tests: centerOn, the keys, a minimap click.
- **E. View:** views/workflow.js and tests/web/test_workflow_view.py.
  - Tests: default view, `x=` in the hash, breadcrumb.
  - Then run `make check` and `make check-ui` and take new screenshots.

R7.12 comes later and only fills `wfg-ref` in render.js.

**agy audits** (read-only, head verifies):
1. Layout on alpha and the real board: overlaps, wrong current point, crossings, cap.
2. The diff: aria, tab order, reduced motion, edge-token contrast in both themes, CSP.

## 7. Risks and questions

**Risks**
- File order may not be the real work order; the snake wrap can confuse.
- `context-stroke` support varies by browser. The CSS fallback covers it.
- More than 70 tasks are cramped on a phone. Table stays the default there.

**Questions**
1. Done phases start collapsed (recommended) or expanded?
2. Open centred on Now (recommended) or fit the whole project?
3. Parallel branches from running jobs (live) or only from partial/doing tasks (stable)?
