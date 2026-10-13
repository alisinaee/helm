# WP35b: UI smoke for the new shell, visual fixes

tools/ui_smoke.py tested the old project view (.proj-main, .proj-side, sec-*-body). It now tests the app shell: the
left nav (#nav), the main region (#main), the right panel (#side) and the section routes.

## Smoke coverage

- Temp ROADMAP_HOME with fixtures/demo alpha, beta, gamma and tests/fixtures/splitnet (copied, never the real home).
  Server on 127.0.0.1 port 0 with --no-usage-loop --no-phone.
- Routes: every section of alpha (overview, inbox, roadmap, work board/list/tree, issues, agents, tokens, rules,
  research, activity, settings); overview, inbox, work and tokens of beta and gamma; #/all/overview, #/all/inbox,
  #/all/tokens. 81 page runs in all.
- Five size and theme combos for alpha: 1440x900 dark and light, 1024x768 dark, 768x1024 dark, 500x900 dark. Other
  routes run at 1440x900 dark only.
- Checks per run: no data-render-error, no "could not be shown", nav and right panel present, main non-empty, no
  "Coming soon" in main, and the section marker (.page-title, .ov-card, .wk-col, .wk-table, .wk-tree, .lane,
  .iss-form, .met-row). The right panel must not still show the static placeholder.
- Screenshots of alpha go to build/ui-smoke/ (65 PNG, gitignored). Old PNGs are removed at the start of a run.
- Self-test page (web/dev/tests.html) must report PASS at each combo.
- Run time about 50 s. Scheme probe still checks that light and dark really differ.
- Runs are serial with up to 3 attempts per dump. Headless Chrome with --virtual-time-budget sometimes returns the
  placeholder shell before the module graph loads; parallel Chrome instances made this happen most of the time.
- Chrome missing: prints "SKIP: Chrome not found" and exits 0.
- tests/web/test_ui_smoke_sections.py: the smoke SECTIONS list equals the SECTIONS and SETTINGS ids in
  web/js/routes.js, and every section has at least one smoke route.

## Visual problems found (screenshots read: overview, work board, roadmap, tokens, issues, agents at 1440 dark and
light; overview and work at 1024 and 500; roadmap at 768)

Fixed:
1. At 641 to 1199 px the nav is a 56 px rail, but the badge rules keyed on data-nav="mini" did not apply. Count badges
   overflowed the rail and were clipped at the edge. Fix: app.js applyLayout sets data-nav="mini" below 1200 px too
   (isSheetWidth), so the same rail rules apply.
2. Overview, Open blockers: "1 tasks". Now "1 task" (overview.js).
3. Issues: the Open / Blockers / All filter tabs touched the bottom of the New issue card. Added a top margin
   (plan.css, .iss-filters).

Left, with reason:
4. Agents: the Stop button wraps onto its own line on the running rows, and the token numbers of "Last 10 finished"
   are not in one column. Needs more CSS than the 51 KB budget has left (52186 of 52224 bytes now).
5. Roadmap: phases that are already done (8/8) still show an Approve button. This is a product question, not a
   visual bug.
6. Tokens: the Spend cap input sits about 9 px lower than the Save cap button; the empty Limits block is a large
   centred message. Cosmetic, left for the budget.
7. Work board at 500 px: each phase filter chip takes its own row, so the filters run to five rows. Cards have spare
   space at the bottom. Cosmetic.
8. Roadmap at 768 px: the lane card grid uses about half the width. Cosmetic.
9. At 1440 px the shell is capped at 1280 px and centred, leaving 73 px gutters. Design choice, left.

## Checks

- python3 -m unittest discover -s tests -t . -q: 1124 tests, OK (2 expected failures, as before).
- python3 tools/ui_smoke.py: ok (81 page runs, 65 screenshots).
