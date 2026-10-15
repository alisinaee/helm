"""Deterministic JSON export of the SQLite store into the file shapes the repo tracks (tasks.json, jobs.json,
head.jsonl). Read-only on the db; each file is written atomically (temp file, fsync, rename).

Same db content gives byte-identical files: sorted keys, stable row order (phase position, then insertion
order; head by seq), indent 2 for the JSON documents, compact one-object-per-line for head.jsonl, and a trailing
newline. Core columns that are NULL are left out, which matches how migrate reads a missing key.
"""

import json
import os
import tempfile

from roadmap.store import schema

TASKS_FILE = "tasks.json"
JOBS_FILE = "jobs.json"
HEAD_FILE = "head.jsonl"
FILE_MODE = 0o644
FILES_ALL = (TASKS_FILE, JOBS_FILE, HEAD_FILE)

PHASE_CORE = ("id", "name", "status")
TASK_CORE = ("id", "phase", "title", "status")
JOB_CORE = ("id", "task", "title", "model", "status", "started", "ended")


def _doc_text(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, indent=2) + "\n"


def _line_text(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _build(row, core):
    """Rebuild one source object: the json `data` extras plus the core columns that are not NULL."""
    obj = json.loads(row["data"])
    for key in core:
        if row[key] is not None:
            obj[key] = row[key]
    return obj


def _write_atomic(path, text):
    """Write text to path via a temp file in the same directory, fsync, then rename over path."""
    directory = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=directory, prefix="." + os.path.basename(path) + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(text.encode("utf-8"))
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, FILE_MODE)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _snapshot(conn):
    """Read every table inside one read transaction so the three files come from the same state."""
    conn.execute("BEGIN")
    try:
        phases = [_build(r, PHASE_CORE) for r in
                  conn.execute("SELECT id, name, status, data FROM phases ORDER BY position, id")]
        tasks = [_build(r, TASK_CORE) for r in
                 conn.execute("SELECT id, phase, title, status, data FROM tasks ORDER BY rowid")]
        jobs = [_build(r, JOB_CORE) for r in
                conn.execute("SELECT id, task, title, model, status, started, ended, data FROM jobs "
                             "ORDER BY rowid")]
        head = [json.loads(r["data"]) for r in conn.execute("SELECT data FROM asks ORDER BY seq")]
    finally:
        conn.execute("COMMIT")
    return phases, tasks, jobs, head


def export(conn, out_dir):
    """Write tasks.json, jobs.json and head.jsonl into out_dir from the db behind conn.

    Returns the list of written paths. Call it outside db.txn(): it opens its own read transaction.
    """
    phases, tasks, jobs, head = _snapshot(conn)
    os.makedirs(out_dir, exist_ok=True)

    tasks_doc = {"schemaVersion": schema.current_version("tasks"), "phases": phases, "tasks": tasks}
    jobs_doc = {"schemaVersion": schema.current_version("jobs"), "jobs": jobs}
    head_text = "".join(_line_text(obj) + "\n" for obj in head)

    texts = {TASKS_FILE: _doc_text(tasks_doc), JOBS_FILE: _doc_text(jobs_doc), HEAD_FILE: head_text}
    written = []
    for name in FILES_ALL:
        path = os.path.join(out_dir, name)
        _write_atomic(path, texts[name])
        written.append(path)
    return written
