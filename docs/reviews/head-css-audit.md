| file:line | problem | fix |
|-----------|---------|-----|
| head.css:10 | Grid template columns use fixed px widths (20px, 60px, 32px) that don't scale with content | Use minmax() or auto for ID/kind columns; let content dictate width |
| head.css:11 | Row padding `var(--sp-2)` (likely 8px) on all sides; combined with cell padding creates double spacing | Consolidate padding to either `.hd-row` OR `.hd-tbl td`, not both |
| head.css:25 | `.hd-item+.hd-item` adds top border on every row, but `.hd-tbl td` already has `border-bottom` (line 44) | Remove one: keep `border-bottom` on `td` or `border-top` on `.hd-item`, not both |
| head.css:44 | Cell padding `8px 10px` + row padding `var(--sp-2)` = ~16px vertical, 20px horizontal per cell | Pick one padding layer; recommend cell padding only, remove row padding |
| head.css:45 | `.is-open>.hd-row>td` removes bottom border but `.hd-detail>td` (line 61) adds its own border-bottom | Keep detail row border; remove line 45 override to avoid inconsistency |
| head.css:46 | Sticky `th` uses `var(--surface-2)` but even rows use `var(--surface-1)` (line 47) — header may blend on scroll | Ensure header background contrasts with both surface-0 and surface-1 |
| head.css:47 | `tbody:nth-of-type(even)` zebra striping applies to all rows including `.is-open` detail rows | Exclude detail rows: `tbody:nth-of-type(even) > tr:not(.is-open) > td` |
| head.css:48 | Hover and `.is-open` both set `background:var(--surface-2)` — redundant | Merge into single selector: `.hd-tbl tbody>tr:hover>td, .hd-tbl .is-open>.hd-row>td` (already done) — OK |
| head.css:51-53 | Column widths use `%` and `min-width` mix; `.hd-n` 1% + 72px mobile, `.hd-sumc` 100% + 150px min | Use `grid-template-columns` on table (CSS Grid) or consistent `width:auto` with `min-width` only |
| head.css:58-59 | `.hd-age` 56px, `.hd-when` 112px fixed widths — may truncate or waste space | Use `width:1%; white-space:nowrap` like other narrow cols; let content size naturally |
| head.css:61 | `.hd-detail>td` padding `var(--sp-2) var(--sp-3) var(--sp-4)` differs from main row padding | Align with main cell padding (8px 10px) or define a panel padding variable |
| head.css:64-68 | Mobile: `.hd-n` sticky left:0, `.hd-sumc` left:72px, `.hd-stc` left:222px — hardcoded offsets break if col widths change | Use `position:sticky; left:0` on first col only; let subsequent cols stack naturally |
| head.css:69 | Mobile `.hd-panel` sticky `left:0` width `calc(100vw - 32px)` — assumes viewport padding, may overflow | Use `width:100%; max-width:100vw` with `box-sizing:border-box` |
| head.css:39 | Mobile media query reorders flex items with `order` but `.hd-row.row-grid` becomes flex — loses grid alignment | Keep grid on mobile or use subgrid; flex wrap creates ragged columns |
| head.css:42-43 | Duplicate `.hd-tbl{width:100%}` (lines 42 and 43) | Remove line 43 |