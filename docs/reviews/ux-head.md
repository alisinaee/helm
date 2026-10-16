# R10.2 Head UX review (list view)

Screenshots: `build/ui-smoke/alpha-head-*.png` (1440 light, 1024 and 768 and 500 dark). Rules: `docs/UI-CHECKLIST.md`
(rule 0 row alignment, rule 1 contrast and focus, rule 5 no page scroll at 375/768/1024/1440, rule 10 tables).
UX search: "data table density", "truncation tooltip", "dark mode contrast", "responsive table mobile".

| # | issue | screenshot | rule source | fix | P | after |
|---|-------|------------|-------------|-----|---|-------|
| 1 | "You wrote" shows the triage summary, not the person's words | 1440 light | truncation tooltip (show the real content, full text on hover) | main cell = first 120 chars of the verbatim text (service previews_of); summary as a muted second line only when it differs; full text in title | P1 | real words in the row |
| 2 | "Head replied" says "Open to load" on every row | 1440 light | data table density (no empty placeholder columns) | rows endpoint sends replyPreview (first 100 chars) with the paged rows, same-origin page only; snapshot rows take it from their paged twin | P1 | reply preview or "No reply yet"; dash while the page loads |
| 3 | table wider than the list at 1440 with the side panel open: Added, Acc and Copy clipped | 1440 light | rule 0 fixed columns; responsive table mobile | Added column hidden below 1600 px (age keeps the date in its title; the open row shows "Added"); reply and text minimums reduced | P1 | every column visible at 1440 |
| 4 | status and kind chips change width row to row | 1440 light | rule 0 fixed columns | chips in State and the first Kind chip get min-width 76 px, centred | P2 | chips line up in one column |
| 5 | filter labels (Search, Kind, Session, Order) touch their controls | 1440 light | rule 8 forms: visible labels with spacing | label is an inline flex row with a gap | P2 | labels spaced from controls |
| 6 | at 500 px the reply column is off screen | 500 dark | responsive table mobile | below 600 px the reply is a muted line under "You wrote"; the reply column is hidden | P2 | reply visible on the phone width |
| 7 | at 768 px Acc and Copy sit off to the right of an in-table scroll | 768 dark | rule 5 (no page scroll); data table density | left as an in-table scroll: the page does not scroll, # stays sticky; wider fit would need a card layout | P3 | not changed |
| 8 | pager reads "Showing 7 of ..." and phone reply shows a dash in the 500 px capture | 500 dark | rule 5 reserve space | capture timing: the paged rows had not arrived inside the headless virtual-time budget; code path checked by tests | P3 | not a layout fault |
| 9 | muted text (--text-3) on the table background | all | dark mode contrast (4.5:1 text) | tools/contrast.py reports ok; tokens file is outside this pass | P3 | not changed |

Checks: tests/unit/test_head_previews.py (service previews, same-origin vs cross-origin route), tests/web/test_head_view.py
(column and CSS pins updated for the new widths), tests/web/test_head_*.py, lint_js, contrast.py. CSS stays under
HEAD_CSS_MAX (7168 bytes).
