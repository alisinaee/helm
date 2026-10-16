# UI/UX tester v2 (2026-10-16)

Live app http://127.0.0.1:8780, project roadmap-board, real data. Widths 1440 and 375. Measured with getBoundingClientRect, scrollWidth/clientWidth and Range text widths. Dark/light not checked in this pass.

Search notes: `ui-ux-pro-max` ux domain ran for: table column alignment, dead space, mobile tables, list readability (hits used below). "dashboard density" returned 0 database matches, so no guidance from it; the checklist rules were used instead.

Rules used: UI-CHECKLIST rule 0 (aligned fixed columns), rule 5 (no horizontal scroll at 375, tables become stacked rows), dead space (block with more than 40% empty text), mobile table labels.

## Sections without data (reported as no data, not as empty findings)

- Work: no Work items (`bin/roadmap work list`).
- Issues: no open issues (`bin/roadmap issue list`).
- Research: no research notes yet (onboarding 3 of 4 done).

## Findings

| # | section | width | rule (checklist / skill) | measured evidence | fix |
|---|---|---|---|---|---|
| 1 | all 14 sections | 375 | rule 5: no horizontal scroll | document scrollWidth 423 > clientWidth 375 on every section. `.top-tools` spans x 24 to 423, so the top-bar buttons (including the panel toggle) are cut off. `.side-tabs` scrollWidth 198 inside a 16 px box. | Let `.top-tools` wrap or scroll inside its own box; keep the top bar within 375 px; fix `.side-tabs` width. |
| 2 | roadmap (phase cards) | 1440 | rule 0: action in the same column on every row | 20 `.rc-move.row-grid` rows; action cell x (relative to card) is 214 px on 16 rows, 300 px on 3 rows, 991 px on 1 row. Card widths are 337, 251 and 1028 px, so the action column moves with the card width. 4 rows misaligned by more than 2 px. | Give cards a fixed grid track or equal widths so the action sits at one offset; do not let single-item cards stretch the action column. |
| 3 | overview (phases) | 1440 | dead space (>40% empty) | 8 `.ph-count.num` cells are 222 px wide and hold 19 to 49 px of text (about 80 to 91% empty). | Narrow the count track to about 56 px; keep it right-aligned. |
| 4 | agents | 1440 | dead space; rule 0 | 13 `.rg-chips.ag-effort` cells are 191 px wide and hold 26 to 42 px of text (78 to 86% empty); 4 cells of 208 px hold 37 px. | Use a fixed effort track of about 72 px. |
| 5 | tokens | 1440 | dead space (>40% empty) | `.rg-t` title cells are 437 px wide and hold 51 and 95 px (78 and 88% empty); one 518 px cell holds 37 px. | Shrink the title track or give the space to the numbers. |
| 6 | tokens | 375 | rule 5: no overflow in cards | `.row-grid.tk-spend` scrollWidth 328 > 311 in a card; `.lim-bar` 321 > 311. | Reduce the card's inner padding or let the spend row wrap at phone width. |
| 7 | agents | 375 | mobile tables: stacked rows keep labels | Header row `.rg-agent.rg-head` collapses to 9 cells of 0 px width, so stacked rows show no field labels. | Show a label per field on the stacked row (or keep a visible header at phone width). |
| 8 | agents | 375 | dead space | Same effort cells as #4 at phone width: 14 cells, 26 to 42 px of text in a 191 px box. | Covered by the fix for #4 (check at 375 after the change). |
| 9 | workflow | 375 | rule 5 / overflow | 2 SVG icons clipped: 93 px in 64 px box, 66 px in 58 px box. | Give the SVG its own size or let it scroll inside the box. |

## Measured misalignments

- Rule-0 column misalignment: 4 rows (roadmap phase cards, finding #2). All other row groups (inbox, overview lists, activity, rules, roadmap lane headers, phase badges) were aligned within 2 px.
- Dead-space blocks: 8 overview, 4 agents at 1440, 13 agents at 1440 plus 14 at 375, 5 tokens at 1440 (findings #3 to #5, #8).

## Top 3 by severity

1. #1 horizontal overflow at 375 on every section (top bar cut off).
2. #2 roadmap action column moves across phase cards (rule 0, top priority).
3. #4 agents effort column wastes 78 to 86% of its width.
