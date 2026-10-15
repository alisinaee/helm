# Job staffer-mv9hov2e-a76c4914 (staffer, done)

web/js/views/workflow.js:37: `cache` Map caches raw snapshots by pid without invalidating on `snap.rev` changes; Fix: Key cache by or invalidate on `snap.rev` change, or read `vm.project.snapshot`.
web/js/views/workflow.js:120: `fetchSnapshot` throttles with `now - entry.at < FRESH_MS` (5s) ignoring `snap.rev`; Fix: Invalidate throttle check when `snap.rev` changes.
web/js/views/workflow.js:122: Map reads data via independent `getJson("/api/v1/projects/" + ...)` call instead of the snapshot; Fix: Read data from `vm.project.snapshot`.
web/js/views/workflow.js:88: `nowMs()` reads `Date.now()` clock instead of snapshot timestamp; Fix: Use `vm.now` or `snap.server_time` / `snap.fetchedAt`.
web/js/views/workflow.js:536: `mapStates` caches per-project UI view and `fitted: true` without invalidation on `snap.rev`; Fix: Key `mapStates` by `snap.rev` or clear `fitted`.
web/js/views/workflow.js:707: `kit.model.buildGraph` performs a one-time build from un-invalidated `ctx.raw`; Fix: Rebuild graph model whenever `snap.rev` updates.
web/js/views/workflow.js:735: Map HTML only embeds task counts (`matched of total items`), so when task counts don't change `dom.patch` skips DOM write; Fix: Embed `snap.rev` in container markup so `dom.patch` detects revision changes.
web/js/views/workflow.js:803: `mountMaps` skips render with `if (!host || host.firstChild) return;`; Fix: Clear `host.replaceChildren()` or re-mount when revision or `pendingMap` changes.
web/js/views/workflow.js:973: `sectionView` reads snapshots from local `cache.get(pid)` instead of `vm.project.snapshot`; Fix: Consume `vm.project.snapshot` directly.
web/js/views/workflow.js:718: Map omits Order toggle (Dependency | Time) and rank columns; Fix: Add Dependency/Time order control and rank layout.
web/js/views/workflow.js:754: Controls toolbar misses the 100% zoom button; Fix: Add 100% button (`actual()`) to toolbar controls.
web/js/views/workflow.js:942: Legend displays non-spec status names ("Running", "Blocked or failed", "Todo"/"Queued"); Fix: Align legend with spec's 4 status swatches (done, doing, todo, blocked).
web/js/graph/model.js:74: Task status includes non-spec "defer" / "deferred" state; Fix: Map task states only to spec statuses (done, doing, todo, blocked).
web/js/graph/model.js:274: Job pill collapse keeps only 2 jobs (`PILL_KEEP = 2`) when jobs > 3; Fix: Keep 3 jobs and collapse only overflow into `+n` per spec.
web/js/graph/model.js:287: Job pill label only stores truncated model name (`j.model || j.id`) omitting job id and role; Fix: Store model, role chip, and job id on the node.
web/js/graph/model.js:336: Injects non-spec `sequence` edges between all sequential tasks; Fix: Remove sequence edges and draw only handoff, dependency, and blocker edges.
web/js/graph/layout.js:18: Task node dimensions are 200×52 / 200×56 instead of spec 168×44; Fix: Set `NODE_W` to 168 and `NODE_H` to 44.
web/js/graph/layout.js:20: Job pill width is fixed to 36px (`PILL_W = 36`), preventing display of role and job id; Fix: Widen pill to fit model/role chip and job id.
web/js/graph/layout.js:401: Phases are laid out as vertical snake frames instead of horizontal swimlanes; Fix: Lay out phases as horizontal swimlane bands with left sticky labels and right gutters.
web/js/graph/layout.js:428: Blocker issues and queue placed in a generic top strip; Fix: Position blocker in lane above blocked task, and queue at far left of its lane.
web/js/graph/layout.js:521: Edge routes computed as orthogonal polyline segments; Fix: Route edges as SVG cubic Bezier paths (`M x y C ...`).
web/js/graph/render.js:152: Task node uses `wfg-n wfg-task wfg-s-*` instead of `class="n n-<type> s-<status>"`; Fix: Use spec node class naming convention.
web/js/graph/render.js:158: Task node renders text glyphs (`GLYPH`) and lacks `after` count corner badge; Fix: Render a status dot and corner badge with `n.after`.
web/js/graph/render.js:167: Job pill omits status class `s-<status>` and running pulse element; Fix: Add status class and animated pulse element to running jobs.
web/js/graph/render.js:173: Job pill only renders truncated model label; Fix: Render model/role chip, job id, and pulse inside the pill.

[unrestricted] agy modified the working tree during this staffer run — verify the task asked for it. Delta (`git status --porcelain` entries that appeared or changed during the run):
   M roadmap/services/limits.py
   M roadmap/services/usage.py
   M tests/web/render_tokens_simple.mjs
   M web/js/views/limits.js
   M web/js/views/tokens.js
   M web/js/views/topbar.js
  ?? docs/HEAD-AGENT-V2.md
  ?? docs/reviews/agy-ux-agents.md
  ?? docs/reviews/agy-ux-overview.md
  ?? docs/reviews/agy-ux-roadmap.md
  ?? docs/reviews/agy-ux-settings.md
  ?? docs/reviews/agy-ux-workflow.md
  ?? docs/reviews/agy-wave1-verify.md
  ?? tests/unit/test_usage_truth.py
  ?? tests/web/test_tokens_truth.py
ACTION FOR THE CALLING AGENT: inspect these changes (`git diff`) before trusting this staffer. Rollback: `git checkout -- <path>` for tracked files, delete the new untracked ones.
