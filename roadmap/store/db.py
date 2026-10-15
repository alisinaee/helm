"""SQLite store (stdlib sqlite3): one file, WAL, one short write transaction per command.

Not wired into the service yet. Tables: meta, phases, tasks, jobs, asks (head entries),
events (append-only; rev is the integer generation). Schema version lives in PRAGMA user_version.
"""

import contextlib
import hashlib
import json
import sqlite3
import time

SCHEMA_VERSION = 1
BUSY_TIMEOUT_MS = 5000

# version -> statements that take the schema from version-1 to version.
MIGRATIONS = {
    1: [
        "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
        "CREATE TABLE IF NOT EXISTS phases ("
        " id TEXT PRIMARY KEY, position INTEGER NOT NULL, name TEXT NOT NULL,"
        " status TEXT NOT NULL, data TEXT NOT NULL DEFAULT '{}')",
        "CREATE TABLE IF NOT EXISTS tasks ("
        " id TEXT PRIMARY KEY, phase TEXT REFERENCES phases(id), title TEXT NOT NULL,"
        " status TEXT NOT NULL, data TEXT NOT NULL DEFAULT '{}')",
        "CREATE INDEX IF NOT EXISTS tasks_phase ON tasks(phase)",
        "CREATE TABLE IF NOT EXISTS jobs ("
        " id TEXT PRIMARY KEY, task TEXT, title TEXT NOT NULL, model TEXT, status TEXT NOT NULL,"
        " started TEXT, ended TEXT, data TEXT NOT NULL DEFAULT '{}')",
        "CREATE INDEX IF NOT EXISTS jobs_task ON jobs(task)",
        "CREATE TABLE IF NOT EXISTS asks ("
        " seq INTEGER PRIMARY KEY, t TEXT NOT NULL, id TEXT, ts TEXT, kind TEXT,"
        " data TEXT NOT NULL)",
        "CREATE INDEX IF NOT EXISTS asks_id ON asks(id)",
        "CREATE TABLE IF NOT EXISTS events ("
        " rev INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, kind TEXT NOT NULL,"
        " entity TEXT, payload TEXT NOT NULL DEFAULT '{}')",
        "CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events"
        " BEGIN SELECT RAISE(ABORT, 'events are append-only'); END",
        "CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events"
        " BEGIN SELECT RAISE(ABORT, 'events are append-only'); END",
    ],
}

TABLES = ("meta", "phases", "tasks", "jobs", "asks", "events")


def is_locked_error(exc):
    msg = str(exc).lower()
    return isinstance(exc, sqlite3.OperationalError) and ("locked" in msg or "busy" in msg)


def retry_locked(fn, attempts=8, base_delay=0.05):
    """Call fn(); on 'database is locked/busy' back off and try again. Other errors raise at once."""
    for i in range(attempts):
        try:
            return fn()
        except sqlite3.OperationalError as exc:
            if not is_locked_error(exc) or i == attempts - 1:
                raise
            time.sleep(base_delay * (2 ** i))
    raise RuntimeError("unreachable")


def connect(path, busy_timeout_ms=BUSY_TIMEOUT_MS):
    """Open a connection in autocommit mode (transactions are explicit via txn()), WAL, FKs on."""
    conn = sqlite3.connect(str(path), timeout=busy_timeout_ms / 1000.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = %d" % int(busy_timeout_ms))
    conn.execute("PRAGMA foreign_keys = ON")
    retry_locked(lambda: conn.execute("PRAGMA journal_mode = WAL").fetchone())
    ensure_schema(conn)
    return conn


@contextlib.contextmanager
def txn(conn):
    """BEGIN IMMEDIATE; COMMIT on success, ROLLBACK and re-raise on any error."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def schema_version(conn):
    return conn.execute("PRAGMA user_version").fetchone()[0]


def ensure_schema(conn):
    """Apply pending MIGRATIONS in one IMMEDIATE transaction. Safe when several processes start at once."""
    if schema_version(conn) == SCHEMA_VERSION:
        return  # fast path: no write lock needed when already current
    with txn(conn):
        current = schema_version(conn)
        if current > SCHEMA_VERSION:
            raise RuntimeError("database schema %d is newer than this code (%d)" % (current, SCHEMA_VERSION))
        for version in range(current + 1, SCHEMA_VERSION + 1):
            for stmt in MIGRATIONS[version]:
                conn.execute(stmt)
            conn.execute("PRAGMA user_version = %d" % version)


def table_checksums(conn):
    """Row count and sha256 over every row (rowid order) per table. Equal output means equal content."""
    out = {}
    for table in TABLES:
        digest = hashlib.sha256()
        count = 0
        for row in conn.execute("SELECT * FROM %s ORDER BY rowid" % table):
            digest.update(json.dumps(tuple(row), sort_keys=True, default=str).encode("utf-8"))
            count += 1
        out[table] = {"rows": count, "sha256": digest.hexdigest()}
    return out
