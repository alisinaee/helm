"""Job registry in the SQLite store (roadmap/store/db.py, docs/roadmap.db), used when the switch in
services/jobs.py says sqlite.

start, finish, list and claim. Every write is one IMMEDIATE transaction: the jobs row and its event (events.append)
commit together or not at all. The full job record lives in the data column, shaped like a jobs.json entry.
claim is single-flight per task: while a job runs on the task, a second claim returns that job unchanged.
Files of an edit job are required; only review and audit jobs may claim with no files.
"""

import json
import re

from roadmap.errors import EXIT_CONFLICT, EXIT_NOT_FOUND, EXIT_USAGE, RoadmapError
from roadmap.services import jobs
from roadmap.store import db, events

KINDS = ("edit", "review", "audit")
READ_ONLY_KINDS = ("review", "audit")
_ID_RE = re.compile(r"^j(\d+)$")


def db_path(data_dir):
    return db.db_path(data_dir)


def _open(data_dir):
    jobs._require_data_dir(data_dir)
    return db.open_project(data_dir)


def _load(conn, job_id):
    row = conn.execute("SELECT data FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return None if row is None else json.loads(row["data"])


def _all(conn):
    return [json.loads(row["data"]) for row in conn.execute("SELECT data FROM jobs ORDER BY rowid")]


def _save(conn, job):
    conn.execute(
        "INSERT OR REPLACE INTO jobs (id, task, title, model, status, started, ended, data)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (job["id"], job.get("task"), job["title"], job["model"], job["status"], job.get("started"),
         job.get("ended"), json.dumps(job, sort_keys=True)),
    )


def _next_id(conn):
    nums = []
    for row in conn.execute("SELECT id FROM jobs"):
        match = _ID_RE.match(str(row["id"]))
        if match:
            nums.append(int(match.group(1)))
    return "j" + str(max(nums, default=0) + 1)


def _check_parent(conn, parent):
    text = "" if parent is None else str(parent).strip()
    if not text:
        return None
    if _load(conn, text) is None:
        raise RoadmapError("not_found", "no job with id '" + text + "'", EXIT_NOT_FOUND)
    return text


def _after_finish(data_dir, conn, job, status):
    """The task-file side effects of a finished job, as the JSON backend does them (partial reset, verify flag)."""
    task = job.get("task")
    if not task:
        return
    doc = {"jobs": _all(conn)}
    if status == "failed":
        jobs._reset_partial(data_dir, doc, task)
    else:
        jobs._mark_verify(data_dir, doc, task)


def start(data_dir, title, model, task=None, parent=None, role=None, effort=None, engine_model=None):
    """Record a running job and return it. parent is an explicit job id only (the env fallback is JSON-only)."""
    clean_title = jobs._clean_title(title)
    clean_model = jobs._clean_model(model)
    clean_task = jobs._clean_task(task, data_dir)
    clean_effort = jobs._clean_effort(effort)
    clean_engine = "" if engine_model is None else str(engine_model).strip()[:jobs.TITLE_MAX]
    conn = _open(data_dir)
    try:
        with db.txn(conn):
            clean_parent = _check_parent(conn, parent)
            clean_role = jobs._clean_role(role, clean_parent)
            job = {"id": _next_id(conn), "title": clean_title, "model": clean_model}
            if clean_task:
                job["task"] = clean_task
            if clean_effort:
                job["effort"] = clean_effort
            if clean_engine:
                job["engine_model"] = clean_engine
            if clean_parent:
                job["parent"] = clean_parent
                job["role"] = clean_role
            job.update({"status": "running", "started": jobs._now_iso(), "ended": None})
            _save(conn, job)
            events.append(conn, "job.started", "job", job["id"], {"task": clean_task or None, "model": clean_model})
    finally:
        conn.close()
    if clean_task:
        jobs._mark_partial(data_dir, clean_task)
    return dict(job)


def finish(data_dir, job_id, status, note=None, tokens_k=None, reason=None):
    """Mark a running job done or failed. Same rules and errors as jobs.finish_job."""
    if status not in ("done", "failed"):
        raise RoadmapError("usage", "status must be done or failed", EXIT_USAGE)
    wanted = str(job_id or "").strip()
    clean_reason = jobs.first_error_line(reason) if status == "failed" else ""
    conn = _open(data_dir)
    try:
        with db.txn(conn):
            job = _load(conn, wanted)
            if job is None:
                raise RoadmapError("not_found", "no job with id '" + wanted + "'", EXIT_NOT_FOUND)
            if job.get("status") != "running":
                raise RoadmapError("conflict", wanted + " is already " + str(job.get("status")) + "; not changed",
                                   EXIT_CONFLICT)
            counted = jobs._counted(job)
            if tokens_k is not None and float(tokens_k) < counted:
                raise RoadmapError("usage", wanted + " already counted " + jobs._fmt_k(counted) + " of progress; "
                                   "--tokens must be the job's final total, at least that", EXIT_USAGE)
            job["status"] = status
            job["ended"] = jobs._now_iso()
            if tokens_k is not None:
                job["tokensK"] = round(float(tokens_k), 1)
            if note and str(note).strip():
                job["note"] = str(note).strip()
            if clean_reason:
                job["reason"] = clean_reason
            _save(conn, job)
            events.append(conn, "job.finished", "job", wanted, {"status": status, "tokensK": job.get("tokensK")})
        _after_finish(data_dir, conn, job, status)
    finally:
        conn.close()
    if clean_reason and jobs._UNAVAILABLE_RE.search(clean_reason):
        jobs._block_engine(data_dir, str(job.get("model") or ""), clean_reason)
    return dict(job)


def list_jobs(data_dir):
    """Every job record in insertion order (read only, like jobs.list_jobs)."""
    conn = _open(data_dir)
    try:
        return _all(conn)
    finally:
        conn.close()


def _clean_files(files, kind):
    if files is None:
        items = []
    elif isinstance(files, str):
        items = files.split(",")
    else:
        items = list(files)
    clean = sorted({str(f).strip() for f in items if str(f).strip()})
    if not clean and kind not in READ_ONLY_KINDS:
        raise RoadmapError("usage", "a " + kind + " job needs its files; only review and audit jobs may have none",
                           EXIT_USAGE)
    return clean


def claim(data_dir, task, files, worker, kind="edit", title=None, model="unknown"):
    """Single-flight claim of a task. Returns (job, created): when a job already runs on the task, that job comes
    back with created False and nothing is written. Otherwise a running job is recorded with its files."""
    clean_task = jobs._clean_task(task, data_dir)
    if not clean_task:
        raise RoadmapError("usage", "claim needs a task id", EXIT_USAGE)
    clean_kind = "edit" if kind is None else str(kind).strip()
    if clean_kind not in KINDS:
        raise RoadmapError("usage", "kind must be one of " + ", ".join(KINDS), EXIT_USAGE)
    clean_files = _clean_files(files, clean_kind)
    clean_worker = str(worker or "").strip()
    if not clean_worker:
        raise RoadmapError("usage", "claim needs a worker name", EXIT_USAGE)
    clean_model = jobs._clean_model(model)
    clean_title = jobs._clean_title(title or ("claim " + clean_task))
    conn = _open(data_dir)
    try:
        with db.txn(conn):
            row = conn.execute("SELECT data FROM jobs WHERE task = ? AND status = 'running' ORDER BY rowid LIMIT 1",
                               (clean_task,)).fetchone()
            if row is not None:
                return json.loads(row["data"]), False
            job = {"id": _next_id(conn), "title": clean_title, "model": clean_model, "task": clean_task,
                   "status": "running", "started": jobs._now_iso(), "ended": None,
                   "worker": clean_worker, "kind": clean_kind, "files": clean_files}
            _save(conn, job)
            events.append(conn, "job.claimed", "job", job["id"], {"task": clean_task, "worker": clean_worker,
                                                                  "kind": clean_kind, "files": clean_files})
    finally:
        conn.close()
    jobs._mark_partial(data_dir, clean_task)
    return dict(job), True
