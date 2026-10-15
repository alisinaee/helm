"""JSON data files mirrored in the sqlite store (used only when the sqlite switch is on; JSON stays the default).

Table files(name, data) keeps the newest text of each data file. sync_in writes the db copy over the file, or seeds
the db from the file on first use. sync_out saves the file into the db. Both run inside the caller's db.txn(), so the
db copy is the one that commits or rolls back with the op. restore_file puts a snapshot back when an op fails.
"""

import os

from roadmap.store import atomic, db

TABLE_SQL = "CREATE TABLE IF NOT EXISTS files (name TEXT PRIMARY KEY, data TEXT NOT NULL)"


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
