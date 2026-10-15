# Head ledger: unhandled asks (R7.46)

Scope: asks, bugs, questions and reviews in `bin/roadmap head list --all` (H27 to H108). Rules and decisions skipped. Evidence: `git log --oneline -60` and task statuses in `docs/tasks.json`.

## NOT HANDLED

| id | Still missing | Suggested task title | Likely files |
|---|---|---|---|
| H35 | Ledger says done, but Opus review (H96) says open; audit outputs unverified | Verify H35 agy/Cursor head audits, then close | docs/reviews/agy-head-*.md |
| H47 | Parallel audits marked done; Opus says still open | Verify H47 audit outputs, then close | docs/reviews/agy-*.md, docs/jobs.json |
| H48 | Sync root cause across sections not found (R7.40 fixed only Cursor P2 items) | Find root cause of sections not syncing (R7.45) | web/js/api.js, web/js/routes.js, roadmap/http/routes.py |
| H52 | Unclear ask; no reply resolves it | Ask the person what H52 means, then close or re-bind | none (ledger only) |
| H58 | Model and effort labels not checked on a live OpenCode run (account has no credit) | Verify OpenCode model and effort labels on one live run | roadmap/services/jobs.py, web/js/views/agents.js |
| H69 | Claude extension in Arc: browser reach was not confirmed by a working connection | Confirm Chrome connection for the Argon test | none (setup) |
| H73 | Argon test still waits on Chrome connection | Run Argon test once Chrome connection is confirmed | docs/reviews/ (new output) |
| H74 | Gemini send button ignores clicks; message never sent | Person sends the Argon test prompt by hand; log reply | docs/reviews/ (new output) |
| H75 | "Work as task" for Gemini did not change send behaviour | Fold into Argon test; drop if Argon route is dropped | none |
| H76 | Test question typed but never sent; no answer read back | Run the one-paragraph Argon test question and record the answer | docs/reviews/ (new output) |
| H78 | Cursor did not fix lazy load; only a diagnosis was written | Fix Head lazy load (R7.44) | web/js/views/head.js, roadmap/http/routes.py, roadmap/services/head.py |
| H79 | Cursor grok fix for lazy load and list cut not verified as landed | Fix Head lazy load and list cut (R7.44) | web/js/views/head.js, tests/web |
| H80 | Argon role agreed in reply; first question not sent, no decision | Decide Argon review use; send first design question | docs/reviews/ (new output) |
| H81 | "Is the board updated and correct?" not confirmed after sync fixes | Verify board freshness after sync fixes (R7.45) | web/js/api.js, roadmap/services/usage.py, tests/web/test_sync_refresh.py |
| H88 | 5h usage stale (34% on 2026-10-14); 80% stop cannot be checked; no tasks started | Push current 5h and weekly usage by hand, then check the 80% stop | docs/budget.json, roadmap/services/usage.py |
| H89 | Opus review done, but tasks from its advice P2 (R7.33) and P5 (R7.36) still todo | Verify P2 sync findings (R7.33) | docs/reviews/cursor-sync-grok.md, web/js/api.js |
| H96 | Same as H89: P2 and P5 still todo | Ledger hygiene: triage H51, H59, H67; close H36, H49 (R7.36) | roadmap/services/headops.py, docs/head.jsonl |
| H100 | OpenCode jobs failed (account has no credit); restart not done | Restart failed OpenCode audits once funded, or move to Haiku | roadmap/services/jobs.py, docs/jobs.json |
| H105 | Missing items and lazy load in Head; sections not syncing | Show every Head ledger item with paged API and lazy load (R7.44); fix sync (R7.45) | web/js/views/head.js, roadmap/http/routes.py, roadmap/services/head.py |

Count NOT HANDLED: 19 ids (H35, H47, H48, H52, H58, H69, H73, H74, H75, H76, H78, H79, H80, H81, H88, H89, H96, H100, H105).

## Marked done but unverified

- H36: state "declined", yet Haiku tasks were started (reply). Close it via R7.36.
- H38: text is only "if need update that"; no target can be identified.
- H44, H47: OpenCode registration change was left uncommitted at the time; audit outputs not checked against code.
- H57: fix shipped, but old job rows still show "opencode" (H63 reply).
- H63: Agents page checked on an old build; hard reload and recheck not confirmed.
- H70: "give that access" has no stated target.
- H77: "try again" after VPN fix; no retry evidence.
- H83: reruns started; results are present in docs/reviews but not verified against the code.
- H102, H104: bound, not closed; the Standing mandate lives in ~/.claude/skills/head, outside this repo, so not checkable here.
