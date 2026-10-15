# Job staffer-mv9f9e86-3c8b4927 (staffer, done)

web/css/map.css:51: `.wf-table th` sets `text-align: left` with higher specificity (0,1,1) than `.rg-num` (0,1,0), forcing numeric headers `Start`, `Duration`, `Tokens` to be left-aligned.
web/js/views/workflow.js:521: Timeline gutter header `<span>Jobs</span><span>Tokens</span>` lacks `.wf-gn`/`.wf-gt` or `.rg-num`, leaving header text left-aligned over right-aligned data cells.
web/js/views/workflow.js:857: `tableHtml` renders an HTML `<table>` (`.wf-table`) instead of using the shared `.row-grid` utility required by rule 0 for row lists.
web/css/map.css:50: `.wf-table` uses fixed table styling (`min-width: 42rem`) rather than the shared `.row-grid` tracks and track variable `--rg`.
web/js/views/workflow.js:892: Detail strip job ID (`.wf-id`) is numeric text rendered without tabular-nums / `.rg-num` right alignment.
web/js/views/workflow.js:894: Detail strip numbers in `.wf-cols` lack narrow-screen collapse rules to keep numbers right-aligned on phone viewports.
web/js/views/workflow.js:395: `viewOf` defaults to Table view on phone (< 768px), opening a 42rem wide table on 375px screens.
web/css/map.css:50: `.wf-table` sets `min-width: 42rem` (672px) without phone media query to convert to stacked card rows (UI checklist rule 5).
web/css/map.css:5: `.wf-grid` sets fixed tracks `9rem 960px 8.5rem` (`width: max-content`), forcing wide horizontal scrolling on mobile.
web/js/views/workflow.js:1023: `.wf-detail` is placed outside `.wf-scroll` directly in the page body, risking viewport overflow if children expand past 375px.
web/js/views/workflow.js:893: Task title `<span>` in `detailHtml` lacks `min-width: 0` or text truncation, risking flex overflow at 375px on long text.
web/css/components.css:48: Controls `.seg` navs use `display: inline-flex` without `flex-wrap: wrap`, preventing internal wrap if labels expand at 375px.
web/js/views/workflow.js:871: Table view action cell `<td>` has `text-align: left` rather than fixed-width right alignment or justify-self positioning.
web/js/views/workflow.js:847: `actionHtml` returns bare string `MISSING` (`"—"`) for jobs without tasks instead of a structured fixed-width action cell.
web/js/views/workflow.js:884: "Approve in Roadmap" action button (~140px) overflows the fixed 4.5rem (72px) track 8 in `.wf-cols` `--rg`.
web/js/views/workflow.js:890: Detail strip action falls back to bare string `MISSING` (`"—"`) when task is unapproved/unactionable.
web/css/map.css:48: `--rg` defines 8 tracks in `.wf-cols` but `.row-grid` appends a 9th `var(--ref-col)` track, leaving actions misaligned with copy column.
web/js/views/workflow.js:863: Table header and body omit the standard copy reference button track (`.ref-copy` / `var(--ref-col)`).
web/css/components.css:1038: Mobile rule `.row-grid > .btn` fails to position actions when `detailHtml` outputs raw text `"—"`.

[unrestricted] agy modified the working tree during this staffer run — verify the task asked for it. Delta (`git status --porcelain` entries that appeared or changed during the run):
  ?? docs/reviews/agy-375-roadmap.md
  ?? docs/reviews/agy-testgaps.md
  ?? docs/reviews/agy-testgaps.prompt.txt
  ?? docs/reviews/cursor-sync-root.md
ACTION FOR THE CALLING AGENT: inspect these changes (`git diff`) before trusting this staffer. Rollback: `git checkout -- <path>` for tracked files, delete the new untracked ones.
