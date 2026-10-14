# Job staffer-mv7pifpy-a4a780c4 (staffer, done)

|file:line|row|problem|class to use|
|web/js/views/tokens.js:104|`<li class="spend-row">`|Numbers and save cap action not in fixed grid columns|`.row-grid`|
|web/css/components.css:594|`.spend-row`|Row with numbers and actions styled with flexbox instead of fixed grid columns|`.row-grid`|
|web/js/views/tree.js:27|`<div class="wk-tree-row">`|Task id number not in fixed grid column|`.row-grid`|
|web/js/views/tree.js:42|`<button class="wk-phase-btn">`|Phase id, task count numbers and toggle action not in fixed grid columns|`.row-grid`|
|web/js/views/tokens.js:149|`<tr>` in `projectTableHtml`|Project token counts and share numbers in table row instead of fixed grid columns|`.row-grid`|
|web/js/views/phases.js:101|`<button class="defer-toggle">`|Deferred count number and toggle action in flex row instead of fixed grid columns|`.row-grid`|
|web/js/views/list.js:163|`<thead><tr>` in `headHtml`|Table header row for numbers and actions does not use fixed grid columns|`.row-grid`|
|web/js/views/list.js:175|`<tr data-wk-task>` in `rowHtml`|Task numbers and selection action in HTML table row instead of fixed grid columns|`.row-grid`|
|web/js/views/list.js:205|`<tr class="wk-group-head">`|Group header with task count number not in fixed grid columns|`.row-grid`|

DONE

[unrestricted] agy modified the working tree during this staffer run — verify the task asked for it. Delta (`git status --porcelain` entries that appeared or changed during the run):
   M web/js/views/workflow.js
  ?? web/css/graph.css
  ?? web/js/graph/render.js
  ?? web/js/graph/viewport.js
ACTION FOR THE CALLING AGENT: inspect these changes (`git diff`) before trusting this staffer. Rollback: `git checkout -- <path>` for tracked files, delete the new untracked ones.
