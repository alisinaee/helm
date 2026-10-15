# Job staffer-mv9hhvrr-b827065e (staffer, done)

I have launched the test suite to verify current test baselines and will proceed with the audit once it completes.
Waiting for test execution to complete.
web/js/views/agents.js:84: `elapsedText` ignores `job.started` string when `job.startedMs` is null, showing MISSING instead of parsing like line 68; fix: fall back to `Date.parse(job.started)` or `job.elapsedS`.
web/js/views/agents.js:94: `.mt-label` placeholder text uses `var(--fs-12)` (12px), failing body/label text >= 13px (Rule 6); fix: style `.mt-label` with `font-size: var(--fs-13)` and `color: var(--text-2)`.
web/js/views/agents.js:103: Stop button has `data-focus`, but on job completion child 7 becomes an empty `<span></span>`, dropping focus to `<body>` on redraw; fix: provide a fallback focus target on the row.
web/js/views/agents.js:104: Disabled Stop button (`job.task ? "" : " disabled"`) lacks `aria-disabled="true"` and an explanation; fix: add `title="Job has no task assigned"` and `aria-disabled="true"`.
web/js/views/agents.js:107: Running jobs show no status chip or live pulse indicator, unlike finished rows and other views; fix: add a status badge (`chipHtml("running", "success")`) or `<span class="rdot"></span>`.
web/js/views/agents.js:130: Task link in `finishedHtml` lacks `aria-label="' + esc("Task " + job.task) + '"`, inconsistent with line 92; fix: add `aria-label="' + esc("Task " + job.task) + '"` to the link.
web/js/views/agents.js:130: Finished rows with no task render empty `""` leaving a blank cell, inconsistent with line 94; fix: render `<span class="mt-label">No task assigned</span>` when `!job.task`.
web/js/views/agents.js:138: Empty placeholder `<span></span>` in finished rows creates an unneeded blank 5th grid row on phone; fix: add `display: none` for empty child 7 in `@media (max-width: 639px)`.
web/js/views/agents.js:147: Project group header uses `h3.grp-h` colliding with child section `h3.ov-h`, and running jobs lack a visible heading; fix: promote project name to `<h2>` and add an `<h3>` for running agents.
web/js/views/agents.js:148: Header `head` is rendered as an `<li>` inside `<ul>`/`<ol>`, causing screen readers to announce it as list item #1; fix: move `head` outside the list or add ARIA table/row/columnheader roles.
web/js/views/agents.js:157: Running agents empty state `emptyHtml("No agents running.")` provides no action (Rule 10); fix: pass an action parameter, e.g. `<a href="#/p/' + esc(entry.id) + '/work">View tasks</a>`.
web/js/views/agents.js:163: Finished jobs empty state uses raw `<p class="ov-sum">` without an action instead of `emptyHtml()` (Rule 10); fix: replace with `emptyHtml("No finished jobs yet.", ...)`.
web/js/views/agents.js:164: `<section class="ov-card" aria-label="Agents">` duplicates identical landmark names in All Projects; fix: set `aria-label="' + esc(showName ? "Agents - " + entry.name : "Agents") + '"`.
web/js/views/agents.js:187: `run("task.stop", ...)` passes no `key`/`value`/`apply` for optimistic updates (Rule 2); fix: pass optimistic state options to `run()` and disable the button immediately on click.
web/css/flow.css:12: `.grp-h` sets `font-size: var(--fs-12)` (12px), which is smaller than child heading `.ov-h` (13px) and body text minimum; fix: change to `font-size: var(--fs-13)` or `var(--fs-15)`.
web/css/flow.css:49: Nested worker indent `padding-left: var(--sp-3)` causes horizontal overflow/clipping within `.main` at 768px (Rule 5); fix: clamp worker indentation or adjust `--rg` tracks at 768px.
web/css/flow.css:56: Phone media query is `@media (max-width: 599px)`, but `components.css:827` triggers at 639px, leaving a 600–639px gap with small touch targets; fix: update to `@media (max-width: 639px)`.
web/css/flow.css:56: On phone, `.ag-row .btn` sets `min-height: 44px` but omits `min-width: 44px` while `components.css:821` sets `min-width: 0`; fix: add `min-width: 44px` to `.ag-row .btn`.
web/css/flow.css:56: `.ag-row .ref-copy` is omitted from mobile touch target rules and remains 24x24px; fix: add `.ag-row .ref-copy { min-height: 44px; min-width: 44px; }` to the mobile media query.
web/css/components.css:835: Action button on mobile sets `justify-self: start; width: auto`, violating Rule 0 requiring actions to stay right-aligned; fix: change to `justify-self: end`.

[unrestricted] agy modified the working tree during this staffer run — verify the task asked for it. Delta (`git status --porcelain` entries that appeared or changed during the run):
   M docs/head-gate.json
   M roadmap/commands/status.py
   M tests/web/test_head_view.py
   M web/css/components.css
   M web/css/flow.css
   M web/css/work.css
   M web/js/views/list.js
   M web/js/views/overview.js
  ?? docs/reviews/agy-sec-routes.md
  ?? docs/reviews/agy-ux-head.md
  ?? docs/reviews/agy-ux-roadmap.md
  ?? docs/reviews/agy-ux-roadmap.prompt.txt
  ?? docs/reviews/agy-ux-settings.md
  ?? docs/reviews/agy-ux-settings.prompt.txt
  ?? docs/reviews/agy-ux-tokens.md
  ?? docs/reviews/agy-ux-tokens.prompt.txt
  ?? docs/reviews/agy-ux-work.md
  ?? docs/reviews/agy-ux-workflow.md
  ?? docs/reviews/agy-ux-workflow.prompt.txt
  ?? docs/reviews/agy-wave1-verify.prompt.txt
  ?? docs/reviews/agy-wf-sync.prompt.txt
  ?? tests/unit/test_backlog_snapshot.py
  ?? tests/web/test_r756_rows.py
ACTION FOR THE CALLING AGENT: inspect these changes (`git diff`) before trusting this staffer. Rollback: `git checkout -- <path>` for tracked files, delete the new untracked ones.
