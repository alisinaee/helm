# R7.21 Wave plan (Opus head, 2026-10-15)

Rules: no file appears in two packages of one wave. Shared files (routes.js, app.js, components.css, commands.py, snapshot.py, cli.py, CHANGELOG) have ONE owner per wave. Workers: strict file list, stage own files by path, temp ROADMAP_HOME, never touch port 8780, open a new browser tab. Size S ~15K, M ~30K, L ~45K Haiku tokens.
Already built (check state first, `git status`, then do only the gap): Backlog core (parsers has `backlog`, test_backlog_core.py), Git service/routes/ops (git.py, gitops.py, test_git_service/routes/ops.py), tokens/limits tests (test_limits_simple.py, test_tokens_simple.py). FINISH-PLAN: R6.18 and R6.19 are closed as built (verify only).

## Wave 1 (start now, 8 packages, no overlap)
| id | task | goal | files (code + tests) | done-check | size | worker |
|---|---|---|---|---|---|---|
| W1.a | R7.22 step 1 | backlog state in parsers, md marks, planfmt, guide, task and backlog CLI (finish gaps) | roadmap/core/{parsers,mdtables,planfmt,guide}.py, roadmap/commands/{backlog,task}.py, tests/unit/test_backlog_core.py | test_backlog_core, test_planfmt*, test_mdtables* | M | haiku |
| W1.b | R7.29 step 5 | `roadmap git` command (status, log, branches, commit, push), job-done link | roadmap/commands/git.py, roadmap/cli.py (COMMAND_MODULES hunk), roadmap/commands/job.py, tests/unit/test_git_cmd.py | test_git_cmd, test_git_ops, test_job_cmd | M | haiku |
| W1.c | R7.29 step 6 | Git GUI: status, history, branches, commit and push policy; comment strip in components.css | web/js/views/git.js, web/css/git.css, web/css/components.css (comment strip only, hunk), web/js/views/nav.js, web/js/routes.js, tests/web/test_git_view.py, tests/web/render_git.mjs | test_git_view, test_assets, test_shell; make check-ui | L | haiku |
| W1.d | R7.28 A, B, D | Tokens simple screen: weekly stop, share rows, read-only spend; top bar text | web/js/views/limits.js, web/js/views/tokens.js, web/js/views/topbar.js, tests/web/test_limits_simple.py, tests/web/test_tokens_simple.py | test_limits_simple, test_tokens_simple, test_usage_entry | L | haiku |
| W1.e | R7.30 | Workflow map: Open in new tab, full-screen view with left nav hidden | web/js/views/workflow.js, web/js/graph/*.js, web/css/map.css, tests/web/test_workflow_view.py, tests/web/test_workflow_graph.py | test_workflow_view, test_workflow_graph, test_graph_viewport | M | haiku |
| W1.f | R7.16 5b/6 + R7.12 docs | logging steps 5b and 6; copy-ref docs step; settings logging UI | web/js/views/settings.js, web/js/log.js, tests/web/test_settings_logging.py, tests/web/test_log_client.py, docs/{AGENT-INTERFACE,TOKEN-COST,SECURITY,LOGGING-SPEC,R7.12-SPEC}.md, skills/* lead and worker lines | test_settings_logging, test_log_client, test_logs_cmd, test_log; `python3 scripts/check_docs.py` | M | haiku |
| W1.g | R7.5 leftovers | rows rule 0: tree, list, overview squeeze, fixed grid columns | web/js/views/{tree,list,overview}.js, web/css/plan.css, tests/web/test_rows_b.py, tests/web/test_r754_rows.py | test_rows_b, test_r754_rows, test_rows; make check-ui | M | haiku |
| W1.h | R6.18, R6.19, R6.22 | verify only: research flag, progress tokens, stale pill, Cmd-K palette, Workflow light mode, 500 px, keyboard, Start/Stop click | none edited; audit file docs/reviews/agy-wave1-verify.md; own port 8791, temp home | test_palette, test_research*, test_ui_smoke_sections (read-only) | S | agy (audit), head verifies |

Head after wave 1: run unit + `make check`, `make check-ui` alone, register jobs, commit per package, push; close R6.18, R6.19, R6.22, R7.5, R7.12, R7.16, R7.29 (if W1.b+W1.c green), R7.30. CSS budget: 72 KB cap; W1.c strips comments to make room first.

## Wave 2 (after wave 1 committed; 5 packages)
| id | task | goal | files | done-check | size | worker |
|---|---|---|---|---|---|---|
| W2.a | R7.22 step 2 | ops `task.backlog`, `task.promote`, `backlog.add`, undo, activity, person-only and start guards | roadmap/services/commands.py, roadmap/services/cmdops.py, tests/unit/test_backlog_ops.py | test_backlog_ops, test_commands*, test_undo* | M | haiku |
| W2.b | R7.22 step 3 | backlog in snapshot and status line, excluded from active counts | roadmap/core/snapshot.py, roadmap/commands/status.py, tests/unit/test_backlog_snapshot.py | test_backlog_snapshot, test_snapshot* | S | haiku |
| W2.c | R7.22 step 5 | graph status map and workflow toggle | web/js/graph/model.js, web/js/views/workflow.js, tests/web/test_workflow_graph.py | test_workflow_graph, test_workflow_view | S | haiku |
| W2.d | R7.28 C | delete lim-range, lim-num, steppers, sheet, preset CSS; grid for share and spend rows (net negative CSS) | web/css/components.css, tests/web/test_limits_simple.py (css assertions) | test_limits_simple, test_assets; make check-ui | S | haiku |
| W2.e | review | Cursor auto reviews wave 1 diff (git GUI/commands, tokens, logging); agy audit of tokens.js and limits.js controls (spec 6 audit) | docs/reviews/cursor-wave1.md, docs/reviews/agy-tokens-audit.md | no high/medium open | M | cursor, agy |
Deps: W2.a waits for W1.f only if log.py changes (none listed, so independent); W2.b-c need W1.a; W2.d needs W1.c and W1.d merged. Fixes from W2.e go into wave 3 packages named F.

## Wave 3 (after wave 2; 3 packages)
| id | task | goal | files | done-check | size | worker |
|---|---|---|---|---|---|---|
| W3.a | R7.22 step 4 | Backlog column and section in Work (board, work, list, tree, overview) | web/js/views/{board,work,list,tree,overview}.js, web/css/work.css, tests/web/test_work.py, tests/web/test_backlog_view.py | test_work, test_backlog_view, test_rows_b; make check-ui | L | haiku |
| W3.b | R7.24 W1 + R7.25 W1 | Work v2 ops (quick add, move, reorder, due, labels) and public `issue.status`, `next:` line in issue command | roadmap/services/commands.py, roadmap/core/mdtables.py, roadmap/commands/{task,issue}.py, tests/unit/test_work_v2_ops.py, tests/unit/test_work_unified_ops.py | test_work_v2_ops, test_work_unified_ops, test_cmd_issue | L | haiku |
| W3.c | F | fixes from W2.e review, one per finding | files the review names (none from W3.a, W3.b) | the finding's test | S | haiku |
Deps: W3.a needs W1.g (rows) and W2.a-b; W3.b needs W2.a (same commands.py, serial).

## Wave 4 (after wave 3; 3 packages)
| id | task | goal | files | done-check | size | worker |
|---|---|---|---|---|---|---|
| W4.a | R7.24 W2 + R7.25 W2 | snapshot fields for Work v2 and `issuesClosed`, status fold, status line | roadmap/core/snapshot.py, roadmap/commands/status.py, tests/unit/test_work_v2_snapshot.py | test_work_v2_snapshot, test_backlog_snapshot | M | haiku |
| W4.b | R7.24 W3 + R7.25 W3 | board: cards, quick add, drag, issue cards, blocker badge, Kind filter; move `.iss*` out of plan.css | web/js/views/board.js, web/css/work.css, web/css/plan.css, tests/web/test_work_v2_board.py | test_work_v2_board, test_work; make check-ui | L | haiku |
| W4.c | R7.24 W5 + R7.25 W5 | drawer: edit fields, issue actions (Start, Close, Won't fix, Link task) via `issueView` | web/js/views/details.js, tests/web/test_work_v2_details.py | test_work_v2_details | M | haiku |
Deps: W4.a needs W3.b; W4.b needs W3.a (work.css) and R7.23 topbar badge (already in); W4.c needs W3.b (ops exist).

## Wave 5 (after wave 4; 2 packages)
| id | task | goal | files | done-check | size | worker |
|---|---|---|---|---|---|---|
| W5.a | R7.24 W4 + R7.25 W4 | Work shell: menu, keys, Issues tab (`k=issues`, `g u`), Work badge; delete issues.js | web/js/views/{work,list,tree,topbar}.js, web/js/{routes,router,keys,app}.js, web/js/views/issues.js (delete), tests/web/test_work_v2_shell.py, tests/web/test_work_unified_shell.py | test_work_v2_shell, test_work_unified_shell, test_shell, test_aria_al | L | haiku |
| W5.b | review | Cursor auto review of waves 3-4 (ops, snapshot, board, drawer) | docs/reviews/cursor-wave4.md | no high/medium open | M | cursor |

## Wave 6 (close, serial)
| id | task | goal | files | size | worker |
|---|---|---|---|---|---|
| W6.a | all | fixes from W5.b; then docs: CHANGELOG, AGENT-INTERFACE, PRODUCT-SPEC, skills for backlog, git, Work v2, tokens | review-named files; then docs/CHANGELOG.md, docs/AGENT-INTERFACE.md, docs/PRODUCT-SPEC.md, skills/* | M | haiku |
| W6.b | all | `make release-check`, `make check-ui` alone, `check_docs.py`, HANDOVER section 0 update, close tasks, Opus WP18 final review | docs/HANDOVER.md, docs/tasks.json via `bin/roadmap` | S | head (Opus) |

## Cross-wave notes
- Chain (critical path): W1.a -> W2.a -> W3.b -> W4.a/W4.c -> W5.a; W1.g -> W3.a -> W4.b -> W5.a.
- Cursor runs one review at a time and needs the VPN. agy output is verified (about 35% wrong facts); run `git status` after each agy job.
- Hard stops: 5h usage 90%, weekly 85% (H111). If tight, drop in order: W5.b, W2.e extras, W1.e, then W4.c polish. Never drop W1.h or W6.b.
- Usage push before every wave: `bin/roadmap usage push` by hand; ask the person for current 5h and weekly % first.
- Unrelated uncommitted work now in the tree (head core/snapshot/headops, head.js and their tests): commit or stash before wave 1 so W1 packages stage only their own files; W2.b and W4.a edit snapshot.py, which also holds head changes.
