# Head v3 plan (R7.82)

Joint result: Cursor grok xhigh analysis (docs/reviews/cursor-v3-analysis.md) + head spot-check of the code.
Goal: one live truth, no duplicate work, a core supervisor that continues tasks, file leases, priority from the
Head chat, a head that stays smart on a cheap model. Stdlib Python, light.

## 1. Diagnosis: top 10 risks (verified file:line)

1. No watcher. The service only answers HTTP; reap runs when a hook fires (services/hooks.py:92); `roadmap watch`
   is a CLI poll the model must remember. A dead worker with no later hook stays `running`.
2. Task status drift. `job start` marks todo -> partial (services/jobs.py:107, :156). `job done` leaves it partial;
   only `failed` resets (jobs.py:200). Nothing sets a task `done` from a job or commit (only asks: head.py:432).
3. Ask never closes after good work: fold_asks closes only when every bound task is `done` (head.py:418), which
   (2) never produces. Three clocks: tasks.json, jobs.json, derived head status.
4. Write is not one fact. commands.run writes the record, then appends activity, then undo outside one unit
   (commands.py:826-837). A crash between them splits board and log. JSONL trim and append share no lock.
5. Many writers on jobs.json (hooks, CLI, gitops, tools/*-job.sh, hand edits) - ARCHITECTURE weak spot 3.
6. Revision misses files: BASE_FILES + head.jsonl + rules only (loader.py:23, :62). head-text, spool, gate, undo
   do not bump the ETag, so a reply can be invisible until another file changes. revision() and _build() are two
   reads (loader.py:91), so a cached snapshot can mix generations.
7. Duplicate asks: Jaccard >= 0.6 is a suggestion only (core/head.py:286). snapshot.py:261 sends `dup` as a bare
   id string, the Head view needs `row.dup.id` (views/head.js:486): the Merge button never shows (1-line bug).
8. Duplicate captures: a spooled capture gets a random nonce (head.py:309); a direct capture appends a new Hn even
   for the same text hash. Same sentence -> two asks -> two tasks.
9. Two jobs on one task allowed: start_job always appends (jobs.py:104). No title fingerprint on tasks.
   A detector line with no task id is dropped (hooks.py:1076), so that work is invisible.
10. File ownership empty: gitops._owners reads job["files"] (gitops.py:185) but start_job never writes `files`;
   conflicts appear at commit time, after both workers edited. Polling is 2 s / 30 s (app.js:27).

## 2. Stack decision

| Topic | Decision | Why |
|---|---|---|
| Store | SQLite WAL, one file `docs/board.db` (stdlib sqlite3), `BEGIN IMMEDIATE` per command | one transaction for task+job+ask+lease+event; cross-process safe; no flock gaps |
| JSON files | Read-only export (`roadmap export`, deterministic, sorted) after each commit; import once by `migrate` | git diff + cross-account handover keep working; no second writable truth |
| Event log | `events` table, appended in the same transaction; tables are the projection (truth) | audit, undo, SSE rev; no full event-sourcing rebuild (too heavy) |
| Revision | `events.id` max = integer generation; every write bumps it, incl. head text/spool/gate | one counter for every screen |
| Push | SSE `GET /api/v1/stream?since=rev`, 25 s keepalive; poll fallback 10 s | ThreadingHTTPServer handles a few long-lived clients; stdlib only |
| Supervisor | thread inside `serve` + `roadmap tick` one-shot when serve is down; single-runner via `leases(name='supervisor')` heartbeat | always on, never two supervisors |
| Hooks | write only via the op registry (short sqlite txn, busy_timeout 5 s); on busy -> spool table row, never a file | no lost captures |

## 3. Supervisor loop

Tick every 5 s (and on each commit event):
1. Reap: job heartbeat older than 3 min (or watch file/pid gone) -> `failed(reason=lost)`; leases released.
2. Lease expiry: lease past `expires` with no heartbeat -> release, event `lease.expired`.
3. Fold: job done + commit bound -> task `done`; job done without commit -> task `verify` (derived badge, not a
   new stored status); asks whose tasks are all done -> closed (`by: auto`).
4. Queue: ready tasks = todo, deps done, files not leased, budget guard (A1) ok, usage below stops.
   Order: P0, needs-you, amber age, P1, P2, P3; ties oldest first.
5. Continue: when autonomy is on, launch the top ready item through services/launcher.py with an idempotency key
   `task:<id>:try:<n>`; else write it to `head next` output only.

Job lifecycle: `queued -> claimed -> running (heartbeat 60 s) -> done | failed`; retry: max 2, backoff 2/10 min,
only for reason in {lost, unavailable}; third failure -> `needs-you`.
- Claim = one txn: assert no `running` job on the task (single-flight; a repeat start returns the same job id),
  insert leases for every file in `files`, insert job. Any overlap -> refuse with the owner job id.
- `files` required at start (empty -> refuse, except role=review/audit which takes no lease).
- Idempotency: `Idempotency-Key` on POST /cmd and `--key` on CLI; table `idem(key, body_hash, result)`; same key +
  same body -> first result; different body -> conflict.
- Fingerprints: ask = sha256(normalized text) (open ask with same fp -> link, bump prio, no new Hn); task =
  sha256(norm title + phase) (create returns existing open id). Jaccard stays a near-miss suggestion.
- Crash safety: every state change is one txn; supervisor restart rebuilds from tables; no in-memory queue.
- Commit check (gitops) reads the same leases table; a file staged by a job that does not lease it -> refuse.

## 4. Priority model (P0-P3) from the Head chat

- Set in code at capture (core/head.py), never by model prose:
  P0: urgent, asap, now, blocker, broken, "first", "top priority"; P1: today, this session, next;
  P3: later, someday, backlog, nice to have, maybe; else P2.
- Same-fingerprint repeat capture -> raise by one level (repeat = the person cares).
- Triage copies ask prio to tasks (keep the higher). `head set Hn prio=0` / task `prio` op = event, undoable.
- UI: a fixed-width P column (UI rule 0) on Head, Work, Overview; P0 rows sort first everywhere.

## 5. Sync design

- Server: every txn returns `rev`; events carry `{rev, kind, ids}`. SSE sends `rev` + changed ids only.
- Client (app.js): one EventSource per tab; on event -> `GET /snapshot?since=rev` returns changed rows only
  (or full when gap > 500 events); views patch rows by key (R7.80 keyed rows) - no full re-render.
- All Projects: one stream for summaries; per-project rev in each summary.
- Fallback: stream down -> 10 s ETag poll on the integer rev; reload on new build id (weak spot 8).
- Every screen reads the same projection at the same rev: snapshot built inside one read txn (fixes risk 6).

## 6. Migration packages (ordered; disjoint files; Haiku workers unless marked)

Wave 0 - hotfixes on the current stack (parallel, tiny):
- H1 snapshot.py:261 send `dup` as `{id, score}`. Test: Merge button rendered for a dup row. (Haiku)
- H2 jobs.py finish_job: done -> task stays partial but sets `verify`; commit bind -> done. Test in
  tests/unit/test_jobs_fold.py. (Haiku; Opus review)
- H3 loader.py: stamp head-text, spool, gate, undo in revision. Test: reply bumps rev. (Haiku)

Wave 1 - store core (serial, Opus review each):
- P1 `roadmap/store/db.py` (connect, WAL, schema, txn ctx) + `roadmap/store/migrate.py` (JSON -> db, idempotent).
  Tests: tests/unit/test_db.py - two writes roll back together; two processes, one wins; migrate twice = same.
  OPUS + CURSOR REVIEW.
- P2 `roadmap/store/events.py` (append in txn, rev, since-query). Tests: rev strictly increases; events per txn.
- P3 `roadmap/store/export.py` deterministic JSON export. Test: export == golden for fixtures/demo.

Wave 2 - services onto the db (parallel; each owns its files):
- W1 services/jobs.py + tests/unit/test_jobs_db.py: claim/single-flight/files required. OPUS REVIEW.
- W2 services/tasks.py + services/commands.py: run() in one txn with activity + undo. Tests: crash mid-op leaves
  nothing. OPUS REVIEW.
- W3 services/head.py + store/head*: captures, spool table, ask fingerprint. Tests: same text twice -> one Hn.
- W4 services/loader.py + core/snapshot.py: snapshot in one read txn, integer rev. Tests: same rev same bytes.
- W5 services/gitops.py: owners from leases table. Test: commit by non-owner refused.

Wave 3 - supervisor and leases:
- S1 `roadmap/services/supervisor.py` + `roadmap/services/leases.py` + tests/unit/test_supervisor.py: reap, expiry,
  fold, queue order, retry/backoff, single runner. OPUS + CURSOR REVIEW (core reliability).
- S2 roadmap/http/server.py start/stop thread; `roadmap tick` command (roadmap/commands/tick.py). Test: tick
  without serve does one full pass.
- S3 services/hooks.py: writes via ops only; heartbeat on tool hooks; no-task-id lines -> `untracked` ask row.

Wave 4 - priority and dedupe:
- Q1 core/head.py prio rules + `head set prio`. Tests: phrase table -> P0..P3; repeat bumps.
- Q2 idempotency table + `--key` in CLI and routes.py. Tests: retry same id; changed body conflicts.
- Q3 task fingerprint in tasks.py create. Test: same title+phase returns existing id.

Wave 5 - sync and head:
- U1 roadmap/http/routes.py `/stream` SSE + `snapshot?since`. Test: write wakes a subscriber with new rev.
- U2 web/js/app.js + web/js/api.js EventSource, row patching, poll fallback. Check: make check-ui. CURSOR REVIEW.
- U3 web/js/views/{head,work,overview}.js P column (UI-CHECKLIST). (Haiku; Opus design glance)
- N1 `head next` (roadmap/commands/head.py): reads supervisor queue, prints <= 15 lines of exact commands.
  Test: output lines are runnable ops. This makes a cheap model a good head: it executes, never schedules.

Done-check for every package: `python3 -m unittest discover -s tests -t . -q`, `make check`; UI ones `make check-ui`.
Workers: temp ROADMAP_HOME, never port 8780, no serve/service commands, stage own files by path.

## Cursor analysis: agreements, disagreements, decisions

Agreements (verified): no watcher; status drift (jobs.py:107/200, head.py:418); lock gap in run (commands.py:826+);
revision misses head-text/spool/gate/undo (loader.py:23/62); dup sent as string (snapshot.py:261 vs head.js:486);
random spool nonce (head.py:309); start_job always appends (jobs.py:104); empty `files` (gitops.py:185);
SQLite WAL single store; events in same txn; SSE + poll fallback; supervisor thread; P0-P3 set in code.

Disagreements and decisions:
1. Cursor: "JSON only as backup". Decision: deterministic JSON export after every commit stays git-tracked, because
   handover across accounts/machines and code review read docs/*.json. Read-only; import only via migrate.
2. Cursor P2 test "replay rebuilds same rows". Decision: drop full replay (heavy); events serve audit, undo, rev.
3. Cursor: job done should clear partial. Decision: done without commit -> derived `verify`; done only via
   commit bind or person accept, so "done" means verified, not "the agent said so".
4. Cursor: supervisor only in serve. Decision: also `roadmap tick` one-shot + DB heartbeat lease, so a stopped
   service never stops reaping and two supervisors never run.
5. Cursor ordering P1..P9. Decision: Wave 0 hotfixes first (dup bug, status fold, revision stamps) - cheap,
   immediate trust gains on the current stack, independent of the migration.
6. Cursor: lease refuses empty files. Decision: same, except review/audit roles (read-only) take no lease.
7. Added beyond Cursor: retry policy with backoff and a needs-you cap; untracked detector lines become asks
   instead of being dropped; reload on new build id.
