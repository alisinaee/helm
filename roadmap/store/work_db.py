"""Work items (the human card) and their agent tasks (the machine packages) in the SQLite store (v4).

Every function takes an open connection that the caller already holds inside db.txn(). Each write appends its event
(store/events.py) in that same txn, so the row and its event commit or roll back together. Not wired into the service
or the JSON path yet.
"""

import datetime

from roadmap.errors import EXIT_INVALID_DATA, EXIT_NOT_FOUND, RoadmapError
from roadmap.store import events, tasks_db

STATUSES = ("Backlog", "Todo", "Doing", "Review", "Done", "Won't do")
KINDS = ("task", "issue")
TITLE_MAX = 60


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _prio(value):
    """Accept 0-3 or 'P0'-'P3'; store the integer."""
    text = str(value).strip().upper()
    if text.startswith("P"):
        text = text[1:]
    if text not in ("0", "1", "2", "3"):
        raise RoadmapError("invalid_data", "prio must be P0-P3", EXIT_INVALID_DATA)
    return int(text)


def _check(value, allowed, what):
    if value not in allowed:
        raise RoadmapError("invalid_data", what + " must be one of " + ", ".join(allowed), EXIT_INVALID_DATA)


def _row_dict(row):
    out = {
        "id": row["id"], "kind": row["kind"], "title": row["title"], "outcome": row["outcome"],
        "status": row["status"], "prio": "P%d" % row["prio"], "owner": row["owner"], "phase": row["phase"],
        "created": row["created"], "updated": row["updated"], "accepted_at": row["accepted_at"],
        "reopened": row["reopened"],
    }
    return out


def _next_id(conn):
    row = conn.execute("SELECT COALESCE(MAX(CAST(SUBSTR(id, 2) AS INTEGER)), 0) FROM work_items"
                       " WHERE id GLOB 'W[0-9]*'").fetchone()
    return "W%d" % (int(row[0]) + 1)


def add(conn, title, outcome="", kind="task", status="Todo", prio=2, owner="you", phase=None):
    """Add a Work item. Returns its dict with the new W id. Writes event work.add."""
    title = (title or "").strip()
    if not title or len(title) > TITLE_MAX:
        raise RoadmapError("invalid_data", "title must be 1-%d characters" % TITLE_MAX, EXIT_INVALID_DATA)
    _check(kind, KINDS, "kind")
    _check(status, STATUSES, "status")
    now = _now()
    wid = _next_id(conn)
    conn.execute(
        "INSERT INTO work_items (id, kind, title, outcome, status, prio, owner, phase, created, updated, reopened)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)",
        (wid, kind, title, outcome or "", status, _prio(prio), owner or "you", phase, now, now),
    )
    events.append(conn, "work.add", "work_item", wid, {"title": title, "kind": kind, "status": status})
    return get(conn, wid)


def get(conn, work_id):
    """One Work item as a dict, or None."""
    row = conn.execute("SELECT * FROM work_items WHERE id = ?", (work_id,)).fetchone()
    return None if row is None else _row_dict(row)


def list_items(conn, status=None, kind=None):
    """Work items in id order, optionally filtered by status and/or kind."""
    sql = "SELECT * FROM work_items"
    where, args = [], []
    if status is not None:
        where.append("status = ?")
        args.append(status)
    if kind is not None:
        where.append("kind = ?")
        args.append(kind)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY CAST(SUBSTR(id, 2) AS INTEGER)"
    return [_row_dict(r) for r in conn.execute(sql, args).fetchall()]


def _require(conn, work_id):
    item = get(conn, work_id)
    if item is None:
        raise RoadmapError("not_found", "no Work item " + str(work_id), EXIT_NOT_FOUND)
    return item


def add_agent_task(conn, task_id, title, work_id, status="todo", phase=None, data=None):
    """Add an agent task under a Work item. Refused without work_id (tasks_db checks that first). Writes task.add."""
    _require(conn, work_id)
    tasks_db.insert_agent_task(conn, task_id, title, status, work_id, phase=phase, data=data)
    events.append(conn, "task.add", "agent_task", task_id, {"work_id": work_id, "title": title})
    return tasks_db.get_agent_task(conn, task_id)


def link(conn, task_id, work_id):
    """Point an existing agent task at a Work item (task -> work). Writes event task.link."""
    _require(conn, work_id)
    task = tasks_db.get_agent_task(conn, task_id)
    if task is None:
        raise RoadmapError("not_found", "no agent task " + str(task_id), EXIT_NOT_FOUND)
    old = task["work_id"]
    tasks_db.set_work(conn, task_id, work_id)
    events.append(conn, "task.link", "agent_task", task_id, {"from": old, "to": work_id})
    return tasks_db.get_agent_task(conn, task_id)


def agent_tasks(conn, work_id):
    """The agent tasks under one Work item."""
    _require(conn, work_id)
    return tasks_db.agent_tasks_for_work(conn, work_id)


def set_status(conn, work_id, status):
    """Set the person's status on a Work item. Done stamps accepted_at; leaving Done counts a reopen and clears it.
    A no-op (no event) when the status does not change. Writes event work.status."""
    _check(status, STATUSES, "status")
    item = _require(conn, work_id)
    old = item["status"]
    if old == status:
        return item
    now = _now()
    accepted = now if status == "Done" else None
    reopened = item["reopened"] + (1 if old == "Done" and status != "Done" else 0)
    conn.execute("UPDATE work_items SET status = ?, updated = ?, accepted_at = ?, reopened = ? WHERE id = ?",
                 (status, now, accepted, reopened, work_id))
    events.append(conn, "work.status", "work_item", work_id, {"from": old, "to": status})
    return get(conn, work_id)
