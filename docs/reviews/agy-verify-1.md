# agy batch 1: verification

Checked against the real code and docs in this repo (read-only). Every row of the six agy files was checked.
Line numbers are the real ones; "drift +N" means the quoted text sits N lines after the cited line.

Verdicts:
- KEEP: the row's claim is true and the change is safe to apply.
- WRONG: the claim or the proposed fix is false (cited code or doc says otherwise).
- UNVERIFIED: the claim is partly true, but the proposal needs a human decision or a check I could not finish (for example it drops needed information or conflicts with project vocabulary).

Command run: `python3 tools/check_docs.py` gives "checked 13 documented roadmap command(s): 0 failed". It runs only in a temp
ROADMAP_HOME/HOME. Help-only commands (hooks install, serve, service, and others) are checked with `--help` only, so
it does not catch wrong flags on them (README:317 `--replace-legacy` passes, and the flag exists anyway).

## 1. agy-r74-planfmt-gaps.md (40 rows: 39 KEEP, 1 WRONG, 0 UNVERIFIED)

Test-gap rows: test_planfmt.py has no F or L test at all, so the "missing in" claims hold. Cited test line numbers are approximate.

| row id | verdict | one-line evidence |
|---|---|---|
| 01 format_feature minimal | KEEP | emits `F F1 - 2 - - \| Title` (planfmt.py:398-403) |
| 02 hold=True | KEEP | status `hold` (planfmt.py:401); parse sets hold (:219, :242) |
| 03 prio/phase/parent/acc | KEEP | emitted (:402-406); parsed back (:242-244) |
| 04 invalid prio to 2 | KEEP | planfmt.py:398 |
| 05 blank acc, no `#` | KEEP | planfmt.py:404-406 |
| 06 fewer than 6 tokens | KEEP | planfmt.py:214-215 |
| 07 invalid F id | KEEP | FEAT_ID_RE `^F[1-9][0-9]?$` (:31) rejects F0 and F100 (:217-218) |
| 08 status not -/hold | KEEP | message matches (:219-220) |
| 09 prio not 1/2/3 | KEEP | message matches (:221-222) |
| 10 phase dot/symbol | KEEP | message matches (:223-224) |
| 11 parent bad format | KEEP | message matches (:225-226) |
| 12 self parent | KEEP | message matches (:227-228) |
| 13 empty title | KEEP | :232-234 |
| 14 title over 80 | KEEP | FEAT_TITLE_MAX=80 (:20), check at :235-237 |
| 15 empty acceptance | KEEP | :230-231; parse_plan strips lines first (:78), so trailing ` #` is caught |
| 16 acceptance over 160 | KEEP | FEAT_ACC_MAX=160 (:21), check at :239-241 |
| 17 duplicate F id | KEEP | :99-104 (message matches); test_planfmt.py:111 covers P/T only |
| 18 L with under 3 tokens | KEEP | :252-253 |
| 19 L invalid F id | KEEP | :255-256 |
| 20 L invalid task id | KEEP | :257-259 |
| 21 valid L, several tasks | KEEP | returns the tasks list (:260); no L test exists |
| 22 repeated L lines | KEEP | L lines skip the seen map (:96-98) |
| 23 format_task feats `f:F1,F2` | KEEP | planfmt.py:426-428 |
| 24 empty feats omitted | KEEP | planfmt.py:427 |
| 25 feats round trip | KEEP | parsed into a list (:169-173, :193-205) |
| 26 a: then f: order | KEEP | planfmt.py:423-428 |
| 27 `f:-` gives None | KEEP | planfmt.py:195-196 |
| 28 f: bad id | KEEP | message matches (:198-201) |
| 29 f: over 3 ids | KEEP | :202-204; FEAT_MAX_PER_TASK=3 (:18) |
| 30 apply_records skips non-feature | KEEP | features.py:82-83 |
| 31 dry_run writes nothing | KEEP | features.py:103-105 returns wrote False |
| 32 apply_records "parent cycle" | WRONG | no cycle case exists. Parents are one level only (core/features.py:135-140), so a cycle cannot be written. The usage raise (features.py:100-102) is still right for other validation errors. Drop the example. |
| 33 link adds to orphan task | KEEP | features.py:206-223; tasks.py:411-420; orphans at core/features.py:64-70 |
| 34 link already linked is idempotent | KEEP | tasks.py:411-412 skips duplicates; added is [] (features.py:223) |
| 35 link up to cap of 3 | KEEP | tasks.py:414-419 raises only when already at 3 |
| 36 unlink missing task | KEEP | features.py:233-235 raises not_found |
| 37 unlink feature not present | KEEP | features.py:238-239, no write |
| 38 unlink last feature pops feats | KEEP | features.py:243-244 |
| 39 status line, 0 orphans | KEEP | features.py:292-293 |
| 40 status line, 1 orphan | KEEP | features.py:294 gives "1 orphan task" |

## 2. agy-r76-docs.md (36 rows: 16 KEEP, 18 WRONG, 2 UNVERIFIED)

The FACTS-based "fix" is wrong in most rows, because the code agrees with the docs in those cases.

| row id | verdict | one-line evidence |
|---|---|---|
| 01 README:6 port 8765 | KEEP | README shows 8765; default is 8780 (commands/serve.py:18) |
| 02 README:18 port | KEEP | same (serve.py:18) |
| 03 README:33 port | KEEP | same |
| 04 README:92 port | KEEP | same |
| 05 README:99 skills install location | KEEP | `skills install` copies into `<project>/.claude/skills` (commands/skills.py:1,15,31) |
| 06 README:163 missing `feature` | KEEP | feature group is registered (cli.py); no README table row |
| 07 README:163 missing `watch` | KEEP | watch registered (cli.py); no README table row |
| 08 README:163 missing `skills` | KEEP | skills registered (cli.py); no README table row |
| 09 README:172 `service logs [-f]` | WRONG | `-f/--follow` exists on logs (commands/service.py:32) |
| 10 README:173 `serve --no-phone` | KEEP | commands/serve.py:28 |
| 11 README:184 cap 30 | KEEP | KEEP_FINISHED = 200 (services/jobs.py:17) |
| 12 README:190 plan import options | WRONG | plan import has --project, --dry-run and --replace-phase (commands/plan.py:51-55) |
| 13 README:191 plan export --phase | WRONG | --phase exists (commands/plan.py:59-60) |
| 14 README:204 "only waiting command" | KEEP | watch also blocks (commands/watch.py:1,35,53) |
| 15 README:208 comments arg order | WRONG | argparse takes ID and --last in either order (commands/comment.py:27-29); doc form is valid |
| 16 README:210 budget show --phase | WRONG | --phase exists (commands/budget.py:29) |
| 17 README:212 at most 6 notes | WRONG | enforced (commands/research.py:16, 121-123, 186) |
| 18 README:214 120 lines / 6 KB | WRONG | enforced (commands/research.py:17-18, 167-170) |
| 19 README:216 hooks `<id>` | WRONG | install, uninstall and status each take a project id (commands/hooks.py:12, 17, 21) |
| 20 README:225 rules add --budget | WRONG | --budget exists for kind budget (commands/rules.py:25) |
| 21 README:228 60 rules / 8 KB | WRONG | enforced (services/rules.py:5, 19-21, 89-90) |
| 22 README:236 "open not built" | KEEP | `roadmap open --help` runs; commands/open.py exists |
| 23 README:236 "phone not built" | KEEP | `roadmap phone --help` runs; phone is registered (cli.py) |
| 24 README:263 port 8765 | KEEP | serve.py:18 |
| 25 README:317 --replace-legacy | WRONG | flag exists (commands/hooks.py:13). check_docs.py passes it only as --help. |
| 26 README:360 table omits feature | UNVERIFIED | feature group exists (cli.py); the table body was not read |
| 27 README:360 table omits phase | UNVERIFIED | `phase approve` exists (commands/limits.py:52-54); the table body was not read |
| 28 AGENT-INTERFACE:39 grammar lacks F/L | KEEP | planfmt parses F and L (planfmt.py:86-91) |
| 29 AGENT-INTERFACE:109 caps | WRONG | `research check` enforces them (commands/research.py:16-18, 167-170, 186); doc is right |
| 30 AGENT-INTERFACE:188 plan --project | WRONG | plan import takes --project (commands/plan.py:51) |
| 31 AGENT-INTERFACE:190 task set --project | WRONG | task set takes --project (commands/task.py:56) |
| 32 AGENT-INTERFACE:215 research new --project | WRONG | research new takes --project (commands/research.py:45) |
| 33 skill-draft roadmap-update:12 --project wording | KEEP | --project is per command; the blanket "optional" line is loose, so clarifying it is safe |
| 34 skill-draft roadmap-update:22 limit | WRONG | `--limit 10` is a valid flag (commands/task.py:44); the explicit flag is fine, so no default change is needed |
| 35 skill-draft roadmap-plan-new:26 caps | WRONG | enforced (commands/research.py:16-18) |
| 36 skill-draft roadmap-plan-new:58 plan export | WRONG | --phase exists (commands/plan.py:59-60); the quote is on line 57, and line 58 is plan import |

## 3. agy-r77-strings-sz.md (40 rows: 34 KEEP, 0 WRONG, 6 UNVERIFIED)

Every quoted string exists in the cited file. Several are split across concatenated JS lines, so the cited line is off by up to 2.

| row id | verdict | one-line evidence |
|---|---|---|
| 01 settings.js:37 | KEEP | string exists; proposal is a plain reword |
| 02 settings.js:43 | UNVERIFIED | string exists (split across lines); the proposal drops "cannot change limits, overrides, rules, caps or approvals" |
| 03 settings.js:50 | UNVERIFIED | string exists (split across lines); the proposal drops where global limits and rules live |
| 04 tokens.js:40 | KEEP | exact match |
| 05 tokens.js:85 | KEEP | built as `"The tick at " + WARN_AT + "% is the warning line."` (line 85) |
| 06 tokens.js:95 | KEEP | "(from autonomy.json)" is on line 96 |
| 07 tokens.js:106 | KEEP | drift +1 |
| 08 tokens.js:163 | KEEP | drift +1 |
| 09 tokens.js:170 | KEEP | drift +1 |
| 10 tokens.js:173 | KEEP | drift +1 |
| 11 tokens.js:175 | KEEP | drift +1 |
| 12 tokens.js:176 | UNVERIFIED | string exists (drift +1); the proposal drops "they land on that day" (day attribution) |
| 13 tokens.js:177 | KEEP | drift +1; duplicate of 170, so removing it is fine |
| 14 tokens.js:204 | KEEP | drift +2 |
| 15 tokens.js:208 | KEEP | drift +2 |
| 16 tree.js:24 | KEEP | exact match |
| 17 usage.js:26 "Usage is old" | KEEP | built as `"Usage is old: " + why` |
| 18 usage.js:26 "Run Sync now..." | KEEP | exact match |
| 19 usage.js:30 "Stale" | KEEP | exact match |
| 20 usage.js:30 "min old" | KEEP | `esc(minutes) + " min old"` (line 31) |
| 21 usage.js:52 | KEEP | exact match |
| 22 work.js:113 | KEEP | exact match |
| 23 work.js:127 | KEEP | exact match |
| 24 work.js:130 | KEEP | exact match |
| 25 work.js:135 | KEEP | exact match |
| 26 workflow.js:198 "Head" to "Lead agent" | UNVERIFIED | "head" is the project's role term (workflow.js:90, 198); changing it conflicts with CLAUDE.md and HANDOVER vocabulary |
| 27 workflow.js:372 | KEEP | exact match |
| 28 workflow.js:377 | KEEP | exact match |
| 29 workflow.js:651 | UNVERIFIED | string exists; the proposal removes the `roadmap job start` how-to from the empty state |
| 30 workflow.js:667 | KEEP | "nodes" is on line 668 |
| 31 workflow.js:673 | KEEP | exact match |
| 32 workflow.js:674 | KEEP | exact match |
| 33 workflow.js:676 | KEEP | exact match |
| 34 workflow.js:681 | KEEP | exact match |
| 35 workflow.js:715 | KEEP | exact match |
| 36 workflow.js:717 | KEEP | exact match |
| 37 workflow.js:746 | KEEP | exact match |
| 38 workflow.js:764 | KEEP | exact match |
| 39 workflow.js:817 | KEEP | exact match |
| 40 workflow.js:857 | UNVERIFIED | string exists; the proposal drops the "press Enter to open its task" keyboard hint |

## 4. agy-n01-strings-ak.md (40 rows: 30 KEEP, 0 WRONG, 10 UNVERIFIED)

Extra conflicts: board.js:16 labels the `partial` state "Doing", and details.js:10 uses "To do" (not "To Do").

| row id | verdict | one-line evidence |
|---|---|---|
| 01 activity.js:44 "last 15 lines" | KEEP | exact match; matches the 15-line note in activity.js:3 |
| 02 activity.js:44 "50 at most" | KEEP | exact match |
| 03 activity.js:51 | KEEP | exact match |
| 04 agents.js:53 "no task" | KEEP | exact match |
| 05 agents.js:55 "handed to" | KEEP | exact match |
| 06 agents.js:109 "Last 10 finished" | KEEP | built as `"Last " + FINISHED_MAX + " finished"` |
| 07 agents.js:118 "Stop asks the project..." | UNVERIFIED | exists; "asks" becomes "halts", which changes what Stop does |
| 08 board.js:188 "Move to Todo" to "To Do" | UNVERIFIED | exists; "To Do" is inconsistent with details.js:10 "To do" |
| 09 board.js:189 "Queue run" | KEEP | button is at line 190; label change only |
| 10 board.js:191 "Stop run" | KEEP | exact match |
| 11 board.js:254 Drag/keys hint | UNVERIFIED | exists (lines 255-256); the proposal drops the Alt+Up and Alt+Down shortcut |
| 12 board.js:257 | KEEP | exact match |
| 13 details.js:11 "Partial" to "In progress" | UNVERIFIED | board.js:16 labels this state "Doing"; "In progress" would be a third name |
| 14 details.js:90 | KEEP | exact match |
| 15 details.js:98 | KEEP | exact match |
| 16 details.js:108 | KEEP | exact match |
| 17 details.js:109 | KEEP | exact match |
| 18 details.js:112 | KEEP | exact match |
| 19 details.js:137 "a session is picking it up" | UNVERIFIED | exists; "agent starting now" changes which actor the state names |
| 20 details.js:138 "picked up at the session's next stop" | UNVERIFIED | exists; "awaiting agent pause" changes the actor and the meaning |
| 21 details.js:139 | KEEP | exact match |
| 22 details.js:157 | KEEP | exact match |
| 23 details.js:207 | KEEP | exact match |
| 24 details.js:279 | KEEP | exact match |
| 25 details.js:317 | KEEP | exists (drift +1) |
| 26 details.js:340 "Definition of done" | KEEP | exact match |
| 27 details.js:387 | KEEP | exact match |
| 28 details.js:388 "It may have been closed or answered" | UNVERIFIED | exists; "Item was resolved" overclaims, since the code cannot know the item was resolved |
| 29 extras.js:31 "spikes" | KEEP | exact match |
| 30 extras.js:32 "real hardware" | KEEP | exact match |
| 31 home.js:30 | KEEP | exact match |
| 32 home.js:48 "need you" to "awaiting input" | UNVERIFIED | exists; r77 proposes "Action needed" for the same phrase (tree.js:24), so the two proposals conflict |
| 33 home.js:88 | KEEP | exact match |
| 34 home.js:99 "Fix file syntax" | UNVERIFIED | exists; "syntax" assumes a parse error, which the banner does not say |
| 35 inbox.js:15 | KEEP | exact match |
| 36 inbox.js:130 | KEEP | exact match |
| 37 inbox.js:156 | KEEP | exact match |
| 38 issues.js:58 | KEEP | exact match |
| 39 issues.js:64 | KEEP | exists (lines 64-65); the blocker behaviour is kept in the proposal |
| 40 kpi.js:25 "partly done" to "in progress" | UNVERIFIED | exists; same "Doing" vocabulary conflict as row 13 |

## 5. agy-n02-strings-lr.md (40 rows: 36 KEEP, 0 WRONG, 4 UNVERIFIED)

| row id | verdict | one-line evidence |
|---|---|---|
| 01 legend.js:8 | KEEP | exact match |
| 02 legend.js:11 | KEEP | exact match |
| 03 legend.js:13 | KEEP | exact match |
| 04 legend.js:14 | KEEP | exact match |
| 05 legend.js:15 | KEEP | exact match |
| 06 legend.js:26 | KEEP | exact match |
| 07 legend.js:33 | KEEP | exact match |
| 08 limits.js:54 " of weekly" to " of weekly quota" | UNVERIFIED | exists; "quota" is new vocabulary, while limits.js uses "weekly limit" and "allowance" |
| 09 limits.js:64 | KEEP | exact match |
| 10 limits.js:66 | KEEP | exact match |
| 11 limits.js:67 | KEEP | exact match |
| 12 limits.js:103 | KEEP | exact match |
| 13 limits.js:112 | KEEP | exact match |
| 14 limits.js:129 | KEEP | exact match; removes the filename |
| 15 limits.js:130 | KEEP | exact match; removes the filename |
| 16 limits.js:132 | UNVERIFIED | exists; the proposal "Pending snapshot sync" keeps the jargon the row objects to |
| 17 limits.js:174 | KEEP | exact match |
| 18 limits.js:181 | KEEP | exact match |
| 19 limits.js:258 | KEEP | exact match |
| 20 list.js:106 "No model" | KEEP | exact match |
| 21 list.js:160 | KEEP | exact match |
| 22 list.js:173 " sub" to " subtasks" | UNVERIFIED | exists; the column is fixed-width (UI rule 0), so a longer label needs a visual check |
| 23 list.js:174 " cmt" to " notes" | UNVERIFIED | exists; same fixed-width column concern |
| 24 nav.js:43 | KEEP | exact match |
| 25 nav.js:47 | KEEP | exact match |
| 26 nav.js:78 | KEEP | exact match |
| 27 needsyou.js:11 | KEEP | exact match |
| 28 needsyou.js:14 | KEEP | exact match |
| 29 needsyou.js:15 | KEEP | exact match |
| 30 next.js:15 | KEEP | exact match |
| 31 next.js:18 | KEEP | exact match |
| 32 overview.js:59 | KEEP | exact match |
| 33 overview.js:62 "Work is stopped by this limit." | KEEP | exact match |
| 34 overview.js:62 "Work keeps running." | KEEP | exact match |
| 35 overview.js:78 | KEEP | exact match |
| 36 overview.js:82 | KEEP | exact match |
| 37 overview.js:95 | KEEP | exact match |
| 38 overview.js:105 | KEEP | exact match |
| 39 overview.js:115 | KEEP | exact match |
| 40 palette.js:189 | KEEP | exact match |

## 6. agy-n03-presence-gaps.md (24 rows: 24 KEEP, 0 WRONG, 0 UNVERIFIED)

Every code claim matches roadmap/services/presence.py. The "tests only check X" claims match the visible test file (tests/unit/test_presence.py, 108 lines). It has no scalar-JSON, zero-stamp, or ensure_dir-failure case.

| row id | verdict | one-line evidence |
|---|---|---|
| 01 file_for relative path | KEEP | abspath(str()) (presence.py:26) |
| 02 file_for Path object | KEEP | str(data_dir) (presence.py:26) |
| 03 _moment "1000.5" | KEEP | float(now) (presence.py:31) |
| 04 _load scalar JSON | KEEP | not a dict gives {} (presence.py:40); test covers only [1, 2] (test_presence.py:79-84) |
| 05 _store OSError | KEEP | caught, debug log, False (presence.py:45-51) |
| 06 _stamp bool hook | KEEP | presence.py:56-57; test covers watch:true and hook:"soon" only |
| 07 _stamp zero | KEEP | presence.py:58 returns 0.0 |
| 08 touch_hook backward clock | KEEP | presence.py:67 is False for negatives, so it writes |
| 09 touch_hook now omitted | KEEP | time.time() via _moment (presence.py:31) |
| 10 touch_hook keeps watch fields | KEEP | setdefault (presence.py:70-71) |
| 11 touch_hook invalid now | KEEP | float() raises inside the fail-open block (presence.py:73-74) |
| 12 set_watch non-int pid | KEEP | presence.py:82 stores None |
| 13 set_watch bool pid | KEEP | presence.py:82 guard |
| 14 set_watch keeps hook | KEEP | setdefault (presence.py:83) |
| 15 set_watch invalid now | KEEP | fail-open (presence.py:85-86) |
| 16 clear_watch no file | KEEP | _load gives {} then writes (presence.py:92-96) |
| 17 clear_watch exception | KEEP | fail-open (presence.py:97-98) |
| 18 state future hook | KEEP | presence.py:111 fails the condition, so NONE |
| 19 state future watch, fresh hook | KEEP | presence.py:108 fails, :111 passes, so OPEN |
| 20 state watch boundary 0 | KEEP | 0 <= 0 < 60 (presence.py:108) |
| 21 state hook boundary 0 | KEEP | presence.py:111 |
| 22 state now omitted | KEEP | _moment (presence.py:106) |
| 23 state invalid now | KEEP | fail-open NONE (presence.py:114-115) |
| 24 state both expired | KEEP | presence.py:108-113 gives NONE |

## Safe to apply (KEEP rows only)

Apply these only. Rows marked WRONG or UNVERIFIED must not be applied.

- agy-r74 (test additions, 39): rows 01-31, 33-40. Skip row 32.
- agy-r76 (docs, 16): README:6, README:18, README:33, README:92, README:99, README:163 (feature, watch, skills), README:173, README:184, README:204, README:236 (open and phone wording), README:263, AGENT-INTERFACE:39, skill-draft roadmap-update:12.
- agy-r77 (UI strings, 34): rows 01, 04-11, 13-25, 27, 28, 30-39. Skip 02, 03, 12, 26, 29, 40 (UNVERIFIED).
- agy-n01 (UI strings, 30): rows 01-06, 09, 10, 12, 14-18, 21-27, 29, 30, 31, 33, 35-39.
- agy-n02 (UI strings, 36): all rows except 08, 16, 22, 23.
- agy-n03 (test-gap notes, 24): all rows, 01-24.

Note: rerun `python3 tools/check_docs.py` after any README or skill-draft edit.
