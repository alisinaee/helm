Read-only pass on architecture, writers, locks, and sync. Findings stay in this chat — no plan file.

The board is a request server over many JSON files. Nothing inside the service watches, continues work, or stops two workers from doing the same task. Reliability needs a single transactional store and a supervisor loop. The browser and the command registry can stay.

## 1. Reliability risks

1. **No watcher.** `ThreadingHTTPServer` (`roadmap/http/server.py`) only acts on HTTP. `roadmap watch` (`roadmap/commands/watch.py:53`) is a CLI poll the model must remember to run. Hook reap runs only when a hook fires (`roadmap/services/hooks.py:92`). A dead worker with no later hook stays `running`.

2. **Status drift is the steady state after a good job.** Task states are `todo|partial|done|hold` (`roadmap/services/commands.py:33`). `job start` moves `todo` to `partial` (`roadmap/services/jobs.py:156`). `job done` leaves `partial` (`roadmap/services/jobs.py:199`). Only `failed` returns the task to `todo` (`roadmap/services/jobs.py:207`). `bind_commit` never changes task status (`roadmap/services/jobs.py:124`). `fold_asks` closes an ask only when every bound task is `done` (`roadmap/services/head.py:418`). A finished job therefore leaves the task looking in progress and the ask open. The snapshot then paints a linked task `running` only while a job is `running` (`roadmap/core/snapshot.py:190`). Three clocks: task file, job file, derived head status (`roadmap/core/head.py:172`).

3. **Lock is per call, not per fact.** `flock` on the directory fd waits 10s (`roadmap/store/lock.py:30`). It is not re-entrant (`roadmap/services/commands.py:7`). `commands.run` writes the record, drops the lock, then appends `activity.jsonl`, then `undo.jsonl` (`roadmap/services/commands.py:811`). A crash or a second writer in that gap leaves the board and the log disagreeing. JSONL append (`roadmap/store/jsonl.py:15`) and trim-rewrite (`roadmap/store/jsonl.py:62`) share no lock of their own. Hand edits and shell writers bypass the flock (`docs/ARCHITECTURE.html` weak spot 3).

4. **Revision is a stat hash, and it misses files.** `loader.revision` hashes path, mtime, and size (`roadmap/services/loader.py:52`). It stamps `head.jsonl` and omits `head-text.jsonl`, `head-spool.jsonl`, `head-gate.json`, and `undo.jsonl` (`roadmap/services/loader.py:23`). A reply or a spooled capture does not change the ETag (`roadmap/http/routes.py:151`). `revision()` and `_build()` are two reads (`roadmap/services/loader.py:91`), so one cached snapshot can mix two generations. The UI polls every 2s, 30s when hidden (`web/js/app.js:27`, `roadmap/http/routes.py:211`). All Projects skips a project whose summary rev matches (`web/js/app.js:239`). Screens agree only after the next poll that notices a stamped file.

5. **Duplicate asks are suggestions, and the suggestion is dropped on the wire.** Jaccard ≥ 0.6 on the summary, never a block (`roadmap/core/head.py:22`, `roadmap/core/head.py:286`). `fold` stores `{id, score}`. `head_row` sends `dup` as the id string (`roadmap/core/snapshot.py:260`). The Head screen merges only when `row.dup.id` is set (`web/js/views/head.js:485`). The Merge control never appears. Capture under a busy lock uses `os.urandom` as the nonce (`roadmap/services/head.py:309`). Adopt skips a replay only when that nonce is already in `head.jsonl` (`roadmap/services/head.py:257`). A direct `capture` stores hash `h` and still appends a new id (`roadmap/services/head.py:294`). Same sentence, two Hn rows, two tasks if the head triages both.

6. **Two jobs on one task are allowed.** `start_job` always appends (`roadmap/services/jobs.py:103`). Plan apply rejects a repeated id inside one input (`roadmap/services/tasks.py:277`). Nothing fingerprints title. A detector with no task id is skipped (`roadmap/services/hooks.py:1076`), so that work never exists on the board.

7. **File ownership is empty at runtime.** Commit refusal reads `job["files"]` (`roadmap/services/gitops.py:185`). `start_job` never writes `files`. The check at `roadmap/services/gitops.py:234` therefore sees no owners. Disjoint files live in the runbook, not in the service. Conflict shows up at commit time, after both workers have edited.

`docs/HEAD-AGENT-V2.md` is design-only. `head next` is not a command. A cheap model is still the scheduler, and it forgets.

## 2. Stack

Stdlib Python, atomic JSON (`roadmap/store/atomic.py`), and ETag polls fit one person and a low write rate. They miss this bar: one live truth, no duplicate work, a process that continues tasks, leases that hold for the whole job.

Keep the service, the op registry, and the web app. Replace the database. SQLite WAL is the single store: one transaction for task, job, head, activity, and lease. An append-only `events` table in that same transaction is the audit log. Tables are the projection. Writable JSON beside SQLite would bring the split back. Export JSON only as a backup.

Server-sent events on one generation counter replace the 2s poll for the open project. Keep the ETag GET as the fallback for a dropped stream. A supervisor thread inside `serve` reaps, folds, expires leases, and queues the next action. The model runs printed commands. It does not decide what is already running.

## 3. Target and migration

```
hooks/CLI/UI → POST /cmd (idempotency key)
            → one SQLite transaction (projection + event)
supervisor thread: reap, fold, leases, next-action queue
GET /events (SSE rev) → app.js; poll stays as fallback
```

Each package ships with its own tests and leaves the others runnable.

- **P1 store.** `roadmap/store/db.py`, `roadmap/store/migrate.py`. Import current JSON once. Tests: two writes roll back together; two processes, one commit.
- **P2 events.** `events` row in the same transaction as the projection. Tests: replay rebuilds the same rows.
- **P3 rev.** Integer generation on every commit. Stamp text, spool, gate, and undo. Fix `head_row` so `dup` is `{id, score}`. Tests: a reply bumps rev; Merge sees `dup.id`.
- **P4 supervisor.** `roadmap/services/supervisor.py`, started from `roadmap/http/server.py`. Reap stale jobs, fold asks, single-flight per task. Tests: `job done` clears `partial`; a second start on that task conflicts; a dead watch file fails the job without a new hook.
- **P5 leases.** `job start` requires `files`. Table `path → job` until done, fail, or expiry. `git commit` and the launch path both read it. Tests: overlap refused; launch with an empty file list refused.
- **P6 idempotency.** Command key, task fingerprint, capture hash. Tests: retry returns the same id; exact title does not create a second task.
- **P7 priority.** Column on asks and tasks, set in code at capture. Tests: an urgent line outranks an older normal ask.
- **P8 sync.** `GET /api/v1/events`, `web/js/app.js` subscribes. Tests: a write wakes the subscriber with the new rev.
- **P9 `head next`.** Implement the loop in `docs/HEAD-AGENT-V2.md` against the database. Tests: at most 15 lines, each line an exact command.

P1–P4 are the reliability core. P5–P7 are duplicates, conflicts, and priority. P8–P9 are live screens and a head that stays smart on a cheap model.

## 4. Duplicates and conflicts

- **Command key.** `Idempotency-Key` on `POST /api/v1/cmd` and on CLI. Same key and same body returns the first result. Same key and a different body conflicts.
- **Ask fingerprint.** `sha256` of normalized text. A second capture with the same hash links to the open Hn and bumps its priority. It does not allocate a new id. Jaccard stays a suggestion for near misses.
- **Task fingerprint.** Normalized title plus phase. Create returns the existing id when the fingerprint is open.
- **Job single-flight.** One `running` job per task id. A repeat start returns that job id.
- **Lease.** `path → job id`, exclusive, taken inside the start transaction, released on done, fail, or supervisor expiry. Overlap refuses the start. Commit checks the same table. A job with no files cannot launch.

## 5. Priority

Features already have `prio` 1–3 (`roadmap/core/planfmt.py:269`). Tasks and asks have none. Head order is newest-first. The runbook’s “priority” is which section to work, not a field.

Store `prio` on the ask at capture, in code: `P0` for urgent, asap, blocker, or “do this first”; `P1` for this session; `P2` normal; `P3` for later or backlog. On triage, copy that value onto the task, keeping the higher one. The supervisor orders `head next` as P0, then needs-you, then amber age, then P1, and it skips a task whose files are leased. The model may set `head set Hn prio=0` as an event. It does not invent priority in prose.

