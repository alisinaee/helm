# UX review: Inbox (R10.2)

Screenshots: build/ui-smoke/alpha-inbox-{500x900,768x1024,1024x768,1440x900}-dark.png and 1440x900-light.png (before), the same names after the R10.2 run (after).
Rule sources: UI-CHECKLIST.md rule number, or ui-ux-pro-max `--domain ux` search: "data table density" (DT), "form input buttons" (FB), "dark mode contrast" (DC), "responsive mobile list" (RM). The search "list row alignment" and "list alignment" returned no database match, so row rules come from UI-CHECKLIST rule 0 and are labelled as such.

| # | issue (element and what is wrong) | screenshot | fix | P | after | rule source |
|---|---|---|---|---|---|---|
| 1 | Expand button `›`: glyph sits top-left in a box; the target looks like an empty tall box at 500 px | 500, 1024, 1440 dark | grid-centred glyph, larger glyph, chevron turns 90 deg when the row opens | P1 | centred, rotates; state shown by shape, not colour | checklist 0 (action column fixed), DT |
| 2 | Copy icon on its own line above the question heading, at the far right, off the action column edge | 500, 1440 dark | id line becomes a flex row; copy button sits at its end, 32 px | P1 | copy button on the id line | checklist 0, DT |
| 3 | Section title and copy icon split into two rows; a blank band above the summary | 500, 768, 1440 | page head uses a 2-track grid (title, copy column) | P2 | title and copy share one row | checklist 0 (header aligned to tracks) |
| 4 | Default option is a solid saturated block (btn-primary) that out-weighs the decision and clashes with the minimal look | 1440 dark and light | border and tint in accent, text label "default" kept | P2 | quiet accent border, still named "default" in text | checklist 1 (status not by colour alone), DC |
| 5 | Question text shown twice (row title and body heading) | all | not changed: the row truncates, the body gives the full text | P3 | not changed | RM (no duplicate text in a narrow row) |
| 6 | Horizontal scrollbar at 768 and the top bar cut off at the right edge (`Auto`, `?`, panel button) | 768 | outside the Inbox (shell top bar, head/shell CSS); not touched | P1 | open, for the shell owner | checklist 5 (no horizontal scroll), RM |
| 7 | Second vertical scrollbar inside the content area at 768 | 768 | outside the Inbox (same shell cause as 6) | P2 | open, for the shell owner | checklist 5, RM |
| 8 | Other input and Send clipped at x about 487 in the 1440 dark frame while the Projects drawer opens | 1440 dark (before) | not reproduced in the after frame; likely drawer transition | P3 | not seen in after frame | checklist 5 |
| 9 | Filter chips very tight (about 8 px gap) and wrap as a block | 1440 | no change: gap comes from head.css (other worker's file) | P3 | unchanged | DT (group spacing) |
| 10 | Default-option description (the "default" word) is 11 px, low weight | 500, 1440 | accent colour, opacity 1 | P3 | accent, readable | DC (4.5:1), checklist 6 |
| 11 | Mono "Other" label and the body labels use a different size from the rest | 500 | not changed; the mono label is the form's visible label | P3 | unchanged | FB (visible label) |
| 12 | Send button fills the whole width, the heaviest control in a row | 500 | not changed (phone: tap target 44 px kept) | P3 | unchanged | FB, checklist 2 |

Totals: P0 0; P1 3 (1 and 2 fixed; 6 open, shell top bar); P2 3 (3 and 4 fixed; 7 open, shell); P3 6 (5, 8-12, none blocking). Open shell items 6 and 7 are for the shell owner, not this pass.

Verification: `python3 tools/ui_smoke.py` ran; the inbox frames are clean. The 26 failures are overview and tokens markers for beta and gamma ("Coming soon", missing .ov-card and .met-row), not Inbox routes.

## R10.14 / H200 redesign (compact rows, inline options)

Before (2000px live page, H200): options were full-width ~1700px buttons, Send a full-width bar, Other input full width; each question repeated id and title 3 times (header row, sub-row, H3); grey filter blocks, wide empty gutter, big collapse box.

After (code, not yet screenshotted: `ui_smoke.py` was running for another worker, so alpha-inbox-1440 and -500 are still to be inspected):
- One grid row per item: kind chip 84px | id + title (one time, ellipsis; wraps when open) | task chip | age (tabular-nums, right) | 28px ghost chevron. The sub-row and body H3/id are gone.
- Body indented under the title column: options are content-sized pills (letter key + label) that wrap inline; default is shown by accent border and the word "default". Other input (max 480px) and a small primary Send share one row.
- Content column max 960px; filters are a compact segmented control with counts; the summary is one muted small line; items older than 24h are muted.
- Keys: a, b, c pick an option of the focused open question (1 to 6 unchanged); focus-visible rings; 44px targets only under 600px.
- CSS: inbox.css 6.4 KB to about 4.3 KB, shared total under the cap.
