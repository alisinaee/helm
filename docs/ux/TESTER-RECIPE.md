# UI/UX tester recipe (Haiku workers; person H196, 2026-10-16)

One section per worker. Test, fix, re-test. Rules come from three sources, cite one per finding:
1. `docs/UI-CHECKLIST.md` (house rules: rule 0 = numbers and actions in fixed grid columns, full width).
2. `~/.claude/skills/ui-ux-pro-max/` (UX domain only): `python3 ~/.claude/skills/ui-ux-pro-max/scripts/search.py "<topic>" --domain ux -n 3`
   (no `--design-system`, no -I). Topics: data table density, row alignment, scroll container, sticky header,
   responsive table mobile, dark mode contrast, form input buttons, empty state, truncation tooltip.
3. `docs/ux/web-interface-guidelines.md` (Vercel Labs, MIT): a11y, focus, forms, numbers (tabular-nums),
   motion, content overflow, touch targets.

## Steps
1. Screenshots: `python3 tools/ui_smoke.py` (own headless Chrome + fixtures; never port 8780). Open
   `build/ui-smoke/alpha-<section>-*.png` at 500, 768, 1440, 2560, dark and light.
2. Review in this order: grid alignment (rule 0) -> scroll (one container, sticky headers, no page x-scroll) ->
   responsive (500/768) -> density and dead space -> typography and contrast -> controls (one per action, fixed
   column, 44px touch) -> empty/overflow states -> modern minimal look (Linear-like).
3. Write `docs/reviews/ux-<section>.md`: # | issue (element + what) | screenshot | rule source | fix | P0-P3 | after.
4. Fix P0-P2 in the section's own files only (shell issues go to the shell owner; list them, do not fix).
5. Re-run ui_smoke, re-open the images, fill the "after" column (max 2 rounds). Keep CSS caps green.
6. Commit by path; report issues found/fixed and what is still open.

## The person's taste (hard rules, from H199-H205)
- Controls are content-sized: never full-width inputs, buttons or option bars. Number inputs ~64px with the unit
  inline ("[ 15 ] %"). Primary action (Send/Save) sits on the same row as its input.
- One-line cells: no wrapped dates or ids; right-aligned tabular numbers in fixed columns; ellipsis + tooltip.
- No repeated titles, no dead vertical space, no stray icons on their own line, no page-level scrollbars.
- Forms and cards max ~960px wide; tables may use the full width but keep columns tight.
- Modern minimal (Linear/Vercel): ghost icon buttons (28px, aria-label), compact segmented controls, muted helper text.
