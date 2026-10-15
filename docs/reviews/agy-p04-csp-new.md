| file:line | pattern | risk | fix |
| --- | --- | --- | --- |
| web/js/views/workflow.js:639 | unescaped value in HTML attribute (`data-wf-map-op="' + op + '"`) | low: parameter `op` is interpolated into attribute string without `esc()`; callers currently pass string literals ("out", "in", etc.) | wrap with `esc(op)` |
| web/js/views/workflow.js:440 | unescaped value in SVG class attribute (`class="wf-bar wf-b-' + it.status + ..."`) | low: status string interpolated into class attribute without `esc()`; constrained by `statusOf()` | wrap with `esc(it.status)` |
| web/js/views/workflow.js:442 | unescaped value in SVG data attribute (`data-lane="' + g.lane + '"`) | none: numeric lane index interpolated into attribute without `esc()` | wrap with `esc(String(g.lane))` |
| web/js/views/workflow.js:443 | unescaped values in SVG data attributes (`data-x="' + g.x0 + '" data-y="' + g.cy + '"`) | none: numeric coordinates interpolated into attributes without `esc()` | wrap with `esc(String(g.x0))` and `esc(String(g.cy))` |
| web/js/views/workflow.js:439 | unescaped values in SVG rect attributes (`x="' + (g.x1 - 3) + '" y="' + y + '"`) | none: calculated numeric coordinates in SVG geometry attributes | keep as validated numbers or wrap with `esc()` |
| web/js/views/workflow.js:443 | unescaped values in SVG rect attributes (`x="' + g.x0 + '" y="' + y + '" width="' + w + '"`) | none: calculated numeric coordinates in SVG geometry attributes | keep as validated numbers or wrap with `esc()` |
| web/js/views/workflow.js:475 | unescaped values in SVG rect attributes (`class="wf-lane..." y="' + i * LANE_H + '"`) | none: integer index and constant LANE_H produce clean numbers | keep as validated numbers |
| web/js/views/workflow.js:479 | unescaped values in SVG line attributes (`x1="' + X(t) + '" y2="' + H + '"`) | none: numeric coordinates from layout scales | keep as validated numbers |
| web/js/views/workflow.js:483 | unescaped values in SVG text attributes (`x="' + x + '" y="' + (AXIS_H - 8) + '"`) | none: numeric coordinates for axis ticks | keep as validated numbers |
| web/js/views/workflow.js:493 | unescaped values in SVG path attribute (`d="M ' + sx + " " + p.cy + ..."`) | none: numeric coordinates in SVG path descriptor | keep as validated numbers |
| web/js/views/workflow.js:500 | unescaped values in SVG path attribute (`d="M ' + b.x0 + " " + b.cy + ..."`) | none: numeric coordinates in SVG path descriptor | keep as validated numbers |
| web/js/views/workflow.js:507 | unescaped value in SVG class attribute (`class="wf-mark wf-m-' + m.status + '"`) | low: status string interpolated into class attribute without `esc()`; constrained to doing/done/blocked | wrap with `esc(m.status)` |
| web/js/views/workflow.js:509 | unescaped values in SVG path attribute (`d="M ' + x + " " + (cy - 6) + ..."`) | none: numeric coordinates in SVG path descriptor | keep as validated numbers |
| web/js/views/workflow.js:513 | unescaped values in SVG root attributes (`width="' + PLOT_W + '" height="' + H + '"`) | none: constant PLOT_W and calculated integer height | keep as validated numbers |
| web/js/views/workflow.js:515 | unescaped values in SVG line attributes (`x1="' + xNow + '" y2="' + H + '"`) | none: numeric timestamp coordinate and height | keep as validated numbers |
| web/js/views/workflow.js:516 | unescaped values in SVG axis attributes (`width="' + PLOT_W + '" height="' + AXIS_H + '"`) | none: constant PLOT_W and AXIS_H dimensions | keep as validated numbers |
| web/js/views/workflow.js:518 | unescaped value in SVG text attribute (`x="' + xNow + '"`) | none: numeric coordinate for now text | keep as validated numbers |
| web/js/views/workflow.js:919 | unescaped value in SVG class attribute (`class="' + cls + '"`) | low: parameter `cls` interpolated into class attribute without `esc()`; callers pass static class literals | wrap with `esc(cls)` |
| web/js/views/workflow.js:1049 | DOM update via `setHtml(detail, ...)` from `../dom.js` | none: delegates DOM write to approved `dom.js` helper; no direct innerHTML or insertAdjacentHTML | compliant with architecture; no change needed |
| web/js/views/tasks.js:75 | unescaped value in HTML class attribute (`class="' + cls + '"`) | none: `cls` composed from static status class tokens | wrap with `esc(cls)` |
| web/js/views/tasks.js:100 | unescaped value in HTML class attribute (`class="task-row ' + cls + '"`) | none: `cls` composed from static class tokens | wrap with `esc(cls)` |
| web/js/views/details.js:129 | unescaped boolean expression in HTML attribute (`aria-pressed="' + (state === s[0]) + '"`) | none: evaluates to boolean "true" or "false" string | safe; optional explicit ternary for clarity |
| web/js/views/details.js:227 | unescaped boolean expression in HTML attribute (`data-done="' + (done === true) + '"`) | none: evaluates to boolean "true" or "false" string | safe; optional explicit ternary for clarity |
| web/js/ref.js:99 | HTML attribute escaping verified (`data-ref="' + esc(ref) + '" data-sum="' + esc(...) + '"`) | none: all attributes properly sanitized via `esc()` | compliant; no change needed |
| web/js/log.js:376 | event listener audit: `window.addEventListener("error", onError)` | none: uses standard DOM `addEventListener`; no inline on* handlers or eval | compliant; no change needed |
| web/js/graph/render.js:21 | DOM node construction: `document.createElementNS` and `node.setAttribute` | none: pure DOM createElementNS; no inline style attributes, no on* handlers, no innerHTML | compliant; no change needed |
| web/js/graph/minimap.js:15 | DOM node construction: `document.createElementNS` and `node.setAttribute` | none: pure DOM createElementNS; no inline style attributes, no on* handlers, no innerHTML | compliant; no change needed |
