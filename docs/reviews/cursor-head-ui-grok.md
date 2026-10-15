Read-only review of the Head screen. I’ll pull the view, styles, tests, fixture, and the UI rules so the findings stay tied to exact lines.

Line numbers shifted from the first read. I’ll re-check the row, panel, and badge markup before locking the findings.

The Head view changed after the first pass. I’ll pull the current markup in chunks so the line cites match the file on disk.

The screen is mid-edit. I’ll re-read the live row markup so the review matches what is on disk now.

The Head screen still reads as a spreadsheet with a control strip above it. Kind is missing, dates do not share a column, and the open row is four labelled blocks.

## 1. Fifteen problems

1. **Kind is not on the row.** `rowHtml` prints a chevron, id, summary, copy, then a meta strip of status, bound, age, and date. `row.kind` is never written. `web/js/views/head.js:360-375`. A scan cannot tell ask from bug from rule.

2. **Empty filler on every unbound row.** `boundHtml` returns the words "Not bound yet" when `links` is empty (`web/js/views/head.js:227`), and the row always mounts that cell (`:371`). The open panel repeats it as "Not bound yet. Use Bind below." (`:340`). On the demo fixture that is H4 and H5.

3. **Age is a blank cell for almost every row.** `ageText` returns `""` when `age` is not a number (`:186-187`). The fold only sets age for `new` and `understood` (`roadmap/core/head.py:228`). The cell is still emitted (`head.js:372-373`). In the open filter, only H4 has an age. The other rows keep an empty span in the meta line.

4. **The date is not a fixed column, so rule 0 fails.** The grid is only `20px 60px minmax(0,1fr) 32px` (`web/css/head.css:9`). Age and Added live in `.hd-meta`, which is a wrapping flex row (`head.css:19`, `head.js:369-374`). `text-align:right` on `.hd-when` (`head.css:21`) aligns text inside that flex item. It does not line the dates up from row to row. Bound chips change the date's position.

5. **The summary is still cramped.** `.hd-c` forces `white-space:nowrap` and ellipsis (`head.css:15`). The summary override clamps to **3** lines at `line-height:1.4` (`head.css:18`), on the 13px body. `SUM_SHOW` is 240 (`head.js:34`), so a long fallback is stuffed into that clamp. Checklist body size is 13px and line-height about 1.5. Three tight lines under a meta strip is not a readable 1–2 line ask.

6. **The filter bar is a raw control strip, and the selected tab has no style.** `barHtml` (`head.js:158-169`) puts Search (placeholder `/ search`), Kind, Session, Order, `+ Log`, and six `<a class="hd-filter">` links in one flex row. `aria-current="page"` is set (`:124`). `head.css` has no `.hd-filter` rule and no `[aria-current]` rule. Labels use `.hd-lbl` at 12px (`head.css:33`).

7. **Attention is duplicated, and the default list hides the unhandled ask.** `alertsHtml` (`head.js:104-118`) adds "N unhandled / Show", "N needs you / Show", and "N done, not accepted / Review" above those same six links. Default filter is `open` (`:51`, `:122`, `:158`, `:701`, `:747`). Default order is newest first (`sortRows` `:293`, `sectionView` `:751`). The render test locks the first row as H6. H4, the only unhandled ask, is not first.

8. **Rules, not spacing.** Item separators are `border-top:1px solid var(--line)` (`head.css:24`). The footer repeats that rule (`:35`). The badge is `border:1px solid var(--success)` plus a dot (`:4-6`). Attachments are another `border:1px solid var(--line)` (`:31`). `--line` is the strong token. Work rows use `--track`.

9. **Secondary text is 12px.** `.hd-now-rest` (`head.css:7`), `.hd-none,.hd-reason,.hd-job` (`:23`), `.hd-asset` (`:31`), and `.hd-added,.hd-hist,.hd-lbl` (`:33`) all set `--fs-12`. Chips stay `--fs-11` from `web/css/components.css:252`. The header utility `.rg-head` is also 11px (`components.css:795-797`). Checklist item 6: body at least 13px.

10. **375px is a wrapped table, not cards.** The media query (`head.css:38`) sets `display:flex; flex-wrap:wrap` and reorders the same cells. No `background`, no `border`, no `border-radius`, no gap between cards. The file comment on line 1 says "phone cards". The query does not build one. Copy is pushed with `margin-left:auto` inside the wrap, so it does not sit in a stable action column.

11. **Hit targets are under 44px.** The last grid track is `32px` (`head.css:9`). `.ref-copy` is `var(--ref-col)` which is `1.5rem` (`tokens.css:2`) and `opacity:.4` until hover (`components.css:800-801`). That is a hover-only action. Filter links are plain `<a>`s, so they miss even the 32px phone minimum `base.css` gives `button`, `select`, and `a.btn` (`base.css:76-80`). `--h-row` is 32px (`tokens.css:43`). Checklist item 2 wants 44px on a phone.

12. **The opened row is four forms, not the message.** `panelHtml` always builds "You wrote", "Head replied", "State", and "Bound to" (`head.js:387-395`, `:339`). With no reply, the second block says "No reply captured yet" (`:306`). History is an empty `<p class="hd-hist">` when there is no history (`:395`). The footer then dumps Confirm, Reopen, Needs you, Decline, merge, bind suggestions, and Bind/Split/Merge (`:396-431`) under another rule (`head.css:35`).

13. **The head badge is buried, and it is drawn as a bordered pill.** Screen order is title, Expand all, then the badge section, then alerts, then the bar, then the list (`head.js:475-483`). The badge text is `Head: Opus 5.5` inside `<strong class="hd-badge">` (`:90-91`), styled with a border and a generated dot (`head.css:4-6`). Unclaimed state puts the whole command `run roadmap head claim` inside that pill (`head.js:91`). The 12px usage line sits beside it (`head.css:7`).

14. **Empty and loading are unstyled sentences.** No rows use `<div class="hd-empty">` (`head.js:455`). `head.css` has no `.hd-empty` rule, so the shared `.empty` / `.empty-title` block (`components.css:335-347`) is not used. Expanded text sets `data-state="loading"` (`head.js:388`) and the string "Loading the text…" (`:298`). No rule styles `[data-state=loading]`. There is no `aria-busy`.

15. **Glyphs stand in for meaning.** Status word for done is `done ✓` (`head.js:24`). Carried is `↺` (`:358`). The row affordance is a `▸` cell (`:364`). Checklist item 7: the sprite, not glyphs. The check and the arrow are also extra noise in an already full meta line.

## 2. Redesign

Replace the whole of `web/css/head.css`. Do not keep the current rules. From `web/js/views/head.js`, delete the alert nav, the Order `<select>`, the age cell, the "Not bound yet" strings, the four block headings, and the empty reply/history nodes. Keep `esc`, the head ops, Expand all, the hit button, hash keys `f`, `q`, `kind`, `sid`, `id`, and `sort` (so an old `#head?sort=old` link still parses). Stop using `sort` to order rows.

### Screen order

1. Title row: `Head`, model chip, usage text, previous head on a second quiet line, Expand all and `+ Log` on the right.
2. Filter tabs with counts. Unhandled is first and is the default. Search sits on the same row.
3. A closed `<details>` labelled Narrow, holding Kind and Session only.
4. The list, or one empty state.

No alert nav. No Order control.

### DOM

```html
<section class="hd-screen" data-project="alpha" aria-labelledby="hd-h">
  <header class="hd-top">
    <div class="hd-idline">
      <h2 id="hd-h" class="hd-title">Head</h2>
      <p class="hd-now">
        <strong class="chip chip-success hd-badge">Head · Opus 5.5</strong>
        <span class="hd-now-rest">acct B · since 09:02 (1h) · 5h 41% · week 63%</span>
      </p>
    </div>
    <div class="hd-top-acts">
      <button type="button" class="btn hd-all" data-action="head-expand-all">Expand all</button>
      <button type="button" class="btn hd-log" data-action="head-log">+ Log</button>
    </div>
  </header>
  <p class="page-note">prev: Opus 5.5 acct A until 08:55</p>

  <div class="hd-tools" data-f="unhandled">
    <nav class="hd-tabs" aria-label="Filter">
      <a class="hd-tab" href="#head?f=unhandled" aria-current="page">Unhandled <span class="hd-count">1</span></a>
      <a class="hd-tab" href="#head?f=needs">Needs you <span class="hd-count">1</span></a>
      <a class="hd-tab" href="#head?f=doing">Doing <span class="hd-count">2</span></a>
      <a class="hd-tab" href="#head?f=open">Open <span class="hd-count">5</span></a>
      <a class="hd-tab" href="#head?f=done" title="1 not accepted">Done <span class="hd-count hd-count-warn">2</span></a>
      <a class="hd-tab" href="#head?f=all">All <span class="hd-count">7</span></a>
    </nav>
    <label class="hd-search">
      <span class="sr-only">Search asks</span>
      <input type="search" data-field="q" placeholder="Search asks" aria-label="Search asks">
    </label>
    <details class="hd-narrow">
      <summary>Narrow</summary>
      <div class="hd-narrow-row">
        <label class="hd-sel"><span>Kind</span><select data-field="kind"></select></label>
        <label class="hd-sel"><span>Session</span><select data-field="sid"></select></label>
      </div>
    </details>
  </div>

  <div class="hd-list">
    <div class="row-grid hd-row hd-head rg-head" aria-hidden="true">
      <span class="hd-c">Kind</span>
      <span class="hd-c">Ask</span>
      <span class="hd-c">Status</span>
      <span class="hd-c hd-when">Added</span>
      <span class="hd-c">Acc</span>
      <span class="hd-c">Ref</span>
    </div>
    <ul class="hd-items" aria-label="Logged messages">
      <li class="hd-item">
        <div class="row-grid hd-row" data-id="H4">
          <button type="button" class="hd-hit" data-action="head-toggle" data-id="H4" aria-expanded="false" aria-controls="hd-p-H4" aria-label="Show H4 ask. Make the Head grid match rule 0"></button>
          <span class="hd-c hd-kind">
            <span class="hd-id"><span class="hd-chev" aria-hidden="true">▸</span>H4</span>
            <span class="chip chip-neutral">ask</span>
          </span>
          <span class="hd-c hd-sum" data-sum="Make the Head grid match rule 0" title="Make the Head grid match rule 0">
            <span class="hd-sum-text">Make the Head grid match rule 0</span>
          </span>
          <span class="hd-c hd-status"><span class="chip chip-neutral">new</span></span>
          <span class="hd-c hd-when rg-num hd-amber" title="Waiting. 2026-10-15T09:20:00Z">15 Oct 12:50</span>
          <span class="hd-c hd-acc-cell"></span>
          <span class="hd-c hd-copy"><!-- existing copyButton --></span>
        </div>
        <div class="hd-panel" id="hd-p-H4" hidden>
          <pre class="hd-text" data-state="loading" aria-busy="true">Loading the text…</pre>
          <p class="hd-meta"><span class="hd-reason">Not triaged yet</span> · <span class="hd-added" title="ISO">Added 15 Oct 2026 12:50</span></p>
          <div class="hd-foot"><div class="hd-acts"><!-- Needs you, Decline --></div>
            <details class="hd-more"><summary class="btn">More</summary><div class="hd-acts"><!-- Bind..., Split..., Merge... --></div></details>
          </div>
          <!-- existing hidden forms -->
        </div>
      </li>
    </ul>
  </div>
</section>
```

Closed row, six tracks, same tracks on the header:

| Track | Width | Content |
|---|---|---|
| Kind | `6.5rem` | id, caret, kind chip. If `row.carried`, add `<span class="chip chip-neutral">carried</span>`. No `↺`. |
| Ask | `minmax(0,1fr)` | `.hd-sum-text` clamped to 2 lines at 15px / 1.5. If `links.length`, a `.hd-bound` flex of the existing chips under the text. If no links, omit `.hd-bound`. Never print "Not bound yet" here. |
| Status | `7.5rem` | existing status chip. `done` text is `done`, not `done ✓`. Auto-done is `<span class="chip chip-warning" title="Auto-done: waiting for the person">done?</span>`. |
| Added | `8.5rem` | `whenText(row.ts)`, class `hd-c hd-when rg-num`, plus `hd-stale` or `hd-amber` when those flags are set. Title is `Stale. ` or `Waiting. ` plus the ISO string. Empty string when there is no timestamp. No age cell. |
| Acc | `5.5rem` | If `!readOnly && status === "done" && !acc`, button `Accept`, `data-action="head-accept"`. If `acc`, button text `Accepted`, `aria-checked="true"`. Otherwise an empty `<span class="hd-c hd-acc-cell"></span>`. No checkbox glyphs. |
| Ref | `var(--ref-col)` | existing `copyButton`, last track. |

Kind chip tone map, word still on the chip: `bug` → `chip-danger`, `rule` → `chip-defer`, `decision` → `chip-success`, `review` → `chip-warning`, everything else → `chip-neutral`.

Bound chips stay the current `<a class="chip chip-neutral" href="..." title="task:R7.31">`. Put them in `.hd-bound` inside the Ask cell. Do not add a second status chip per task on the closed row.

Open panel, in this order, omit a node when its data is missing:

- `<pre class="hd-text">` full message. `data-state="loading"` and `aria-busy="true"` until `loadText` finishes. Ready: `data-state="ready"`, `aria-busy="false"`. Error: `data-state="error"`.
- `<ul class="hd-assets" data-role="assets">` only when `assets.length`. Each item `<li class="hd-asset">shot.png</li>`.
- `<pre class="hd-reply">` only when `reply` is a non-empty string. Do not print "No reply captured yet" or "Loading the reply…".
- `<p class="hd-meta">` with `<span class="hd-reason">` plus the existing `<span class="hd-added" title="...">Added 15 Oct 2026 12:50</span>`.
- `<p class="hd-hist">` only when `history.length`. H1 still renders `09:12 hook new · 09:13 head triage`.
- `<div class="hd-links">` of bound chips only when `links.length`. No "Bound to" heading.
- `<div class="hd-foot">` then `<div class="hd-acts">` for Confirm done, Reopen, Needs you, Decline, the dup Merge button, and bind-suggestion buttons. Then `<details class="hd-more"><summary class="btn">More</summary><div class="hd-acts">` for Bind…, Split…, Merge…. Forms stay the existing hidden `<form class="hd-form">` siblings. Do not use the class `hd-menu`.

Empty, no rows:

```html
<div class="empty hd-empty">
  <p class="empty-title">Nothing logged yet. Every message you type is logged here.</p>
  <p><button type="button" class="btn" data-action="head-log">+ Log</button></p>
</div>
```

Filter miss, same `.empty` shell, title `Nothing in this view.`, action `<a class="btn" href="#head?f=all">Show all</a>`.

Unclaimed badge: `<strong class="chip hd-badge">Head · not claimed</strong>` and the rest span text `Run roadmap head claim`. No `hd-badge-off` border.

### CSS

Delete every current rule in `web/css/head.css` (the bordered badge and its `::before`, the 12px rest line, the `20px 60px minmax(0,1fr) 32px` grid, `.hd-c` nowrap, the 3-line clamp, `.hd-meta{grid-column:2 / -1}`, the `--line` row and footer borders, the asset border, and the `599px` flex-wrap query). Paste this as the entire file. No comment header, no blank lines. `wc -c web/css/head.css` must stay ≤ 4096 (`HEAD_CSS_MAX`). It is about 3.1 KB. If it is over, delete `.hd-row .ref-copy{opacity:1}` first.

```css
.hd-screen{display:grid;gap:var(--sp-4);min-width:0;width:100%;line-height:1.5}
.hd-top,.hd-idline,.hd-now,.hd-top-acts,.hd-tools,.hd-tabs,.hd-bound,.hd-status,.hd-foot,.hd-acts,.hd-links,.hd-assets{display:flex;flex-wrap:wrap;gap:var(--sp-2);align-items:center}
.hd-top,.hd-tools{justify-content:space-between}
.hd-title{font-size:var(--fs-17)}
.hd-now-rest,.hd-meta,.hd-hist,.hd-reason{margin:0;color:var(--text-2);font-size:var(--fs-13)}
.hd-tab{display:inline-flex;align-items:center;gap:var(--sp-1);min-height:var(--h-control);padding:0 var(--sp-3);border:1px solid var(--track);border-radius:var(--r-control);background:var(--surface-1);color:var(--text-2);text-decoration:none}
.hd-tab[aria-current=page]{background:var(--sel);border-color:var(--accent);color:var(--text-1);font-weight:600}
.hd-count{font-variant-numeric:tabular-nums;color:var(--text-3)}
.hd-tab[aria-current=page] .hd-count{color:var(--text-1)}
.hd-count-warn{color:var(--warning)}
.hd-search{flex:1 1 12rem;min-width:0}
.hd-search input,.hd-sel select,.hd-form input{font:inherit;color:var(--text-1);background:var(--surface-1);border:1px solid var(--track);border-radius:var(--r-control);min-height:var(--h-control);padding:0 var(--sp-2)}
.hd-search input{width:100%}
.hd-narrow{flex-basis:100%}
.hd-narrow summary{cursor:pointer;min-height:var(--h-control)}
.hd-narrow-row{display:flex;flex-wrap:wrap;gap:var(--sp-2);padding-top:var(--sp-2)}
.hd-sel{display:grid;gap:var(--sp-1);min-width:8rem;color:var(--text-2);font-size:var(--fs-13)}
.hd-screen .chip{font-size:var(--fs-13);height:auto;min-height:var(--h-small)}
.hd-row.row-grid{--rg:6.5rem minmax(0,1fr) 7.5rem 8.5rem 5.5rem;position:relative;align-items:start;grid-template-columns:var(--rg) var(--ref-col)}
.hd-head{align-items:center;font-size:var(--fs-13);color:var(--text-3)}
.hd-hit{position:absolute;inset:0;margin:0;padding:0;border:0;background:none;cursor:pointer}
.hd-hit:focus-visible{outline:2px solid var(--focus);outline-offset:-2px}
.hd-row a,.hd-row button:not(.hd-hit){position:relative;z-index:1}
.hd-row .ref-copy{opacity:1}
.hd-c{min-width:0}
.hd-kind{display:grid;gap:var(--sp-1);justify-items:start}
.hd-id{display:inline-flex;gap:var(--sp-1);align-items:center;font-family:var(--font-mono);color:var(--text-3);font-variant-numeric:tabular-nums}
.hd-chev{display:inline-block}
.is-open .hd-chev{transform:rotate(90deg)}
.hd-sum{display:grid;gap:var(--sp-1);white-space:normal}
.hd-sum-text{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;font-size:var(--fs-15);line-height:1.5;color:var(--text-1)}
.hd-when{text-align:right;font-variant-numeric:tabular-nums;color:var(--text-2);white-space:nowrap}
.hd-stale{color:var(--danger)}.hd-amber{color:var(--warning)}
.hd-acc{border:0;background:none;color:var(--accent);cursor:pointer;min-height:var(--h-control);padding:0 var(--sp-2)}
.hd-acc[aria-checked=true]{color:var(--text-2)}
.hd-items{display:grid;margin:0;padding:0}
.hd-item{padding:var(--sp-3) 0}
.hd-item+.hd-item{box-shadow:inset 0 1px 0 var(--track)}
.hd-panel{display:grid;gap:var(--sp-3);padding-top:var(--sp-3);min-width:0}
.hd-panel[hidden],.hd-form[hidden]{display:none}
.hd-text,.hd-reply{margin:0;max-width:90ch;font:inherit;font-size:var(--fs-15);line-height:1.5;color:var(--text-1);white-space:pre-wrap;overflow-wrap:anywhere}
.hd-reply{color:var(--text-2);font-size:var(--fs-13)}
.hd-text[data-state=loading]{min-height:4.5rem;padding:var(--sp-3);border-radius:var(--r-card);background:var(--surface-2);color:var(--text-2)}
.hd-text[data-state=error]{color:var(--danger)}
.hd-asset{font-family:var(--font-mono);font-size:var(--fs-13);color:var(--text-2)}
.hd-form{width:100%}
.hd-form input{flex:1 1 10rem}
.hd-more{flex-basis:100%}
@media (max-width:767px){
.hd-head{display:none}
.hd-items{gap:var(--sp-2)}
.hd-item,.hd-item+.hd-item{padding:var(--sp-3);background:var(--surface-1);border:1px solid var(--track);border-radius:var(--r-card);box-shadow:none}
.hd-row.row-grid{grid-template-columns:minmax(0,1fr) auto auto;grid-template-areas:"kind status when" "sum sum sum" ". acc copy";row-gap:var(--sp-2);column-gap:var(--sp-2)}
.hd-kind{grid-area:kind}.hd-status{grid-area:status;justify-self:end}.hd-when{grid-area:when;justify-self:end}.hd-sum{grid-area:sum}.hd-acc-cell{grid-area:acc;justify-self:end}.hd-copy{grid-area:copy;justify-self:end}
.hd-tab,.hd-acc,.hd-search input,.hd-sel select,.hd-all,.hd-log,.hd-acts .btn,.hd-more summary,.hd-row .ref-copy{min-height:44px}
.hd-row .ref-copy{width:44px;height:44px}
.hd-foot,.hd-acts{align-items:stretch;flex-direction:column}
}
```

Phone cards start at 767px so 375 and 768 both stack. Kind left, status and the time right, summary full width, Accept and copy on the right. Desktop keeps the six fixed tracks. No chevron transition, so reduced motion needs nothing extra. `base.css` already kills transitions.

### JS changes

`FILTERS` becomes `[["unhandled","Unhandled"],["needs","Needs you"],["doing","Doing"],["open","Open"],["done","Done"],["all","All"]]`.

Every `|| "open"` that sets the filter (`passes`, `filterHtml`, `barHtml` / the tools wrapper, `setField`, `sectionView`) becomes `|| "unhandled"`.

`countsOf` must also return `doing`, `open`, `done`, and `all`, using `head.counts` when that key exists, otherwise a count of `rows`. `done` and `all` are always counted from `rows` (the snapshot has no `done` total). Keep `doneUnacc`.

`filterHtml(opts, counts)` emits the `<a class="hd-tab">` string in the DOM above. Done gets `title="N not accepted"` and `hd-count-warn` only when `doneUnacc > 0`. The count number is still the done total. Pass `q`, `kind`, and `sid` through `hashOf`. Do not pass `sort`.

Replace `sortRows(rows, sort)` with an attention sort. Ignore the `sort` argument. Rank: `new` 0, `understood` 1, `needs-you` 2, `doing` 3, `bound` 4, `done` 5, `declined` 6, `merged` 7, anything else 9. `carried` sorts before the same rank. Tie-break is `ts` ascending (oldest waiting first). On the demo fixture with `f:"all"` the ids are `H4, H5, H1, H6, H2, H7, H3`.

`boundHtml`: on an empty list, `return ""`. Delete both "Not bound yet" strings.

`STATUS_WORDS.done` is `"done"`.

`nowHtml` returns only `<p class="hd-now">` plus, when `prev.length`, a following `<p class="page-note">`. Badge markup is the chip above. `headHtml` puts that `<p class="hd-now">` inside `.hd-idline`, and the page-note after `</header>`.

Delete the call to `alertsHtml`. Leave the function out. Delete the Order `<label>` in the bar.

Rename the bar wrapper to `<div class="hd-tools" data-f="...">` containing the tab `<nav>`, the search label, and the `<details class="hd-narrow">`. The change listener's `closest(".hd-bar")` becomes `closest(".hd-tools")`. `setField` stops reading `sort`.

`rowHtml` builds the six cells in the DOM. `aria-label` is `(open ? "Hide " : "Show ") + id + " " + (row.kind || "") + ". " + (row.sum || "")`.

`loadText` must not call `textContent` on `.hd-sum`. That wipes the inner nodes (`head.js:545-546`). Write the summary onto `.hd-sum-text`, and set `title` on `.hd-sum`. Also set `aria-busy` on `.hd-text` to `"false"` when the text arrives, and `"true"` on the error path only until the error string is shown, then `"false"`.

`panelHtml` follows the open-panel list above. Primary buttons stay in the first `.hd-acts`. Bind, Split, and Merge go in `.hd-more`. In the `head-form` click handler, after finding the panel, set `const more = panel.querySelector(".hd-more"); if (more) more.open = true;` before toggling the form.

`emptyHtml` uses the `.empty` markup above. Keep the two sentences exactly.

`headerHtml` returns the six-cell header. `headHtml` renders it inside `.hd-list` before `<ul class="hd-items">`.

Page-level loading stays `pageState` in `inbox.js` (skeleton, `aria-busy`). Do not add a second page skeleton.

## 3. Test assertions to update

`tests/web/render_head.mjs` can stay. Change assertions in `tests/web/test_head_view.py`.

`TRACKS` and `test_ten_fixed_tracks_on_the_shared_grid_and_summary_takes_the_rest`:

```python
TRACKS = "var(--rg) var(--ref-col)"
# css contains this exact rule:
# .hd-row.row-grid{--rg:6.5rem minmax(0,1fr) 7.5rem 8.5rem 5.5rem;position:relative;align-items:start;grid-template-columns:var(--rg) var(--ref-col)}
self.assertEqual(len("6.5rem minmax(0,1fr) 7.5rem 8.5rem 5.5rem".split(" ")) + 1, 6)
self.assertIn("minmax(0,1fr)", css)
self.assertNotIn("grid-column:2 / -1", css)
```

`test_summary_wraps_to_two_lines_in_every_row`:

```python
self.assertRegex(css, r"\.hd-sum-text\{[^}]*-webkit-line-clamp:2")
self.assertNotIn("-webkit-line-clamp:3", css)
```

`test_numbers_right_aligned_and_actions_in_fixed_tracks`:

```python
self.assertIn(".hd-when{text-align:right;font-variant-numeric:tabular-nums", css)
self.assertNotIn(".hd-age", css)
self.assertIn(".hd-acc{border:0", css)
```

`test_phone_turns_rows_into_cards_and_hides_the_header`:

```python
self.assertIn("@media (max-width:767px)", css)
self.assertIn("background:var(--surface-1)", css)
self.assertIn("border:1px solid var(--track)", css)
self.assertIn("border-radius:var(--r-card)", css)
self.assertIn('.hd-head{display:none}', css)
self.assertNotIn(".hd-when{display:none}", css)
self.assertNotIn("flex-wrap:wrap", css[css.index("@media (max-width:767px)"):])
self.assertIn("min-height:44px", css)
```

`test_rows_and_header_share_the_grid_class`: replace `assertNotIn("hd-head"` with `assertIn('class="row-grid hd-row hd-head rg-head"'`.

`test_header_sits_outside_the_list_and_the_list_holds_only_items`: replace `assertNotIn("headerHtml"` with `assertIn("headerHtml()", src)`. Keep `assertNotIn("hd-menu"`.

`test_each_row_has_eight_cells_and_no_header`: rename. With 7 rows plus the header, `html.count('class="hd-c')` is `6 * 8`. Assert the header node occurs before `<ul class="hd-items"`. Assert `assertNotIn("<li class=\"row-grid"`.

`test_no_session_column_and_no_dash_in_empty_cells`: keep the `hd-s` and `–` checks. Add `self.assertNotIn("Not bound yet", self.out["screen"])`.

`test_newest_first_by_default_and_oldest_on_request`: replace the reversed-order and `H6` checks with:

```python
self.assertEqual(ROW_ID.findall(self.out["screen"]),
                 ["H4", "H5", "H1", "H6", "H2", "H7", "H3"])
```

`test_whole_row_toggle_has_no_nested_buttons_inside_it`: the chevron is no longer `hd-c`. Expect `<span class="hd-chev" aria-hidden="true">`.

`test_numbers_and_summary_sit_in_their_own_cells`: expect `class="hd-c hd-sum"` and `class="hd-sum-text"`. Expect `hd-when rg-num hd-amber` on H4. Do not expect `hd-age`.

`test_added_column_shows_local_time_with_the_iso_title`: widen the class regex so an amber/stale suffix is allowed:

```python
r'<span class="hd-c hd-when rg-num(?: hd-amber| hd-stale)?" title="([^"]+)">([^<]+)</span>'
```

Keep the `hd-added` / `Added <day> <Mon> <year> <time>` check on `self.out["open"]`.

`test_head_badge_names_the_model_first_on_the_now_line`:

```python
self.assertIn('<strong class="chip chip-success hd-badge">Head · Opus 5.5</strong>', html)
self.assertIn('class="hd-now-rest">acct B', html)
self.assertLess(html.index("hd-badge"), html.index("hd-tabs"))
```

`test_no_head_claim_says_how_to_claim`:

```python
self.assertIn('<strong class="chip hd-badge">Head · not claimed</strong>', html)
self.assertIn("Run roadmap head claim", html)
self.assertNotIn("hd-badge-off", html)
```

`test_alerts_count_unhandled_needs_and_unaccepted_done`: on `self.out["screen"]` (`f:"all"`):

```python
self.assertIn('>Unhandled <span class="hd-count">1</span>', html)
self.assertIn('>Needs you <span class="hd-count">1</span>', html)
self.assertIn('title="1 not accepted"', html)
self.assertIn('>Done <span class="hd-count hd-count-warn">2</span>', html)
self.assertNotIn('class="hd-alert"', html)
self.assertNotIn('class="hd-filter"', html)
```

`test_done_rows_offer_confirm_and_reopen_in_the_panel`: keep the H7 accept and H3 reopen checks and `done?`. Replace `assertIn("done ✓"` with `assertIn(">done</span>"` and `assertNotIn("done ✓"`.

Block-order test (`"You wrote", "Head replied", "State", "Bound to"`): delete it. Replace with: open H1 contains `<pre class="hd-reply">Queued for Opus and bound to R7.31.</pre>`, `<ul class="hd-assets" data-role="assets">`, `<li class="hd-asset">shot.png</li>`, and `<span class="hd-reason">`. Assert those four labels are absent.

`test_reply_placeholder_when_none_was_captured`: `self.assertNotIn("No reply captured yet", self.out["noReply"])`.

Add a source check that the default filter literal is `"unhandled"` and that `">ask</span>"` (the kind chip) appears in `self.out["screen"]`. H2's bug chip is `chip-danger`.

Leave these as they are: esc / no innerHTML, the five `run("head.*")` ops, Confirm done, `hd-foot` / `hd-acts`, hidden split form, hash `#head?f=unhandled&q=a%20b&kind=bug`, empty sentence plus `head-log`, "Nothing in this view." plus `#head?f=all`, read-only has no write actions, filter counts (unhandled 1, done 2, open 5), H1 expanded and H4 hidden, history line on the open H1 panel, `HEAD_CSS_MAX` 4096, no raw hex in `head.css`.

