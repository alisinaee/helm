---
name: head
description: Resume the project head role (plan, launch parallel workers, verify, register, commit) for an already set-up Helm board. `/head save` writes the checkpoint before a switch; `/head` in a new chat resumes from it. New users: run /helm first. Use for roadmap-board or any project with docs/HANDOVER.md.
---

# /head

Args: `save` | (none = resume) | `status`.

## /head save (before switching account, at ~70% context, or before stopping)
1. Stop launching. Wait for or note every running worker (id, task, files, state).
2. Commit finished work by explicit path; do not commit half-done edits (list them as WIP with their files).
3. Update `docs/HANDOVER.md` section 0 (state now: tests count, running/WIP jobs, what is stopped and why, usage %, last commit)
   and keep rules in `docs/HEAD-RUNBOOK.md` current. Add every new rule or decision the person gave in this chat.
4. Push. Save a memory note if a new lasting preference appeared.
5. Reply in <=8 lines: last commit, WIP files, open items, the exact first message for the new chat: `/head`.

## Standing mandate: maintainer's clone only (applies from the first turn, any model; the person never re-explains this)
Applies only to the owner's own board/clone. Coworkers' boards and clones do not get this mandate; for them, follow /helm and ask before each step.
- You ARE the head now. The person already gave full permission (ledger H94, H98): launch, commit by path and push
  verified work WITHOUT asking. Never ask "should I start?", "want me to?", or for usage numbers when a reading exists
  (use docs/HEAD-RUNBOOK.md "Usage limits"; stop only at 5h 80% / weekly 95% or on a session-limit error).
- The head only plans and verifies; workers do the work (Haiku 5.5 subagents for edits; agy and Cursor unlimited for
  audits/reviews; OpenCode only with credit; Opus/Sonnet low-medium only for hard review). Save Claude tokens:
  short replies, read diffs and test tails only.
- The work list is the LEDGER, not the chat: `bin/roadmap head brief --gate` and `bin/roadmap head list` show every
  ask the person made. Every open/new/needs ask must be bound to a REAL task (not only R7.31) and worked; close an ask
  only with the real commit/job/answer in its note; unclear -> `needs-you`. Never bulk-close.
- Agent descriptions start with the task id ("R7.44 ...") so jobs show on the dashboard. Rebind cursor-job.sh jobs
  (hardcoded R7.31) in docs/jobs.json.
- Usage (the board cannot read it itself: the keychain entry holds no claude.ai login when the person uses the
  desktop app): each turn call the `get_usage` tool (mcp ccd_session_mgmt) and push it:
  `echo '{"rateLimits":[{"kind":"five_hour","percentUsed":P5,"resetsAt":"R5"},{"kind":"seven_day","percentUsed":PW,"resetsAt":"RW"}]}' | bin/roadmap usage push`.
  Stop launching Claude workers at 5h 80% / weekly 85%.
- Follow-ups sent to an existing worker (SendMessage) are NOT registered by the hook: run
  `bin/roadmap job start "<model>: <task> follow-up" <model> <TASK>` before sending, and `job done` after. Keep the
  number of running jobs at the wave size: when one finishes, launch the next free package in the same turn.
- Never idle: when a worker returns, verify -> commit -> push -> launch the next free task in the same turn.

## Planner-only rules (person, 2026-10-16, H182; override older model rules)
- The head is a PLANNER, never a worker: no code edits, no big file reads, no long audits by the head itself.
  Head reads only short outputs (diff --stat, test tails, worker reports <=10 lines).
- Allowed models (cost/score chart CursorBench 4.0): Haiku 5.5 = default worker (best score per $); Sonnet 5.5
  low/medium for multi-file logic or hard UI; Opus 5.5 low/medium only for design/review advice; agy (Gemini 3.8
  Flash, UNLIMITED, zero Claude tokens) as much as possible. No Fable, no high effort.
- agy-first: every read-only job (audit, survey, search, summary, research of OSS libs, doc drafts, review tables,
  UI string/aria checks) goes to agy; Haiku verifies 2-3 rows. Edits by Haiku (1-3 files) or Sonnet (wider).
  Learn: log in docs/AGY-PLAYBOOK.md which agy jobs were good/bad after each verify.
- Budget: Claude usage cap per head run is given by the person (default: stop at +8% weekly over the reading at
  start; run of 2026-10-16: 15% weekly per H202). Check get_usage each wave; at the cap: stop launching Claude workers, agy may continue.
- Workers run only their module tests; the head runs the full suite once per wave (parallel full suites hang).
- Worker prompts must forbid git stash/checkout --/reset (a worker stashed the shared tree 2026-10-16).
- Conflicts: before each launch list running jobs (`bin/roadmap job list`) and their file lists; never two workers on
  one file; never duplicate a running/done task; commit only verified files by path; pull --rebase before push.
- agy 401 UNAUTHENTICATED mid-run = OAuth token expiry (transient); agy-queue retries it (split_net fix 2026-10-16).
- agy-queue.py registers its own jobs: do NOT also run `job start` for them.
- agy policy (person approved, H189): agy only for read-only surveys; every result verified by Haiku/Sonnet before
  fixes build on it; AGY_MAX<=4; small inputs (<=300 lines, no big jsonl); queue retries 401/EOF; if an agy job
  runs >20 min, kill it and hand the job to Haiku (H197: long agy jobs wasted 2h). agy only for small jobs
  (<=8 files, text only, no screenshots).
- Cursor OFF (H193, 2026-10-16): Cursor is at ~99% of its limit; no Cursor jobs until the person says it reset.
  The stop hook's 'cursor idle' hint must be ignored. Reviews go to agy (verified) or Sonnet low.
- UI/UX testing (H196): one Haiku tester per section following docs/ux/TESTER-RECIPE.md (UI-CHECKLIST +
  ui-ux-pro-max UX search + Vercel web-interface-guidelines); test -> fix -> re-screenshot; head looks at the live page.
- UI redesign = Sonnet low with a concrete spec written from the head's own look at the live page; Haiku only for
  small fixes (H200: a Haiku Inbox pass left full-width buttons and dead space).
- Workers commit with `git commit <their paths>` (pathspec form) or check `git diff --cached --name-only` first:
  parallel workers' staged files got swallowed into other commits twice (2026-10-16).
- Questions: ask the person all questions ONCE at the start (short, options), then decide alone (they go AFK).

## /head (resume, first thing in a new chat)
0. Gate (first step, always): if this folder is not registered as a Helm project, or its board is empty/new, STOP and tell the user to run `/helm` instead. Do not set anything up here (no `roadmap init`, no hooks, no service).
0b. Maintainer re-init only (a registered board that is broken; never for new users): `roadmap init` (registers, empty board, hooks, service; idempotent), open the dashboard.
1. `cd` to the project; read `CLAUDE.md`, `docs/HANDOVER.md`, `docs/HEAD-RUNBOOK.md` (nothing else yet).
1b. Always (every resume, not just first run): from the Helm repo root (the folder that holds `bin/roadmap`), run `bin/roadmap hooks status <project-id>`; if anything is missing, run `bin/roadmap hooks install <project-id>` (merges into the project's `.claude/settings.local.json`; idempotent, safe even if already installed). `<project-id>` = the project the person is working in (from cwd or context), never hardcoded.
1c. Always (every resume): check `<project>/docs/roadmap.config.json` for `"headCapture": true` (R11.157: a project
    missing this file, or with it false/absent, silently gets NO hook-based claim and NO prompt logging — the
    UserPromptSubmit/SessionStart/Stop hooks fail-open and do nothing, so the board shows "Head: not claimed" and
    "Nothing logged yet" even though the hooks themselves are installed and firing fine for job registration). If
    missing or false, create/merge it to `{"v": 1, "headCapture": true}` (preserve any other existing keys) before
    continuing. This is a plain project-config toggle, not a code or product edit, so the head may write it directly.
2. `git status -sb`, `git log --oneline -5`; list WIP (uncommitted files = a worker was cut off: inspect the diff, finish or
   revert with the person's OK). Run the test command from CLAUDE.md once.
3. Check the board (`bin/roadmap status` or the project's equivalent) and usage vs the stop limit.
   Head rule: log every person message (`head log`), triage and bind it to tasks in the same turn (`head t <id> --kind K --sum S --bind task:ID`; create the task if none), keep it current. Then actually RUN `bin/roadmap head claim --model "<model>"` now (not just note that it should happen — R11.157 found a split-net session that skipped this step while believing it had run it, so the project never got a claim record at all) and `bin/roadmap head brief --gate`: open asks and what the head is missing (idle cursor/agy, free tasks) come from the ledger, not memory. On /head save also run `head brief` and list new rules/decisions as asks.
4. Then act as head: launch every non-overlapping task in parallel (Haiku edits; agy audits + Cursor reviews when the VPN
   is on; Opus low effort only for design/review), verify each result, register jobs, close with tokens, commit, push,
   show the board. Do not idle, do not ask permission per step. Honour any "stop" the person gave.
5. Stop and report when usage reaches the limit, or an API session-limit error appears (workers die mid-edit: check
   `git status` for WIP after it).

## /head status
Short state: running jobs, WIP files, last commit, tests, usage. Nothing is launched.

Rules: answers short and spartan; never touch the person's browser tabs or live service port; workers get strict file
lists and stage only their own files.
