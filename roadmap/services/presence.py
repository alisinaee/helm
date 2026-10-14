"""Session presence (R7.1 T1): tells the board whether a Claude session is listening for a project.

Two stamps per project are kept in presence-<hash>.json in the state directory (never in the repo):
"hook" (the last hook event, written at most once per HOOK_THROTTLE_S) and "watch" with "watchPid" (set while
`roadmap watch` is polling, cleared when it exits). state() turns them into "watching" (watch stamp under WATCH_FRESH_S
old), "open" (hook stamp under HOOK_FRESH_S old) or "none". Writes are atomic. Every public function fails open: it
never raises, a missing or corrupt file reads as "none", and a failed write is simply skipped.
"""

import hashlib
import os
import time

from roadmap.log import get_logger
from roadmap.store import atomic, paths

HOOK_THROTTLE_S = 30
WATCH_FRESH_S = 60
HOOK_FRESH_S = 600
WATCHING, OPEN, NONE = "watching", "open", "none"
log = get_logger("services.presence")


def file_for(data_dir):
    """The presence file for one project's data folder, in the state directory."""
    digest = hashlib.sha256(os.path.abspath(str(data_dir)).encode("utf-8")).hexdigest()[:16]
    return os.path.join(paths.state_dir(), "presence-" + digest + ".json")


def _moment(now):
    return time.time() if now is None else float(now)


def _load(data_dir):
    """The stored stamps as a dict; an empty dict when the file is missing, unreadable or not a JSON object."""
    try:
        doc = atomic.read_json(file_for(data_dir), default={})
    except Exception:  # corrupt presence reads as no presence, never as an error
        return {}
    return doc if isinstance(doc, dict) else {}


def _store(data_dir, doc):
    """Write the stamps atomically. Returns False (and logs at debug level) when the write fails."""
    try:
        paths.ensure_dir(paths.state_dir())
        atomic.write_json(file_for(data_dir), doc)
        return True
    except Exception as exc:  # presence is advisory: a failed write must not break the caller
        log.debug("presence not saved: %s", type(exc).__name__)
        return False


def _stamp(value):
    """A stored timestamp as a float, or None when it is missing or not a number."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def touch_hook(data_dir, now=None):
    """Record a hook event. Writes at most once per HOOK_THROTTLE_S; returns True when it wrote."""
    try:
        moment = _moment(now)
        doc = _load(data_dir)
        last = _stamp(doc.get("hook"))
        if last is not None and 0 <= moment - last < HOOK_THROTTLE_S:
            return False
        doc["hook"] = moment
        doc.setdefault("watch", None)
        doc.setdefault("watchPid", None)
        return _store(data_dir, doc)
    except Exception:  # fail open
        return False


def set_watch(data_dir, pid, now=None):
    """Mark a `roadmap watch` process as polling. Returns True when it wrote."""
    try:
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
