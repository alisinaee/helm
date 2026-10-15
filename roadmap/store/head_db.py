"""Head ledger on the SQLite store (opt-in backend; JSON head.jsonl stays the default).

The file is the project store (docs/roadmap.db, see db.open_project). Entries live in the asks table
(id H<n>, data JSON with text, sum, fp). log() returns the existing entry when the same normalised text was
logged in the last 24 h, so a repeated message does not create a second Hn. update()
appends its change to the events log in the same transaction (head.triage for set fields, head.bind for links).
Spool rows hold hook captures until a writer takes them. The spool table is created here, not in db.py.
"""

import contextlib
import datetime
import hashlib
import json
import os
import re

from roadmap.errors import EXIT_NOT_FOUND, EXIT_USAGE, RoadmapError
from roadmap.store import db, events

DUP_WINDOW = datetime.timedelta(hours=24)
_PUNCT = re.compile(r"[^\w\s]")
_ID_RE = re.compile(r"^H(\d+)$")
_SPOOL_DDL = (
    "CREATE TABLE IF NOT EXISTS head_spool (seq INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL,"
    " src TEXT NOT NULL, sid TEXT, text TEXT NOT NULL, adopted TEXT)"
)


def fingerprint(text):
    """sha1 of the normalised text: lowercase, punctuation stripped, whitespace collapsed."""
    norm = " ".join(_PUNCT.sub("", str(text or "").lower()).split())
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()


def _stamp(now=None):
    value = now or datetime.datetime.now(datetime.timezone.utc)
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


@contextlib.contextmanager
def _conn(db_path):
    """Open the project store. db_path names the store file (roadmap.db); only its directory is used, so a
    caller that still passes another file name in the data dir reaches the same store."""
    conn = db.open_project(os.path.dirname(os.path.abspath(db_path)))
    try:
        with db.txn(conn):
            conn.execute(_SPOOL_DDL)
        yield conn
    finally:
        conn.close()


def _next_id(conn):
    best = 0
    for (eid,) in conn.execute("SELECT id FROM asks WHERE t = 'e'"):
        match = _ID_RE.match(str(eid or ""))
        if match:
            best = max(best, int(match.group(1)))
    return "H" + str(best + 1)


def log(db_path, text, kind, sum_text, now=None):
    """Insert one entry, or return the entry already logged with the same fingerprint in the last 24 h.

    Returns {"id", "status": "logged", "dup": bool, "kind", "sum", "len"}; dup entries carry the stored kind and sum.
    """
    fp = fingerprint(text)
    current = now or datetime.datetime.now(datetime.timezone.utc)
    cutoff = _stamp(current - DUP_WINDOW)
    with _conn(db_path) as conn:
        with db.txn(conn):
            row = conn.execute(
                "SELECT id, kind, data FROM asks WHERE t = 'e' AND ts >= ? AND json_extract(data, '$.fp') = ?"
                " ORDER BY seq DESC LIMIT 1", (cutoff, fp),
            ).fetchone()
            if row is not None:
                stored = json.loads(row["data"])
                return {"id": row["id"], "status": "logged", "dup": True, "kind": row["kind"],
                        "sum": stored.get("sum"), "len": stored.get("len")}
            eid = _next_id(conn)
            body = {"fp": fp, "len": len(str(text)), "sum": sum_text, "text": str(text)}
            conn.execute(
                "INSERT INTO asks (t, id, ts, kind, data) VALUES ('e', ?, ?, ?, ?)",
                (eid, _stamp(current), kind, json.dumps(body, sort_keys=True)),
            )
    return {"id": eid, "status": "logged", "dup": False, "kind": kind, "sum": sum_text, "len": body["len"]}


def update(db_path, eid, *, by, sets=None, links=(), note=None, now=None):
    """Apply one update to an existing entry and append its events in the same transaction.

    sets: field -> value (status/kind/sum) recorded as head.triage; links: "+ref" / "-ref" recorded as head.bind.
    Returns {"id", "rev"} where rev is the last event written.
    """
    if not isinstance(eid, str) or not _ID_RE.match(eid):
        raise RoadmapError("usage", "not a head id: " + repr(eid), EXIT_USAGE)
    sets = dict(sets or {})
    links = list(links or ())
    for ref in links:
        if not isinstance(ref, str) or ref[:1] not in ("+", "-"):
            raise RoadmapError("usage", "link must be +ref or -ref, got " + repr(ref), EXIT_USAGE)
    rev = None
    with _conn(db_path) as conn:
        with db.txn(conn):
            row = conn.execute("SELECT seq, kind, data FROM asks WHERE t = 'e' AND id = ? ORDER BY seq DESC LIMIT 1",
                               (eid,)).fetchone()
            if row is None:
                raise RoadmapError("not_found", "no head entry " + eid, EXIT_NOT_FOUND)
            body = json.loads(row["data"])
            kind = sets.pop("kind", row["kind"])
            body.update(sets)
            refs = list(body.get("links", []))
            for ref in links:
                refs = [r for r in refs if r[1:] != ref[1:]]
                if ref[0] == "+":
                    refs.append(ref)
            body["links"] = refs
            conn.execute("UPDATE asks SET kind = ?, data = ? WHERE seq = ?",
                         (kind, json.dumps(body, sort_keys=True), row["seq"]))
            payload = {"by": by, "note": note}
            if sets or not links:
                rev = events.append(conn, "head.triage" if sets else "head.update", "head", eid,
                                    dict(payload, set=sets))
            if links:
                rev = events.append(conn, "head.bind", "head", eid, dict(payload, link=links))
    return {"id": eid, "rev": rev}


def spool_add(db_path, text, *, src="hook", sid=None, now=None):
    """Park one hook capture until a writer adopts it. Returns the spool seq."""
    with _conn(db_path) as conn:
        with db.txn(conn):
            cur = conn.execute("INSERT INTO head_spool (ts, src, sid, text) VALUES (?, ?, ?, ?)",
                               (_stamp(now), str(src), sid, str(text)))
            return int(cur.lastrowid)


def spool_pending(db_path):
    """Spool rows not yet adopted, oldest first."""
    with _conn(db_path) as conn:
        rows = conn.execute("SELECT seq, ts, src, sid, text FROM head_spool WHERE adopted IS NULL ORDER BY seq")
        return [dict(row) for row in rows.fetchall()]
