# CSP Review: Inline Style, Inline Event Handlers, and innerHTML

| file:line | pattern | fix |
|---|---|---|
| [web/js/dom.js:42](../../web/js/dom.js#L42) | `innerHTML` assignment (`el.innerHTML = html`) in `patch()` | Use Trusted Types policy, `DOMParser`, or template elements with DOM manipulation APIs |
| [web/js/dom.js:59](../../web/js/dom.js#L59) | `innerHTML` assignment (`el.innerHTML = html`) in `setHtml()` | Use Trusted Types policy, `Element.replaceChildren()`, or DOM construction APIs |
| [web/js/dom.js:28](../../web/js/dom.js#L28) | CSSOM inline style modification (`el.style.width = ...`) | Use CSS custom property (e.g. `el.style.setProperty('--pct', ...)`) or discrete utility classes |
| [web/js/views/workflow.js:913](../../web/js/views/workflow.js#L913) | Indirect `innerHTML` write via `setHtml(detail, detailHtml(...))` | Refactor `detailHtml()` to construct DOM elements via `document.createElement` and `replaceChildren` |
| [web/js/app.js:208](../../web/js/app.js#L208) | Indirect `innerHTML` write via `patch(entry[0], entry[1]())` | Refactor view renderers to return DOM elements/fragments or enforce TrustedHTML |
| [web/js/app.js:213](../../web/js/app.js#L213) | Indirect `innerHTML` write via `patch()` on error banner | Construct error banner using safe DOM APIs (`document.createElement`, `textContent`) |
| [web/js/app.js:481](../../web/js/app.js#L481) | Indirect `innerHTML` write via `patch("toasts", toastsHtml())` | Construct toast elements using DOM APIs (`document.createElement`, `textContent`) |

## Audited Files Summary

- [web/index.html](../../web/index.html) (55 lines): 0 inline styles, 0 inline event handlers, 0 innerHTML uses. Clean.
- [web/js/routes.js](../../web/js/routes.js) (40 lines): 0 inline styles, 0 inline event handlers, 0 innerHTML uses. Clean.
- [web/js/views/planner.js](../../web/js/views/planner.js) (493 lines): 0 inline styles, 0 inline event handlers, 0 innerHTML uses (uses `textContent` at L468). Clean.
- [web/js/dom.js](../../web/js/dom.js) (114 lines): 2 `innerHTML` sinks (L42, L59), 1 CSSOM style mutation (L28). 0 inline event handlers.
- [web/js/views/workflow.js](../../web/js/views/workflow.js) (1015 lines): 1 indirect `innerHTML` caller via `setHtml` (L913). 0 inline styles, 0 inline event handlers.
- [web/js/app.js](../../web/js/app.js) (505 lines): 3 indirect `innerHTML` callers via `patch` (L208, L213, L481). 0 inline styles, 0 inline event handlers.

## UI Rule Compliance

- UI Rule 0: Numbers and actions align in fixed grid columns (verified in [workflow.js:739-755](../../web/js/views/workflow.js#L739-L755) and [planner.js:181-202](../../web/js/views/planner.js#L181-L202) using `.row-grid` and `.rg-num`).
