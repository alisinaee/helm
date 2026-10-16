# Inbox tasks check (2026-10-16)

Scope: head asks H52, H58, H81, H88, H119, H154 and the new asks H162-H172; rule proposals RP5-RP14; blocker R3.2.
Format: id | ask | done? (evidence) | leftover action.

## Head asks

| id | ask | done? (evidence) | leftover action |
|---|---|---|---|
| H52 | ask: "they did face issue, first know how to run max effort" (text cut off twice) | no; unclear (docs/head.jsonl H52 needs-you) | needs you: see Needs you |
| H58 | review: run an OpenCode task, check model and effort show in Agents | partly; Agents shows engine and effort (web/js/views/agents.js:45-50, 166-168; commit 445800b). OpenCode run blocked: no account credit (docs/HEAD-RUNBOOK.md, OpenCode line) | needs you: see Needs you |
| H81 | question: "updated and correct?" | no; ask is unclear (needs-you since 10:45) | needs you: see Needs you |
| H88 | ask: run server and dashboard in pane, then start tasks, limit 80% of 5h | server/tasks part done (head note 10:45); usage % still needed. docs/autonomy.json holds a reading pushed 2026-10-16 11:15 (weekly 98%, 5h 3%) | needs you: see Needs you |
| H119 | review: run the Cursor high-effort full UI check | no; Cursor review j857 failed (VPN off, head note 16:57) | needs you: see Needs you |
| H154 | ask: clean the Planner | planner cleaned (docs/reviews/planner-cleanup.md; 0 orphans, 26 items); 10 features await your accept | needs you: see Needs you |
| H162 | /head: read last checkpoint and project state | not a code task; resume is a head action | none in this run |
| H163 | run the server on pane | no; needs a server start, and port 8780 restarts are out of scope for this run | needs you: start it yourself or ask again |
| H164 | rule: no limit | done in this run: docs/HEAD-RUNBOOK.md Usage stop lines updated (see commit). docs/autonomy.json still holds limit.fiveHourStopAtPercent 80 (roadmap/services/budget.py:50-54) | needs you: see Needs you |
| H165 | ask sonnet low to review leftovers and queue them; run haiku per item | done by this check (haiku, not sonnet; this table is the review) | none |
| H166 | "i dont see any running task why?" | not checked here (docs/jobs.json not read in this run) | open; ask head to answer from jobs |
| H167 | "the last sonnet task?" | not checked here | open; ask head to answer from jobs |
| H168 | add Sonnet leftovers as board tasks | done: R9.4 (head note) | none |
| H169 | Panel UI: dead space in tasks column, column alignment | no; a Cursor UI task, outside this run's file list | open; queue a Cursor UI review after H119 VPN is on |
| H170 | list the inbox tasks, short | done by this table | none |
| H171 | Inbox asks: choice buttons a/b/c plus free text | done: R9.30 (head note) | none |
| H172 | gather inbox tasks, check against code, do leftovers | done by this run (table + RP5-RP13 checks) | none |

## Rule proposals (docs/rules-proposals.json, status "proposed")

| id | ask | done? (evidence) | leftover action |
|---|---|---|---|
| RP5 | Show real model and effort on Agents | done: web/js/views/agents.js:45-50 (effortLabel), 166-168, 194-196; roadmap/services/jobs.py:116-128 (effort and engine_model stored); commits 61aaf25, 445800b; tests/web/test_agents.py, tests/unit/test_jobs.py pass | none in code; you accept with `roadmap rules accept RP5` |
| RP6 | Register every job, including follow-ups | done: roadmap/services/hooks.py:341-344 (SendMessage), 1223-1242 (_followup_start calls jobs.start_job); test tests/unit/test_followup_jobs.py. Gap by design: a SendMessage to an agent not in docs/agents-map.json is skipped and logged (hooks.py:1239) | none in code; you accept |
| RP7 | Workers never run usage sync, keychain, 8780, person tabs | rule present: docs/HEAD-RUNBOOK.md worker prompt line (never run usage sync; never touch 8780, keychain, browser tabs). Keychain reads live only in roadmap/services/usage.py:80-100 (sync path); nothing in tools/ enforces the rule (prompt-only) | none in code; you accept |
| RP8 | UI rule 0 | not in scope of this run's list | open (not asked here) |
| RP9 | Head shows every captured item | done: pager in web/js/views/head.js:764-801 (offset, limit, Load more), routes.py:561-600 (offset/limit, HEAD_LIMIT_MAX 200). Snapshot is a preview only (roadmap/core/snapshot.py:35, 44: 40 open, 5 done, 8192 bytes); badge counts come from full fold. tests/unit/test_head_paging.py, tests/web/test_head_paging_view.py pass | none in code; you accept |
| RP10 | Every message captured; head reviews rule items | no; a process rule | needs you |
| RP11 | No secrets in Head, ledger or logs | no; a policy rule | needs you |
| RP12 | Work items human cards; agent tasks never cards | no; a model rule (see H151 in HEAD-RUNBOOK) | needs you |
| RP13 | Usage stops 80% 5h and 95% week | superseded by H164 "no limit". Runbook updated in this run (docs/HEAD-RUNBOOK.md). Code still enforces 5h 80% (docs/autonomy.json, budget.py) | needs you: see Needs you |
| RP14 | Model roles: Haiku edits; Opus/Sonnet low/medium review; Cursor and agy reviews; agy verified | no; a policy rule (already in HEAD-RUNBOOK models line) | needs you |

## Blocker

| id | ask | done? (evidence) | leftover action |
|---|---|---|---|
| R3.2 | release cutover (1.0.0) | no; docs/NEXT-WAVE.md item 8: cutover is done last, with the person present | needs you |

## Needs you (exact questions)

- H52: What did you mean? The text was cut off twice; please restate it.
- H58: Top up OpenCode credit, then should I run the OpenCode check that Agents shows model and effort?
- H81: Which update do you mean ("updated and correct?")?
- H88: Is the usage reading in docs/autonomy.json (weekly 98%, 5h 3%, pushed 2026-10-16 11:15) current?
- H119: Turn VPN on, then should I rerun the Cursor full-UI review (j857 failed with VPN off)?
- H154: Accept the 10 waiting Planner features in docs/reviews/planner-cleanup.md?
- H164: Should docs/autonomy.json drop the 5-hour stop (80) that the budget guard still reads?
- RP5, RP6, RP7, RP9: Accept these as done? (`roadmap rules accept RP<n>`)
- RP10: Accept "every message from you is captured in Head; the head reviews rule items"?
- RP11: Accept "no secrets in Head, the ledger or logs"?
- RP12: Accept "Work items are human cards; agent tasks are machine packages never shown as cards"?
- RP13: Accept the superseding of 80%/95% by "no limit" (H164)?
- RP14: Accept "Haiku edits; Opus or Sonnet low/medium only for hard review; Cursor and agy for reviews; agy output verified"?
- R3.2: Ready for the 1.0.0 cutover with you present?
