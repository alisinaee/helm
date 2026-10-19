"""The systemd --user unit that runs `roadmap serve` on Linux: render and write the unit file, the lifecycle through
systemctl --user, status parsing and the stale check. The Linux counterpart of services/launchd.py: the same public
functions and status keys, so commands/service.py can pick either backend at call time.

Every external command goes through RUNNER, a callable taking an argv list and returning (returncode, stdout,
stderr), as in launchd. Tests replace RUNNER with a fake, so nothing runs systemctl for real. The unit goes to
~/.config/systemd/user/helm.service. Logs stay in store.paths.logs_dir() (server.log), as on macOS.
"""

import os
import re
import sys
import tempfile

from roadmap.errors import EXIT_EXTERNAL, EXIT_NOT_FOUND, RoadmapError
from roadmap.services import launchd

UNIT_NAME = "helm.service"
UNIT_MODE = 0o644
SYSTEMCTL = "systemctl"
NOT_LOADED_RC = 5  # systemctl: the unit is not loaded (stop/disable of a unit systemd does not know)
ACTIVE_STATES = ("active", "activating", "reloading")
SHOW_PROPERTIES = "ActiveState,MainPID,ExecMainStatus,LoadState"
ENV_KEYS = ("ROADMAP_BIND_HOST", "ROADMAP_PUBLIC_HOST", "ROADMAP_HOME")
SAFE_WORD = re.compile(r"^[A-Za-z0-9_./:@+=,-]+$")

def _guarded_runner(argv):
    """The launchd subprocess runner (argv list, no shell, timeout), except under unittest: a test that forgot to
    install a fake must never reach the real systemctl (it would restart or disable the person's service)."""
    if "unittest" in sys.modules:
        return 1, "", "systemctl is not run under tests"
    return launchd._default_runner(argv)


# Tests replace this attribute with a fake.
RUNNER = _guarded_runner


def unit_dir():
    """The systemd user unit folder, ~/.config/systemd/user."""
    return os.path.join(os.path.expanduser("~"), ".config", "systemd", "user")


def plist_path():
    """The unit file path. It is named plist_path so commands/service.py calls the same name on both backends."""
    return os.path.join(unit_dir(), UNIT_NAME)


def _word(text, exec_line=False):
    """One systemd word: as it is when plain, else double-quoted. A % is escaped (specifiers); a $ is escaped in
    ExecStart only, where systemd expands variables."""
    if SAFE_WORD.match(text):
        return text
    body = text.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%")
    if exec_line:
        body = body.replace("$", "$$")
    return '"' + body + '"'


def render_unit(repo=None, env=None):
    """The unit text. repo defaults to this checkout; env (default os.environ) decides which of ENV_KEYS get an
    Environment line, so a variable that is not set is left out."""
    repo = os.path.abspath(repo or launchd.repo_root())
    env = os.environ if env is None else env
    lines = [
        "[Unit]",
        "Description=Helm dashboard",
        "After=network-online.target",
        "",
        "[Service]",
        "WorkingDirectory=" + repo.replace("%", "%%"),
        "Environment=PYTHONUNBUFFERED=1",
    ]
    for key in ENV_KEYS:
        if key in env:
            lines.append("Environment=" + _word("%s=%s" % (key, env[key])))
    argv = [os.path.join(repo, "bin", "roadmap"), "serve", "--no-phone"]
    lines += [
        "ExecStart=" + " ".join(_word(part, exec_line=True) for part in argv),
        "Restart=on-failure",
        "RestartSec=5",
        "",
        "[Install]",
        "WantedBy=default.target",
        "",
    ]
    return "\n".join(lines)


def _write_unit(path, text):
    """Write the unit atomically with mode 0644 (systemd reads it as the user)."""
    folder = os.path.dirname(path)
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".unit-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fchmod(fh.fileno(), UNIT_MODE)
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _systemctl(args, runner=None):
    run = runner or RUNNER
    return run([SYSTEMCTL, "--user"] + list(args))


def _fail(action, rc, err):
    detail = (err or "").strip().splitlines()[0] if (err or "").strip() else "exit status %d" % rc
    return RoadmapError("external", "systemctl --user " + action + " failed: " + detail, EXIT_EXTERNAL)


def _must(action, rc, err):
    if rc != 0:
        raise _fail(action, rc, err)


def _installed_unit():
    path = plist_path()
    if not os.path.isfile(path):
        raise RoadmapError("not_found", "the service is not installed; run roadmap service install",
                           EXIT_NOT_FOUND)
    return path


def install(python=None, runner=None):
    """Write the unit, reload the user manager, then enable and start it. Returns the unit path.
    python is accepted for parity with launchd.install: bin/roadmap picks its own interpreter."""
    path = plist_path()
    _write_unit(path, render_unit())
    rc, _, err = _systemctl(["daemon-reload"], runner)
    _must("daemon-reload", rc, err)
    rc, _, err = _systemctl(["enable", "--now", UNIT_NAME], runner)
    _must("enable --now", rc, err)
    return path


def uninstall(runner=None):
    """Disable and stop the unit, remove the file and reload. Logs and config are kept. A failure to disable an
    installed unit is an error, and then the file is kept. Returns True when a unit file was removed."""
    path = plist_path()
    installed = os.path.exists(path)
    rc, _, err = _systemctl(["disable", "--now", UNIT_NAME], runner)
    if rc != 0 and installed:
        raise _fail("disable --now", rc, err)
    if installed:
        os.remove(path)
    rc, _, err = _systemctl(["daemon-reload"], runner)
    _must("daemon-reload", rc, err)
    return installed


def start(runner=None):
    """Start the unit (it must be installed)."""
    _installed_unit()
    rc, _, err = _systemctl(["start", UNIT_NAME], runner)
    _must("start", rc, err)


def stop(runner=None):
    """Stop the unit. The unit file stays, so start works again. Stopping a unit systemd does not know is not an
    error."""
    rc, _, err = _systemctl(["stop", UNIT_NAME], runner)
    if rc != 0 and rc != NOT_LOADED_RC:
        raise _fail("stop", rc, err)


def restart(runner=None):
    """Restart the unit (it must be installed). systemctl restart also starts a unit that is not running."""
    _installed_unit()
    rc, _, err = _systemctl(["restart", UNIT_NAME], runner)
    _must("restart", rc, err)


def parse_show(text):
    """The Key=Value pairs of `systemctl show` output as a dict. Lines without "=" are ignored."""
    fields = {}
    for line in (text or "").splitlines():
        key, sep, value = line.partition("=")
        if sep:
            fields[key.strip()] = value.strip()
    return fields


def status(runner=None):
    """Whether systemd runs the unit, and its state and pid. Read-only: systemctl --user show. The keys match
    launchd.status: loaded means the unit is active (or starting, or reloading)."""
    path = plist_path()
    rc, out, _ = _systemctl(["show", UNIT_NAME, "-p", SHOW_PROPERTIES], runner)
    info = {"label": UNIT_NAME, "plist": path, "plistInstalled": os.path.isfile(path), "loaded": False,
            "state": None, "pid": None, "lastExitCode": None, "runs": None}
    if rc == 0:
        fields = parse_show(out)
        info["state"] = fields.get("ActiveState") or None
        pid = fields.get("MainPID", "")
        info["pid"] = int(pid) if pid.isdigit() and int(pid) > 0 else None
        info["lastExitCode"] = fields.get("ExecMainStatus") or None
        info["loaded"] = info["state"] in ACTIVE_STATES
    return info


def stale(runner=None, repo=None):
    """Whether web/, roadmap/http/ or roadmap/services/ changed after the running unit's process started, so a
    restart is needed (see launchd.STALE_WATCH_DIRS). Read-only: systemctl show plus ps. False when the unit is not
    running, its pid is unknown, or the start time can't be read (the same safe default as launchd.stale)."""
    run = runner or RUNNER
    state = status(run)
    pid = state.get("pid")
    result = {"stale": False, "pid": pid, "startedAt": None, "newestChange": None}
    if not state["loaded"] or not pid:
        return result
    started = launchd.process_start_time(pid, run)
    if started is None:
        return result
    newest = launchd._newest_mtime(repo or launchd.repo_root(), launchd.STALE_WATCH_DIRS)
    result["startedAt"] = started
    result["newestChange"] = newest
    result["stale"] = newest is not None and newest > started
    return result


def tail_lines(path, count=100):
    """The last count lines of path (see launchd.tail_lines). Looked up at call time, so a patch on launchd applies."""
    return launchd.tail_lines(path, count)


def follow(path, emit, should_stop, sleep=None, poll_s=0.5):
    """Print the lines appended to path (see launchd.follow). Looked up at call time, so a patch on launchd applies."""
    if sleep is None:
        return launchd.follow(path, emit, should_stop, poll_s=poll_s)
    return launchd.follow(path, emit, should_stop, sleep=sleep, poll_s=poll_s)
