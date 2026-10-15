"""SQLite store (stdlib sqlite3): one file per project (docs/roadmap.db), WAL, one short write transaction per command.

open_project(data_dir) is the single entry point. Tables: meta, phases, tasks, jobs, asks (head entries),
events (append-only; rev is the integer generation). Schema version lives in PRAGMA user_version.
v4: work_items (human Work items); tasks gains work_id (agent tasks), and agent_tasks is a view over tasks.
"""

import contextlib
import hashlib
import json
import os
import re
import sqlite3
import time

SCHEMA_VERSION = 4
BUSY_TIMEOUT_MS = 5000
DB_FILE = "roadmap.db"  # the one store file per project, in the data dir (docs/roadmap.db, gitignored)

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
    2: [
        "ALTER TABLE events ADD COLUMN entity_id TEXT",
        "ALTER TABLE events ADD COLUMN idem TEXT",
        "CREATE UNIQUE INDEX IF NOT EXISTS events_idem ON events(idem)",
    ],
    3: [
        "CREATE TABLE IF NOT EXISTS leases (file TEXT PRIMARY KEY, job_id TEXT NOT NULL,"
        " acquired REAL NOT NULL, expires REAL NOT NULL)",
        "CREATE INDEX IF NOT EXISTS leases_job ON leases(job_id)",
    ],
    4: [
        "CREATE TABLE IF NOT EXISTS work_items ("
        " id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK (kind IN ('task', 'issue')),"
        " title TEXT NOT NULL, outcome TEXT NOT NULL DEFAULT '',"
        " status TEXT NOT NULL CHECK (status IN ('Backlog', 'Todo', 'Doing', 'Review', 'Done', 'Won''t do')),"
        " prio INTEGER NOT NULL DEFAULT 2 CHECK (prio BETWEEN 0 AND 3),"
        " owner TEXT NOT NULL DEFAULT 'you', phase TEXT,"
        " created TEXT NOT NULL, updated TEXT NOT NULL, accepted_at TEXT,"
        " reopened INTEGER NOT NULL DEFAULT 0, data TEXT NOT NULL DEFAULT '{}')",
        "CREATE INDEX IF NOT EXISTS work_items_status ON work_items(status)",
        # Agent tasks keep their R7.x ids in the tasks table. work_id is required by the code path
        # (work_db / tasks_db refuse a row without it); NULL is allowed in SQL until the JSON import is mapped.
        "ALTER TABLE tasks ADD COLUMN work_id TEXT REFERENCES work_items(id)",
        "CREATE INDEX IF NOT EXISTS tasks_work ON tasks(work_id)",
        "CREATE VIEW IF NOT EXISTS agent_tasks AS"
        " SELECT id, phase, title, status, data, work_id FROM tasks",
    ],
}

TABLES = ("meta", "phases", "tasks", "jobs", "asks", "events", "work_items")

_ADD_COLUMN = re.compile(r"ALTER TABLE (\w+) ADD COLUMN (\w+)")


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


def db_path(data_dir):
    """Path of the project's one store file: <data_dir>/roadmap.db."""
    return os.path.join(str(data_dir), DB_FILE)


def open_project(data_dir):
    """The one store connection for a project: WAL, busy_timeout, FKs on, migrations applied. Every module
    (jobs, head, tasks, loader) opens the project through here, so one txn can cover them all."""
    return connect(db_path(data_dir))


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
                _apply(conn, stmt)
            conn.execute("PRAGMA user_version = %d" % version)


def _apply(conn, stmt):
    """Run one migration statement. ADD COLUMN is skipped when the column already exists, so a re-run is a no-op."""
    m = _ADD_COLUMN.match(stmt)
    if m and any(row[1] == m.group(2) for row in conn.execute("PRAGMA table_info(%s)" % m.group(1))):
        return
    conn.execute(stmt)


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
