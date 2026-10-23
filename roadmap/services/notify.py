"""Desktop wake-up notifications (GAP-ANALYSIS 2.1): one macOS notification through osascript when a Start is queued,
a blocking question is asked, or a limit first blocks a project.

The notification is sent with an argv list (no shell). Every text is one line, capped at TEXT_MAX characters and
escaped for AppleScript. Only ids and short summaries go in: a notification never carries free text beyond that.
At most one notification per RATE_S seconds for each (project, kind), kept in notify.json in the state directory.
The config key "notify" (global config, default true) turns it off. Off macOS, without osascript, or when osascript
fails, nothing happens: the call returns False, never raises, and logs at most once a minute.

Tests never reach the real osascript: when the test runner is loaded and no runner is injected, notify is a no-op.
"""

import hashlib
import json
import os
import plistlib
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
NAME_MAX = 80
OSASCRIPT_TIMEOUT_S = 3
STATE_FILE = "notify.json"
TITLE = "Helm"
APPLET_NAME = "Helm.app"
APPLET_VERSION = 2
APPLET_ID = "dev.helm.notify"
MESSAGE_FILE = "notify-message.json"
STAMP_FILE = "helm-notify.stamp"
BUILD_TIMEOUT_S = 60
LOGO = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "web", "logo.png")
# The kinds the Settings page can switch one by one (config "notifyKinds", default all on). "test" is not listed:
# it only goes out from the Send test button.
KINDS = (("question", "Blocking question"), ("start", "Start queued"), ("limit", "Limit reached"),
         ("head-needs-you", "Head needs you"), ("head-review", "Head review waiting"))
log = get_logger("services.notify")
_last_log = [0.0]
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


def _line(text, limit=TEXT_MAX):
    """One line of plain text, at most limit characters."""
    line = _CONTROL_RE.sub(" ", str("" if text is None else text))
    return " ".join(line.split())[:limit]


def _clean(text, limit=TEXT_MAX):
    """_line with the characters that break an AppleScript string escaped."""
    return _line(text, limit).replace("\\", "\\\\").replace('"', '\\"')


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


def _config():
    try:
        cfg = config.load()
    except Exception:  # an unreadable config means no notification, never an error
        return None
    return cfg


def _enabled():
    cfg = _config()
    return cfg is not None and cfg.get("notify", True) is not False


def _kind_on(kind):
    """False when the person switched this kind off on the Settings page (config "notifyKinds")."""
    cfg = _config()
    kinds = cfg.get("notifyKinds") if cfg else None
    return not (isinstance(kinds, dict) and kinds.get(kind) is False)


def settings():
    """What the Settings page shows: the master switch and one row per kind."""
    cfg = _config() or {}
    kinds = cfg.get("notifyKinds") if isinstance(cfg.get("notifyKinds"), dict) else {}
    return {"enabled": cfg.get("notify", True) is not False,
            "kinds": [{"id": k, "label": label, "on": kinds.get(k) is not False} for k, label in KINDS]}


def set_enabled(value):
    """The master switch (config "notify")."""
    config.update(lambda cfg: cfg.__setitem__("notify", bool(value)))
    return settings()


def set_kind(kind, value):
    """One kind on or off (config "notifyKinds"). An unknown kind is refused with ValueError."""
    if kind not in dict(KINDS):
        raise ValueError("unknown notification kind")

    def mutate(cfg):
        kinds = cfg.get("notifyKinds")
        if not isinstance(kinds, dict):
            kinds = {}
            cfg["notifyKinds"] = kinds
        kinds[kind] = bool(value)

    config.update(mutate)
    return settings()


def send_test(runner=None, applet=None):
    """The Send test notification button: kind "test", no rate limit, only while the master switch is on."""
    return notify("test", TITLE + " \u00b7 Test", "This is a test notification from Helm.", "-", runner=runner,
                  force=True, applet=applet)


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


# ---------------------------------------------------------------- the Helm.app applet (icon)

def _applet_script(message_path):
    """The applet's AppleScript: read title and body from the JSON file and show the notification. The path is fixed
    at build time; plutil reads JSON, so no text is ever pasted into a shell line."""
    quoted = message_path.replace("\\", "\\\\").replace('"', '\\"')
    return ('on run\n'
            '  set p to "%s"\n'
            '  set t to do shell script "/usr/bin/plutil -extract title raw -o - " & quoted form of p\n'
            '  set b to do shell script "/usr/bin/plutil -extract body raw -o - " & quoted form of p\n'
            '  display notification b with title t\n'
            '  delay 1\n'
            'end run\n' % quoted)


def _stamp(script):
    try:
        with open(LOGO, "rb") as handle:
            logo = handle.read()
    except OSError:
        logo = b""
    digest = hashlib.sha1(script.encode("utf-8") + logo).hexdigest()
    return "%d:%s" % (APPLET_VERSION, digest)


def _run_argv(argv):
    done = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                          timeout=BUILD_TIMEOUT_S, check=False)
    return done.returncode == 0


def ensure_applet(folder, run=None):
    """Path of the built Helm.app in folder, building it first when it is missing or its stamp differs (script,
    icon or APPLET_VERSION changed). Returns None when it cannot be built. run(argv) -> bool replaces subprocess."""
    run = run or _run_argv
    app = os.path.join(folder, APPLET_NAME)
    message = os.path.join(folder, MESSAGE_FILE)
    script = _applet_script(message)
    stamp = _stamp(script)
    stamp_path = os.path.join(app, "Contents", "Resources", STAMP_FILE)
    try:
        with open(stamp_path, "r", encoding="utf-8") as handle:
            if handle.read().strip() == stamp:
                return app
    except OSError:
        pass
    work = os.path.join(folder, "applet-build")
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    try:
        source = os.path.join(work, "notify.applescript")
        with open(source, "w", encoding="utf-8") as handle:
            handle.write(script)
        built = os.path.join(work, APPLET_NAME)
        if not run(["osacompile", "-o", built, source]):
            return None
        resources = os.path.join(built, "Contents", "Resources")
        icns = os.path.join(work, "applet.icns")
        if run(["sips", "-s", "format", "icns", LOGO, "--out", icns]) and os.path.exists(icns):
            shutil.copyfile(icns, os.path.join(resources, "applet.icns"))
        _patch_plist(os.path.join(built, "Contents", "Info.plist"))
        try:
            os.remove(os.path.join(resources, "Assets.car"))
        except OSError:
            pass
        with open(os.path.join(resources, STAMP_FILE), "w", encoding="utf-8") as handle:
            handle.write(stamp)
        run(["codesign", "--force", "--deep", "--sign", "-", built])  # the edits break osacompile's signature
        shutil.rmtree(app, ignore_errors=True)
        os.replace(built, app)
        return app
    except Exception as exc:  # no applet: the caller falls back to osascript
        _log_once("applet build: " + type(exc).__name__)
        return None
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _patch_plist(path):
    with open(path, "rb") as handle:
        info = plistlib.load(handle)
    info.update({"CFBundleName": "Helm", "CFBundleDisplayName": "Helm", "CFBundleIdentifier": APPLET_ID,
                 "LSUIElement": True, "CFBundleIconFile": "applet"})
    info.pop("CFBundleIconName", None)  # the default script icon lives in Assets.car under this name
    with open(path, "wb") as handle:
        plistlib.dump(info, handle)


def _show_applet(folder, title, body, run):
    """Show through Helm.app. True when the applet was built, got the text and was opened."""
    app = ensure_applet(folder, run)
    if app is None:
        return False
    atomic.write_json(os.path.join(folder, MESSAGE_FILE), {"title": _line(title), "body": _line(body)})
    return bool((run or _run_argv)(["open", "-g", "-j", "-a", app]))


# ---------------------------------------------------------------- sending

def notify(kind, title, body, project, runner=None, now=None, force=False, applet=None):
    """Show one notification for (project, kind) unless the last one was less than RATE_S ago. Returns True when a
    notification was shown. runner(argv) -> bool replaces every subprocess call (tests inject it). With a runner the
    osascript path is used unless applet=True. force skips the rate limit and the kind switch (the test button)."""
    try:
        return _notify(kind, title, body, project, runner, now, force, applet)
    except Exception as exc:  # a notification must never break the write that asked for it
        _log_once(type(exc).__name__)
        return False


def _notify(kind, title, body, project, runner, now, force, applet):
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
    if not force and not _kind_on(kind):
        return False
    folder = paths.ensure_dir(paths.state_dir())
    if not force:
        moment = time.time() if now is None else now
        if not _allowed(summary(project), summary(kind), moment, os.path.join(folder, STATE_FILE)):
            return False
    title = title or TITLE
    use_applet = (runner is None) if applet is None else applet
    if use_applet:
        try:
            if _show_applet(folder, title, body, runner):
                return True
        except Exception as exc:  # fall back to plain osascript
            _log_once("applet: " + type(exc).__name__)
    argv = ["osascript", "-e", script_for(title, body)]
    shown = (runner or _run_osascript)(argv)
    if not shown:
        _log_once("osascript did not succeed")
    return bool(shown)


def project_of(data_dir):
    """The registered project entry (a copy) whose data folder is data_dir, or None."""
    wanted = os.path.abspath(data_dir)
    for entry in config.list_projects():
        folder = os.path.join(os.path.abspath(str(entry.get("path") or "")), entry.get("dataDir") or "docs")
        if folder == wanted:
            return entry
    return None


def display_name(entry):
    """The full project name for a title (the name, else the id), never cut at SUMMARY_MAX."""
    return _line(entry.get("name") or entry.get("id") or "", NAME_MAX)


def title_for(name):
    return TITLE + " \u00b7 " + name


def notify_dir(data_dir, kind, label, body_for, runner=None, now=None, applet=None):
    """notify for the project that owns data_dir. label names the event for callers only. The title is
    "Helm \u00b7 <project name>"; body_for(name) builds the body from the full project name. Returns False without
    reading the config when notifications cannot be shown."""
    try:
        if runner is None and (_under_tests() or not _macos()):
            return False
        entry = project_of(data_dir)
        if entry is None:
            return False
        name = display_name(entry)
        return notify(kind, title_for(name), body_for(name), entry.get("id"), runner=runner, now=now, applet=applet)
    except Exception as exc:  # the write that asked for the notification is already saved
        _log_once(type(exc).__name__)
        return False
