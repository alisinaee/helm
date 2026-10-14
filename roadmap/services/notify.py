"""Desktop wake-up notifications (GAP-ANALYSIS 2.1): one macOS notification through osascript when a Start is queued,
a blocking question is asked, or a limit first blocks a project.

The notification is sent with an argv list (no shell). Every text is one line, capped at TEXT_MAX characters and
escaped for AppleScript. Only ids and short summaries go in: a notification never carries free text beyond that.
At most one notification per RATE_S seconds for each (project, kind), kept in notify.json in the state directory.
The config key "notify" (global config, default true) turns it off. Off macOS, without osascript, or when osascript
fails, nothing happens: the call returns False, never raises, and logs at most once a minute.

Tests never reach the real osascript: when the test runner is loaded and no runner is injected, notify is a no-op.
"""

import os
import re
import shutil
import subprocess
import sys
import time

from roadmap.log import get_logger
from roadmap.store import atomic, config, paths

RATE_S = 60
TEXT_MAX = 120
SUMMARY_MAX = 60
OSASCRIPT_TIMEOUT_S = 3
STATE_FILE = "notify.json"
TITLE = "roadmap-board"
log = get_logger("services.notify")
_last_log = [0.0]
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


def _clean(text, limit=TEXT_MAX):
    """One line of plain text, at most limit characters, with the characters that break an AppleScript string
    escaped."""
    line = _CONTROL_RE.sub(" ", str("" if text is None else text))
    line = " ".join(line.split())[:limit]
    return line.replace("\\", "\\\\").replace('"', '\\"')


def summary(text):
    """A short one-line summary of a free text (at most SUMMARY_MAX characters). Never used for secrets."""
    return " ".join(_CONTROL_RE.sub(" ", str(text or "")).split())[:SUMMARY_MAX]


def script_for(title, body):
    """The AppleScript that shows one notification."""
    return 'display notification "%s" with title "%s"' % (_clean(body), _clean(title))


def _macos():
    return sys.platform == "darwin"


def _under_tests():
    """True while the unit test runner is loaded. No notification is shown from there unless a runner is injected."""
    return "unittest" in sys.modules


def _run_osascript(argv):
    """Run the osascript argv; True when it exits 0. Raises when osascript cannot be run."""
    done = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                          timeout=OSASCRIPT_TIMEOUT_S, check=False)
    return done.returncode == 0


def _log_once(message):
    """Log a problem at most once a minute, so a broken osascript does not fill the log."""
    now = time.time()
    if now - _last_log[0] < RATE_S:
        return
    _last_log[0] = now
    log.warning("notification not shown: %s", message)


def _enabled():
    try:
        return config.load().get("notify", True) is not False
    except Exception:  # an unreadable config means no notification, never an error
        return False


def _allowed(project, kind, moment, path):
    """True when (project, kind) was not notified within RATE_S. Records the attempt when it is allowed."""
    saved = atomic.read_json(path, default={}) if os.path.exists(path) else {}
    last = saved.get("last") if isinstance(saved, dict) and isinstance(saved.get("last"), dict) else {}
    key = project + "/" + kind
    previous = last.get(key)
    if isinstance(previous, (int, float)) and 0 <= moment - previous < RATE_S:
        return False
    last[key] = moment
    atomic.write_json(path, {"last": last})
    return True


def notify(kind, title, body, project, runner=None, now=None):
    """Show one notification for (project, kind) unless the last one was less than RATE_S ago. Returns True when a
    notification was shown. runner(argv) -> bool replaces the osascript call (tests inject it)."""
    try:
        return _notify(kind, title, body, project, runner, now)
    except Exception as exc:  # a notification must never break the write that asked for it
        _log_once(type(exc).__name__)
        return False


def _notify(kind, title, body, project, runner, now):
    if runner is None:
        if _under_tests():
            return False
        if not _macos():
            return False
        if shutil.which("osascript") is None:
            _log_once("osascript is missing")
            return False
    if not _enabled():
        return False
    moment = time.time() if now is None else now
    folder = paths.ensure_dir(paths.state_dir())
    if not _allowed(summary(project), summary(kind), moment, os.path.join(folder, STATE_FILE)):
        return False
    argv = ["osascript", "-e", script_for(title or TITLE, body)]
    shown = (runner or _run_osascript)(argv)
    if not shown:
        _log_once("osascript did not succeed")
    return bool(shown)


def project_of(data_dir):
    """The id of the registered project whose data folder is data_dir, or None."""
    wanted = os.path.abspath(data_dir)
    for entry in config.list_projects():
        folder = os.path.join(os.path.abspath(str(entry.get("path") or "")), entry.get("dataDir") or "docs")
        if folder == wanted:
            return entry.get("id")
    return None


def notify_dir(data_dir, kind, title, body_for, runner=None, now=None):
    """notify for the project that owns data_dir. body_for(project id) builds the body, so the text names the project.
    Returns False without reading the config when notifications cannot be shown (see _notify)."""
    try:
        if runner is None and (_under_tests() or not _macos()):
            return False
        project = project_of(data_dir)
        if project is None:
            return False
        return notify(kind, title, body_for(project), project, runner=runner, now=now)
    except Exception as exc:  # the write that asked for the notification is already saved
        _log_once(type(exc).__name__)
        return False
