"""JSON data files mirrored in the sqlite store (used only when the sqlite switch is on; JSON stays the default).

Table files(name, data) keeps the newest text of each data file. sync_in writes the db copy over the file, or seeds
the db from the file on first use. sync_out saves the file into the db. Both run inside the caller's db.txn(), so the
db copy is the one that commits or rolls back with the op. restore_file puts a snapshot back when an op fails.

Agent task rows (the tasks table, read through the agent_tasks view) also live here: insert_agent_task refuses a row
without work_id, so every agent task belongs to a Work item (see store/work_db.py).
"""

import json
import os

from roadmap.errors import EXIT_INVALID_DATA, RoadmapError
from roadmap.store import atomic, db

TABLE_SQL = "CREATE TABLE IF NOT EXISTS files (name TEXT PRIMARY KEY, data TEXT NOT NULL)"


def insert_agent_task(conn, task_id, title, status, work_id, phase=None, data=None):
    """Insert one agent task. Refused (invalid_data) when work_id is missing or empty. Runs inside the caller's txn."""
    if not work_id:
        raise RoadmapError("invalid_data", "agent task " + str(task_id) + " needs a work_id (its Work item)",
                           EXIT_INVALID_DATA)
    body = json.dumps(data if data is not None else {}, sort_keys=True, ensure_ascii=False)
    conn.execute("INSERT INTO tasks (id, phase, title, status, data, work_id) VALUES (?, ?, ?, ?, ?, ?)",
                 (task_id, phase, title, status, body, work_id))


def set_work(conn, task_id, work_id):
    """Point an existing agent task at a Work item. Returns False when no agent task has that id."""
    cur = conn.execute("UPDATE tasks SET work_id = ? WHERE id = ?", (work_id, task_id))
    return cur.rowcount == 1


def get_agent_task(conn, task_id):
    """One agent task as a dict (or None)."""
    row = conn.execute("SELECT id, phase, title, status, data, work_id FROM agent_tasks WHERE id = ?",
                       (task_id,)).fetchone()
    return None if row is None else _task_dict(row)


def agent_tasks_for_work(conn, work_id):
    """Every agent task under one Work item, in insertion order."""
    rows = conn.execute("SELECT id, phase, title, status, data, work_id FROM tasks"
                        " WHERE work_id = ? ORDER BY rowid", (work_id,)).fetchall()
    return [_task_dict(r) for r in rows]


def _task_dict(row):
    out = {"id": row["id"], "phase": row["phase"], "title": row["title"], "status": row["status"],
           "work_id": row["work_id"]}
    out.update(json.loads(row["data"] or "{}"))
    return out


def open_store(data_dir):
    """The project's one store connection (docs/roadmap.db): the same file jobs and head write to."""
    return db.open_project(data_dir)


def ensure(conn):
    conn.execute(TABLE_SQL)


def read_file(path):
    """The file's text exactly as stored (no newline translation), or None when it does not exist."""
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8", newline="") as fh:
        return fh.read()


def restore_file(path, text):
    """Put a snapshot back: the text, or no file when the snapshot had none."""
    if text is None:
        if os.path.exists(path):
            os.remove(path)
        return
    atomic.write_text(path, text)


def sync_in(conn, path):
    name = os.path.basename(path)
    row = conn.execute("SELECT data FROM files WHERE name = ?", (name,)).fetchone()
    if row is not None:
        atomic.write_text(path, row[0])
        return
    text = read_file(path)
    if text is not None:
        conn.execute("INSERT INTO files (name, data) VALUES (?, ?)", (name, text))


def sync_out(conn, path):
    name = os.path.basename(path)
    text = read_file(path)
    if text is None:
        conn.execute("DELETE FROM files WHERE name = ?", (name,))
    else:
        conn.execute("INSERT INTO files (name, data) VALUES (?, ?)"
                     " ON CONFLICT(name) DO UPDATE SET data = excluded.data", (name, text))
