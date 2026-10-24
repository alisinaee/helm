"""Supervisor: one tick() pass over the project store (docs/roadmap.db). Idempotent and safe to run from several
processes at once: a meta row holds a lock with an expiry, so only one pass works at a time, and a pass with
nothing due changes nothing.

Steps, each state change in its own transaction with its event:
  1 reap: running jobs with no heartbeat for HEARTBEAT_TTL_S -> failed ("no heartbeat"); leases freed.
  2 leases: leases past their expiry (or whose job is gone) are dropped.
  3 retry: a failed job whose cause is lost ("no heartbeat") or engine unavailable is re-queued on the same task as a
    queued job (max MAX_RETRIES retries, backoff 2 min then 10 min). Any other failure, and a job whose retries are
    used up, sends the task's asks to needs-you.
  4 fold: tasks whose latest done job carries a commit ref, and whose other jobs are done or superseded by a later
    done job -> done; open asks whose tasks are all done -> closed by auto, with the commit shas in the note.
next_launches() picks the queued jobs to start next: priority P0..P3 (default P2), then age, skipping jobs whose
task already runs or whose files are leased. Each pick is reserved in the caller's transaction: its status goes
queued -> claimed and its files are leased. Not wired into the service yet (S2 does that).
"""

import datetime
import json
import logging
import math
import time
import uuid

from roadmap.services import head, jobs, jobs_db, leases
from roadmap.store import db, events

HEARTBEAT_TTL_S = 180.0
MAX_RETRIES = 2
BACKOFF_S = (120.0, 600.0)
LOCK_KEY = "supervisor.lock"
LOCK_TTL_S = 60.0
PRIORITIES = ("P0", "P1", "P2", "P3")
DEFAULT_PRIO = "P2"
HAND_STATUSES = ("merged", "declined", "needs-you", "done")
LOST_REASON = "no heartbeat"
DONE_EXCLUDED = ("done", "cancelled")
LIVE_JOB_STATUSES = ("running", "claimed")

if leases.DEFAULT_TTL_S < HEARTBEAT_TTL_S:  # a lease must outlive a live job's heartbeat window
    raise RuntimeError("leases.DEFAULT_TTL_S must be at least HEARTBEAT_TTL_S")

_log = logging.getLogger(__name__)


def _now(now):
    return time.time() if now is None else float(now)


def _iso(epoch):
    return datetime.datetime.fromtimestamp(epoch).astimezone().isoformat(timespec="seconds")


def _epoch_of_iso(text):
    try:
        return datetime.datetime.fromisoformat(str(text)).timestamp()
    except (TypeError, ValueError):
        return None


def _beat_epoch(value):
    """Epoch seconds of a heartbeat value (a number, or numeric or ISO text); None when it is none of these."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        text = str(value).strip()
        try:
            number = float(text)
        except ValueError:
            return _epoch_of_iso(text)
    return number if math.isfinite(number) else None


def _prio_rank(job):
    prio = str(job.get("prio") or DEFAULT_PRIO)
    return PRIORITIES.index(prio) if prio in PRIORITIES else PRIORITIES.index(DEFAULT_PRIO)


def _commit_shas(data):
    return [str(r)[len("commit:"):][:7] for r in (data or {}).get("refs") or [] if str(r).startswith("commit:")]


def _retryable(reason):
    """A failure is retried only when its cause is lost (no heartbeat) or the engine is unavailable."""
    text = str(reason or "")
    return text == LOST_REASON or bool(jobs._UNAVAILABLE_RE.search(text))


def _set_task_status(conn, task_id, status):
    row = conn.execute("SELECT data FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if row is None:
        return
    data = json.loads(row["data"])
    data["status"] = status
    conn.execute("UPDATE tasks SET status = ?, data = ? WHERE id = ?",
                 (status, json.dumps(data, sort_keys=True), task_id))
    events.append(conn, "task.status", "task", task_id, {"status": status, "by": "supervisor"})


def _reset_partial(conn, task_id):
    """A failed job ends its task's 'partial' (doing) state when no other job still runs on it."""
    if task_id is None or conn.execute("SELECT 1 FROM jobs WHERE task = ? AND status = 'running'",
                                       (task_id,)).fetchone():
        return
    row = conn.execute("SELECT status FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if row is not None and row["status"] == "partial":
        _set_task_status(conn, task_id, "todo")


def _reap(conn, now):
    reaped = []
    rows = conn.execute("SELECT data FROM jobs WHERE status = 'running' ORDER BY rowid").fetchall()
    for row in rows:
        job = json.loads(row["data"])
        if job.get("heartbeat") is not None:
            beat = _beat_epoch(job["heartbeat"])
            if beat is None:
                _log.warning("supervisor: job %s has a bad heartbeat %r; skipped", job.get("id"), job["heartbeat"])
                continue
        else:
            beat = _epoch_of_iso(job.get("started"))
        if beat is None or now - beat <= HEARTBEAT_TTL_S:
            continue
        job.update({"status": "failed", "ended": _iso(now), "failed_at": now, "reason": LOST_REASON})
        jobs_db._save(conn, job)
        leases.release(conn, job["id"])
        events.append(conn, "job.failed", "job", job["id"], {"reason": LOST_REASON, "task": job.get("task")})
        _reset_partial(conn, job.get("task"))
        reaped.append(job["id"])
    return reaped


def needs_you_tasks(conn):
    """Task ids marked needs-you by an escalation, read from the store with SQL (no migration needed)."""
    rows = conn.execute("SELECT id FROM tasks WHERE json_extract(data, '$.needs_you') = 1 ORDER BY rowid")
    return [r["id"] for r in rows.fetchall()]


def _task_needs_you(conn, task_id, job_id):
    """The task's open asks go to needs-you (hand-set status, so fold leaves them alone)."""
    row = conn.execute("SELECT data FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if row is not None:
        data = json.loads(row["data"])
        data["needs_you"] = True
        conn.execute("UPDATE tasks SET data = ? WHERE id = ?", (json.dumps(data, sort_keys=True), task_id))
    link = "task:" + task_id
    for ask in conn.execute("SELECT seq, id, data FROM asks WHERE t = 'e' ORDER BY seq").fetchall():
        body = json.loads(ask["data"])
        if link not in (body.get("links") or []) or body.get("status") in HAND_STATUSES:
            continue
        body.update({"status": "needs-you", "by": "supervisor"})
        conn.execute("UPDATE asks SET data = ? WHERE seq = ?", (json.dumps(body, sort_keys=True), ask["seq"]))
        events.append(conn, "ask.needs_you", "ask", ask["id"], {"task": task_id, "job": job_id})
    events.append(conn, "task.needs_you", "task", task_id, {"job": job_id})


def _escalate(conn, job, task, needs_you):
    job["escalated"] = True
    jobs_db._save(conn, job)
    _task_needs_you(conn, task, job["id"])
    needs_you.append(task)


def _later_done(conn, task, seq):
    row = conn.execute("SELECT 1 FROM jobs WHERE task = ? AND status = 'done' AND rowid > ?", (task, seq)).fetchone()
    return row is not None


def _retry(conn, now):
    queued, needs_you = [], []
    rows = conn.execute("SELECT rowid AS seq, data FROM jobs WHERE status = 'failed' ORDER BY rowid").fetchall()
    for row in rows:
        job = json.loads(row["data"])
        task = job.get("task")
        if not task or job.get("retried_by") or job.get("escalated") or _later_done(conn, task, row["seq"]):
            continue
        attempt = int(job.get("attempt") or 1)
        if not _retryable(job.get("reason")) or attempt > MAX_RETRIES:
            _escalate(conn, job, task, needs_you)
            continue
        failed_at = job.get("failed_at")
        if failed_at is None:
            failed_at = _epoch_of_iso(job.get("ended"))
        failed_at = now if failed_at is None else float(failed_at)
        wait = BACKOFF_S[min(attempt - 1, len(BACKOFF_S) - 1)]
        new_id = jobs_db._next_id(conn)
        new = {"id": new_id, "title": job["title"], "model": job["model"], "task": task, "status": "queued",
               "started": None, "ended": None, "kind": job.get("kind") or "edit",
               "files": list(job.get("files") or []), "prio": job.get("prio") or DEFAULT_PRIO,
               "attempt": attempt + 1, "retry_of": job["id"], "queued_at": now,
               "not_before": failed_at + wait}
        if job.get("worker"):
            new["worker"] = job["worker"]
        jobs_db._save(conn, new)
        job["retried_by"] = new_id
        jobs_db._save(conn, job)
        events.append(conn, "job.queued", "job", new_id, {"task": task, "retry_of": job["id"],
                                                         "attempt": attempt + 1, "not_before": new["not_before"]})
        queued.append(new_id)
    return queued, needs_you


def _fold_tasks(conn):
    """A task is done when its latest done job carries a commit ref (bound to this task's own jobs) and every other
    job of the task is done, cancelled, or a failure superseded by a later done job."""
    done = []
    rows = conn.execute("SELECT id FROM tasks WHERE status != 'done' ORDER BY rowid").fetchall()
    for row in rows:
        task_id = row["id"]
        jobs_of = conn.execute("SELECT rowid AS seq, status, data FROM jobs WHERE task = ? ORDER BY rowid",
                               (task_id,)).fetchall()
        dones = [r["seq"] for r in jobs_of if r["status"] == "done"]
        if not dones:
            continue
        last_done = max(dones)
        bound = any(_commit_shas(json.loads(r["data"])) for r in jobs_of if r["status"] == "done")
        if not bound:
            continue
        blocking = [r for r in jobs_of if r["status"] not in DONE_EXCLUDED
                    and not (r["status"] == "failed" and r["seq"] < last_done)]
        if blocking:
            continue
        _set_task_status(conn, task_id, "done")
        done.append(task_id)
    return done


def _work_states(data_dir):
    """(states, owner) of the Work items for the ask fold; empty when there is no readable work.json."""
    if data_dir is None:
        return {}, {}
    from roadmap.services import work
    try:
        return work.head_states(data_dir)
    except Exception:
        return {}, {}


def _fold_asks(conn, data_dir=None):
    from roadmap.services import work
    work_states, owner = _work_states(data_dir)
    tasks = {r["id"]: (r["status"], json.loads(r["data"]))
             for r in conn.execute("SELECT id, status, data FROM tasks").fetchall()}
    closed = []
    for ask in conn.execute("SELECT seq, id, data FROM asks WHERE t = 'e' ORDER BY seq").fetchall():
        body = json.loads(ask["data"])
        if body.get("status") in HAND_STATUSES:
            continue
        verdict = work.ask_close(body.get("links") or [], work_states, owner)
        if verdict is not None:  # bound to a Work item: closes only when it is accepted or Won't do
            if verdict[0]:
                body.update({"status": "done", "by": "auto", "note": verdict[1]})
                conn.execute("UPDATE asks SET data = ? WHERE seq = ?", (json.dumps(body, sort_keys=True), ask["seq"]))
                events.append(conn, "ask.closed", "ask", ask["id"], {"by": "auto", "note": verdict[1]})
                closed.append(ask["id"])
            continue
        ids = [str(ref)[len("task:"):] for ref in body.get("links") or [] if str(ref).startswith("task:")]
        if not ids or any(tasks.get(t, (None,))[0] != "done" for t in ids):
            continue
        parts = []
        for task_id in ids:
            shas = _commit_shas(tasks[task_id][1])
            parts.append(", ".join(task_id + " " + s for s in shas) if shas else task_id)
        note = "auto: " + ", ".join(parts)
        body.update({"status": "done", "by": "auto", "note": note})
        conn.execute("UPDATE asks SET data = ? WHERE seq = ?", (json.dumps(body, sort_keys=True), ask["seq"]))
        events.append(conn, "ask.closed", "ask", ask["id"], {"by": "auto", "note": note})
        closed.append(ask["id"])
    return closed


def _take_lock(conn, owner, now):
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (LOCK_KEY,)).fetchone()
    if row is not None:
        held = json.loads(row["value"])
        if held.get("owner") != owner and float(held.get("until", 0)) > now:
            return False
    value = json.dumps({"owner": owner, "until": now + LOCK_TTL_S}, sort_keys=True)
    conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (LOCK_KEY, value))
    return True


def _drop_lock(conn, owner):
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (LOCK_KEY,)).fetchone()
    if row is not None and json.loads(row["value"]).get("owner") == owner:
        conn.execute("DELETE FROM meta WHERE key = ?", (LOCK_KEY,))


def _tick_json(data_dir, now=None):
    """The pass for a JSON-store project: only the ask fold runs, through the JSON path (head.fold_asks), so no
    SQLite file is created. Reap and retry act on the SQLite job store and have no JSON counterpart yet."""
    closed = head.fold_asks(data_dir, now=now)
    return {"ran": True, "reaped": [], "expired_leases": [], "queued": [], "needs_you": [], "done_tasks": [],
            "closed_asks": closed}


def tick(data_dir, now=None):
    """One supervisor pass. Returns {"ran": False, "reason": ...} when another pass holds the lock, else
    {"ran": True, "reaped", "expired_leases", "queued", "needs_you", "done_tasks", "closed_asks"} with lists of ids.
    An error in the pass propagates after the lock is released."""
    if head.sqlite_db(data_dir) is None:  # JSON store: never create or read docs/roadmap.db for this project
        return _tick_json(data_dir, now)
    now_s = _now(now)
    owner = uuid.uuid4().hex
    conn = db.open_project(data_dir)
    try:
        with db.txn(conn):
            if not _take_lock(conn, owner, now_s):
                return {"ran": False, "reason": "another supervisor pass holds the lock"}
        try:
            with db.txn(conn):
                report = {"reaped": _reap(conn, now_s), "expired_leases": leases.drop_expired(conn, now_s)}
                report["queued"], report["needs_you"] = _retry(conn, now_s)
                report["done_tasks"] = _fold_tasks(conn)
                report["closed_asks"] = _fold_asks(conn, data_dir)
            report["ran"] = True
        finally:
            with db.txn(conn):
                _drop_lock(conn, owner)
    finally:
        conn.close()
    return report


def next_launches(conn, slots, now=None, work_prio=None):
    """The queued jobs to start next, at most slots of them, best first: priority P0..P3, then age (queued_at),
    then insertion order. Skips a job whose task already runs or is claimed, or whose files are leased or taken by
    an earlier pick. Each pick is reserved in the caller's transaction: its status goes queued -> claimed and its
    files are leased, so the same job is never returned twice. work_prio ({task id: 'P0'..'P3'},
    services/work.task_prios) replaces the job's own prio for a task of a Work item (WORK-MODEL
    section 2).
    Returns job dicts (claimed)."""
    limit = max(0, int(slots))
    if limit == 0:
        return []
    now_s = _now(now)
    placeholders = ",".join("?" for _ in LIVE_JOB_STATUSES)
    busy = {r["task"] for r in conn.execute(
        "SELECT task FROM jobs WHERE status IN (" + placeholders + ") AND task IS NOT NULL", LIVE_JOB_STATUSES)}
    taken = leases.held_files(conn, now_s)
    queued = []
    for row in conn.execute("SELECT rowid, data FROM jobs WHERE status = 'queued' ORDER BY rowid").fetchall():
        queued.append((row["rowid"], json.loads(row["data"])))
    work_prio = work_prio or {}

    def rank(job):
        prio = work_prio.get(job.get("task"))
        return PRIORITIES.index(prio) if prio in PRIORITIES else _prio_rank(job)

    queued.sort(key=lambda item: (rank(item[1]), float(item[1].get("queued_at") or 0.0), item[0]))
    picked = []
    for _, job in queued:
        if len(picked) >= limit:
            break
        if job.get("not_before") is not None and float(job["not_before"]) > now_s:
            continue
        task = job.get("task")
        files = set(job.get("files") or [])
        if (task and task in busy) or (files & taken):
            continue
        if not leases.acquire(conn, job["id"], sorted(files), now=now_s)["ok"]:
            continue
        job["status"] = "claimed"
        job["claimed_at"] = _iso(now_s)
        cur = conn.execute("UPDATE jobs SET status = 'claimed', data = ? WHERE id = ? AND status = 'queued'",
                           (json.dumps(job, sort_keys=True), job["id"]))
        if cur.rowcount != 1:
            leases.release(conn, job["id"])
            continue
        events.append(conn, "job.claimed", "job", job["id"], {"task": task, "by": "supervisor"})
        picked.append(job)
        taken |= files
        if task:
            busy.add(task)
    return picked
