# R7.21 Finish plan: 1.0.0 and cutover (Opus, 2026-10-15)

## 1. Done means
1. These are closed: R7.16 steps 1-6, R7.13 H1-H7, R7.12 P8, R7.5 B, the agy-n10 CSP rows, aria-controls ids, the copy button on workflow nodes and planner rows, and the R6.22 check. R6.18 and R6.19 are closed as already built.
2. `make release-check` is green. `make check-ui` is green when run alone. CSS is 72 KB or less (68 KB now). Snapshot features are 8 KB or less.
3. Cursor grok reviews R3.6 and R3.7 are done, with every high or medium finding fixed or listed in SECURITY Known limits. The Opus WP18 review finds no blocker.
4. `check_docs.py` passes, CHANGELOG 1.0 is complete, and HANDOVER is current.
5. RELEASE.md steps 0, 1, 2, 4 and 5 are done on split-net with limits on Warn, and the local tag `v1.0.0` exists.

## 2. Waves
One owner per file; shared files (routes.js, app.js, index.html, components.css, cli.py, services/commands.py, AGENT-INTERFACE.md, skills) get re-read hunks. Running: j564 (L1), j567 (H1), j568 (H2), j569 (P8), j570 (R7.5 B), Cursor web review.

**Wave B**
| id | owner | files | parallel | K |
|---|---|---|---|---|
| L2 endpoint | Haiku | http/{routes,security,server}.py, tests/unit/test_log_route.py | after j564 | 30 |
| L3 command | Haiku (head reads hook.py) | commands/logs.py, cli.py, services/commands.py, commands/hook.py, tests/unit/test_logs_cmd.py | with L2 | 30 |
| H3 | Haiku | services/{features,featops}.py, core/snapshot.py, tests/unit/test_snapshot_features_size.py | after j567 | 35 |
| W1 CSP and aria | Haiku | agy-n10/n07 rows in web/js/{app,dom}.js, views/workflow*.js; not index.html or planner.js | now | 25 |
| V1 R6.22 check | Haiku, read-only | own port 8791, temp home, own new tab | now | 15 |

**Wave C**
| id | owner | files | waits | K |
|---|---|---|---|---|
| H4 | Haiku | commands/{feature,plan}.py, tests/unit/test_cmd_feature_tree.py | H2, H3 | 30 |
| H5 | Haiku | views/planner.js, css/planner.css, tests/web/test_planner*.py, plus the planner CSP rows and the copy button | H3 and the person's answers | 45 |
| H6 | Haiku | views/work.js, routes.js | H3 | 20 |
| C1 | Haiku | workflow node copy button in views/workflow*.js | W1 | 15 |
| L5 | Haiku | views/settings.js, index.html, components.css (600 B or less) | j570 | 25 |

**Wave D** (runs in series)
| id | owner | files | waits | K |
|---|---|---|---|---|
| D1 = H7 + L6 | Haiku | AGENT-INTERFACE, TOKEN-COST, SECURITY, PRODUCT-SPEC, PLANNER-SPEC, lead and worker skills, CHANGELOG | P8, H4, L3 | 30 |
| F1 review fixes | Haiku per finding | the files the reviews name | the reviews | 40 |
| D2 | head | HANDOVER (mark NEXT-WAVE as old) | D1 | 5 |

Total: about 400K Haiku, 60K head and verifiers.

## 3. Gates and cutover
**Review gates.** Cursor runs one review at a time and needs the VPN.
1. R3.6, grok-4.7-xhigh, web review (running); fixes go into F1.
2. R3.7, grok-4.7-xhigh, after L2 and L3: the log endpoint, redaction, rate limit, and hook emitters.
3. Cursor auto, after H4: the plan tree H1-H4 (cycles, depth, `ask` lost on rewrite).
4. Cursor auto, after D1: docs and RELEASE.md commands against the code.
5. Opus WP18 final review of the diff, then a feature freeze.

**Cutover** (RELEASE.md together with the GAP-ANALYSIS rollout). The person does steps 3-7.
1. Head: `make release-check`, `make check-ui` alone, clean `git status`, `doctor`.
2. Head: dry run on a copy of split-net's data in a temp home; files stay byte-identical.
3. The person: `roadmap backup`, then `project init` and `project add split-net`.
4. The person: `hooks install split-net --replace-legacy` with limits on Warn. Note the backup path. Run it for 1-2 days and compare job counts. 8765 and 8780 run side by side.
5. The person: install the skills (dry run first).
6. The person: switch the limits to Stop, then test `stop` and `resume`.
7. The person: stop 8765, set the CHANGELOG date, `git tag -a v1.0.0`.
8. Later, as its own change: delete legacy.html (RELEASE.md step 6).

**The person also:** keeps the VPN on (`agy /login` on 403), pushes usage before each wave, answers the 5 Planner v2 and 5 logging questions before H5 and L5.

## 4. Risks and cuts
**Risks**
- **Weekly usage** was about 86% at the last push, and the stop is at 95%. If it gets tight, drop H6, C1 and the W1 aria rows first, never the reviews.
- **CSS** has about 4 KB left, and H5 and L5 compete for it. Reuse existing classes and do not raise the cap.
- **hook.py** must stay fail-open; the head reads that diff.
- **agy** gets about 35% of facts wrong, so verify its rows and run `git status` after each job.
- **Workers reuse the "seed" tab:** prompts must say to open a new tab (tabs_create).

**Not in 1.0**
- the launcher, and automatic usage (document it as a known limit)
- phone writes and phone UI logs
- per-project logs
- planner drag-and-drop
- the swimlane timeline, $ cost, and the cross-project board
- any feature after Wave C

## 5. Next 8 jobs
1. **L2** (Haiku), after j564 commits.
2. **L3** (Haiku), in parallel with L2.
3. **H3** (Haiku), after j567 commits.
4. **W1** (Haiku), now.
5. **V1** (Haiku), now: light mode, 500 px, keyboard, Start/Stop clicks.
6. **agy batch** (AGY_MAX=3; a Haiku verifies 3 rows of each):
   - g1 (type 6): CHANGELOG bullets for R7.12-R7.17, into agy-g1-changelog.md
   - g2 (type 8): workflow v2 strings, into agy-g2-strings-wf.md
   - g3 (type 2): core/features.py tree gaps after H1, into agy-g3-tree-gaps.md
   - g4 (type 1): log.py redaction and caps after j564, into agy-g4-log-redaction.md
7. **Cursor R3.7** (`CURSOR_MODEL=grok-4.7-xhigh`), after R3.6 finishes and L2 and L3 are committed.
8. **Head** (2K):
   - Close R6.18 and R6.19 as built.
   - Add the new-tab rule to HEAD-RUNBOOK.
   - Send the person the 10 open questions in one message.
