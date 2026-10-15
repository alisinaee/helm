# Head List Table Layout Audit

| file:line | problem | css fix |
|---|---|---|
| web/css/head.css:42 | `.hd-tbl` lacks `table-layout: fixed`, causing browser auto-layout to jitter column widths across filter changes | `.hd-tbl { table-layout: fixed; }` |
| web/css/head.css:43 | Duplicate rule `.hd-tbl{width:100%}` immediately follows identical declaration on line 42 | Delete duplicate `.hd-tbl{width:100%}` |
| web/css/head.css:51 | `.hd-n{width:1%}` relies on shrink-to-fit auto sizing, causing column shifts between 1-digit and 4-digit IDs | `.hd-n { width: 4.5rem; min-width: 4.5rem; }` |
| web/css/head.css:52 | `.hd-kind{width:1%}` lacks explicit track width, causing shift between short ("bug") and long ("preference") kinds | `.hd-kind { width: 6rem; min-width: 6rem; }` |
| web/css/head.css:53 | `.hd-sumc{width:100%;min-width:150px}` absorbs remaining width in auto layout, over-compressing other columns | `.hd-sumc { width: auto; min-width: 14rem; }` |
| web/css/head.css:55 | `.hd-stc{width:1%}` shrink-to-fit track fluctuates based on variable status chip text ("needs you", "done ✓") | `.hd-stc { width: 6.5rem; min-width: 6.5rem; }` |
| web/css/head.css:56 | `.hd-bnd{width:1%;white-space:normal}` squeezes bound task chips into awkward multiline wraps | `.hd-bnd { width: 11rem; min-width: 11rem; }` |
| web/js/views/head.js:492 | Dedicated "Acc" table column rendered on line 492 is blank for almost all rows, wasting horizontal column budget | `.hd-acc { display: none; }` |
| web/css/head.css:57 | `.hd-cp{width:1%}` lacks explicit icon track width, risking clipped copy button tap target | `.hd-cp { width: 2.5rem; min-width: 2.5rem; text-align: center; }` |
| web/css/head.css:58 | `.hd-age{width:56px;min-width:56px}` uses rigid pixel width rather than font-relative token units | `.hd-age { width: 3.5rem; min-width: 3.5rem; }` |
| web/css/head.css:59 | `.hd-when{width:112px;min-width:112px}` hardcodes fixed pixel width rather than responsive rem units | `.hd-when { width: 6.5rem; min-width: 6.5rem; }` |
| web/css/head.css:68 | Sticky table column offsets `left:72px` and `left:222px` hardcode fragile pixel sums that break on padding shifts | `.hd-n { left: 0; } .hd-sumc { left: 4.5rem; } .hd-stc { left: calc(4.5rem + 150px); }` |
| web/css/head.css:25 | `.hd-item+.hd-item{border-top:1px solid var(--line)}` matches `<tbody class="hd-item">`, creating double borders with td `border-bottom` | `.hd-tbl .hd-item + .hd-item { border-top: 0; }` |
| web/css/head.css:42 | `.hd-tbl` lacks an outer border/card container, leaving table floating uncontained above the blank area | `.hd-list { border: 1px solid var(--line); border-radius: var(--r-card); }` |
| web/css/head.css:45 | `.hd-tbl .is-open>.hd-row>td{border-bottom:0}` removes border, but open detail row lacks visual accent line | `.hd-detail > td { box-shadow: inset 3px 0 0 var(--focus); }` |
| web/css/head.css:26 | `.hd-panel{display:grid;gap:var(--sp-4)}` stacks all 4 blocks vertically in 1 column across the full 9-column span | `@media (min-width: 1100px) { .hd-panel { grid-template-columns: repeat(2, minmax(0, 1fr)); } }` |
| web/css/head.css:29 | `.hd-text,.hd-reply{max-width:90ch}` caps width at 90ch in a full-width table cell, wasting ~40% width on 1440px screens | `.hd-tbl .hd-text, .hd-tbl .hd-reply { max-width: none; }` |
| web/css/head.css:29 | `.hd-reply` and `.hd-text` lack `max-height` and overflow scrolling, allowing long logs to explode vertical height | `.hd-reply { max-height: 24em; overflow: auto; } .hd-text { max-height: 32em; overflow: auto; }` |
| web/js/views/head.js:407 | Empty `<p class="hd-hist"></p>` rendered when history is empty still consumes space in `.hd-blk` grid gap | `.hd-hist:empty { display: none; }` |
| web/css/head.css:41 | `.hd-list{flex:1 1 auto}` stretches to viewport height, leaving unstyled blank area beneath short tables | `.hd-list { flex: 1 1 auto; background: var(--surface-0); }` |
