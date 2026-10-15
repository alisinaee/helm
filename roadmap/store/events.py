"""Append-only event log in the SQLite store. One shared integer rev across all event kinds.

Callers pass an open connection that is already inside db.txn(); the event row commits or
rolls back with the write it describes. Not wired into the service yet.
"""

import datetime
import json


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def append(conn, kind, entity, entity_id, payload=None, idem=None):
    """Insert one event and return its rev (int). Must run inside an open transaction.

    idem: optional idempotency key. Appending a key that already exists returns the first
    event's rev and inserts nothing.
    """
    if not conn.in_transaction:
        raise RuntimeError("events.append must run inside db.txn()")
    if idem is not None:
        row = conn.execute("SELECT rev FROM events WHERE idem = ?", (idem,)).fetchone()
        if row is not None:
            return int(row[0])
    body = json.dumps(payload if payload is not None else {}, sort_keys=True, default=str)
    cur = conn.execute(
        "INSERT INTO events (ts, kind, entity, entity_id, payload, idem) VALUES (?, ?, ?, ?, ?, ?)",
        (_now(), kind, entity, None if entity_id is None else str(entity_id), body, idem),
    )
    return int(cur.lastrowid)


def current_rev(conn):
    """Highest rev written so far, 0 when the log is empty."""
    return int(conn.execute("SELECT COALESCE(MAX(rev), 0) FROM events").fetchone()[0])


def since(conn, rev, limit=100):
    """Events with rev > rev, oldest first, at most limit. Page by passing the last rev back."""
    if limit < 1:
        raise ValueError("limit must be >= 1")
    rows = conn.execute(
        "SELECT rev, ts, kind, entity, entity_id, payload FROM events WHERE rev > ? ORDER BY rev LIMIT ?",
        (int(rev), int(limit)),
    ).fetchall()
    out = []
    for row in rows:
        out.append({
            "rev": row["rev"],
            "ts": row["ts"],
            "kind": row["kind"],
            "entity": row["entity"],
            "entity_id": row["entity_id"],
            "payload": json.loads(row["payload"]),
        })
    return out
