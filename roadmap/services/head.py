"""Head store service (HEAD-SPEC sections 2, 3, 7): appends entries, updates and session records to head.jsonl under the
data-dir lock, keeps the redacted verbatim text in head-text.jsonl, parks hook captures in head-spool.jsonl while the
lock is busy, and writes the resume brief. The fold and heuristics are in roadmap/core/head.py; redaction in
roadmap/core/secrets.py. Writers that take the lock adopt the spool first, in order."""

import fcntl
import hashlib
import json
import os
import re
from datetime import datetime, timedelta, timezone

from roadmap.core import head, secrets
from roadmap.errors import EXIT_INVALID_DATA, EXIT_NOT_FOUND, EXIT_USAGE, RoadmapError
from roadmap.store import jsonl, lock

FILE = "head.jsonl"
TEXT_FILE = "head-text.jsonl"
SPOOL_FILE = "head-spool.jsonl"
MAX_ENTRIES = 5000
MAX_ID = 9999
TEXT_MAX = 8000
SUM_MAX = head.SUM_MAX
NOTE_MAX = 160
BRIEF_MAX_LINES = 15
SOURCES = ("hook", "cli", "gui", "import")
BY = ("head", "person", "auto")
SET_KEYS = ("status", "kind", "sum", "into")
KINDS = ("ask", "decision", "rule", "bug", "preference", "question", "review", "info")
SESSION_EVENTS = ("claim", "start", "end")
MAX_LINKS = head.MAX_LINKS
_ID_RE = re.compile(r"^H(\d+)$")
_CONTROL = re.compile("[\x00-\x08\x0b-\x1f\x7f]")  # keeps tab and newline; control characters are stripped
_CLOSED = head.CLOSED_STATUSES


def _kind(item):
    """The kind without the '?' guess mark."""
    return str(item.get("kind") or "").rstrip("?")


def _path(data_dir, name):
    return os.path.join(data_dir, name)


def _ts(now=None):
    moment = now if now is not None else datetime.now(timezone.utc)
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def session_key(session_id):
    """First 8 hex digits of sha256(session_id): the raw id is never stored. None when there is no id."""
    if not session_id:
        return None
    return hashlib.sha256(str(session_id).encode("utf-8")).hexdigest()[:8]


def clean_text(text):
    """Control characters stripped, secrets masked, then cut to the verbatim limit (masks are never split)."""
    return secrets.scrub(_CONTROL.sub("", "" if text is None else str(text)))[:TEXT_MAX]


def make_summary(text, given=None):
    """The one-line summary: the head's own text when given, else the heuristic. Masked, one line, 100 chars."""
    base = given if given is not None else head.summarize(text)
    return secrets.scrub(" ".join(str(base or "").split()))[:SUM_MAX]


def _short(value, limit):
    text = " ".join(str(value or "").split())
    return text[:limit] if text else None


def _digest(text):
    return "sha1:" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def _records(data_dir):
    objs, _ = jsonl.read_objects(_path(data_dir, FILE))
    return [o for o in objs if o.get("v") == head.VERSION and o.get("t") in head.RECORD_TYPES]


def _next_id(objs):
    """The next H id after the highest one in the entries. Raises when the cap or the id range is spent."""
    entries = [o for o in objs if o.get("t") == "e"]
    if len(entries) >= MAX_ENTRIES:
        raise RoadmapError("cap", "head holds " + str(MAX_ENTRIES) + " entries; no more can be logged",
                           EXIT_USAGE)
    best = 0
    for entry in entries:
        match = _ID_RE.match(str(entry.get("id", "")))
        if match:
            best = max(best, int(match.group(1)))
    if best + 1 > MAX_ID:
        raise RoadmapError("cap", "head ids are used up (H" + str(MAX_ID) + ")", EXIT_USAGE)
    return "H" + str(best + 1)


def _append_entry_locked(data_dir, entry, text):
    """Assign the next id and append the entry and its text. The caller holds the lock."""
    objs, _ = jsonl.read_objects(_path(data_dir, FILE))
    eid = _next_id(objs)
    line = dict(entry, id=eid)
    jsonl.append_line(_path(data_dir, FILE), line)
    jsonl.append_line(_path(data_dir, TEXT_FILE), {"id": eid, "text": text})
    return line


def _spool_append(data_dir, payload):
    """Park one unnumbered entry in the spool without the directory lock. flock on the spool file orders it
    against the adopting writer."""
    path = _path(data_dir, SPOOL_FILE)
    if os.path.islink(path):
        raise RoadmapError("invalid_data", "refusing to append to a symlink, left unchanged: " + path, EXIT_INVALID_DATA)
    os.makedirs(data_dir, exist_ok=True)
    line = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            fh.write(line)
            fh.flush()
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def _adopt_locked(data_dir):
    """Move spooled captures into head.jsonl, in spool order, then empty the spool. Caller holds the lock.
    Returns the number adopted. Entries past the cap are dropped with a count in the result."""
    path = _path(data_dir, SPOOL_FILE)
    if not os.path.exists(path):
        return 0
    if os.path.islink(path):
        raise RoadmapError("invalid_data", "refusing to read a symlinked spool, left unchanged: " + path, EXIT_INVALID_DATA)
    adopted = 0
    with os.fdopen(os.open(path, os.O_RDWR), "r+", encoding="utf-8") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            for raw in fh.read().splitlines():
                if not raw.strip():
                    continue
                try:
                    payload = json.loads(raw)
                except ValueError:
                    continue
                if not isinstance(payload, dict) or not isinstance(payload.get("e"), dict):
                    continue
                try:
                    _append_entry_locked(data_dir, payload["e"], str(payload.get("text", "")))
                except RoadmapError:
                    break
                adopted += 1
            fh.seek(0)
            fh.truncate()
            fh.flush()
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    return adopted


def capture(data_dir, text, *, session_id=None, src="hook", acct=None, kind=None, sum_text=None,
            from_id=None, now=None, timeout=None):
    """Log one message verbatim (redacted) with its heuristic kind and summary.

    Returns {"id", "status": "logged" | "spooled", "kind", "sum", "len"}. The id is assigned under the lock.
    When the lock stays busy for timeout seconds (the default when None), the entry goes to the spool and has no id
    until the next locked writer adopts it. Empty text raises usage."""
    if src not in SOURCES:
        raise RoadmapError("usage", "capture source '" + str(src) + "' is not valid", EXIT_USAGE)
    clean = clean_text(text)
    if not clean.strip():
        raise RoadmapError("usage", "nothing to log: the text is empty", EXIT_USAGE)
    entry = {
        "v": head.VERSION, "t": "e", "ts": _ts(now), "src": src, "sid": session_key(session_id),
        "acct": _short(acct, 8), "kind": (kind or head.guess_kind(clean)), "sum": make_summary(clean, sum_text),
        "len": len(clean), "h": _digest(clean),
    }
    if from_id:
        entry["from"] = str(from_id)[:12]
    try:
        with lock.locked(data_dir, timeout):
            _adopt_locked(data_dir)
            line = _append_entry_locked(data_dir, entry, clean)
        return {"id": line["id"], "status": "logged", "kind": line["kind"], "sum": line["sum"], "len": line["len"]}
    except RoadmapError as exc:
        if exc.code != "locked":
            raise
    _spool_append(data_dir, {"e": entry, "text": clean})
    return {"id": None, "status": "spooled", "kind": entry["kind"], "sum": entry["sum"], "len": entry["len"]}


def update(data_dir, eid, *, by, sets=None, links=(), note=None, now=None, timeout=None):
    """Append one update record: set fields, +/- link refs and an optional note. The entry must exist.
    Agents cannot change ts, src or text: only SET_KEYS are accepted. Returns the record written."""
    if by not in BY:
        raise RoadmapError("usage", "update by must be one of " + "|".join(BY), EXIT_USAGE)
    if not isinstance(eid, str) or not _ID_RE.match(eid):
        raise RoadmapError("usage", "not a head id: " + repr(eid), EXIT_USAGE)
    sets = dict(sets or {})
    unknown = sorted(set(sets) - set(SET_KEYS))
    if unknown:
        raise RoadmapError("usage", "cannot set " + ", ".join(unknown) + " (allowed: " + ", ".join(SET_KEYS) + ")",
                           EXIT_USAGE)
    if "status" in sets and sets["status"] not in head.MANUAL_STATUSES:
        raise RoadmapError("usage", "status must be one of " + "|".join(head.MANUAL_STATUSES), EXIT_USAGE)
    if "kind" in sets and sets["kind"] not in KINDS:
        raise RoadmapError("usage", "kind must be one of " + "|".join(KINDS), EXIT_USAGE)
    if "sum" in sets:
        sets["sum"] = make_summary("", sets["sum"])
    refs = list(links or ())
    if len(refs) > MAX_LINKS:
        raise RoadmapError("usage", "at most " + str(MAX_LINKS) + " link changes per update", EXIT_USAGE)
    for ref in refs:
        if not isinstance(ref, str) or ref[:1] not in ("+", "-") or head.parse_link(ref[1:]) is None:
            raise RoadmapError("usage", "link must be +kind:value or -kind:value, got " + repr(ref), EXIT_USAGE)
    clean_note = secrets.scrub(" ".join(str(note or "").split()))[:NOTE_MAX] or None
    rec = {"v": head.VERSION, "t": "u", "id": eid, "ts": _ts(now), "by": by}
    if sets:
        rec["set"] = sets
    if refs:
        rec["link"] = refs
    if clean_note:
        rec["note"] = clean_note
    with lock.locked(data_dir, timeout):
        _adopt_locked(data_dir)
        if not any(o.get("t") == "e" and o.get("id") == eid for o in _records(data_dir)):
            raise RoadmapError("not_found", "no head entry " + eid, EXIT_NOT_FOUND)
        jsonl.append_line(_path(data_dir, FILE), rec)
    return rec


def session(data_dir, ev, *, session_id=None, acct=None, model=None, usage=None, now=None, timeout=None):
    """Append one session record (claim, start or end). usage keeps only h5 and wk percentages."""
    if ev not in SESSION_EVENTS:
        raise RoadmapError("usage", "session event must be one of " + "|".join(SESSION_EVENTS), EXIT_USAGE)
    rec = {"v": head.VERSION, "t": "s", "ts": _ts(now), "sid": session_key(session_id), "acct": _short(acct, 8),
           "model": _short(model, 40), "ev": ev}
    if usage:
        kept = {k: usage[k] for k in ("h5", "wk") if isinstance(usage.get(k), (int, float))
                and not isinstance(usage.get(k), bool)}
        if kept:
            rec["usage"] = kept
    rec = {k: v for k, v in rec.items() if v is not None}
    with lock.locked(data_dir, timeout):
        _adopt_locked(data_dir)
        jsonl.append_line(_path(data_dir, FILE), rec)
    return rec


def rows(data_dir, link_state=None, now=None):
    """The folded entries (roadmap/core/head.py fold), in file order. link_state maps refs to their states."""
    return head.fold(_records(data_dir), link_state=link_state, now=now)


def text_of(data_dir, eid):
    """The redacted verbatim text of one entry, or None. Reads head-text.jsonl; the last line for an id wins."""
    found = None
    objs, _ = jsonl.read_objects(_path(data_dir, TEXT_FILE))
    for obj in objs:
        if obj.get("id") == eid and isinstance(obj.get("text"), str):
            found = obj["text"]
    return found


def _age_text(minutes):
    minutes = max(0, int(minutes))
    if minutes < 60:
        return str(minutes) + "m"
    if minutes < 1440:
        return str(minutes // 60) + "h"
    return str(minutes // 1440) + "d"


def brief(data_dir, link_state=None, now=None):
    """The resume digest as plain lines, at most BRIEF_MAX_LINES: counts, needs-you, open asks (oldest first) and
    decisions and rules from the last 7 days."""
    now = now or datetime.now(timezone.utc)
    items = rows(data_dir, link_state=link_state, now=now)
    open_rows = [r for r in items if r["status"] not in _CLOSED]
    unhandled = [r for r in open_rows if r["status"] in ("new", "understood")]
    doing = [r for r in open_rows if r["status"] == "doing"]
    needs = [r for r in open_rows if r["status"] == "needs-you"]
    oldest = max((r["age_min"] for r in unhandled if r["age_min"] is not None), default=None)
    head_line = "head: %d open, %d unhandled%s, %d doing, %d needs-you" % (
        len(open_rows), len(unhandled), (" (oldest " + _age_text(oldest) + ")") if oldest is not None else "",
        len(doing), len(needs))
    lines = [head_line]
    if needs:
        lines.append("needs you:")
        lines += ["  %s %s" % (r["id"], r["sum"][:60]) for r in needs[:2]]
    asks = sorted((r for r in open_rows if r["status"] != "needs-you" and _kind(r) not in ("decision", "rule")),
                  key=lambda r: str(r["ts"]))
    if asks:
        lines.append("open asks, oldest first:")
        for r in asks[:6]:
            lines.append("  %s %s %s %s" % (r["id"], _kind(r), r["status"], r["sum"][:60]))
    recent = []
    cutoff = now - timedelta(days=7)
    for r in items:
        when = head.parse_ts(r["ts"])
        if (_kind(r) in ("decision", "rule") and when is not None and when >= cutoff
                and r["status"] not in ("declined", "merged")):
            recent.append(r)
    if recent:
        lines.append("decisions and rules, 7 days:")
        for r in recent[-2:]:
            lines.append("  %s %s %s" % (r["id"], _kind(r), r["sum"][:60]))
    if len(lines) > BRIEF_MAX_LINES:
        lines = lines[:BRIEF_MAX_LINES - 1] + ["  more: roadmap head list"]
    return lines
