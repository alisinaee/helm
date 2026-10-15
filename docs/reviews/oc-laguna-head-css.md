| file:line | problem | fix |
|-----------|---------|-----|
| web/css/head.css:43 | Duplicate `width:100%` already declared on line 42 | Remove line 43 |
| web/css/head.css:44 | Hardcoded `padding:8px 10px` instead of design system spacer vars | Use `var(--sp-2) var(--sp-3)` |
| web/css/head.css:44 | `vertical-align:top` on cells creates extra vertical space | Use `vertical-align:middle` |
| web/css/head.css:53 | `min-width:150px` forces wide summary column | Reduce to `100px` |
| web/css/head.css:58 | `width:56px;min-width:56px` — redundant identical min-width | Remove `min-width:56px` |
| web/css/head.css:59 | `width:112px;min-width:112px` — redundant identical min-width | Remove `min-width:112px` |
| web/css/head.css:58 | Fixed `width:56px` for age column wastes horizontal space | Use `width:min-content` |
| web/css/head.css:59 | Fixed `width:112px` for when column wastes space | Use `width:min-content` |
| web/css/head.css:61 | Unequal padding `var(--sp-2) var(--sp-3) var(--sp-4)` on detail row | Use uniform `var(--sp-2) var(--sp-3)` |
| web/css/head.css:10 | `grid-template-columns:20px 60px minmax(0,1fr) 32px` — 60px second column may be excessive | Reduce to `40px` |
| web/css/head.css:44 | `background:var(--surface-0)` on `th` is overridden by line 46 (`--surface-2`) — wasted declaration | Remove from `th` selector |
| web/css/head.css:2 | `gap:var(--sp-3)` between screen sections wastes vertical space | Use `var(--sp-2)` |
