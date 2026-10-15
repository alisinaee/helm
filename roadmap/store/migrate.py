"""Import an existing project's JSON files (tasks.json, jobs.json, head.jsonl) into the SQLite store.

Idempotent: rows are upserted by key and rows whose key left the source are pruned, so a second run
over the same files leaves identical rows. Only reads the JSON files; never writes or edits them.
"""

import datetime
import hashlib
import json
import os
import re

from roadmap.core import workstatus
from roadmap.errors import EXIT_INVALID_DATA, RoadmapError
from roadmap.store import db

WORK_MAP_FILE = "work-map-R7.json"
_TASK_BIND = re.compile(r"^([+-]?)task:(.+)$")
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


def _lift_asks(lines, task_to_work):
    """Add a work: link next to each task: link of a mapped R7 task. The task ref stays. Returns (rows, lifted)."""
    out, lifted = [], 0
    for n, o in lines:
        links = o.get("link")
        if isinstance(links, list):
            extra = []
            for entry in links:
                m = _TASK_BIND.match(entry) if isinstance(entry, str) else None
                if m and m.group(2) in task_to_work:
                    new = "%swork:%s" % (m.group(1), task_to_work[m.group(2)])
                    if new not in links and new not in extra:
                        extra.append(new)
            if extra:
                o = dict(o, link=links + extra)
                lifted += len(extra)
        out.append((n, o))
    return out, lifted


def _work_map(docs_dir, tasks):
    """The R7 map (docs/work-map-R7.json) or None. Refuses a map whose refs do not resolve."""
    doc = _read_json(os.path.join(docs_dir, WORK_MAP_FILE), None)
    if doc is None:
        return None
    items, task_to_work = doc.get("items", {}), doc.get("tasks", {})
    known = {t["id"] for t in tasks}
    for tid, wid in task_to_work.items():
        if wid not in items:
            raise RoadmapError("invalid_data", "work map: %s maps to unknown %s" % (tid, wid), EXIT_INVALID_DATA)
        if tid not in known:
            raise RoadmapError("invalid_data", "work map: no agent task " + tid, EXIT_INVALID_DATA)
    return items, task_to_work


def _work_rows(conn, items, task_to_work, tasks):
    """Work item rows with the status rolled up from their agent tasks (legacy: all done -> Done, accepted=migrate)."""
    state = {t["id"]: t.get("status", "todo") for t in tasks}
    existing = {r[0]: r[1] for r in conn.execute("SELECT id, accepted_at FROM work_items")}
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = []
    for wid in sorted(items, key=lambda s: int(s[1:])):
        tids = [t for t, w in task_to_work.items() if w == wid]
        accepted = existing.get(wid)
        status = workstatus.rollup({"state": "", "reopened": 0},
                                   [{"state": state[t]} for t in tids], accepted is not None)["status"]
        if status == workstatus.REVIEW:
            status, accepted = workstatus.DONE, accepted or "migrate"
        rows.append((wid, "task", items[wid]["title"], items[wid].get("outcome", ""), status, 2, "you",
                     "R7", now, now, accepted))
    return rows


_WORK_UPSERT = (
    "INSERT INTO work_items (id, kind, title, outcome, status, prio, owner, phase, created, updated, accepted_at)"
    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    " ON CONFLICT(id) DO UPDATE SET title = excluded.title, outcome = excluded.outcome,"
    " phase = excluded.phase, status = excluded.status,"
    " accepted_at = COALESCE(work_items.accepted_at, excluded.accepted_at),"
    " updated = CASE WHEN work_items.status = excluded.status THEN work_items.updated ELSE excluded.updated END"
)


def migrate(conn, docs_dir):
    """Import docs_dir's tasks.json, jobs.json, head.jsonl and (if present) work-map-R7.json in one transaction.
    Returns a summary dict. Idempotent: a second run over the same files leaves identical rows."""
    tasks_doc = _read_json(os.path.join(docs_dir, "tasks.json"), {})
    jobs_doc = _read_json(os.path.join(docs_dir, "jobs.json"), {})
    head = _read_jsonl(os.path.join(docs_dir, "head.jsonl"))
    phases = tasks_doc.get("phases", [])
    tasks = tasks_doc.get("tasks", [])
    jobs = jobs_doc.get("jobs", [])
    work = _work_map(docs_dir, tasks)
    items, task_to_work = work if work else ({}, {})
    head, lifted = _lift_asks(head, task_to_work)
    asks = _ask_rows(head)
    sources = {name: _file_sha(os.path.join(docs_dir, name)) for name in
               ("tasks.json", "jobs.json", "head.jsonl", WORK_MAP_FILE)}

    with db.txn(conn):
        _upsert(conn, "phases", "id", ("id", "position", "name", "status", "data"), _phase_rows(phases))
        if items:
            conn.executemany(_WORK_UPSERT, _work_rows(conn, items, task_to_work, tasks))
        _upsert(conn, "tasks", "id", ("id", "phase", "title", "status", "data"), _task_rows(tasks))
        conn.executemany("UPDATE tasks SET work_id = ? WHERE id = ?",
                         [(w, t) for t, w in sorted(task_to_work.items())])
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
        "work": {"items": len(items), "tasks_mapped": len(task_to_work), "binds_lifted": lifted},
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
