"""Logging for the roadmap package: the namespace, the file handler with rotation, the redaction filter and the
access-log line. Standard library only, and it imports nothing from the project (see the layering rule).

server.log is a RotatingFileHandler: 1 MB per file, 5 backups, mode 0600. Every record passes the redaction filter,
which hides Bearer tokens, Anthropic keys (sk-ant-...) and any k=<value> pair (the phone token parameter).

The debug event log (debug_event, read_events, log_status) is one JSON-lines file, <state dir>/logs/debug.jsonl,
rotated at 5 MB into 3 backups. It never raises and never logs its own failures.
"""

import collections
import datetime
import json
import logging
import math
import os
import re
import stat
import threading
import uuid
from logging.handlers import RotatingFileHandler

ROOT_NAME = "roadmap"
SERVER_LOG = "server.log"
MAX_BYTES = 1_000_000
BACKUP_COUNT = 5
FILE_MODE = 0o600
_FILE_TAG = "roadmap_file"

_REDACTIONS = (
    (re.compile(r"Bearer\s+\S+"), "Bearer [redacted]"),
    (re.compile(r"sk-ant-\S+"), "sk-ant-[redacted]"),
    (re.compile(r"k=\S+"), "k=[redacted]"),
    (re.compile(r"token=\S+"), "token=[redacted]"),
    (re.compile(r"ghp_\w+"), "ghp_[redacted]"),
    (re.compile(r"sk-proj-\S+"), "sk-proj-[redacted]"),
)
_CTRL = re.compile(r"[\x00-\x1f\x7f]")

_root = logging.getLogger(ROOT_NAME)
if not _root.handlers:
    _root.addHandler(logging.NullHandler())


def get_logger(name=""):
    """Return the logger for a roadmap module, for example get_logger("services.jobs")."""
    return logging.getLogger(ROOT_NAME + "." + name if name else ROOT_NAME)


def redact(text):
    """Return text with bearer tokens, Anthropic keys and k=<value> pairs replaced by a placeholder."""
    out = str(text)
    for pattern, replacement in _REDACTIONS:
        out = pattern.sub(replacement, out)
    return out


class RedactingFilter(logging.Filter):
    """Formats each record, redacts the message and keeps the record. It never drops a record."""

    def filter(self, record):
        try:
            message = record.getMessage()
        except Exception:  # a bad format string must not leak the raw arguments
            message = str(record.msg)
        record.msg = redact(message)
        record.args = ()
        return True


class _OwnerOnlyRotatingHandler(RotatingFileHandler):
    """RotatingFileHandler that creates each file with mode 0600, including the files made after a rollover."""

    def _open(self):
        fd = os.open(self.baseFilename, os.O_WRONLY | os.O_CREAT | os.O_APPEND, FILE_MODE)
        return os.fdopen(fd, self.mode, encoding=self.encoding)


def setup_file_logging(logs_dir, logger=None):
    """Attach the rotating server.log handler (with the redaction filter) to the roadmap logger. Calling it again
    for the same directory adds nothing. Returns the log file path."""
    os.makedirs(logs_dir, mode=0o700, exist_ok=True)
    target = logger if logger is not None else logging.getLogger(ROOT_NAME)
    path = os.path.join(logs_dir, SERVER_LOG)
    for handler in target.handlers:
        if getattr(handler, _FILE_TAG, None) == path:
            return path
    handler = _OwnerOnlyRotatingHandler(path, mode="a", maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT,
                                        encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
    handler.addFilter(RedactingFilter())
    setattr(handler, _FILE_TAG, path)
    target.addHandler(handler)
    if target.level == logging.NOTSET or target.level > logging.INFO:
        target.setLevel(logging.INFO)
    return path


def access_line(method, path, status, elapsed_ms):
    """One access-log line: method, the path without its query string or fragment, status and milliseconds."""
    bare = str(path).split("#", 1)[0].split("?", 1)[0]
    return redact("%s %s %d %dms" % (method, bare, int(status), int(elapsed_ms)))


# ---- Debug event log (R7.16 step 1). One JSON line per event in <state dir>/logs/debug.jsonl. ----

DEBUG_FILE = "debug.jsonl"
DEBUG_MAX_BYTES = 5 * 1024 * 1024
DEBUG_BACKUPS = 3
DEBUG_CAP_BYTES = DEBUG_MAX_BYTES * (DEBUG_BACKUPS + 1)
SETTINGS_FILE = "debug-log.json"
LEVELS = {"DEBUG": 10, "INFO": 20, "WARN": 30, "ERROR": 40}
SOURCES = frozenset(("ui", "core", "hook"))
EVENTS = frozenset((
    "ui.load", "ui.route", "ui.action", "ui.submit", "ui.error", "ui.reject", "ui.csp", "ui.api", "ui.render",
    "ui.console", "ui.resize", "ui.theme", "ui.mark",
    "core.api", "core.write", "core.guard", "core.limit", "core.exc", "core.start", "core.stop",
    "hook.event", "hook.error",
))
_MSG_CAP, _ROUTE_CAP, _REF_CAP, _SID_CAP = 300, 120, 120, 32
_STR_CAP, _STACK_CAP, _DATA_CAP = 200, 1500, 1024
_MAX_KEYS, _MAX_ITEMS, _MAX_DEPTH, _MAX_FRAMES = 20, 10, 3, 12
_DENIED_KEYS = ("token", "cookie", "csrf", "auth", "passw", "secret", "clip", "value", "apikey", "api_key",
                "session")
_ABS_PATH = re.compile(r"(?<![\w~./])/[^\s'\"<>]+")
_HOME_PATH = re.compile(r"/(?:Users|home)/[^\s/\"'<>]+(?:/[^\s\"'<>]*)?")
_DEFAULTS = {"enabled": True, "debug": False}
_state_override = None
_lock = threading.Lock()
_settings_lock = threading.Lock()
_settings_cache = {"key": None, "value": dict(_DEFAULTS)}


def set_state_dir(path):
    """Point the debug log at another state directory (tests and the command use it). None restores the default."""
    global _state_override
    _state_override = None if path is None else os.path.abspath(str(path))
    _settings_cache["key"] = None


def _state_base():
    """The state directory: ROADMAP_HOME/state when set, else the default under ~ (same rule as store/paths.py,
    which this layer may not import)."""
    if _state_override is not None:
        return _state_override
    root = os.environ.get("ROADMAP_HOME", "").strip()
    if root:
        return os.path.join(os.path.abspath(os.path.expanduser(root)), "state")
    return os.path.join(os.path.expanduser("~"), "Library", "Application Support", "roadmap-board")


def _cut(text, limit):
    return text if len(text) <= limit else text[:limit - 1] + "…"


def _scrub(text):
    """Home path to ~, and any other absolute path to the last segment only."""
    home = os.path.expanduser("~")
    if home and home != "/":
        text = text.replace(home, "~")
    return _ABS_PATH.sub(lambda m: "…/" + os.path.basename(m.group(0).rstrip("/")), text)


def printable(text):
    """Return text with every control character (newline, tab, ESC...) replaced by a space, so it prints as one line."""
    return _CTRL.sub(" ", str(text))


def _clean_text(value, limit):
    return _cut(_scrub(redact(printable(value))), limit)


def _clean_field(value, limit):
    """A route or ref: no control characters, redacted, and any home directory path (/Users/<name>...) shown as ~.
    Other path-like text (such as /api/v1/log) is kept as it is."""
    return _cut(_HOME_PATH.sub("~", redact(printable(value))), limit)


def _clean_stack(text):
    return _cut("\n".join(_scrub(text).splitlines()[:_MAX_FRAMES]), _STACK_CAP)


def _clean(value, depth=0, key=""):
    """Return a JSON-safe copy of value with the caps, redaction and denied keys applied. Never raises on odd input."""
    if depth > _MAX_DEPTH:
        return "…"
    if value is None or isinstance(value, bool) or isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, str):
        if key.lower() == "stack":
            return _clean_stack(redact(value))
        return _clean_text(value, _STR_CAP)
    if isinstance(value, dict):
        out = {}
        for raw_key, item in list(value.items())[:_MAX_KEYS]:
            full = redact(str(raw_key))
            if any(part in full.lower() for part in _DENIED_KEYS):
                continue
            name = _cut(full, 40)
            out[name] = _clean(item, depth + 1, name)
        return out
    if isinstance(value, (list, tuple)):
        return [_clean(item, depth + 1, key) for item in list(value)[:_MAX_ITEMS]]
    return _clean_text(str(value), _STR_CAP)


def _clean_data(data):
    """Return the data object within 20 keys, 10 items and 1 KB serialized (not counting the stack, which has its own
    1500-byte cap); over the cap it becomes {"cut": true}."""
    if data is None:
        return None
    cleaned = _clean(data if isinstance(data, dict) else {"detail": data})
    stack = cleaned.pop("stack", None) if isinstance(cleaned, dict) else None
    if len(json.dumps(cleaned, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > _DATA_CAP:
        return {"cut": True}
    if stack is not None:
        cleaned["stack"] = stack
    return cleaned


def _now():
    return datetime.datetime.now().astimezone().isoformat(timespec="milliseconds")


def _strip_query(text):
    return str(text).split("?", 1)[0]


def _ensure_dir(path):
    """Create path as an owner-only directory. Returns False when path exists as a symlink or not a directory."""
    if not os.path.lexists(path):
        os.makedirs(path, 0o700, exist_ok=True)
    st = os.lstat(path)
    return stat.S_ISDIR(st.st_mode)


def _is_symlink(path):
    try:
        return stat.S_ISLNK(os.lstat(path).st_mode)
    except FileNotFoundError:
        return False
    except OSError:
        return True


def _write_all(fd, payload):
    view = memoryview(payload)
    while view:
        view = view[os.write(fd, view):]


def _open_append(path):
    """Open for append, owner-only, refusing a symlink at the leaf (O_NOFOLLOW). Returns None on failure."""
    try:
        return os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    except OSError:
        return None


def _rotate(logs):
    """Shift debug.jsonl -> .1 -> .2 -> .3 and drop the oldest. Refuses (False) when any slot is a symlink."""
    paths = [os.path.join(logs, DEBUG_FILE)]
    paths += [os.path.join(logs, "%s.%d" % (DEBUG_FILE, i)) for i in range(1, DEBUG_BACKUPS + 1)]
    if any(_is_symlink(p) for p in paths):
        return False
    try:
        if os.path.lexists(paths[-1]):
            os.remove(paths[-1])
        for idx in range(len(paths) - 1, 0, -1):
            if os.path.lexists(paths[idx - 1]):
                os.replace(paths[idx - 1], paths[idx])
    except OSError:
        return False
    return True


def _append(payload):
    """Append one encoded line, rotating first when it would pass the size limit. Returns True when written."""
    with _lock:
        logs = os.path.join(_state_base(), "logs")
        if not _ensure_dir(logs):
            return False
        path = os.path.join(logs, DEBUG_FILE)
        fd = _open_append(path)
        if fd is None:
            return False
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode):
                return False
            if st.st_size + len(payload) > DEBUG_MAX_BYTES:
                os.close(fd)
                fd = None
                if not _rotate(logs):
                    return False
                fd = _open_append(path)
                if fd is None:
                    return False
            if os.fstat(fd).st_mode & 0o077:
                os.fchmod(fd, 0o600)
            _write_all(fd, payload)
            return True
        finally:
            if fd is not None:
                os.close(fd)


def _read_settings():
    """The settings dict (enabled, debug). A missing, symlinked or unreadable file gives the defaults."""
    path = os.path.join(_state_base(), SETTINGS_FILE)
    try:
        st = os.lstat(path)
    except OSError:
        return dict(_DEFAULTS)
    if not stat.S_ISREG(st.st_mode):
        return dict(_DEFAULTS)
    key = (path, st.st_ino, st.st_mtime_ns, st.st_size)
    if _settings_cache["key"] == key:
        return dict(_settings_cache["value"])
    value = dict(_DEFAULTS)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            raw = json.loads(os.read(fd, 4096).decode("utf-8"))
        finally:
            os.close(fd)
        if isinstance(raw, dict):
            for name in _DEFAULTS:
                if isinstance(raw.get(name), bool):
                    value[name] = raw[name]
    except (OSError, ValueError):
        value = dict(_DEFAULTS)
    _settings_cache["key"] = key
    _settings_cache["value"] = value
    return dict(value)


def _write_settings(values):
    base = _state_base()
    path = os.path.join(base, SETTINGS_FILE)
    if not _ensure_dir(base) or _is_symlink(path):
        return False
    tmp = path + "." + uuid.uuid4().hex[:12] + ".tmp"
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            _write_all(fd, json.dumps(values).encode("utf-8"))
        finally:
            os.close(fd)
        os.replace(tmp, path)
        return True
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        return False


def _set_setting(name, value):
    try:
        with _settings_lock:
            current = _read_settings()
            current[name] = bool(value)
            return _write_settings(current)
    except Exception:  # fail-open: a broken switch never raises into the caller
        return False


def enabled():
    """True when the debug log is on (default on). Never raises."""
    try:
        return _read_settings()["enabled"]
    except Exception:
        return True


def debug_enabled():
    """True when DEBUG-level events are written too (default off). Never raises."""
    try:
        return _read_settings()["debug"]
    except Exception:
        return False


def set_enabled(value):
    """Turn the debug log on or off and store the choice in the state dir. Returns True when saved."""
    return _set_setting("enabled", value)


def set_debug(value):
    """Turn DEBUG-level events on or off. Returns True when saved."""
    return _set_setting("debug", value)


def _build_record(src, level, ev, msg, route, ref, sid, data):
    if ev not in EVENTS or src not in SOURCES:
        return None
    if level not in LEVELS:
        level = "INFO"
    if sid is None:
        sid = "core-%d" % os.getpid() if src == "core" else ""
    record = {
        "ts": _now(),
        "sid": _clean_text(str(sid), _SID_CAP),
        "src": src,
        "lvl": level,
        "ev": ev,
        "route": _clean_field(_strip_query(route or ""), _ROUTE_CAP),
        "msg": _clean_text("" if msg is None else str(msg), _MSG_CAP),
    }
    if ref:
        record["ref"] = _clean_field(_strip_query(ref), _REF_CAP)
    cleaned = _clean_data(data)
    if cleaned is not None:
        record["data"] = cleaned
    return record


def debug_event(src, lvl, ev, msg=None, route=None, ref=None, sid=None, data=None):
    """Append one event to the debug log. Returns True when a line was written. Unknown names, switched-off logging
    and any failure give False; this function never raises and never logs its own failures."""
    try:
        if lvl == "DEBUG" and not debug_enabled():
            return False
        if not enabled():
            return False
        record = _build_record(src, lvl, ev, msg, route, ref, sid, data)
        if record is None:
            return False
        payload = (json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
        return _append(payload)
    except Exception:
        return False


def _parse_ts(text):
    try:
        moment = datetime.datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None
    return moment.astimezone() if moment.tzinfo is None else moment


def _cutoff(since):
    if since is None:
        return None
    if isinstance(since, datetime.datetime):
        return since.astimezone() if since.tzinfo is None else since
    if isinstance(since, (int, float)):
        return datetime.datetime.fromtimestamp(float(since)).astimezone()
    return _parse_ts(str(since))


def _read_paths():
    """Debug log files, oldest first."""
    logs = os.path.join(_state_base(), "logs")
    names = ["%s.%d" % (DEBUG_FILE, i) for i in range(DEBUG_BACKUPS, 0, -1)] + [DEBUG_FILE]
    return [os.path.join(logs, name) for name in names]


def _iter_records(path):
    """Yield each parsed JSON object line; skip symlinks, non-files and corrupt lines."""
    try:
        st = os.lstat(path)
        if not stat.S_ISREG(st.st_mode):
            return
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        return
    with os.fdopen(fd, "rb") as fh:
        for raw in fh:
            try:
                rec = json.loads(raw.decode("utf-8"))
            except Exception:  # bad UTF-8, bad JSON, or a line too deep or too large to parse: skip only that line
                continue
            if isinstance(rec, dict) and isinstance(rec.get("ev"), str):
                yield rec


def _matches(rec, filters):
    since, src, ev, ref, session, floor = filters
    if src is not None and rec.get("src") != src:
        return False
    if ev is not None and rec.get("ev") != ev:
        return False
    if ref is not None and rec.get("ref") != ref:
        return False
    if session is not None and rec.get("sid") != session:
        return False
    if floor and LEVELS.get(rec.get("lvl"), 0) < floor:
        return False
    if since is not None:
        moment = _parse_ts(rec.get("ts")) if isinstance(rec.get("ts"), str) else None
        if moment is None or moment < since:
            return False
    return True


def read_events(since=None, src=None, ev=None, ref=None, session=None, level_min=None, limit=200):
    """Return matching debug events, oldest first (newest last). limit keeps the newest N; None keeps all.
    Corrupt lines are skipped. Never raises: a failure gives an empty list."""
    try:
        filters = (
            _cutoff(since),
            src,
            ev,
            ref,
            session,
            LEVELS.get(level_min, 0) if isinstance(level_min, str) else 0,
        )
        keep_newest = limit if isinstance(limit, int) and not isinstance(limit, bool) and limit >= 0 else None
        kept = collections.deque(maxlen=keep_newest)
        for path in _read_paths():
            for rec in _iter_records(path):
                if _matches(rec, filters):
                    kept.append(rec)
        return list(kept)
    except Exception:
        return []


def log_status():
    """Return the switch state, the directory, the file sizes and the caps. Paths are shown with ~ for home."""
    try:
        logs = os.path.join(_state_base(), "logs")
        files = {}
        names = [DEBUG_FILE] + ["%s.%d" % (DEBUG_FILE, i) for i in range(1, DEBUG_BACKUPS + 1)]
        for name in names:
            try:
                st = os.lstat(os.path.join(logs, name))
            except OSError:
                continue
            if stat.S_ISREG(st.st_mode):
                files[name] = st.st_size
        settings = _read_settings()
        return {
            "enabled": settings["enabled"],
            "debug": settings["debug"],
            "dir": _scrub(logs),
            "files": files,
            "total_bytes": sum(files.values()),
            "max_file_bytes": DEBUG_MAX_BYTES,
            "backups": DEBUG_BACKUPS,
            "cap_bytes": DEBUG_CAP_BYTES,
        }
    except Exception:
        return {"error": True}


REPORT_MARKS = 5
REPORT_MSG_CAP = 160


def _report_line(rec):
    """One report line: hh:mm:ss src ev route ref msg. The message is collapsed to one line, scrubbed and capped."""
    ts = str(rec.get("ts", ""))
    clock = ts[11:19] if len(ts) >= 19 else "--:--:--"
    msg = re.sub(r"\s+", " ", str(rec.get("msg") or "")).strip()
    fields = [clock, str(rec.get("src") or "-"), str(rec.get("ev") or "-"), str(rec.get("route") or "-"),
              str(rec.get("ref") or "-")]
    line = " ".join(printable(_HOME_PATH.sub("~", redact(field))) for field in fields)
    return line + " " + _cut(_scrub(redact(msg)), REPORT_MSG_CAP) if msg else line + " -"


def report_lines(n):
    """The event lines of the debug report, oldest first: the newest n WARN and ERROR events plus the last 5 ui.mark
    events (no repeats). Each is 'hh:mm:ss src ev route ref msg'. Never raises: a failure gives an empty list."""
    try:
        warns = read_events(level_min="WARN", limit=n)
        seen = [json.dumps(rec, sort_keys=True) for rec in warns]
        marks = [rec for rec in read_events(ev="ui.mark", limit=REPORT_MARKS)
                 if json.dumps(rec, sort_keys=True) not in seen]
        merged = sorted(warns + marks, key=lambda rec: str(rec.get("ts", "")))
        return [_report_line(rec) for rec in merged]
    except Exception:
        return []
