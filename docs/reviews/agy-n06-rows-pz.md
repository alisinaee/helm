# Review: List Rows Column Alignment (agy-n06-rows-pz)

UI rule: numbers and actions align in fixed grid columns (numbers right-aligned tabular, actions in one fixed column, titles ellipsize).

| file:line | row | problem | class |
|---|---|---|---|
| web/js/views/planner.js:215 | Uncovered feature callout item | Row lacks `row-grid`; action button "Link tasks" is inline after text instead of sitting in a fixed action column; title does not ellipsize in fixed grid track | UNKNOWN |
| web/js/views/planner.js:229 | Orphan task callout item | Row lacks `row-grid`; assign select action is inline after text instead of sitting in a fixed action column; title does not ellipsize in fixed grid track | UNKNOWN |
| web/js/views/planner.js:329 | Project picker item | Row lacks `row-grid`; project button lacks fixed grid columns and title ellipsis | UNKNOWN |
| web/js/views/projects.js:93 | Project row | Row uses flexbox instead of fixed grid columns across head, meter, and badges; project name lacks `rg-t` to ellipsize in fixed column | p-row |
| web/js/views/projects.js:111 | All projects summary row | Row lacks progress meter column present in project rows; badges container (line 114) lacks `row-grid` and fixed slot columns; title lacks `rg-t` ellipsis | p-row p-all |
| web/js/views/recent.js:15 | Progress log row | Row lacks `row-grid`; date number lacks `rg-num` tabular right-alignment; log text lacks `rg-t` ellipsis | log-row |
| web/js/views/research.js:67 | Onboarding checklist row | Row lacks `row-grid`; status chip, title, and hint lack fixed grid columns; titles and hints wrap with `<br>` instead of ellipsizing (`rg-t` missing) | act-row |
| web/js/views/research.js:76 | Research note item | Row lacks `row-grid`; byte size and line count numbers are formatted in inline string instead of right-aligned tabular columns (`rg-num` missing); note title lacks `rg-t` ellipsis | UNKNOWN |
| web/js/views/research.js:118 | Research project link item | Row lacks `row-grid`; project link does not sit in fixed grid columns or ellipsize | UNKNOWN |
| web/js/views/roadmap.js:72 | Task card | Card layout lacks `row-grid`; token count number (`rc-meta .num`) lacks right-aligned tabular column; move action buttons in `rc-move` lack fixed action column; title lacks `rg-t` ellipsis | rc |
| web/js/views/roadmap.js:118 | Phase lane header row | Header row lacks `row-grid`; Approve action and multiple metrics (done/total, est, spent, budget in `lane-stats .num`) lack fixed grid columns and right-aligned tabular figures; phase name lacks `rg-t` ellipsis | lane-head |
| web/js/views/roadmap.js:135 | Timeline phase row | Row lacks `row-grid`; estimate and spent numbers are formatted inside inline text `<p class="tl-text num">` instead of right-aligned tabular columns; phase name lacks `rg-t` ellipsis | tl-row |
| web/js/views/rules.js:47 | Rule row | Row lacks `row-grid`; Delete action button lacks fixed action column; rule text lacks `rg-t` ellipsis; budget numbers are formatted inside inline text instead of right-aligned tabular column (`rg-num`) | rule-row |
| web/js/views/running.js:60 | Finished job row | Title `fin-title` lacks `rg-t` class so it does not ellipsize; `fin-main` combines state, model chip, and title rather than separating them into fixed grid columns | fin-row row-grid |
