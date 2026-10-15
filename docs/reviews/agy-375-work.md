# Job staffer-mv9f981p-a9ad2d56 (staffer, done)

[work.css:35](file:///Users/ali/Works/roadmap-board/web/css/work.css#L35): `.wk-table .wk-c-title a` sets `white-space: nowrap`, which combined with mobile `table-layout: auto` ([work.css:56](file:///Users/ali/Works/roadmap-board/web/css/work.css#L56)) causes `.wk-table` to expand to 1700px+ and `.wk-tablewrap` ([work.css:30](file:///Users/ali/Works/roadmap-board/web/css/work.css#L30)) to scroll horizontally at 375px instead of reflowing.
[work.css:30](file:///Users/ali/Works/roadmap-board/web/css/work.css#L30): `.wk-tablewrap` uses `overflow-x: auto`, introducing a horizontal scrollbar on mobile rather than transforming into responsive stacked rows that fit within 375px (Rule 5).
[work.css:54](file:///Users/ali/Works/roadmap-board/web/css/work.css#L54): On mobile (`<= 767px`), numeric columns (`.wk-c-est`, `.wk-c-spent`, `.wk-c-cap`) are hidden with `display: none` instead of collapsing to two lines with numbers kept right-aligned (Rule 0).
[work.css:32](file:///Users/ali/Works/roadmap-board/web/css/work.css#L32): `.wk-table td` defaults to `text-align: left`, leaving the task ID cell ([list.js:184](file:///Users/ali/Works/roadmap-board/web/js/views/list.js#L184), `.wk-c-id.num`) left-aligned rather than right-aligned in its fixed 4.5rem track.
[list.js:177](file:///Users/ali/Works/roadmap-board/web/js/views/list.js#L177): Subtask progress numbers are concatenated as free text inside the `.wk-c-flags` string rather than rendered in a dedicated right-aligned numeric column track.
[list.js:178](file:///Users/ali/Works/roadmap-board/web/js/views/list.js#L178): Comment count numbers are concatenated inside `.wk-c-flags` rather than placed in their own right-aligned numeric column track.
[work.css:59](file:///Users/ali/Works/roadmap-board/web/css/work.css#L59): On mobile, `.wk-c-ref` uses `margin-left: auto` inside the expanded flex row, pushing the row's copy action off-screen to 1700px+ instead of anchoring it in a fixed column at the right viewport edge.
[tree.js:16](file:///Users/ali/Works/roadmap-board/web/js/views/tree.js#L16): In subtask items, the copy button (`.ref-copy`) is rendered outside `<label class="wk-sub">` in an unstyled `<li>`; because `.wk-sub` is a block flex container ([work.css:46](file:///Users/ali/Works/roadmap-board/web/css/work.css#L46)), the action drops onto a new line instead of aligning in a fixed trailing column.
[work.css:46](file:///Users/ali/Works/roadmap-board/web/css/work.css#L46): `.wk-subs li` lacks a grid or flex track specification to position `.wk-sub` and `.ref-copy` in fixed tracks (`minmax(0, 1fr) var(--ref-col)`).
[tree.js:28](file:///Users/ali/Works/roadmap-board/web/js/views/tree.js#L28): In `.wk-tree-row.row-grid`, the task ID (`.wk-id.num`) track (`4.5rem` at [work.css:45](file:///Users/ali/Works/roadmap-board/web/css/work.css#L45)) is left-aligned ([work.css:18](file:///Users/ali/Works/roadmap-board/web/css/work.css#L18)) rather than right-aligned with `.rg-num`.
[tree.js:28](file:///Users/ali/Works/roadmap-board/web/js/views/tree.js#L28): Tree task rows emit no task numeric values (tokens, elapsed, est, spent, subtasks) in fixed right-aligned tracks, omitting numbers specified by Rule 0.
[work.css:65](file:///Users/ali/Works/roadmap-board/web/css/work.css#L65): In mobile Tree rows, `.wk-word` and `.rg-chips` are both assigned to `grid-column: 2; grid-row: 2`, causing status text and flag chips to collide and overlap at 375px.
[work.css:64](file:///Users/ali/Works/roadmap-board/web/css/work.css#L64): In mobile Tree rows, the copy button is assigned to row 1 (`grid-row: 1`) while row 2 has no action track, leaving the action column fragmented across wrapped lines.
[work.css:43](file:///Users/ali/Works/roadmap-board/web/css/work.css#L43): `.wk-phase-btn` hardcodes over 200px of fixed column tracks (`1rem 4.5rem minmax(0,1fr) 4.5rem`), severely constraining available space for phase names at 375px.
[board.js:221](file:///Users/ali/Works/roadmap-board/web/js/views/board.js#L221): Board card numbers (est, spent, subtasks, comments) sit in a fluid wrapping flex paragraph ([work.css:21](file:///Users/ali/Works/roadmap-board/web/css/work.css#L21), `.wk-meta`) without fixed grid tracks or right alignment.
[board.js:241](file:///Users/ali/Works/roadmap-board/web/js/views/board.js#L241): Board column header count (`.wk-count.num`) uses flex `justify-content: space-between` ([work.css:12](file:///Users/ali/Works/roadmap-board/web/css/work.css#L12)) and lacks `.rg-num` right-alignment in a fixed grid track.
[board.js:234](file:///Users/ali/Works/roadmap-board/web/js/views/board.js#L234): Board card actions (status buttons, More menu, copy button) are rendered in a wrapping flex row ([work.css:2](file:///Users/ali/Works/roadmap-board/web/css/work.css#L2), `.wk-acts`) rather than a single fixed action column.
[work.css:50](file:///Users/ali/Works/roadmap-board/web/css/work.css#L50): `.wk-tabs` lacks `flex-wrap: wrap` on mobile screens, risking horizontal overflow at 375px when column counts or titles grow.
[work.css:52](file:///Users/ali/Works/roadmap-board/web/css/work.css#L52): `.wk-chip` sets `max-width: 48%` on mobile, unnecessarily squashing single-chip filter buttons like the plan item filter ([work.js:93](file:///Users/ali/Works/roadmap-board/web/js/views/work.js#L93)) to less than half screen width without text ellipsis.

[unrestricted] agy modified the working tree during this staffer run — verify the task asked for it. Delta (`git status --porcelain` entries that appeared or changed during the run):
   M roadmap/core/snapshot.py
   M roadmap/services/loader.py
   M tests/web/render_ref_p7.mjs
   M tests/web/render_tokens_simple.mjs
   M web/js/api.js
   M web/js/app.js
   M web/js/cmd.js
   M web/js/dom.js
   M web/js/state.js
   M web/js/views/head.js
   M web/js/views/tokens.js
  ?? docs/reviews/agy-375-agents.md
  ?? docs/reviews/agy-375-agents.prompt.txt
  ?? docs/reviews/agy-375-overview.md
  ?? docs/reviews/agy-375-roadmap.prompt.txt
  ?? docs/reviews/agy-375-tokens.md
  ?? docs/reviews/agy-375-tokens.prompt.txt
  ?? docs/reviews/agy-375-workflow.md
  ?? docs/reviews/agy-375-workflow.prompt.txt
  ?? docs/reviews/agy-testgaps.prompt.txt
  ?? tests/unit/test_sync_revision.py
  ?? tests/web/test_dom_patch_focus.py
  ?? tests/web/test_sync_client.py
ACTION FOR THE CALLING AGENT: inspect these changes (`git diff`) before trusting this staffer. Rollback: `git checkout -- <path>` for tracked files, delete the new untracked ones.
