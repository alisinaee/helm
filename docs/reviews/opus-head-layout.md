# Head layout review (Opus 5.5, 2026-10-15) - spec 13 vs head.js / head.css as of 5b3a0fb + WIP

## 1. Six most important problems
1. No fixed tracks for numbers (rule 0): head.css:9 has 4 tracks; status/bound/age/date sit in a flex line (head.css:19,
   head.js:369-375), so age/date drift per row.
2. Filler and empty cells: "Not bound yet" on every closed row (head.js:227); empty age/date spans (372-374); empty
   `.hd-hist` <p> eating a sp-4 gap (395, head.css:25); "No reply captured yet" (306) and 340 repeat empties in the panel.
3. Short summary until opened: summaryText (head.js:273-279) lengthens only from fullCache, so never-opened rows show a
   one-clause sum with dead space (clamp head.css:18 never fills). Snapshot must send a ~240-char sum.
4. Bound chips: id and status are two chips per task (head.js:228-236); running model only in the panel (331-336).
5. Opened panel wastes width and can explode in height. Blocks stack in one column capped at 90ch (head.css:28), leaving
   ~40% of a 1440 screen empty; the reply is a <pre> with no max-height (head.js:390, cap is 8000 chars). Panel indent is a
   magic 28px (head.css:25) that does not match the summary track (20+60+2 gaps = ~96px), so blocks do not align with it.
6. Labels are <p> not headings (head.js:387-395); `.hd-title` used for h2 (475) and task title (328); phone rule
   (head.css:38) turns the row into free flex, so age/date land anywhere.

## 2. Target structure
```
li.hd-item[.is-open]
  div.hd-row.row-grid                      grid: 16px 4.5rem minmax(0,1fr) 6.5rem 3rem 6.5rem var(--ref-col)
    button.hd-hit                          (stretched toggle, as now)
    span.hd-chev | span.hd-id | span.hd-sum | span.hd-status(chip) | span.hd-age.rg-num | span.hd-when.rg-num | span.hd-copy
    div.hd-chips                           row 2, grid-column 3 / -2; ONLY rendered when there is something to show
      a.chip.hd-task  "R7.31 doing · sonnet"   one chip per task (id + status dot + live model), max 2, then +n
      span.chip.hd-kind  (kind, when not "ask")
  div.hd-panel                             padding-left = var(--hd-sum-x) so blocks start under the summary
    section.hd-blk.hd-wrote  > h3.hd-lbl "You wrote"    + pre.hd-text + ul.hd-assets (omit ul when empty)
    section.hd-blk.hd-reply-b> h3.hd-lbl "Head replied" + div.hd-reply (omit block, not placeholder, when no reply)
    section.hd-blk.hd-state  > h3.hd-lbl "State"        + chip + reason + p.hd-added("Added .. · history", one line)
    section.hd-blk.hd-boundb > h3.hd-lbl "Bound to"     + ul.hd-links (title, status, running model; Bind button if none)
    div.hd-foot (actions) + forms
```
CSS changes (head.css):
- :9 replace with the 7-track template above; define `--hd-sum-x: calc(16px + 4.5rem + 2 * var(--sp-2))` on `.hd-screen`.
- :18 clamp 2 lines on desktop (`-webkit-line-clamp:2`), keep `white-space:normal`.
- :19 delete `.hd-meta`; add `.hd-chips{grid-column:3 / -2;grid-row:2;display:flex;flex-wrap:wrap;gap:var(--sp-1)}`.
- :20/:23 drop `.hd-bound`/`.hd-none` from the closed row; empty cells render nothing.
- :25 `.hd-panel{padding:var(--sp-2) var(--sp-2) var(--sp-4) var(--hd-sum-x);display:grid;gap:var(--sp-3);
  grid-template-columns:minmax(0,1fr)}`; `@media (min-width:1100px){.hd-panel{grid-template-columns:repeat(2,minmax(0,1fr))}
  .hd-foot,.hd-form{grid-column:1 / -1}}` (wrote | reply on row 1, state | bound on row 2).
- :28 drop `max-width:90ch`; `.hd-reply{max-height:24em;overflow:auto}`; `.hd-text{max-height:32em;overflow:auto}`.
- bound-task title class -> `.hd-ttl`; `h3.hd-lbl{font:inherit;font-size:var(--fs-12);margin:0}`.
- :38 phone: keep grid, `grid-template-columns:16px minmax(0,1fr) auto var(--ref-col)`; id+summary in track 2 (id as
  prefix), status 3, copy 4; age/date become the last item of `.hd-chips`; clamp 3; panel padding-left 0, one column.
JS: 227 return "" when no links; 233-235 one chip id+status+model; 372-374 blank cell (track kept); 390 omit reply block
when reply is null after load; 395 history inline in `.hd-added`, skipped when empty.

## 3. Acceptance checks
1440px (desktop, 20+ rows, mix of bound/unbound/with reply/with assets):
- Closed row line 1: chevron, id, summary (max 2 lines, fills to status, no dead space), status, age, date, copy;
  age/date right-aligned at the same x in every row.
- Line 2 only when there are bound tasks/kind; one chip per task "id status · model"; no "Not bound yet", "-" or empty pill.
- Never-opened row already shows the long summary (not one clause).
- Opened row: four h3-labelled blocks (You wrote, Head replied, State, Bound to) in 2 columns aligned with the summary;
  full text + attachment chips; reply scrolls past ~24 lines; no empty <p> gaps.
375px (phone):
- No horizontal page scroll; 16px gutter; copy button stays at the right edge of line 1; status chip on line 1.
- Summary wraps to max 3 lines, no ellipsis mid-word; chips line holds bound task(s) then age/date at the end.
- Opened row: one column (wrote, reply, state, bound); long attachment paths wrap; buttons full width, 44px tap height.
- Screen reader / keyboard: Tab reaches each row toggle, Enter opens, h3 navigation lists the four blocks.
