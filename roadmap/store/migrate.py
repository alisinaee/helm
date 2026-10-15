"""Import an existing project's JSON files (tasks.json, jobs.json, head.jsonl) into the SQLite store.

Idempotent: rows are upserted by key and rows whose key left the source are pruned, so a second run
over the same files leaves identical rows. Only reads the JSON files; never writes or edits them.
"""

import hashlib
import json
import os

from roadmap.store import db

TASK_CORE = ("id", "phase", "title", "status")
JOB_CORE = ("id", "task", "title", "model", "status", "started", "ended")
PHASE_CORE = ("id", "name", "status")


def _dumps(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _extra(row, core):
    return _dumps({k: v for k, v in row.items() if k not in core})


def _read_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "rb") as fh:
        return json.loads(fh.read().decode("utf-8"))


def _read_jsonl(path):
    """Return [(line_no, obj)]; line numbers are the stable key because head.jsonl is append-only."""
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, "rb") as fh:
        for n, raw in enumerate(fh, 1):
            text = raw.decode("utf-8").strip()
            if not text:
                continue
            try:
                rows.append((n, json.loads(text)))
            except ValueError as exc:
                raise ValueError("%s line %d: %s" % (path, n, exc)) from exc
    return rows


def _file_sha(path):
    if not os.path.exists(path):
        return None
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _upsert(conn, table, pk, cols, rows):
    """Insert or update by primary key without deleting, so FK children stay valid."""
    updates = ", ".join("%s = excluded.%s" % (c, c) for c in cols if c != pk)
    sql = "INSERT INTO %s (%s) VALUES (%s) ON CONFLICT(%s) DO UPDATE SET %s" % (
        table, ", ".join(cols), ", ".join("?" * len(cols)), pk, updates)
    conn.executemany(sql, rows)


def _prune(conn, table, pk, keep):
    present = [r[0] for r in conn.execute("SELECT %s FROM %s" % (pk, table))]
    stale = [(k,) for k in present if k not in keep]
    if stale:
        conn.executemany("DELETE FROM %s WHERE %s = ?" % (table, pk), stale)
    return len(stale)


def _phase_rows(phases):
    rows = []
    for pos, p in enumerate(phases):
        rows.append((p["id"], pos, p.get("name", ""), p.get("status", "todo"), _extra(p, PHASE_CORE)))
    return rows


def _task_rows(tasks):
    return [(t["id"], t.get("phase"), t.get("title", ""), t.get("status", "todo"), _extra(t, TASK_CORE))
            for t in tasks]


def _job_rows(jobs):
    rows = []
    for j in jobs:
        rows.append((j["id"], j.get("task"), j.get("title", ""), j.get("model"), j.get("status", ""),
                     j.get("started"), j.get("ended"), _extra(j, JOB_CORE)))
    return rows


def _ask_rows(lines):
    return [(n, str(o.get("t", "")), o.get("id"), o.get("ts"), o.get("kind"), _dumps(o)) for n, o in lines]


def migrate(conn, docs_dir):
    """Import docs_dir's tasks.json, jobs.json and head.jsonl in one transaction. Returns a summary dict."""
    tasks_doc = _read_json(os.path.join(docs_dir, "tasks.json"), {})
    jobs_doc = _read_json(os.path.join(docs_dir, "jobs.json"), {})
    head = _read_jsonl(os.path.join(docs_dir, "head.jsonl"))
    phases = tasks_doc.get("phases", [])
    tasks = tasks_doc.get("tasks", [])
    jobs = jobs_doc.get("jobs", [])
    asks = _ask_rows(head)
    sources = {name: _file_sha(os.path.join(docs_dir, name)) for name in
               ("tasks.json", "jobs.json", "head.jsonl")}

    with db.txn(conn):
        _upsert(conn, "phases", "id", ("id", "position", "name", "status", "data"), _phase_rows(phases))
        _upsert(conn, "tasks", "id", ("id", "phase", "title", "status", "data"), _task_rows(tasks))
        _upsert(conn, "jobs", "id", ("id", "task", "title", "model", "status", "started", "ended", "data"),
                _job_rows(jobs))
        _upsert(conn, "asks", "seq", ("seq", "t", "id", "ts", "kind", "data"), asks)
        pruned = {
            "tasks": _prune(conn, "tasks", "id", {t["id"] for t in tasks}),
            "jobs": _prune(conn, "jobs", "id", {j["id"] for j in jobs}),
            "asks": _prune(conn, "asks", "seq", {r[0] for r in asks}),
            "phases": _prune(conn, "phases", "id", {p["id"] for p in phases}),
        }
        for name, sha in sources.items():
            conn.execute("INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = "
                         "excluded.value", ("source:" + name, sha or ""))

    return {
        "phases": len(phases), "tasks": len(tasks), "jobs": len(jobs), "asks": len(asks),
        "pruned": pruned, "sources": sources,
    }


def migrate_project(db_path, docs_dir):
    """Open (creating if needed) the store at db_path and import docs_dir into it."""
    conn = db.connect(db_path)
    try:
        summary = migrate(conn, docs_dir)
        summary["checksums"] = db.table_checksums(conn)
        return summary
    finally:
        conn.close()
