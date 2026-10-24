"""Head store service (HEAD-SPEC sections 2, 3, 7): appends entries, updates and session records to head.jsonl under the
data-dir lock, keeps the redacted verbatim text in head-text.jsonl, parks hook captures in head-spool.jsonl while the
lock is busy, and writes the resume brief. The fold and heuristics are in roadmap/core/head.py; redaction in
roadmap/core/secrets.py. Writers that take the lock adopt the spool first, in order."""

import errno
import fcntl
import hashlib
import json
import os
import re
import stat
import time
from datetime import datetime, timedelta, timezone

from roadmap.core import head, planfmt, secrets
from roadmap.errors import EXIT_CONFLICT, EXIT_INVALID_DATA, EXIT_NOT_FOUND, EXIT_USAGE, RoadmapError
from roadmap.services import jobs
from roadmap.store import db as _store_db
from roadmap.store import atomic, head_db, jsonl, lock
from roadmap.store import config as store_config

FILE = "head.jsonl"
TEXT_FILE = "head-text.jsonl"
SPOOL_FILE = "head-spool.jsonl"
MAX_ENTRIES = 5000
MAX_ID = 9999
TEXT_MAX = 8000
ASSETS_MAX = 20
ASSET_CHARS = 200
SUM_MAX = head.SUM_MAX
NOTE_MAX = 160
BRIEF_MAX_LINES = 15
SOURCES = ("hook", "cli", "gui", "import")
BY = ("head", "person", "auto")
SET_KEYS = ("status", "kind", "sum", "into", "prio", "opts")
OPTS_MIN, OPTS_MAX, OPT_MAX = 2, 6, 80  # a head ask may carry 2..6 answer choices (R9.31); [] clears them
KINDS = ("ask", "decision", "rule", "bug", "preference", "question", "review", "info")
SESSION_EVENTS = ("claim", "start", "end")
MAX_LINKS = head.MAX_LINKS
_ID_RE = re.compile(r"^H(\d+)$")
CLOSE_NEXT = "roadmap head brief"
CLOSES_PER_MINUTE = 3           # the 4th head close inside one minute is refused (use head next)
CLOSE_WINDOW_S = 60
REPEAT_WINDOW_S = 3600          # an answer may not repeat another head close of the last hour
ANSWER_MIN = 20                 # an answer: text needs this many characters
SHA_RE = re.compile(r"\b[0-9a-f]{7,40}\b")
JOB_RE = re.compile(r"\bj\d+\b")
ANSWER_RE = re.compile(r"answer:\s*(.*)", re.IGNORECASE | re.DOTALL)
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


def sqlite_db(data_dir):
    """Path of the head ledger db when the sqlite backend is on (env ROADMAP_STORE=sqlite, or the project entry for
    this data dir has store: sqlite). None keeps the JSON backend, which is the default."""
    if os.environ.get("ROADMAP_STORE", "").strip().lower() == "sqlite":
        return _store_db.db_path(data_dir)
    try:
        projects = store_config.load().get("projects") or []
    except RoadmapError:
        return None
    here = os.path.realpath(data_dir)
    for project in projects:
        if project.get("store") == "sqlite" and os.path.realpath(
                os.path.join(str(project.get("path", "")), str(project.get("dataDir", "docs")))) == here:
            return _store_db.db_path(data_dir)
    return None


def session_key(session_id):
    """First 8 hex digits of sha256(session_id): the raw id is never stored. None when there is no id."""
    if not session_id:
        return None
    return hashlib.sha256(str(session_id).encode("utf-8")).hexdigest()[:8]


def clean_text(text):
    """Control characters stripped, secrets masked, then cut to the verbatim limit. A cut never leaves half a mask:
    a trailing '[' with no closing ']' after it is dropped."""
    out = secrets.scrub(_CONTROL.sub("", "" if text is None else str(text)))[:TEXT_MAX]
    open_at = out.rfind("[")
    if open_at != -1 and "]" not in out[open_at:]:
        out = out[:open_at]
    return out


def make_summary(text, given=None):
    """The one-line summary: the head's own text when given, else the heuristic. Masked, one line, 100 chars."""
    base = given if given is not None else head.summarize(text)
    return secrets.scrub(" ".join(str(base or "").split()))[:SUM_MAX]


def clean_assets(items):
    """Names and paths of a prompt's attachments (HEAD-SPEC section 13): text only, control characters stripped, masked,
    each cut to ASSET_CHARS, no repeats, at most ASSETS_MAX. Anything that is not a list gives []. Never reads a
    file."""
    out = []
    if not isinstance(items, (list, tuple)):
        return out
    for item in items:
        if not isinstance(item, str):
            continue
        name = secrets.scrub(_CONTROL.sub("", " ".join(item.split())))[:ASSET_CHARS].strip()
        if name and name not in out:
            out.append(name)
        if len(out) >= ASSETS_MAX:
            break
    return out


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


def _append_entry_locked(data_dir, entry, text, assets=None):
    """Assign the next id and append the entry and its text (and its assets, when there are any). The caller holds
    the lock."""
    objs, _ = jsonl.read_objects(_path(data_dir, FILE))
    eid = _next_id(objs)
    line = dict(entry, id=eid)
    jsonl.append_line(_path(data_dir, FILE), line)
    text_line = {"id": eid, "text": text}
    if assets:
        text_line["assets"] = list(assets)
    jsonl.append_line(_path(data_dir, TEXT_FILE), text_line)
    return line


def _deadline(timeout):
    """The monotonic time a bounded wait must stop at, or None when no timeout was given."""
    return None if timeout is None else time.monotonic() + max(0.0, float(timeout))


def _open_spool(path, flags):
    """Open the spool without following a symlink, and require one regular file with a single link. A hard link
    to another file on the volume would make writes land in that file, so it is refused, left unchanged."""
    try:
        fd = os.open(path, flags | os.O_NOFOLLOW, 0o600)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise RoadmapError("invalid_data", "refusing a symlinked spool, left unchanged: " + path, EXIT_INVALID_DATA)
        raise
    st = os.fstat(fd)
    if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
        os.close(fd)
        raise RoadmapError("invalid_data", "refusing a spool that is not one regular file, left unchanged: " + path,
                           EXIT_INVALID_DATA)
    return fd


def _flock_bounded(fh, timeout):
    """Take the exclusive flock on fh, waiting at most timeout seconds (the lock default when None)."""
    wait = lock.DEFAULT_TIMEOUT_S if timeout is None else timeout
    deadline = time.monotonic() + max(0.0, float(wait))
    while True:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except OSError as exc:
            if exc.errno not in (errno.EAGAIN, errno.EACCES, errno.EWOULDBLOCK):
                raise
            if time.monotonic() >= deadline:
                raise RoadmapError("locked", "the head spool is busy; try again in a moment", EXIT_CONFLICT)
            time.sleep(lock.POLL_S)


def _spool_append(data_dir, payload, timeout=None):
    """Park one unnumbered entry in the spool without the directory lock. flock on the spool file orders it
    against the adopting writer. The flock wait is bounded by timeout: past it, locked is raised and nothing is
    written."""
    path = _path(data_dir, SPOOL_FILE)
    if os.path.islink(path):
        raise RoadmapError("invalid_data", "refusing to append to a symlink, left unchanged: " + path,
            EXIT_INVALID_DATA)
    os.makedirs(data_dir, exist_ok=True)
    line = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
    fd = _open_spool(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND)
    with os.fdopen(fd, "a", encoding="utf-8") as fh:
        _flock_bounded(fh, timeout)
        try:
            fh.write(line)
            fh.flush()
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def _spooled_entry(e, text, nonce):
    """Rebuild a spooled entry from its text, never trusting the spool's own fields: the text is cleaned again, the
    summary masked again, and only the known keys are kept. nonce marks the entry, so a replayed spool line is not
    logged twice."""
    kind = e.get("kind")
    if not (isinstance(kind, str) and kind.rstrip("?") in KINDS):
        kind = head.guess_kind(text)
    src = e.get("src") if e.get("src") in SOURCES else "hook"
    sid = e.get("sid")
    entry = {
        "v": head.VERSION, "t": "e", "ts": str(e.get("ts") or _ts())[:32], "src": src,
        "sid": str(sid)[:8] if isinstance(sid, str) and sid else None, "acct": _short(e.get("acct"), 8),
        "kind": kind, "sum": make_summary(text, e.get("sum") if isinstance(e.get("sum"), str) else None),
        "len": len(text), "h": _digest(text),
        "prio": e["prio"] if head.valid_prio(e.get("prio")) else head.guess_prio(text),
    }
    if isinstance(e.get("from"), str):
        entry["from"] = e["from"][:12]
    if nonce:
        entry["n"] = nonce
    return entry


def _adopt_locked(data_dir, deadline=None):
    """Move spooled captures into head.jsonl, in spool order. Caller holds the directory lock. Lines that could not
    be adopted (the cap, a refused file, or the deadline passed) stay in the spool, in order, for the next writer.
    A line whose nonce is already in head.jsonl (a replay after a crash) is not logged again. Returns the number
    adopted."""
    path = _path(data_dir, SPOOL_FILE)
    if not os.path.exists(path):
        return 0
    if os.path.islink(path):
        raise RoadmapError("invalid_data", "refusing to read a symlinked spool, left unchanged: " + path,
            EXIT_INVALID_DATA)
    adopted = 0
    fd = _open_spool(path, os.O_RDWR)
    with os.fdopen(fd, "r+", encoding="utf-8") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            head_objs, _ = jsonl.read_objects(_path(data_dir, FILE))
            seen = {o.get("n") for o in head_objs if o.get("t") == "e" and o.get("n")}
            lines = fh.read().splitlines()
            remaining = []
            for raw in lines:
                if not raw.strip():
                    continue
                if remaining or (deadline is not None and time.monotonic() >= deadline):
                    remaining.append(raw)
                    continue
                try:
                    payload = json.loads(raw)
                except ValueError:
                    continue
                if not isinstance(payload, dict) or not isinstance(payload.get("e"), dict):
                    continue
                nonce = payload.get("n") if isinstance(payload.get("n"), str) else None
                if nonce and nonce in seen:
                    adopted += 1
                    continue
                text = clean_text(payload.get("text", ""))
                extra = {"assets": clean_assets(payload.get("assets"))} if payload.get("assets") else {}
                try:
                    _append_entry_locked(data_dir, _spooled_entry(payload["e"], text, nonce), text, **extra)
                except RoadmapError:
                    remaining.append(raw)
                    continue
                if nonce:
                    seen.add(nonce)
                adopted += 1
            fh.seek(0)
            fh.truncate()
            if remaining:
                fh.write("\n".join(remaining) + "\n")
            fh.flush()
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    return adopted


def _bump_repeat_locked(data_dir, digest, now):
    """A repeat of an entry's verbatim text (same digest) raises the newest such entry one priority level (bump_prio),
    as an auto update, and logs no new entry. Returns the capture result, or None when the text is new. The caller
    holds the lock."""
    records = _records(data_dir)
    match = None
    for rec in records:
        if rec.get("t") == "e" and rec.get("h") == digest:
            match = rec.get("id")
    if match is None:
        return None
    row = next((r for r in head.fold(records, now=now) if r["id"] == match), None)
    prio = head.bump_prio(row["prio"] if row else head.PRIO_DEFAULT)
    rec = {"v": head.VERSION, "t": "u", "id": match, "ts": _ts(now), "by": "auto", "set": {"prio": prio}}
    jsonl.append_line(_path(data_dir, FILE), rec)
    return {"id": match, "status": "bumped", "kind": row["kind"] if row else None,
            "sum": row["sum"] if row else "", "len": None, "prio": prio}


def capture(data_dir, text, *, session_id=None, src="hook", acct=None, kind=None, sum_text=None,
            from_id=None, assets=None, now=None, timeout=None, repeat_bump=True):
    """Log one message verbatim (redacted) with its heuristic kind and summary, and its attachment names (assets).

    Returns {"id", "status": "logged" | "spooled", "kind", "sum", "len"}. The id is assigned under the lock.
    When the lock stays busy for timeout seconds (the default when None), the entry goes to the spool and has no id
    until the next locked writer adopts it. Empty text raises usage."""
    if src not in SOURCES:
        raise RoadmapError("usage", "capture source '" + str(src) + "' is not valid", EXIT_USAGE)
    clean = clean_text(text)
    if not clean.strip():
        raise RoadmapError("usage", "nothing to log: the text is empty", EXIT_USAGE)
    db_path = sqlite_db(data_dir)
    if db_path:
        return head_db.log(db_path, clean, kind or head.guess_kind(clean), make_summary(clean, sum_text), now=now)
    names = clean_assets(assets)
    entry = {
        "v": head.VERSION, "t": "e", "ts": _ts(now), "src": src, "sid": session_key(session_id),
        "acct": _short(acct, 8), "kind": (kind or head.guess_kind(clean)), "sum": make_summary(clean, sum_text),
        "len": len(clean), "h": _digest(clean), "prio": head.guess_prio(clean),
    }
    if from_id:
        entry["from"] = str(from_id)[:12]
    try:
        with lock.locked(data_dir, timeout):
            _adopt_locked(data_dir, _deadline(timeout))
            repeat = _bump_repeat_locked(data_dir, entry["h"], now) if repeat_bump else None
            if repeat is not None:
                return repeat
            line = _append_entry_locked(data_dir, entry, clean, names)
        return {"id": line["id"], "status": "logged", "kind": line["kind"], "sum": line["sum"], "len": line["len"],
                "prio": line["prio"]}
    except RoadmapError as exc:
        if exc.code != "locked":
            raise
    _spool_append(data_dir, {"e": entry, "text": clean, "assets": names, "n": os.urandom(8).hex()}, timeout)
    return {"id": None, "status": "spooled", "kind": entry["kind"], "sum": entry["sum"], "len": entry["len"]}


def _answer_key(text):
    """The answer text of a note, lower-cased with single spaces, or '' when the note has no answer: part."""
    match = ANSWER_RE.search(text or "")
    return " ".join(match.group(1).split()).lower() if match else ""


def _commit_exists(data_dir, sha):
    """True when sha names a commit in the project's repo. Lazy import: gitops imports this module."""
    from roadmap.services import gitops
    try:
        root = gitops._root(data_dir)
        return gitops._ref_exists(root, sha + "^{commit}")
    except RoadmapError:
        return False


def _real_ref(data_dir, note):
    """True when the note names a commit sha that exists, or an existing job id."""
    if any(_commit_exists(data_dir, sha) for sha in SHA_RE.findall(note)):
        return True
    wanted = set(JOB_RE.findall(note))
    return bool(wanted) and any(str(job.get("id")) in wanted for job in jobs.list_jobs(data_dir))


def check_close(data_dir, eid, note, now=None):
    """Guard a head close (set status=done by the head): at most CLOSES_PER_MINUTE closes a minute, and a note with a
    real ref (commit sha, job id) or an answer: text of ANSWER_MIN characters that does not repeat a close of the last
    hour. Called by the head's CLI before a head close (not the person's, not the auto fold). The raw note is checked:
    scrub would mask a 40-character sha."""
    moment = (now if now is not None else datetime.now(timezone.utc)).astimezone(timezone.utc)
    closes = [rec for rec in _records(data_dir)
              if rec.get("t") == "u" and rec.get("by") == "head" and isinstance(rec.get("set"), dict)
              and rec["set"].get("status") == "done"]
    recent = [rec for rec in closes if 0 <= (moment - (head.parse_ts(rec.get("ts")) or moment)).total_seconds()
              < CLOSE_WINDOW_S]
    if len(recent) >= CLOSES_PER_MINUTE:
        raise RoadmapError("usage", "more than %d closes a minute on head; use head next" % CLOSES_PER_MINUTE,
                           EXIT_USAGE, next=CLOSE_NEXT)
    if _real_ref(data_dir, note):
        return
    answer = _answer_key(note)
    if len(answer) >= ANSWER_MIN:  # the answer text itself is compared, so a repeat of the last hour is refused
        repeated = any(_answer_key(rec.get("note")) == answer for rec in closes
                       if 0 <= (moment - (head.parse_ts(rec.get("ts")) or moment)).total_seconds() < REPEAT_WINDOW_S)
        if repeated:
            raise RoadmapError("usage", "this answer repeats another close in the last hour; say what this close "
                               "answers", EXIT_USAGE, next=CLOSE_NEXT)
        return
    raise RoadmapError("usage", "a close needs a note with a real ref: a commit sha, a job id, or answer: text of "
                       "%d+ characters" % ANSWER_MIN, EXIT_USAGE, next=CLOSE_NEXT)


def check_umbrella_binds(data_dir, eid, adds=(), removes=(), now=None):
    """A head bind that adds links may not leave the entry bound only to umbrella tasks (R7.31): the R7.34 rule,
    extended from head set to head bind and head t. adds and removes are link refs such as task:R7.69."""
    if not adds:
        return
    moment = (now if now is not None else datetime.now(timezone.utc)).astimezone(timezone.utc)
    current = next((row["links"] for row in head.fold(_records(data_dir), now=moment) if row["id"] == eid), [])
    final = [ref for ref in current if ref not in set(removes)] + list(adds)
    if final and all(ref.startswith("task:") and planfmt.is_umbrella_task(ref[len("task:"):]) for ref in final):
        raise RoadmapError("usage", eid + " would be bound only to an umbrella task; bind a real task first",
                           EXIT_USAGE, next="roadmap head convert " + eid)


def clean_opts(value):
    """Answer choices as a list of 0 or 2..6 distinct non-empty strings of at most 80 characters. [] clears them.
    Anything else is a usage error (R9.31)."""
    if not isinstance(value, (list, tuple)):
        raise RoadmapError("usage", "opts must be a list of 2 to 6 choices", EXIT_USAGE)
    out = []
    for item in value:
        text = " ".join(str(item if item is not None else "").split())[:OPT_MAX]
        if not text:
            raise RoadmapError("usage", "an option must not be empty", EXIT_USAGE)
        if text not in out:
            out.append(text)
    if out and not OPTS_MIN <= len(out) <= OPTS_MAX:
        raise RoadmapError("usage", "give 2 to 6 options (one given)" if len(out) == 1
                           else "give 2 to 6 options, got " + str(len(out)), EXIT_USAGE)
    return out


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
    if "prio" in sets and not head.valid_prio(sets["prio"]):
        raise RoadmapError("usage", "prio must be one of 0|1|2|3 (P0-P3)", EXIT_USAGE)
    if "opts" in sets:
        sets["opts"] = clean_opts(sets["opts"])
    if "sum" in sets:
        sets["sum"] = make_summary("", sets["sum"])
    refs = list(links or ())
    if len(refs) > MAX_LINKS:
        raise RoadmapError("usage", "at most " + str(MAX_LINKS) + " link changes per update", EXIT_USAGE)
    for ref in refs:
        if not isinstance(ref, str) or ref[:1] not in ("+", "-") or head.parse_link(ref[1:]) is None:
            raise RoadmapError("usage", "link must be +kind:value or -kind:value, got " + repr(ref), EXIT_USAGE)
    clean_note = secrets.scrub(" ".join(str(note or "").split()))[:NOTE_MAX] or None
    db_path = sqlite_db(data_dir)
    if db_path:
        return head_db.update(db_path, eid, by=by, sets=sets, links=refs, note=clean_note, now=now)
    rec = {"v": head.VERSION, "t": "u", "id": eid, "ts": _ts(now), "by": by}
    if sets:
        rec["set"] = sets
    if refs:
        rec["link"] = refs
        seen = _done_at_bind(data_dir, [ref[1:] for ref in refs if ref[0] == "+"])
        if seen:
            rec["seen"] = seen
    if clean_note:
        rec["note"] = clean_note
    with lock.locked(data_dir, timeout):
        _adopt_locked(data_dir, _deadline(timeout))
        if not any(o.get("t") == "e" and o.get("id") == eid for o in _records(data_dir)):
            raise RoadmapError("not_found", "no head entry " + eid, EXIT_NOT_FOUND)
        jsonl.append_line(_path(data_dir, FILE), rec)
    return rec


def _done_at_bind(data_dir, refs):
    """The refs (e.g. 'task:R10.27') whose task is already done now. Stored as 'seen' on the bind record so the fold
    does not close the entry on them (R10.27): only a task that turns done after the bind closes an ask."""
    if not refs:
        return []
    done = {"task:" + str(t.get("id")) for t in jobs.task_records(data_dir) if str(t.get("status")) == "done"}
    from roadmap.services import work
    states, owner = work.head_states(data_dir)
    done = {ref for ref in done if ref[len("task:"):] not in owner}
    done |= {ref for ref, state in states.items() if state == "done" and not ref.startswith("_")}
    return [ref for ref in refs if ref in done]


def fold_asks(data_dir, now=None):
    """Close each open ask whose bound tasks are all done (by: auto). The note lists the real commit shas of those
    tasks, e.g. 'auto: R7.44 c1a2b3c, R7.45 d4e5f6a'. An ask with an unfinished task stays open. The person
    still reviews the closed ask. Returns the ids closed."""
    tasks = {str(t.get("id")): t for t in jobs.task_records(data_dir)}
    states = {"task:" + tid: str(t.get("status")) for tid, t in tasks.items()}
    from roadmap.services import work
    work_states, owner = work.head_states(data_dir)
    states.update({k: v for k, v in work_states.items() if not k.startswith("_")})
    closed = []
    for row in head.fold(_records(data_dir), states, now=now):
        if row.get("manual") is not None or _kind(row) != "ask":
            continue
        verdict = work.ask_close(row["links"], work_states, owner)
        if verdict is not None:  # bound to a Work item: closes only when it is accepted or Won't do
            if verdict[0] and not head.all_bound_done(row):
                update(data_dir, row["id"], by="auto", sets={"status": "done"}, note=verdict[1], now=now)
                closed.append(row["id"])
            continue
        ids = [ref[len("task:"):] for ref in row["links"] if ref.startswith("task:")]
        if not ids or any(states.get("task:" + tid) != "done" for tid in ids) or head.all_bound_done(row):
            continue
        note = "auto: " + ", ".join(_task_shas(tasks.get(tid), tid) for tid in ids)
        update(data_dir, row["id"], by="auto", sets={"status": "done"}, note=note, now=now)
        closed.append(row["id"])
    return closed


def _task_shas(task, task_id):
    """The task id and its commit shas, e.g. 'R7.44 c1a2b3c' (one entry per commit), or the id alone."""
    shas = [r[len("commit:"):][:7] for r in (task or {}).get("refs") or [] if str(r).startswith("commit:")]
    return ", ".join(task_id + " " + sha for sha in shas) if shas else task_id


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
        _adopt_locked(data_dir, _deadline(timeout))
        jsonl.append_line(_path(data_dir, FILE), rec)
    return rec


def rows(data_dir, link_state=None, now=None):
    """The folded entries (roadmap/core/head.py fold), in file order. link_state maps refs to their states."""
    return head.fold(_records(data_dir), link_state=link_state, now=now)


def _newest_key(entry):
    """Newest-first sort key, the same as the snapshot head key (core/snapshot.py _newest_key): ts as time, then the
    numeric part of the id, so two entries at one time keep a stable order."""
    when = head.parse_ts(entry.get("ts"))
    num = int("".join(ch for ch in str(entry.get("id") or "") if ch.isdigit()) or 0)
    return (when.timestamp() if when is not None else 0, num)


def accepted_ids(records):
    """The ids whose last status change is the person's done (same rule as the snapshot's _accepted_ids)."""
    last = {}
    for rec in records:
        sets = rec.get("set") if isinstance(rec.get("set"), dict) else {}
        if rec.get("t") == "u" and "status" in sets:
            last[rec.get("id")] = (sets["status"], rec.get("by"))
    return {eid for eid, mark in last.items() if mark == ("done", "person")}


def page(data_dir, *, f="open", offset=0, limit=50, link_state=None, now=None):
    """One page of the full ledger, newest first. f=open takes the open rows, f=all every row. Returns the folded
    entries of the whole ledger ("entries", for id checks), the scope's "total", the counts over the whole ledger
    ("counts"), the accepted ids and the rows offset..offset+limit of the scope (folded entries, not yet rows)."""
    records = _records(data_dir)
    entries = head.fold(records, link_state=link_state, now=now)
    accepted = accepted_ids(records)
    open_rows = [e for e in entries if e["status"] not in head.CLOSED_STATUSES]
    scope = open_rows if f == "open" else entries
    ordered = sorted(scope, key=_newest_key, reverse=True)
    counts = {"open": len(open_rows),
              "unhandled": sum(1 for e in open_rows if e["status"] in ("new", "understood")),
              "doing": sum(1 for e in open_rows if e["status"] == "doing"),
              "needs": sum(1 for e in open_rows if e["status"] == "needs-you"),
              "doneUnacc": sum(1 for e in entries if e["status"] == "done" and e["id"] not in accepted)}
    return {"entries": entries, "total": len(ordered), "counts": counts, "accepted": accepted,
            "rows": ordered[offset:offset + limit]}


def text_of(data_dir, eid):
    """The redacted verbatim text of one entry, or None. Reads head-text.jsonl; the last line for an id wins."""
    found = None
    objs, _ = jsonl.read_objects(_path(data_dir, TEXT_FILE))
    for obj in objs:
        if obj.get("id") == eid and isinstance(obj.get("text"), str):
            found = obj["text"]
    return found


def details_of(data_dir, eid):
    """The text, reply and assets of one entry (HEAD-SPEC section 13): {"text", "reply", "assets"}; text and reply are
    None when absent and assets is []. The last line for each key wins. Reads head-text.jsonl only."""
    out = {"text": None, "reply": None, "assets": []}
    objs, _ = jsonl.read_objects(_path(data_dir, TEXT_FILE))
    for obj in objs:
        if obj.get("id") != eid:
            continue
        if isinstance(obj.get("text"), str):
            out["text"] = obj["text"]
        if isinstance(obj.get("reply"), str):
            out["reply"] = obj["reply"]
        if isinstance(obj.get("assets"), list):
            out["assets"] = clean_assets(obj["assets"])
    return out


PREVIEW_TEXT, PREVIEW_REPLY = 120, 100  # the first characters of the text and the reply in a list row (R10.2)


def _preview(value, limit):
    """The first limit characters of a text, whitespace collapsed, with an ellipsis when cut; None when empty."""
    text = " ".join(str(value or "").split())
    if not text:
        return None
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def previews_of(data_dir, ids):
    """{id: {"text", "reply"}} for the ids given: the short previews of each entry's text and reply, read from
    head-text.jsonl in one pass (the last line for each key wins). None where there is no text or reply."""
    want = set(ids)
    out = {eid: {"text": None, "reply": None} for eid in want}
    if not want:
        return out
    objs, _ = jsonl.read_objects(_path(data_dir, TEXT_FILE))
    raw = {eid: {"text": None, "reply": None} for eid in want}
    for obj in objs:
        eid = obj.get("id")
        if eid not in want:
            continue
        for key in ("text", "reply"):
            if isinstance(obj.get(key), str):
                raw[eid][key] = obj[key]
    for eid in want:
        out[eid] = {"text": _preview(raw[eid]["text"], PREVIEW_TEXT),
                    "reply": _preview(raw[eid]["reply"], PREVIEW_REPLY)}
    return out


def set_reply(data_dir, eid, reply, *, timeout=None):
    """Store the head's reply to one entry (HEAD-SPEC section 13): one line in head-text.jsonl, redacted and cut to
    TEXT_MAX by clean_text. The last reply line for an id wins. Empty reply raises usage, an unknown id not_found.
    Returns the stored length."""
    if not isinstance(eid, str) or not _ID_RE.match(eid):
        raise RoadmapError("usage", "not a head id: " + repr(eid), EXIT_USAGE)
    clean = clean_text(reply)
    if not clean.strip():
        raise RoadmapError("usage", "nothing to store: the reply is empty", EXIT_USAGE)
    with lock.locked(data_dir, timeout):
        _adopt_locked(data_dir, _deadline(timeout))
        if not any(o.get("t") == "e" and o.get("id") == eid for o in _records(data_dir)):
            raise RoadmapError("not_found", "no head entry " + eid, EXIT_NOT_FOUND)
        jsonl.append_line(_path(data_dir, TEXT_FILE), {"id": eid, "reply": clean})
    return len(clean)


def latest_hook_entry(data_dir, session_id):
    """The newest entry this session captured through the hook (src hook), or None. Reads head.jsonl only."""
    key = session_key(session_id)
    if key is None:
        return None
    found = None
    for rec in _records(data_dir):
        if rec.get("t") == "e" and rec.get("src") == "hook" and rec.get("sid") == key:
            found = rec
    return found


def forget_text(data_dir, eid):
    """Drop every verbatim line of one entry from head-text.jsonl, rewriting the file atomically (an append of an
    empty text would leave the old lines in place). Other lines are kept as they are. The caller holds the lock.
    Returns the number of lines dropped."""
    path = _path(data_dir, TEXT_FILE)
    if not os.path.exists(path):
        return 0
    kept, dropped = [], 0
    for raw in jsonl.raw_lines(path):
        if not raw.strip():
            continue
        try:
            obj = json.loads(raw)
        except ValueError:
            kept.append(raw)
            continue
        if isinstance(obj, dict) and obj.get("id") == eid:
            dropped += 1
            continue
        kept.append(raw)
    if dropped:
        atomic.write_text(path, "".join(line + "\n" for line in kept))
    return dropped


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


# ------------------------------------------------------------------ autopilot gate (HEAD-SPEC section 11, H12)

GATE_LIMIT = 5
GATE_WINDOW_S = 600          # at most one gate block per this many seconds
GATE_5H_STOP = 90            # usage stops (percent): the gate stays silent at or above these
GATE_WEEK_STOP = 95
GATE_PAUSE_FILE = "head-pause"   # a file in the data dir: its presence pauses the gate
GATE_STAMP_FILE = "head-gate.json"
GATE_OPEN = ("new", "understood", "bound", "doing")
GATE_UNBOUND_MIN = 15        # an open ask with no link after this many minutes is flagged "unbound"
GATE_MAX_AGE_MIN = 24 * 60   # open asks older than this are counted in a "+N older asks" line, not listed
_IDLE_TOOLS = (("cursor", "cursor idle: run the review audit"), ("agy", "agy idle: run an audit"))


def _at_stop(usage):
    """True when a usage reading is at or over a stop. A missing reading is not a stop."""
    if not isinstance(usage, dict):
        return False
    for key, stop in (("fiveHourPercent", GATE_5H_STOP), ("weeklyPercent", GATE_WEEK_STOP)):
        value = usage.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= stop:
            return True
    return False


def _age_min(ts, now):
    when = head.parse_ts(ts)
    return max(0.0, (now - when).total_seconds() / 60.0) if when is not None else 0.0


def gate(rows, *, queue=(), running=(), dirty=None, unpushed=None, usage=None, paused=False, now=None,
         limit=GATE_LIMIT, audit_tools=None):
    """The autopilot continue items (HEAD-SPEC section 11), at most `limit` short lines, most urgent first: open
    asks oldest first, then queued tasks, then idle cursor and agy (only when there is other work), then
    uncommitted files and unpushed commits. Empty when paused, at a usage stop or when nothing waits.

    Pure: the caller supplies the folded head rows, the queued task ids, the running job records, the uncommitted
    file count and the unpushed commit count (None when unknown) and a usage dict. No file or process is read here."""
    if paused or _at_stop(usage):
        return []
    now = now or datetime.now(timezone.utc)
    asks = []
    older = 0
    for r in sorted(rows or [], key=lambda x: str(x.get("ts") or "")):
        if r.get("status") not in GATE_OPEN or _kind(r) in ("decision", "rule"):
            continue
        age = _age_min(r.get("ts"), now)
        if age > GATE_MAX_AGE_MIN:
            older += 1
            continue
        label = r["status"]
        if label in ("new", "understood"):  # no link yet; red from GATE_UNBOUND_MIN (HEAD-SPEC 11.4)
            label = "unbound" if age > GATE_UNBOUND_MIN else "unanswered"
        asks.append("%s %s %s: %s" % (r["id"], label, _age_text(age), r.get("sum", "")[:50]))
    if older:
        asks.append("+%d older asks: roadmap head list" % older)
    tasks = ["task %s queued, not started" % str(task) for task in queue or ()]
    tools = []
    names = [str(j.get("title", "")) + " " + str(j.get("model", "")) for j in running or () if isinstance(j, dict)]
    text = " ".join(names).lower()
    wanted = None if audit_tools is None else {str(t).lower() for t in audit_tools}
    for word, line in _IDLE_TOOLS:
        if wanted is not None and word not in wanted:
            continue  # the project's head.auditTools leaves this tool out (not installed there)
        if word not in text:
            tools.append(line)
    work = []
    if isinstance(dirty, int) and dirty > 0:
        work.append("%d uncommitted files" % dirty)
    if isinstance(unpushed, int) and unpushed > 0:
        work.append("%d unpushed commits" % unpushed)
    items = asks + tasks + work
    if items:
        items += tools  # idle resources are only worth a line when there is work to review or start
    return items[:limit]
