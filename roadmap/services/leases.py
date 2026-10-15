"""File leases in the SQLite store (docs/roadmap.db, table leases): one row per leased file.

A job that edits files takes a lease on each of them before it runs (acquire). A file leased by another live
job refuses the request, and the refusal names that job and the files. heartbeat() extends a job's leases and
its heartbeat time, release() frees them, expired() lists the leases whose time has run out.

Callers run these inside db.txn(); each lease change appends its event in that same transaction. A lease
whose job is no longer running, or whose time has run out, does not block anyone. Not wired into the service
yet (S2 does that).
"""

import json
import time

from roadmap.store import events

DEFAULT_TTL_S = 180.0


def _now(now):
    return time.time() if now is None else float(now)


def _job_status(conn, job_id):
    row = conn.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return None if row is None else str(row["status"])


def _live(conn, row, now):
    """True when a lease row still holds its file: its time has not run out and its job still runs."""
    return float(row["expires"]) > now and _job_status(conn, row["job_id"]) == "running"


def acquire(conn, job_id, files, ttl_s=DEFAULT_TTL_S, now=None):
    """Lease every file for job_id, all or nothing.

    Returns {"ok": True, "files": [...]} when every file is leased. Otherwise returns
    {"ok": False, "job": <first conflicting job id>, "files": [its files], "conflicts": {job: [files]}}
    and writes nothing. Files this job already holds are fine.
    """
    now_s = _now(now)
    wanted = sorted({str(f).strip() for f in files if str(f).strip()})
    conflicts = {}
    for name in wanted:
        row = conn.execute("SELECT job_id, expires FROM leases WHERE file = ?", (name,)).fetchone()
        if row is None or row["job_id"] == job_id or not _live(conn, row, now_s):
            continue
        conflicts.setdefault(row["job_id"], []).append(name)
    if conflicts:
        first = sorted(conflicts)[0]
        return {"ok": False, "job": first, "files": conflicts[first], "conflicts": conflicts}
    expires = now_s + float(ttl_s)
    for name in wanted:
        conn.execute("INSERT OR REPLACE INTO leases (file, job_id, acquired, expires) VALUES (?, ?, ?, ?)",
                     (name, job_id, now_s, expires))
    events.append(conn, "lease.acquired", "job", job_id, {"files": wanted})
    return {"ok": True, "files": wanted}


def heartbeat(conn, job_id, now=None, ttl_s=DEFAULT_TTL_S):
    """Record a heartbeat for job_id: its jobs row gets heartbeat = now and each of its leases expires at
    now + ttl_s. Returns the number of leases extended. No event (heartbeats are frequent)."""
    now_s = _now(now)
    row = conn.execute("SELECT data FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if row is not None:
        job = json.loads(row["data"])
        job["heartbeat"] = now_s
        conn.execute("UPDATE jobs SET data = ? WHERE id = ?", (json.dumps(job, sort_keys=True), job_id))
    cur = conn.execute("UPDATE leases SET expires = ? WHERE job_id = ?", (now_s + float(ttl_s), job_id))
    return int(cur.rowcount)


def release(conn, job_id):
    """Free every lease held by job_id. Returns the number of files freed (an event is written when > 0)."""
    files = [r["file"] for r in conn.execute("SELECT file FROM leases WHERE job_id = ? ORDER BY file", (job_id,))]
    if not files:
        return 0
    conn.execute("DELETE FROM leases WHERE job_id = ?", (job_id,))
    events.append(conn, "lease.released", "job", job_id, {"files": files})
    return len(files)


def expired(conn, now=None):
    """Leases whose time has run out at now, as [{"file", "job_id", "expires"}], sorted by file."""
    now_s = _now(now)
    rows = conn.execute("SELECT file, job_id, expires FROM leases WHERE expires <= ? ORDER BY file",
                        (now_s,)).fetchall()
    return [{"file": r["file"], "job_id": r["job_id"], "expires": float(r["expires"])} for r in rows]


def drop_expired(conn, now=None):
    """Delete the expired leases and append one lease.expired event per job. Returns the files dropped."""
    gone = expired(conn, now)
    by_job = {}
    for item in gone:
        by_job.setdefault(item["job_id"], []).append(item["file"])
        conn.execute("DELETE FROM leases WHERE file = ?", (item["file"],))
    for job_id in sorted(by_job):
        events.append(conn, "lease.expired", "job", job_id, {"files": by_job[job_id]})
    return [item["file"] for item in gone]


def held_files(conn, now=None):
    """Files under a live lease (time not run out, job still running), as a set."""
    now_s = _now(now)
    rows = conn.execute("SELECT file, job_id, expires FROM leases WHERE expires > ?", (now_s,)).fetchall()
    return {r["file"] for r in rows if _job_status(conn, r["job_id"]) == "running"}
