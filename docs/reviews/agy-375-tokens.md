# Job staffer-mv9f9b51-9c17cdf1 (staffer, done)

[components.css:473](file:///Users/ali/Works/roadmap-board/web/css/components.css#L473): Desktop `--rg` defines 5 column tracks (`minmax(0, 1fr) 5.5rem 6.5rem 7rem 6.5rem`) totaling 6 columns with `var(--ref-col)`, but [tokens.js:39-48](file:///Users/ali/Works/roadmap-board/web/js/views/tokens.js#L39-L48) emits only 4 spans, leaving track 5 (6.5rem) and track 6 empty.
[tokens.js:41](file:///Users/ali/Works/roadmap-board/web/js/views/tokens.js#L41): Resets column is marked `rg-num` with `white-space: nowrap` ([components.css:788](file:///Users/ali/Works/roadmap-board/web/css/components.css#L788)), but renders a long text timestamp (`fmtResets`, e.g. "resets in 3d 0h (Fri 16 Oct, 15:30)") that overflows the fixed 7rem grid track.
[tokens.js:45](file:///Users/ali/Works/roadmap-board/web/js/views/tokens.js#L45): Project name in `<span class="rg-t">` omits the `title` attribute with the full name, violating Rule 0 title requirement when names are truncated by ellipsis.
[components.css:1029](file:///Users/ali/Works/roadmap-board/web/css/components.css#L1029): At `max-width: 639px`, `.row-grid` switches to flex-wrap without a 2-line collapse rule for `.tk-spend`, causing numeric columns to drift horizontally rather than staying aligned in fixed tracks.
[tokens.js:45](file:///Users/ali/Works/roadmap-board/web/js/views/tokens.js#L45): Spend row project title uses `.rg-t` instead of `.rg-main`, so on mobile flex-wrap ([components.css:1034](file:///Users/ali/Works/roadmap-board/web/css/components.css#L1034)) it does not take full width, causing numbers to sit directly beside short titles.
[components.css:1030](file:///Users/ali/Works/roadmap-board/web/css/components.css#L1030): Mobile flex-wrap on `.row-grid` places numeric cells inline following the title, losing right-alignment against the row container edge.
[limits.js:94](file:///Users/ali/Works/roadmap-board/web/js/views/limits.js#L94): `rg-weekly` form uses `.row-grid` but lacks a `--rg` definition in `web/css`, falling back to `:root` 2-column tracks and breaking column alignment.
[limits.js:127](file:///Users/ali/Works/roadmap-board/web/js/views/limits.js#L127): `rg-share` form uses `.row-grid` without a `--rg` definition in `web/css`, leaving project limit rows without fixed column widths for numeric share and used values.
[limits.js:153](file:///Users/ali/Works/roadmap-board/web/js/views/limits.js#L153): `rg-share` header (`rg-head`) renders bare `<span>Used</span>` without `.rg-num`, misaligning the header text (left-aligned) above right-aligned numeric data cells.
[admin.css:11](file:///Users/ali/Works/roadmap-board/web/css/admin.css#L11): Orphaned legacy classes `.spend-name` and `.spend-val` ([admin.css:39](file:///Users/ali/Works/roadmap-board/web/css/admin.css#L39)) persist in CSS despite tokens view migrating to `.row-grid.tk-spend`.
[shell.css:40](file:///Users/ali/Works/roadmap-board/web/css/shell.css#L40): Page-level horizontal scroll containment relies on `.main { overflow-x: hidden; }` clipping instead of responsive layout adaptation.
[admin.css:19](file:///Users/ali/Works/roadmap-board/web/css/admin.css#L19): `.rule-input` sets `width: 100%`, which inside inline container `.lim-share-ctl` ([limits.js:131](file:///Users/ali/Works/roadmap-board/web/js/views/limits.js#L131)) beside a `<select>` risks horizontal overflow at 375px.
[flow.css:8](file:///Users/ali/Works/roadmap-board/web/css/flow.css#L8): `.ov-card` padding (16px) combined with `.main` padding (16px at [shell.css:76](file:///Users/ali/Works/roadmap-board/web/css/shell.css#L76)) constrains available content width to 311px on 375px viewports.
[components.css:93](file:///Users/ali/Works/roadmap-board/web/css/components.css#L93): Nested `.band.is-compact` inside `.ov-card` adds another 16px horizontal padding, constricting the manual usage form to 279px at 375px.
[tokens.js:47](file:///Users/ali/Works/roadmap-board/web/js/views/tokens.js#L47): Non-wrapping `fmtResets` string in `.rg-num` (~208px-260px) risks overflowing narrow card containers when displayed alongside titles on small viewports.
[components.css:473](file:///Users/ali/Works/roadmap-board/web/css/components.css#L473): Desktop `--rg` reserves a 6.5rem fixed action track (track 5), but `.tk-spend` rows ([tokens.js:39-48](file:///Users/ali/Works/roadmap-board/web/js/views/tokens.js#L39-L48)) emit no action elements, leaving an empty phantom action column.
[tokens.js:28](file:///Users/ali/Works/roadmap-board/web/js/views/tokens.js#L28): The 1-hour override action button is rendered in an unstructured paragraph `.ov-actions` rather than aligned in a fixed action column.
[tokens.js:84](file:///Users/ali/Works/roadmap-board/web/js/views/tokens.js#L84): Spend card provides a section-level copy button in `.lim-bar` instead of row-level copy actions in the grid's `var(--ref-col)` track.
[limits.js:87](file:///Users/ali/Works/roadmap-board/web/js/views/limits.js#L87): In `weeklyStopHtml`, the toggle switch button is placed in column 1 (first child) rather than in a fixed trailing action column.
[components.css:791](file:///Users/ali/Works/roadmap-board/web/css/components.css#L791): `.row-grid > .btn` sets `width: 100%` and `justify-self: end`, forcing buttons in `.row-grid` (like the weekly toggle) to stretch across their entire column track.

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
  ?? docs/reviews/agy-375-overview.md
  ?? docs/reviews/agy-375-roadmap.prompt.txt
  ?? docs/reviews/agy-375-workflow.md
  ?? docs/reviews/agy-375-workflow.prompt.txt
  ?? docs/reviews/agy-testgaps.prompt.txt
  ?? tests/unit/test_sync_revision.py
  ?? tests/web/test_dom_patch_focus.py
  ?? tests/web/test_sync_client.py
ACTION FOR THE CALLING AGENT: inspect these changes (`git diff`) before trusting this staffer. Rollback: `git checkout -- <path>` for tracked files, delete the new untracked ones.
