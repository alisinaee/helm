"""Opt-in launcher (R7.1 T4): opens Terminal with `claude` in the project folder when nobody is listening.

Off unless the project's config entry sets "launchOnStart": true. It runs only when presence is "none", at most once
per RATE_S seconds (the stamp is launch.json in the state directory). The command is argv only: the project path is
shell-quoted with shlex, then escaped for AppleScript, and it never comes from a request. Every public function fails
open: it never raises, and any failure just means no launch. Off macOS, and under unittest, nothing runs unless a
runner is injected.
"""

import os
import shlex
import subprocess
import sys
import time

from roadmap.log import get_logger
from roadmap.services import presence
from roadmap.store import atomic, config, paths

FILE = "launch.json"
RATE_S = 600
TIMEOUT_S = 10
log = get_logger("services.launcher")


def _moment(now):
    return float(now) if now is not None else time.time()


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


def _recent(moment):
    """True when a launch happened less than RATE_S seconds before moment. A corrupt stamp reads as not recent."""
    try:
        doc = atomic.read_json(os.path.join(paths.state_dir(), FILE), default={})
        last = doc.get("at") if isinstance(doc, dict) else None
        if isinstance(last, bool) or not isinstance(last, (int, float)):
            return False
        return 0 <= moment - float(last) < RATE_S
    except Exception:  # a broken stamp must not block or break the caller
        return False


def _stamp(moment):
    """Record the launch time. A failed write is skipped; the next call may launch again."""
    try:
        paths.ensure_dir(paths.state_dir())
        atomic.write_json(os.path.join(paths.state_dir(), FILE), {"at": moment})
    except Exception as exc:
        log.debug("launch stamp not saved: %s", type(exc).__name__)


def _run(argv):
    """The real runner: argv only, no shell, bounded time. Returns True on exit status 0."""
    result = subprocess.run(argv, check=False, timeout=TIMEOUT_S, capture_output=True)
    return result.returncode == 0


def maybe_launch(data_dir, runner=None, now=None):
    """Open Terminal with `claude` for the project when it is opted in, presence is none and the rate limit allows.
    Returns True when a launch was requested. The runner gets the argv list (tests inject a fake one)."""
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
        if presence.state(data_dir, moment) != presence.NONE or _recent(moment):
            return False
        argv = ["osascript", "-e", _script(path)]
        _stamp(moment)
        (runner or _run)(argv)
        return True
    except Exception as exc:  # fail open: a launch problem never breaks the caller
        log.debug("launch skipped: %s", type(exc).__name__)
        return False
