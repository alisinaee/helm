# Job staffer-mv9hhyv3-455ac949 (staffer, done)

[`web/js/views/workflow.js:510`](file:///Users/ali/Works/roadmap-board/web/js/views/workflow.js#L510): Timeline status marks use identical diamond paths for doing, done, and blocked, conveying status by colour alone (Rule 1). Fix: use distinct SVG shapes for each status (e.g. circle for doing, checkmark for done, diamond for blocked).
[`web/js/views/workflow.js:520`](file:///Users/ali/Works/roadmap-board/web/js/views/workflow.js#L520): Horizontal timeline scroller `.wf-scroll` lacks keyboard accessibility (Rule 1). Fix: add `tabindex="0" role="region" aria-label="Workflow timeline"` to allow keyboard panning.
[`web/js/views/workflow.js:630`](file:///Users/ali/Works/roadmap-board/web/js/views/workflow.js#L630): Map filter chips `<a class="wfg-chip">` measure ~18px tall with 4px gap, failing phone 44px target and 8px spacing rules (Rule 2). Fix: style `.wfg-chip` with `min-height: 44px; display: inline-flex; align-items: center` and `.wfg-chips` with `gap: var(--sp-2)`.
[`web/js/views/workflow.js:738`](file:///Users/ali/Works/roadmap-board/web/js/views/workflow.js#L738): Filter reset paragraph runs text together without spacing (`filters.<a`). Fix: insert a space before `<a` (`No tasks match these filters. <a ...>`) or replace with `emptyHtml()`.
[`web/js/views/workflow.js:754`](file:///Users/ali/Works/roadmap-board/web/js/views/workflow.js#L754): Diagram toolbar buttons (`.wfg-ctl .btn-small`) use 24px height and 4px gap on mobile (Rule 2). Fix: add `@media (max-width: 767px) { .wfg-ctl .btn { min-height: 44px; min-width: 44px; } .wfg-ctl { gap: var(--sp-2); } }`.
[`web/js/views/workflow.js:832`](file:///Users/ali/Works/roadmap-board/web/js/views/workflow.js#L832): Non-project route displays raw `<p class="wf-hint">` without an actionable navigation link (Rule 10). Fix: use `emptyHtml("Select a project to view diagram.", '<a href="#/all/projects">View projects</a>')`.
[`web/js/views/workflow.js:834`](file:///Users/ali/Works/roadmap-board/web/js/views/workflow.js#L834): Diagram failure banner offers no retry action and `graphFailed` permanently blocks re-fetching (Rule 4, 10). Fix: add a retry button and reset `graphFailed = false` before re-calling `loadGraph()`.
[`web/js/views/workflow.js:837`](file:///Users/ali/Works/roadmap-board/web/js/views/workflow.js#L837): Redundant nested `aria-busy` containers emitted during graph loading. Fix: return `skeletonHtml(["w-60", "w-90"])` directly without the outer `<div aria-busy="true">`.
[`web/js/views/workflow.js:849`](file:///Users/ali/Works/roadmap-board/web/js/views/workflow.js#L849): Table action buttons ("Stop" / "Open") remain 24px high on mobile viewports (Rule 2). Fix: add `@media (max-width: 767px) { .wf-table .btn { min-height: 44px; min-width: 44px; } }` in `map.css`.
[`web/js/views/workflow.js:867`](file:///Users/ali/Works/roadmap-board/web/js/views/workflow.js#L867): Table task cell clips text without `text-overflow: ellipsis` or a `title` attribute, violating Rule 0. Fix: add `title="${task}"` attribute to `<td>` and `text-overflow: ellipsis` in `.wf-table td`.
[`web/js/views/workflow.js:873`](file:///Users/ali/Works/roadmap-board/web/js/views/workflow.js#L873): Table scroller lacks keyboard focus semantics and forces horizontal scrolling on 375px screens instead of stacking (Rules 1, 5). Fix: add `tabindex="0" role="region" aria-label="Jobs table"` and collapse rows on mobile.
[`web/js/views/workflow.js:902`](file:///Users/ali/Works/roadmap-board/web/js/views/workflow.js#L902): Detail strip "Open" link lacks an accessible name with task context (Rule 1). Fix: add `aria-label="Open task " + esc(it.task)`.
[`web/js/views/workflow.js:984`](file:///Users/ali/Works/roadmap-board/web/js/views/workflow.js#L984): Workflow load error banner text promises "Retrying." but lacks a manual retry action button (Rule 4, 10). Fix: include a `<button type="button" class="btn btn-small">Retry now</button>` that triggers `fetchSnapshot(pid)`.
[`web/js/views/workflow.js:986`](file:///Users/ali/Works/roadmap-board/web/js/views/workflow.js#L986): Redundant outer `<div aria-busy="true">` wrapper around `skeletonHtml()` which already defines its own busy region. Fix: return `skeletonHtml(["w-60", "w-90"])` directly.
[`web/js/views/workflow.js:1015`](file:///Users/ali/Works/roadmap-board/web/js/views/workflow.js#L1015): Filtered empty state `<p class="wf-hint">No jobs in this range.</p>` lacks an actionable reset (Rule 10). Fix: use `emptyHtml("No jobs in this range.", '<a href="' + esc(hashFor(route, view, "all", null)) + '">Show all</a>')`.
[`web/css/map.css:48`](file:///Users/ali/Works/roadmap-board/web/css/map.css#L48): `--rg` column definition ends in `auto`, creating an empty 9th grid column because `.row-grid` appends `var(--ref-col)`. Fix: set `grid-template-columns: var(--rg)` explicitly on `.wf-cols`.
[`web/css/map.css:50`](file:///Users/ali/Works/roadmap-board/web/css/map.css#L50): `.wf-table` specifies fixed `min-width: 42rem` with no phone stacking rules, causing horizontal scroll at 375px (Rule 5). Fix: add `@media (max-width: 767px)` rules stacking `tr` cells with 44px min-heights.
[`web/css/map.css:65`](file:///Users/ali/Works/roadmap-board/web/css/map.css#L65): Legend `.wf-k-blocked` swatch uses solid `var(--danger)` background without the hatch pattern present on blocked bars (Rule 1). Fix: apply `background: repeating-linear-gradient(...)` to match the hatch texture.
[`web/css/graph.css:36`](file:///Users/ali/Works/roadmap-board/web/css/graph.css#L36): Focus ring selector targets `.wfg-n` but omits phase fold buttons `.wfg-fold`, leaving them without focus rings (Rule 1). Fix: add `.wfg-fold:focus-visible .wfg-fold-box` to focus stroke selectors.
[`web/css/work.css:50`](file:///Users/ali/Works/roadmap-board/web/css/work.css#L50): Responsive breakpoint rules for `.row-grid.wf-cols` are misplaced inside `work.css` instead of `map.css`. Fix: move `.row-grid.wf-cols` rules from `work.css:50-54` into `map.css`.

[unrestricted] agy modified the working tree during this staffer run — verify the task asked for it. Delta (`git status --porcelain` entries that appeared or changed during the run):
   M docs/head-gate.json
   M roadmap/commands/status.py
   M roadmap/services/commands.py
   M tests/web/test_head_view.py
   M web/css/components.css
   M web/css/flow.css
   M web/css/work.css
   M web/js/views/list.js
   M web/js/views/overview.js
  ?? docs/reviews/agy-sec-routes.md
  ?? docs/reviews/agy-ux-head.md
  ?? docs/reviews/agy-ux-roadmap.prompt.txt
  ?? docs/reviews/agy-ux-settings.md
  ?? docs/reviews/agy-ux-settings.prompt.txt
  ?? docs/reviews/agy-ux-tokens.md
  ?? docs/reviews/agy-ux-work.md
  ?? docs/reviews/agy-wave1-verify.prompt.txt
  ?? docs/reviews/agy-wf-sync.prompt.txt
  ?? tests/unit/test_backlog_ops.py
  ?? tests/unit/test_backlog_snapshot.py
ACTION FOR THE CALLING AGENT: inspect these changes (`git diff`) before trusting this staffer. Rollback: `git checkout -- <path>` for tracked files, delete the new untracked ones.
