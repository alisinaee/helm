"""Opt-in launcher (R7.1 T4): opens Terminal with `claude` in the project folder when nobody is listening.

Off unless the project's config entry sets "launchOnStart": true. It runs only when presence is "none", at most once
per RATE_S seconds per project (the stamp is launch-<hash>.json in the state directory, named like presence). The
check, the rate limit and the stamp happen together under the state directory lock, so two concurrent Starts cannot
both launch. The stamp is written before the command runs. A failed launch (non-zero exit, timeout or an exception)
releases that stamp, so the next Start may retry at once instead of waiting out the window. A damaged stamp (corrupt,
a symlink or not a plain file) fails closed: no launch. A damaged regular file counts as recent for RATE_S from its
own mtime, so it heals by itself. The command is argv only: the project path is shell-quoted with shlex, then escaped
for AppleScript, and it never comes from a request. Every public function fails open: it never raises, and any failure
just means no launch. Off macOS, and under unittest, nothing runs unless a runner is injected.
"""

import os
import shlex
import stat
import subprocess
import sys
import time
from contextlib import contextmanager

from roadmap.log import get_logger
from roadmap.services import presence
from roadmap.store import atomic, config, lock, paths

FILE_PREFIX = "launch-"
RATE_S = 600
TIMEOUT_S = 10
LOCK_WAIT_S = 2.0   # the decision is quick; a busy lock past this means no launch for this Start
log = get_logger("services.launcher")


def _moment(now):
    return float(now) if now is not None else time.time()


def stamp_file_for(data_dir):
    """The launch stamp for one project's data folder, in the state directory."""
    return os.path.join(paths.state_dir(), FILE_PREFIX + presence.digest(data_dir) + ".json")


@contextmanager
def _state_lock():
    """The exclusive state-directory lock around check, stamp and release. Raises (locked) when it stays busy."""
    with lock.locked(paths.state_dir(), timeout=LOCK_WAIT_S):
        yield


def _project_for(data_dir):
    """The config entry whose data folder is data_dir, or None."""
    target = os.path.abspath(str(data_dir))
    for project in config.load().get("projects", []):
        if not isinstance(project, dict):
            continue
        path = project.get("path")
        if not isinstance(path, str) or not path:
            continue
        data = project.get("dataDir") or "docs"
        if os.path.abspath(os.path.join(path, str(data))) == target:
            return project
    return None


def _valid_dir(path):
    """True when path is an absolute, existing folder with no control characters."""
    if not isinstance(path, str) or not os.path.isabs(path) or not os.path.isdir(path):
        return False
    return not any(ord(ch) < 32 or ord(ch) == 127 for ch in path)


def _script(path):
    """The AppleScript that types `cd <quoted path> && claude` into a new Terminal window."""
    command = "cd " + shlex.quote(path) + " && claude"
    escaped = command.replace("\\", "\\\\").replace('"', '\\"')
    return 'tell application "Terminal" to do script "' + escaped + '"'


def _damaged_recent(path, moment):
    """The verdict for a stamp that cannot be trusted. A symlink or other non-file is always recent (no launch). A
    damaged regular file is recent for RATE_S from its own mtime, then it heals."""
    try:
        info = os.lstat(path)
    except OSError:
        return True
    if not stat.S_ISREG(info.st_mode):
        return True
    return moment - info.st_mtime < RATE_S


def _recent(data_dir, moment):
    """True when a launch is recorded less than RATE_S before moment, or the stamp cannot be trusted (fail closed).
    A missing stamp is not recent. A stamp from the future is not recent."""
    path = stamp_file_for(data_dir)
    try:
        doc = presence.read_plain(path)
    except presence.Unreadable:
        return _damaged_recent(path, moment)
    except Exception:  # an unexpected read error: no launch
        return True
    if doc is None:
        return False
    last = doc.get("at")
    if isinstance(last, bool) or not isinstance(last, (int, float)):
        return _damaged_recent(path, moment)
    return 0 <= moment - float(last) < RATE_S


def _stamp(data_dir, moment):
    """Record the launch time. Returns False when the write fails: then nothing may launch, because the rate limit
    could not be recorded."""
    try:
        paths.ensure_dir(paths.state_dir())
        atomic.write_json(stamp_file_for(data_dir), {"at": moment})
        return True
    except Exception as exc:
        log.debug("launch stamp not saved: %s", type(exc).__name__)
        return False


def _claim(data_dir, moment):
    """Under the state lock: check presence, the rate limit and the stamp, then record the launch. True when this
    call may launch. A busy lock, an untrusted presence file, an open session or a failed stamp means no launch."""
    with _state_lock():
        if not presence.readable(data_dir) or presence.state(data_dir, moment) != presence.NONE:
            return False
        if _recent(data_dir, moment):
            return False
        return _stamp(data_dir, moment)


def _release(data_dir, moment):
    """Undo this call's claim after a failed launch, so the next Start may try again at once. Only a stamp that holds
    this call's own time is removed."""
    try:
        with _state_lock():
            doc = presence.read_plain(stamp_file_for(data_dir))
            if doc is not None and doc.get("at") == moment:
                os.unlink(stamp_file_for(data_dir))
    except Exception as exc:
        log.debug("launch claim not released: %s", type(exc).__name__)


def _run(argv):
    """The real runner: argv only, no shell, bounded time. Returns True on exit status 0."""
    result = subprocess.run(argv, check=False, timeout=TIMEOUT_S, capture_output=True)
    return result.returncode == 0


def maybe_launch(data_dir, runner=None, now=None):
    """Open Terminal with `claude` for the project when it is opted in, presence is none and the rate limit allows.
    Returns True when a launch was requested. The runner gets the argv list (tests inject a fake one). A launch that
    fails releases its claim, so the next Start can retry at once."""
    try:
        if runner is None and (sys.platform != "darwin" or "unittest" in sys.modules):
            return False
        project = _project_for(data_dir)
        if project is None or project.get("launchOnStart") is not True:
            return False
        path = project.get("path")
        if not _valid_dir(path):
            return False
        moment = _moment(now)
        if not _claim(data_dir, moment):
            return False
        argv = ["osascript", "-e", _script(path)]
        try:
            launched = (runner or _run)(argv)
        except Exception:
            _release(data_dir, moment)
            raise
        if not launched:
            _release(data_dir, moment)
        return True
    except Exception as exc:  # fail open: a launch problem never breaks the caller
        log.debug("launch skipped: %s", type(exc).__name__)
        return False
