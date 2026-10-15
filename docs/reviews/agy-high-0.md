| file:line | problem | fix |
|---|---|---|
| web/js/views/head.js:482 | List row button omits carried indicator (row.carried), unlike card view (web/js/views/head.js:370,377) | Render carried icon alongside eid when row.carried is true |
| web/js/views/head.js:494 | Detail row <tr class="hd-detail"> lacks hidden attribute when closed (!open), leaving empty table row laid out | Add hidden attribute when closed: <tr class="hd-detail"' + (open ? "" : " hidden") + '> |
| web/js/views/head.js:380 | Copy button hd-copy is placed before hd-meta in rowHtml, violating UI rule 0 right-edge placement | Move hd-copy after hd-meta so copy button stays at the right edge |
| web/js/views/head.js:466 | LIST_COLS classes for Age and Added omit rg-num, misaligning header labels with right-aligned numeric cells | Include rg-num in LIST_COLS for Age (hd-age rg-num) and Added (hd-when rg-num) |
| web/js/views/head.js:603 | loadText updates sumEl.textContent with expanded summary but leaves sumEl title attribute stale | Update sumEl title attribute with summaryText alongside textContent |
| web/js/views/head.js:339 | boundBlockHtml omits title attribute on unlinked ref span, unlike linked branch (line 338) and boundHtml (line 244) | Add title attribute title="' + esc(link.ref) + '" to unlinked chip span |
| web/js/views/head.js:303 | sortRows sorts ascending and reverses array for default new order, inverting relative order of tied rows | Sort directly descending with (when(b) - when(a)) || (num(b) - num(a)) for new sort |
| web/js/views/head.js:297 | when helper treats missing or invalid row.ts as timestamp 0, sorting undated rows as oldest when sorting old | Place undated rows at end of sort order or explicitly handle null timestamp in comparator |
| web/js/views/head.js:215 | refHref returns unscoped #head?id=... ignoring pid for ask refs, breaking links opened outside click interception | Scope ask hash with pid when pid is provided: scopedHash(hashOf({ id: id }), pid) |
| web/js/views/head.js:8 | Verification of all escape paths: user and snapshot data interpolate via esc() and loadText uses textContent | No unescaped injection sinks found; maintain esc() on all HTML interpolations |
