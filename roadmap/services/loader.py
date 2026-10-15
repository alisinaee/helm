"""Load a registered project's data files into a snapshot, and name the process that holds a TCP port.

The project's files are read from <path>/<dataDir> and parsed by roadmap.core.snapshot. A missing or unreadable
file never raises: it becomes an entry in the snapshot's errors[]. port_owner() lives here because subprocess
is allowed only in services/; it runs lsof, read-only.
"""

import contextlib
import hashlib
import json
import os
import subprocess
import threading
from datetime import datetime

from roadmap.core import head as head_format
from roadmap.core.extras import extra_file
from roadmap.core.parsers import error_entry
from roadmap.core.snapshot import build_snapshot
from roadmap.errors import RoadmapError
from roadmap.services import control, head as head_store, limits, presence, rules, usage
from roadmap.store import config as config_store
from roadmap.store import db as store_db
from roadmap.store import events as store_events
from roadmap.store import paths
from roadmap.store.migrate import JOB_CORE, PHASE_CORE, TASK_CORE

BASE_FILES = ("tasks.json", "jobs.json", "autonomy.json", "issues.json", "questions.json", "comments.json",
              "budget.json", "queue.json", "activity.jsonl", "features.json")
CONFIG_FILE = "roadmap.config.json"
UNDO_FILE = "undo.jsonl"  # the undo log (services/commands.py UNDO_FILE)
HEAD_FILES = (head_store.FILE, head_store.TEXT_FILE, head_store.SPOOL_FILE, head_store.GATE_STAMP_FILE,
              head_store.GATE_PAUSE_FILE, UNDO_FILE)  # the head reads and writes these beside head.jsonl
LSOF_TIMEOUT_S = 5


def project_folder(entry):
    """The data folder of a registered project entry: its path joined with dataDir. None when the entry has no
    usable path (empty, null or not text), so no relative folder is ever read from the working directory."""
    root = _project_path(entry)
    if root is None:
        return None
    data_dir = entry.get("dataDir")
    return os.path.join(root, data_dir if isinstance(data_dir, str) and data_dir else config_store.DEFAULT_DATA_DIR)


_CACHE = {}  # project id -> (rev, snapshot): the last build per project; one entry each, so memory stays bounded
_CACHE_LOCK = threading.Lock()


def _stamp(path):
    """(path, mtime_ns, size) of one file, or (path, None, None) when it is missing or cannot be stat'ed."""
    try:
        st = os.stat(path)
    except OSError:
        return (path, None, None)
    return (path, st.st_mtime_ns, st.st_size)


def revision(data_dir, project_id=None):
    """A 16-hex-character revision of everything one snapshot reads: (path, mtime_ns, size) of each project data file
    (the base files, roadmap.config.json, the configured extras, rules.txt and the head files: head.jsonl,
    head-text.jsonl, the head spool, head-gate.json, the head-pause flag and undo.jsonl), the project's presence
    file and control file when they apply, and the usage file. A missing file stamps as None, so creating or deleting
    one changes the revision. Only stat calls and one small config read; nothing is parsed or built."""
    dbp = _store_path(data_dir)
    if dbp is not None:
        return _store_rev(dbp)
    stamps = []
    if data_dir is not None:
        names = list(BASE_FILES) + [CONFIG_FILE]
        cfg = _read_project_config(data_dir, [])
        names += [name for name in _extra_names(cfg, []) if name not in names]
        names += [rules.FILE] + [name for name in HEAD_FILES if name not in names]
        stamps += [_stamp(os.path.join(data_dir, name)) for name in names]
        stamps.append(_stamp(presence.file_for(data_dir)))
    if project_id is not None:
        try:
            stamps.append(_stamp(control.control_path(project_id)))
        except RoadmapError:
            stamps.append(("control", None, None))
    stamps.append(_stamp(paths.usage_file()))
    raw = json.dumps(stamps, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def project_revision(project_id):
    """The revision of one registered project, with no build. Unknown ids raise not_found, as load_snapshot does."""
    entry = config_store.get_project(project_id)
    return revision(project_folder(entry), project_id)


def load_snapshot(project_id, now=None):
    """The snapshot of one registered project, with "rev" (its revision) and "usage" (usage.show()) in it.

    One build per (project, revision): while the revision is unchanged the cached build is returned. On a cache hit
    only the two cheap keys are refreshed on the returned copy: server_time (now) and usage (ageS and stale move with
    the clock). Every other clock-driven value (jobs' elapsed_s and age, head ages, meters) stays as of the build of
    that revision, which is when the data last changed. A call with now= always builds and never caches (tests).
    Raises not_found (exit 3) only for an unknown id."""
    entry = config_store.get_project(project_id)
    folder = project_folder(entry)
    dbp = _store_path(folder)
    if dbp is not None:  # SQLite switch on: no cache (control, presence and usage are not in the store's rev)
        store = _read_store(dbp)
        return dict(_build(entry, folder, store["rev"], now, store))
    rev = revision(folder, project_id)
    if now is None:
        with _CACHE_LOCK:
            hit = _CACHE.get(project_id)
        if hit is not None and hit[0] == rev:
            moment = datetime.now().astimezone()
            return dict(hit[1], server_time=moment.isoformat(timespec="seconds"), usage=usage.show(now=moment))
    snap = _build(entry, folder, rev, now)
    if now is None:
        with _CACHE_LOCK:
            _CACHE[project_id] = (rev, snap)
    return dict(snap)


def _build(entry, folder, rev, now, store=None):
    """One snapshot build for a project entry at revision rev. Missing or unreadable files add errors[], not raises.
    store (the SQLite read of _read_store) replaces tasks.json, jobs.json and the head records when given."""
    errors = []
    project_cfg = _read_project_config(folder, errors)
    project_cfg.setdefault("id", entry["id"])
    project_cfg.setdefault("title", entry["name"])
    names = list(BASE_FILES)
    for name in _extra_names(project_cfg, errors):
        if name not in names:
            names.append(name)
    files = {name: _read_text(folder, name, errors) for name in names}
    if store is not None:
        files.update(store["files"])
    moment = now if now is not None else datetime.now().astimezone()
    snap = build_snapshot(files, project_cfg, moment, control=_control_view(entry["id"]),
                          meters=limits.meters(entry, moment), rules=_rules_view(folder),
                          session=_session_view(folder), folder=_project_path(entry),
                          head_records=store["head"] if store is not None else _head_records(folder),
                          rev=rev, usage=usage.show(now=moment), rule_proposals=_rule_proposals(folder))
    snap["errors"] = errors + snap["errors"]
    return snap


def _store_path(folder):
    """The project's one SQLite store (docs/roadmap.db) when the backend switch is on, else None."""
    if folder is None or head_store.sqlite_db(folder) is None:
        return None
    return store_db.db_path(folder)


@contextlib.contextmanager
def _read_txn(conn):
    """One read transaction: every SELECT inside sees the same committed state."""
    conn.execute("BEGIN")
    try:
        yield conn
    finally:
        conn.execute("COMMIT")


def _store_rev(dbp):
    """The store's integer revision: the highest events rev (0 when none)."""
    conn = store_db.connect(dbp)
    try:
        with _read_txn(conn):
            return store_events.current_rev(conn)
    finally:
        conn.close()


def _store_rows(conn, sql, core):
    """Rows as dicts: the data column's record with the core columns set over it (NULL core values are left out)."""
    out = []
    for row in conn.execute(sql):
        rec = json.loads(row["data"])
        rec.update({key: row[key] for key in core if row[key] is not None})
        out.append(rec)
    return out


def _read_store(dbp):
    """The store's rev, the tasks.json and jobs.json texts and the head records, read in ONE read transaction.
    The rows are shaped back into the JSON documents that roadmap.core.snapshot parses."""
    conn = store_db.connect(dbp)
    try:
        with _read_txn(conn):
            rev = store_events.current_rev(conn)
            phases = _store_rows(conn, "SELECT id, name, status, data FROM phases ORDER BY position", PHASE_CORE)
            tasks = _store_rows(conn, "SELECT id, phase, title, status, data FROM tasks ORDER BY rowid", TASK_CORE)
            jobs = _store_rows(conn, "SELECT id, task, title, model, status, started, ended, data FROM jobs"
                               " ORDER BY rowid", JOB_CORE)
            asks = [json.loads(row["data"]) for row in conn.execute("SELECT data FROM asks ORDER BY seq")]
    finally:
        conn.close()
    head = [o for o in asks if o.get("v") == head_format.VERSION and o.get("t") in head_format.RECORD_TYPES]
    files = {"tasks.json": json.dumps({"phases": phases, "tasks": tasks}), "jobs.json": json.dumps({"jobs": jobs})}
    return {"rev": rev, "files": files, "head": head}


def _rule_proposals(folder):
    """Every rule proposal of the project (R7.103), or None when the file is missing or unreadable."""
    try:
        return rules.proposals(folder)
    except Exception:  # noqa: BLE001 - a bad proposals file must not break the snapshot
        return None


def _head_records(folder):
    """The raw head.jsonl records of the project folder (HEAD-SPEC section 5), or None when there is no folder or
    the file cannot be read, so the snapshot omits the head key (fail-open). Never raises."""
    if folder is None:
        return None
    try:
        return head_store._records(folder)
    except Exception:
        return None


def _session_view(folder):
    """The presence state of the project's data folder: "watching", "open" or "none". Any error gives None, so the
    snapshot omits the session key (fail-open). Never raises."""
    if folder is None:
        return None
    try:
        return presence.state(folder)
    except Exception:
        return None


def _project_path(entry):
    """The registered project root, the directory the Copy command cds into. An empty, null or non-text path gives
    None, and so does any error (fail-open)."""
    try:
        path = entry.get("path")
        if isinstance(path, os.PathLike):
            path = os.fspath(path)
        return path if isinstance(path, str) and path else None
    except Exception:
        return None


def _rules_view(folder):
    """The project's docs/rules.txt rules as {id, scope, kind, value, text} dicts, at most rules.MAX_RULES.

    A missing file gives []. A file that cannot be read or decoded gives [] too. Lines that are not valid rules
    (including text longer than rules.MAX_TEXT) are skipped, as `roadmap rules check` reports them. Never raises.
    """
    if folder is None:
        return []
    try:
        _, parsed, _ = rules.read(folder)
    except Exception:
        return []
    return [{key: rule[key] for key in ("id", "scope", "kind", "value", "text")}
            for rule in parsed[:rules.MAX_RULES]]


def _control_view(project_id):
    """The snapshot's control key: stopped, blocked, reason, overrideUntil and the warnings (budget and weekly).
    An unreadable control file gives an error marker instead of failing the snapshot."""
    try:
        state = control.read_state(project_id)
    except RoadmapError:
        return {"error": "control file unreadable"}
    if not state:
        return {"stopped": False, "blocked": False, "reason": "", "overrideUntil": None, "warn": []}
    block = state.get("block") if isinstance(state.get("block"), dict) else None
    stopped = state.get("stop") is True
    reason = str(block.get("reason", "")) if block else ("stopped by user" if stopped else "")
    return {"stopped": stopped, "blocked": block is not None, "reason": reason,
            "overrideUntil": state.get("overrideUntil") if isinstance(state.get("overrideUntil"), str) else None,
            "warn": [str(w) for w in (state.get("warn") or [])][:6]}


def _read_text(folder, name, errors):
    """The text of folder/name, or None when the file is missing. Other failures are noted in errors."""
    if folder is None:
        return None
    if not _plain_name(name):
        errors.append(error_entry(str(name), ValueError("a data file name must be a plain file name")))
        return None
    try:
        with open(os.path.join(folder, name), "r", encoding="utf-8") as fh:
            return fh.read()
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError) as exc:
        errors.append(error_entry(name, exc))
        return None


def _read_project_config(folder, errors):
    """The project's roadmap.config.json as a dict. Missing gives {}; a broken file adds an error and gives {}."""
    text = _read_text(folder, CONFIG_FILE, errors)
    if text is None:
        return {}
    try:
        data = json.loads(text)
    except ValueError as exc:
        errors.append(error_entry(CONFIG_FILE, exc))
        return {}
    if not isinstance(data, dict):
        errors.append(error_entry(CONFIG_FILE, ValueError("expected a JSON object")))
        return {}
    return data


def _extra_names(project_cfg, errors):
    """The file names the configured extras read, in config order."""
    extras = project_cfg.get("extras")
    if not isinstance(extras, dict):
        return []
    names = []
    for entry in extras.values():
        name = extra_file(entry)
        if name is not None and name not in names:
            names.append(name)
    return names


def _plain_name(name):
    return (isinstance(name, str) and name not in ("", ".", "..") and "/" not in name and "\\" not in name
            and "\x00" not in name)


def port_owner(port):
    """{"pid", "name"} of the process listening on TCP port, from lsof, or None when nobody is or lsof is missing."""
    try:
        proc = subprocess.run(["lsof", "-nP", "-iTCP:%d" % int(port), "-sTCP:LISTEN", "-Fpc"],
                              capture_output=True, text=True, timeout=LSOF_TIMEOUT_S, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    pid = name = None
    for line in proc.stdout.splitlines():
        if line.startswith("p") and pid is None:
            pid = line[1:]
        elif line.startswith("c") and name is None:
            name = line[1:]
    if pid is None:
        return None
    return {"pid": int(pid) if pid.isdigit() else None, "name": name or "unknown"}
