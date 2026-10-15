# Next wave to 1.0.0 (2026-10-14)

## 1. Priority order
1. **R7.1 finish (T2/T3/T4/T6, then T5).** It is the last feature of the interaction model, and T5 is still blocked on T1+T4. Head reviews T3 (hook code).
2. **GUI Start gate in an unapproved phase** (services/commands.py `_h_task_status`). This is a correctness hole that R7.1 makes worse, because Start now wakes a real session.
3. **Cursor Planner review: fix its findings.** This is the last open security review before the tag.
4. **R7.5 row alignment** (agy-a05-rows.md). It is UI rule 0, the person's top UI rule.
5. **R7.3 inline title edit.** Small, but it touches shared views.
6. **R6.34 workflow touch/mouse/CSP check.** Haiku with its own port and its own tab; needs no new code unless it fails.
7. **R7.6/R7.7 docs and strings, R6.22/R6.25 partials.** Cheap, and agy-heavy.
8. **R3.2 cutover** (RELEASE.md), with the person present. Do it last, on a green `make check` + `make check-ui`, then tag 1.0.0.

## 2. New agy jobs (none duplicate R7.6 docs-vs-commands, R7.7 strings s-z or R7.4 planfmt)
| id | type | READ | WRITE | columns | verifier |
|---|---|---|---|---|---|
| n01 | 8 strings a-k | web/js/views/{activity,agents,board,details,extras,home,inbox,issues,kpi}.js | docs/reviews/agy-n01-strings-ak.md | file:line, old, new, why | head picks rows |
| n02 | 8 strings l-r | web/js/views/{legend,limits,list,nav,needsyou,next,overview,palette}.js | docs/reviews/agy-n02-strings-lr.md | same as n01 | head picks rows |
| n03 | 2 test gaps | roadmap/services/presence.py, tests/unit/test_presence.py | docs/reviews/agy-n03-presence-gaps.md | function, missing case, expected | Haiku greps 3 rows |
| n04 | 2 test gaps | roadmap/services/launcher.py, tests/unit/test_launcher.py | docs/reviews/agy-n04-launcher-gaps.md | same as n03 | Haiku greps 3 rows |
| n05 | 2 test gaps | roadmap/services/featops.py, features.py, tests/unit/test_features_service.py | docs/reviews/agy-n05-features-gaps.md | same as n03 | Haiku greps 3 rows |
| n06 | 1 audit, row alignment | web/js/views/{planner,projects,recent,research,roadmap,rules,running,settings}.js | docs/reviews/agy-n06-rows-pz.md | file:line, row, problem, class | Haiku greps 3 rows |
| n07 | 1 audit, aria | web/js/views/{tasks,toast,tokens,topbar,tree,usage,work,workflow}.js | docs/reviews/agy-n07-aria-tz.md | file:line, element, missing, fix | Haiku greps 3 rows |
| n08 | 5 release cmds | docs/RELEASE.md, docs/facts/FACTS.md, roadmap/commands/{hooks,service,skills,project}.py | docs/reviews/agy-n08-release-cmds.md | doc line, command, exists Y/N, flag diff | Haiku runs check_docs.py |
| n09 | 6 CHANGELOG | docs/facts/FACTS.md, docs/R7.1-SPEC.md, docs/HANDOVER.md | docs/reviews/agy-n09-changelog-1.0.md | bullet, source file:line | Haiku greps 3 claims |
| n10 | 1 audit, CSP | web/index.html, web/js/{app,dom,routes}.js, web/js/views/{workflow,planner}.js | docs/reviews/agy-n10-csp.md | file:line, pattern (inline style/handler/innerHTML), fix | Haiku greps 3 rows |

Run n03/n04 only after T1/T4 are committed. Use AGY_MAX=3 and 4 batches. All jobs are read-only plus one new file.

## 3. Haiku packages (strict lists)
R7.1 locks: services/{presence,hooks,launcher,queue}.py, commands/watch.py, core/snapshot.py, store/schema.py, views/details.js, tests/web/test_panel.py.

| pkg | files | parallel? |
|---|---|---|
| H1 Start gate | roadmap/services/commands.py, tests/unit/test_commands*.py (new test file) | yes |
| H2 rows A | web/js/views/{tokens,phases}.js, web/css/components.css, tests/web/test_rows.py (new) | yes; one owner of the CSS |
| H3 rows B | web/js/views/{tree,list}.js | yes; after H2 if it needs new CSS classes |
| H4 inline title | web/js/views/tasks.js, web/js/api.js, tests/web/test_title_edit.py (new) | yes; NOT details.js until T6 is in |
| H5 strings apply | only the views listed in the rows kept from n01/n02/R7.7, minus details.js/tree/list/tokens/phases | after H2-H4, by file |
| H6 docs apply (R7.6, n08, n09) | README.md, docs/RELEASE.md, CHANGELOG.md | yes |
| H7 test gaps n03/n04/n05 | new test files only | after R7.1 |
| H8 R6.34 check | none (own port, temp ROADMAP_HOME, own tab) | yes, read-only |
| H9 Planner review fixes | per finding, never hooks.py/schema.py while R7.1 runs | after the review |

Parallel now: H1, H2, H4, H6, H8. Then H3 and H5 after them. Then H7 and H9.

## 4. Risks
- **Usage.** 86% now, stop at 95%. About 9 points is left for roughly 9 Haiku packages, 10 verifiers and 2 Opus reviews. If it gets tight, drop H5/H7 first.
- **agy writes outside its file.** agy-a05 changed workflow.js and graph files during its run. Check `git status` after every job and revert anything outside its WRITE file.
- **Shared-file collisions.** components.css, app.js, routes.js and state.js: one owner at a time, with re-read-before-edit hunks.
- **Hook code (T3)** can block every tool call if it breaks. Keep it fail-open, and the head reviews it.
- **ui_smoke is flaky under load.** Run `make check-ui` alone, before the cutover.
- **Cutover touches split-net's live hooks and port 8765.** The person must be present: limits on Warn, take a backup, and keep a rollback per GAP-ANALYSIS.md.
