| file:line | problem | fix |
|-----------|---------|-----|
| web/css/head.css:42 | `border-collapse:separate;border-spacing:0` redundant; separate with 0 spacing = collapse behavior but with double borders | Use `border-collapse:collapse` to eliminate double borders between cells |
| web/css/head.css:43 | Duplicate `.hd-tbl{width:100%}` already declared on line 42 | Remove line 43 |
| web/css/head.css:44 | `padding:8px 10px` hardcoded; not using design tokens (`--sp-*`) | Replace with `padding:var(--sp-2) var(--sp-3)` or similar token |
| web/css/head.css:44 | `border-bottom:1px solid var(--line)` on every `th,td` creates double borders between rows (top of next + bottom of prev) | With `border-collapse:collapse`, keep only `border-bottom` on `th` or `td`, not both |
| web/css/head.css:45 | `.is-open>.hd-row>td{border-bottom:0}` removes bottom border on open rows but leaves gap from collapsed borders | Remove when using collapse; handle detail row border separately |
| web/css/head.css:47 | Zebra striping `tbody:nth-of-type(even)>tr>td` with separate borders shows half-borders; also `nth-of-type(even)` on tbody is fragile | Move striping to `tr:nth-child(even)>td` and ensure single border with collapse |
| web/css/head.css:53 | `.hd-sumc{width:100%;min-width:150px}` on table cell: `width:100%` ignored in table-layout; min-width may not constrain | Remove `width:100%`; use `min-width:150px` only; set `table-layout:fixed` on `.hd-tbl` |
| web/css/head.css:56 | `.hd-bnd{width:1%;white-space:normal}` contradictory: 1% forces shrink, `white-space:normal` allows wrap | Remove `width:1%` or change to `width:auto`; let content define width |
| web/css/head.css:58-59 | Fixed `width:56px`/`:112px` + `min-width` same value on `.hd-age`/`.hd-when` — inflexible, overflow risk | Use `min-width` only; let column grow; or use `width:1%` with `white-space:nowrap` for auto-size |
| web/css/head.css:61 | `.hd-detail>td{padding:var(--sp-2) var(--sp-3) var(--sp-4);border-bottom:1px solid var(--line)}` — asymmetric padding (bottom larger), border duplicates row border | Use symmetric padding `var(--sp-3)`; with collapse, remove `border-bottom` or make it the sole row separator |
| web/css/head.css:25 | `.hd-item+.hd-item{border-top:1px solid var(--line)}` adjacent sibling border for list layout; unused in table mode (`.hd-tbl`) | Wrap in `@supports not (display: table)` or move to non-table selector to avoid dead CSS |
| web/css/head.css:26 | `.hd-panel{padding:var(--sp-2) var(--sp-2) var(--sp-4) 28px}` magic number `28px` left padding (chevron alignment) | Replace `28px` with `calc(var(--sp-2) + 20px)` or token `--sp-7` for clarity |
| web/css/head.css:10 | `.hd-row.row-grid{grid-template-columns:20px 60px minmax(0,1fr) 32px}` fixed tracks (20/60/32) waste space on narrow viewports | Use `auto`/`min-content` for icon/chevron columns; `minmax(0,1fr)` for summary only |
| web/css/head.css:68 | Mobile sticky columns `.hd-n{left:0}.hd-sumc{left:72px}...` hardcoded offsets; break if column widths change | Compute `left` via CSS variables matching column widths; or use `position:sticky` without `left` on non-first columns |
| web/css/head.css:36 | `.hd-foot{border-top:1px solid var(--line)}` adds border above footer; table already has row borders — visual double line | Remove `border-top` when inside `.hd-tbl`; keep only for card layout |
