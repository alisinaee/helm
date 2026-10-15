| file:line | problem | fix |
|-----------|---------|-----|
| web/js/views/head.js:14,380,493 | `copyButton` from `../ref.js` receives user text (`row.sum`, `id`) — UNKNOWN if it escapes when generating HTML | Verify `copyButton` implementation escapes `sum`/`id` in its output |
| web/js/views/head.js:18,711 | `showToast` from `./toast.js` receives user text — UNKNOWN if it uses `innerHTML` unsafely | Verify `showToast` uses `textContent` or escapes input |
| web/js/views/head.js:17,218,776 | `buildHash` from `../router.js` used in URL context — UNKNOWN if it properly encodes all segments | Verify `buildHash` encodes values for URL safety |
| web/js/views/head.js:596,598,600,603,580 | `loadText` uses `textContent` for user text (text, reply, history, assets, summary) — **correct**, no innerHTML | No fix needed |
| web/js/views/head.js:378,486 | `row.sum` and `shown` (derived from `full.text`) escaped via `esc()` in attributes and content — **correct** | No fix needed |
| web/js/views/head.js:399,403,405,407 | `textNote`, `replyNote`, `stateReason`, `hist` all user text, all passed through `esc()` in `panelHtml` — **correct** | No fix needed |
| web/js/views/head.js:243,244,338,341 | `boundHtml`/`boundBlockHtml` escape `href`, `label`, `link.ref`, `title`, `status`, `j.model` — **correct** | No fix needed |
| web/js/views/head.js:428,433 | `row.dup.id`, `row.dup.score`, `ref` from server escaped in button attributes/content — **correct** | No fix needed |
| web/js/views/head.js:160,125,148 | URL hash params (`opts.q`, `opts.f`, `opts.kind`, `opts.sid`) escaped in HTML attributes — **correct** | No fix needed |
| web/js/views/head.js:90,98,107 | `now.model`, `rest`, `prev`, alert counts escaped in `nowHtml`/`alertsHtml` — **correct** | No fix needed |
