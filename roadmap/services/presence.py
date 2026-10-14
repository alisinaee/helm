"""Session presence (R7.1 T1): tells the board whether a Claude session is listening for a project.

Two stamps per project are kept in presence-<hash>.json in the state directory (never in the repo):
"hook" (the last hook event, written at most once per HOOK_THROTTLE_S) and "watch" with "watchPid" (set while
`roadmap watch` is polling, cleared when it exits). state() turns them into "watching" (watch stamp under WATCH_FRESH_S
old), "open" (hook stamp under HOOK_FRESH_S old) or "none". Writes are atomic and read-modify-write runs under the state
directory lock, so a hook stamp and a watch stamp never clobber each other. A hook never waits on that lock for long
(LOCK_WAIT_S), and touch_hook first checks the file's mtime with one stat call, so a throttled hook reads nothing.
Stamp files are read without following symlinks, and a file that is not a small plain JSON object is unreadable.
Every public function fails open: it never raises, a missing or corrupt file reads as "none", and a failed write or
a busy lock is simply skipped.
"""

import hashlib
import json
import os
import stat
import time
from contextlib import contextmanager

from roadmap.log import get_logger
from roadmap.store import atomic, lock, paths

HOOK_THROTTLE_S = 30
WATCH_FRESH_S = 60
HOOK_FRESH_S = 600
LOCK_WAIT_S = 0.05      # a presence write waits this long for the state lock, then skips the write
MAX_BYTES = 64 * 1024   # a larger stamp file is unreadable, so no read is unbounded
WATCHING, OPEN, NONE = "watching", "open", "none"
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
log = get_logger("services.presence")


class Unreadable(Exception):
    """A stamp file that is a symlink, not a small plain file, or not a JSON object."""


def digest(data_dir):
    """The short hash that names one project's stamp files (presence and launcher share it)."""
    return hashlib.sha256(os.path.abspath(str(data_dir)).encode("utf-8")).hexdigest()[:16]


def file_for(data_dir):
    """The presence file for one project's data folder, in the state directory."""
    return os.path.join(paths.state_dir(), "presence-" + digest(data_dir) + ".json")


def read_plain(path):
    """The JSON object stored at path, or None when the file is missing. Never follows a symlink (O_NOFOLLOW), reads
    at most MAX_BYTES, and raises Unreadable for anything that is not a small plain file holding a JSON object."""
    try:
        fd = os.open(path, os.O_RDONLY | _NOFOLLOW)
    except FileNotFoundError:
        return None
    except OSError as exc:  # a symlink (ELOOP) or an unopenable path
        raise Unreadable(type(exc).__name__)
    with os.fdopen(fd, "rb") as fh:
        info = os.fstat(fh.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
            raise Unreadable("not a small regular file")
        raw = fh.read(MAX_BYTES + 1)
    try:
        doc = json.loads(raw.decode("utf-8"))
    except ValueError:  # bad JSON or bad UTF-8
        raise Unreadable("not JSON")
    if not isinstance(doc, dict):
        raise Unreadable("not a JSON object")
    return doc


def readable(data_dir):
    """True when the presence file is missing or a plain readable stamp file. Never raises."""
    try:
        read_plain(file_for(data_dir))
        return True
    except Exception:  # unreadable, a symlink or an unexpected error: not trusted
        return False


def _moment(now):
    return time.time() if now is None else float(now)


def _load(data_dir):
    """The stored stamps as a dict; an empty dict when the file is missing, unreadable or not a JSON object."""
    try:
        doc = read_plain(file_for(data_dir))
    except Exception:  # corrupt presence reads as no presence, never as an error
        return {}
    return doc if doc is not None else {}


def _store(data_dir, doc):
    """Write the stamps atomically. Returns False (and logs at debug level) when the write fails."""
    try:
        paths.ensure_dir(paths.state_dir())
        atomic.write_json(file_for(data_dir), doc)
        return True
    except Exception as exc:  # presence is advisory: a failed write must not break the caller
        log.debug("presence not saved: %s", type(exc).__name__)
        return False


@contextmanager
def _state_lock():
    """The exclusive state-directory lock for one read-modify-write. Raises (locked) when it stays busy LOCK_WAIT_S."""
    with lock.locked(paths.state_dir(), timeout=LOCK_WAIT_S):
        yield


def _stamp(value):
    """A stored timestamp as a float, or None when it is missing or not a number."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _written_within_throttle(data_dir, moment):
    """The mtime fast path: True when the stamp file was written less than HOOK_THROTTLE_S before moment. One stat
    call, no read. A future mtime is not recent."""
    try:
        age = moment - os.lstat(file_for(data_dir)).st_mtime
    except OSError:
        return False
    return 0 <= age < HOOK_THROTTLE_S


def touch_hook(data_dir, now=None):
    """Record a hook event. Writes at most once per HOOK_THROTTLE_S; returns True when it wrote."""
    try:
        moment = _moment(now)
        if _written_within_throttle(data_dir, moment):
            return False
        with _state_lock():
            doc = _load(data_dir)
            last = _stamp(doc.get("hook"))
            if last is not None and 0 <= moment - last < HOOK_THROTTLE_S:
                return False
            doc["hook"] = moment
            doc.setdefault("watch", None)
            doc.setdefault("watchPid", None)
            return _store(data_dir, doc)
    except Exception:  # fail open (also when the lock is busy)
        return False


def set_watch(data_dir, pid, now=None):
    """Mark a `roadmap watch` process as polling. Returns True when it wrote."""
    try:
        with _state_lock():
            doc = _load(data_dir)
            doc["watch"] = _moment(now)
            doc["watchPid"] = pid if isinstance(pid, int) and not isinstance(pid, bool) else None
            doc.setdefault("hook", None)
            return _store(data_dir, doc)
    except Exception:  # fail open
        return False


def clear_watch(data_dir):
    """Clear the watch stamp and pid when the watch exits. Returns True when it wrote."""
    try:
        with _state_lock():
            doc = _load(data_dir)
            doc["watch"] = None
            doc["watchPid"] = None
            doc.setdefault("hook", None)
            return _store(data_dir, doc)
    except Exception:  # fail open
        return False


def state(data_dir, now=None):
    """"watching" when a watch stamp is under WATCH_FRESH_S old, else "open" when a hook stamp is under HOOK_FRESH_S
    old, else "none". A future stamp (clock moved back) is not fresh. Never raises."""
    try:
        doc = _load(data_dir)
        moment = _moment(now)
        watch = _stamp(doc.get("watch"))
        if watch is not None and 0 <= moment - watch < WATCH_FRESH_S:
            return WATCHING
        hook = _stamp(doc.get("hook"))
        if hook is not None and 0 <= moment - hook < HOOK_FRESH_S:
            return OPEN
        return NONE
    except Exception:  # fail open
        return NONE
