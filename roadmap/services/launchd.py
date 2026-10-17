"""The launchd user agent that runs `roadmap serve`: render and write the plist, the lifecycle through launchctl,
status parsing, the log tail and the launchd log truncation. WP11.

Every external command goes through RUNNER, a callable taking an argv list and returning (returncode, stdout,
stderr). Tests replace RUNNER with a fake, so nothing runs launchctl for real. The plist goes to the LaunchAgents
folder: ROADMAP_LAUNCH_AGENTS when set, else ~/Library/LaunchAgents. Logs go to store.paths.logs_dir().
"""

import os
import re
import subprocess
import sys
import tempfile
import time
from string import Template
from xml.sax.saxutils import escape

from roadmap.errors import EXIT_EXTERNAL, EXIT_NOT_FOUND, RoadmapError
from roadmap.store import paths

LABEL = "com.roadmap-board.agent"
PLIST_NAME = LABEL + ".plist"
PLIST_MODE = 0o644
LAUNCH_AGENTS_ENV = "ROADMAP_LAUNCH_AGENTS"
TEMPLATE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates", "plist.tmpl")
LAUNCHD_OUT = "launchd.out"
LAUNCHD_ERR = "launchd.err"
LAUNCHD_MAX_BYTES = 5 * 1024 * 1024
TOOL_TIMEOUT_S = 15
PLUTIL = "/usr/bin/plutil"
LAUNCHCTL = "launchctl"
NOT_LOADED_CODES = (3, 113)  # launchctl: no such service (bootout/print of an unloaded job)


def _default_runner(argv):
    """Run argv without a shell and return (returncode, stdout, stderr). A missing tool gives 127."""
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=TOOL_TIMEOUT_S, check=False)
    except FileNotFoundError:
        return 127, "", argv[0] + " not found"
    except subprocess.TimeoutExpired:
        return 124, "", argv[0] + " timed out"
    return proc.returncode, proc.stdout, proc.stderr


# Replaced by tests with a fake. Read at call time, so mock.patch on this module attribute takes effect.
RUNNER = _default_runner


def repo_root():
    """The folder that holds the roadmap package: the PYTHONPATH and WorkingDirectory of the agent."""
    here = os.path.realpath(os.path.abspath(__file__))
    return os.path.dirname(os.path.dirname(os.path.dirname(here)))


def launch_agents_dir():
    """The LaunchAgents folder. ROADMAP_LAUNCH_AGENTS overrides it (tests and unusual setups)."""
    override = os.environ.get(LAUNCH_AGENTS_ENV, "").strip()
    if override:
        return os.path.abspath(os.path.expanduser(override))
    return os.path.join(os.path.expanduser("~"), "Library", "LaunchAgents")


def plist_path():
    return os.path.join(launch_agents_dir(), PLIST_NAME)


def domain():
    """The launchd GUI domain of the current user, gui/<uid>."""
    return "gui/%d" % os.getuid()


def service_target():
    return domain() + "/" + LABEL


def render_plist(python=None, repo=None, logs_dir=None):
    """The plist text. Values are XML-escaped; python defaults to sys.executable, repo to this checkout."""
    python = os.path.abspath(python or sys.executable)
    repo = os.path.abspath(repo or repo_root())
    logs = logs_dir or paths.logs_dir()
    with open(TEMPLATE, "r", encoding="utf-8") as fh:
        template = Template(fh.read())
    values = {
        "label": escape(LABEL),
        "python": escape(python),
        "repo": escape(repo),
        "stdout_path": escape(os.path.join(logs, LAUNCHD_OUT)),
        "stderr_path": escape(os.path.join(logs, LAUNCHD_ERR)),
    }
    return template.substitute(values)


def _write_plist(path, text):
    """Write the plist atomically with mode 0644 (launchd reads it as the user)."""
    folder = os.path.dirname(path)
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".plist-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fchmod(fh.fileno(), PLIST_MODE)
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _launchctl(args, runner=None):
    run = runner or RUNNER
    return run([LAUNCHCTL] + list(args))


def _fail(action, rc, err):
    detail = (err or "").strip().splitlines()[0] if (err or "").strip() else "exit status %d" % rc
    return RoadmapError("external", "launchctl " + action + " failed: " + detail, EXIT_EXTERNAL)


def _must(action, rc, err):
    if rc != 0:
        raise _fail(action, rc, err)


def is_loaded(runner=None):
    """True when launchctl knows the service (print exits 0)."""
    rc, _, _ = _launchctl(["print", service_target()], runner)
    return rc == 0


def install(python=None, runner=None, logs_dir=None):
    """Write the plist, then (re)load it: bootout if loaded, then bootstrap. Returns the plist path."""
    path = plist_path()
    text = render_plist(python=python, logs_dir=logs_dir)
    _write_plist(path, text)
    _launchctl(["bootout", service_target()], runner)  # ignored: it fails when the job is not loaded
    rc, _, err = _launchctl(["bootstrap", domain(), path], runner)
    _must("bootstrap", rc, err)
    return path


def uninstall(runner=None):
    """Unload the job and remove the plist. Logs and config are kept. A bootout failure other than "not loaded" is an
    error, and then the plist is kept, so the job can still be unloaded later. Returns True when a plist was removed."""
    rc, _, err = _launchctl(["bootout", service_target()], runner)
    if rc != 0 and rc not in NOT_LOADED_CODES:
        raise _fail("bootout", rc, err)
    path = plist_path()
    if os.path.exists(path):
        os.remove(path)
        return True
    return False


def start(runner=None):
    """Load the job when it is not loaded, otherwise kick it."""
    if is_loaded(runner):
        rc, _, err = _launchctl(["kickstart", service_target()], runner)
        _must("kickstart", rc, err)
        return
    rc, _, err = _launchctl(["bootstrap", domain(), _installed_plist()], runner)
    _must("bootstrap", rc, err)


def stop(runner=None):
    """Unload the job. The plist stays, so start works again. Stopping an unloaded job is not an error."""
    rc, _, err = _launchctl(["bootout", service_target()], runner)
    if rc != 0 and rc not in NOT_LOADED_CODES:
        raise _fail("bootout", rc, err)


def restart(runner=None):
    """Restart the job with kickstart -k, or load it first when it is not loaded."""
    if not is_loaded(runner):
        return start(runner)
    rc, _, err = _launchctl(["kickstart", "-k", service_target()], runner)
    _must("kickstart -k", rc, err)


def _installed_plist():
    path = plist_path()
    if not os.path.isfile(path):
        raise RoadmapError("not_found", "the service is not installed; run roadmap service install",
                           EXIT_NOT_FOUND)
    return path


_FIELD_RE = re.compile(r"^\s*(state|pid|last exit code|path|program|runs)\s*=\s*(.+?)\s*$")


def parse_print(text):
    """The fields of `launchctl print` output that status shows: state, pid, last exit code, runs, path.
    Unknown lines are ignored; a missing field is None."""
    fields = {"state": None, "pid": None, "lastExitCode": None, "runs": None, "path": None}
    for line in (text or "").splitlines():
        match = _FIELD_RE.match(line)
        if not match:
            continue
        key, value = match.group(1), match.group(2)
        if key == "state" and fields["state"] is None:
            fields["state"] = value
        elif key == "pid" and fields["pid"] is None and value.isdigit():
            fields["pid"] = int(value)
        elif key == "last exit code" and fields["lastExitCode"] is None:
            fields["lastExitCode"] = value
        elif key == "runs" and fields["runs"] is None and value.isdigit():
            fields["runs"] = int(value)
        elif key == "path" and fields["path"] is None:
            fields["path"] = value
    return fields


def status(runner=None):
    """Whether launchd has the job, and its state and pid when it does. Read-only: launchctl print."""
    path = plist_path()
    rc, out, _ = _launchctl(["print", service_target()], runner)
    info = {"label": LABEL, "plist": path, "plistInstalled": os.path.isfile(path), "loaded": rc == 0,
            "state": None, "pid": None, "lastExitCode": None, "runs": None}
    if rc == 0:
        fields = parse_print(out)
        for key in ("state", "pid", "lastExitCode", "runs"):
            info[key] = fields[key]
    return info


# Folders whose contents the running server reads only at startup (the static file allowlist, the HTTP/launchd
# code itself): a change under any of these after the process started means a restart is needed to take effect.
# See docs/HANDOVER.md: "the static file list is built at startup so NEW web files 404 until restart".
STALE_WATCH_DIRS = ("web", os.path.join("roadmap", "http"), os.path.join("roadmap", "services"))


def process_start_time(pid, runner=None):
    """Epoch seconds the given pid has been running since, via `ps -o etimes=`. None when ps fails, the pid is
    unknown, or output is not a plain integer (e.g. the pid has since exited)."""
    run = runner or RUNNER
    rc, out, _ = run(["ps", "-o", "etimes=", "-p", str(pid)])
    text = (out or "").strip()
    if rc != 0 or not text.isdigit():
        return None
    return time.time() - int(text)


def _newest_mtime(repo, dirs):
    """The newest mtime among files under the given dirs (relative to repo), or None if none exist/are readable."""
    newest = None
    for rel in dirs:
        base = os.path.join(repo, rel)
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if not d.startswith(".") and d != "__pycache__"]
            for name in filenames:
                if name.startswith("."):
                    continue
                try:
                    mtime = os.path.getmtime(os.path.join(dirpath, name))
                except OSError:
                    continue
                if newest is None or mtime > newest:
                    newest = mtime
    return newest


def stale(runner=None, repo=None):
    """Whether web/, roadmap/http/ or roadmap/services/ changed after the running service process started, so a
    restart is needed before the change takes effect (see STALE_WATCH_DIRS). Read-only: launchctl print plus ps.
    False (never an error) when the service is not loaded, its pid is unknown, or the pid's start time can't be
    read — those are "can't tell", not "known fresh", but the caller only ever uses this to decide whether to
    prompt/restart, so treating them as non-stale is the safe default."""
    state = status(runner)
    pid = state.get("pid")
    result = {"stale": False, "pid": pid, "startedAt": None, "newestChange": None}
    if not state["loaded"] or not pid:
        return result
    started = process_start_time(pid, runner)
    if started is None:
        return result
    newest = _newest_mtime(repo or repo_root(), STALE_WATCH_DIRS)
    result["startedAt"] = started
    result["newestChange"] = newest
    result["stale"] = newest is not None and newest > started
    return result


def listener_on(port, runner=None):
    """{"pid", "name"} of the process listening on TCP port (lsof, read-only), or None when nothing listens.
    lsof missing or failing gives None as well; the caller decides what that means."""
    rc, out, _ = (runner or RUNNER)(["lsof", "-nP", "-iTCP:%d" % int(port), "-sTCP:LISTEN", "-Fpc"])
    return parse_lsof(out) if rc == 0 else None


def parse_lsof(text):
    """{"pid", "name"} from `lsof -Fpc` output (the first listener), or None when there is no listener."""
    pid = name = None
    for line in (text or "").splitlines():
        if line.startswith("p") and pid is None:
            pid = line[1:]
        elif line.startswith("c") and name is None:
            name = line[1:]
    if pid is None:
        return None
    return {"pid": int(pid) if pid.isdigit() else None, "name": name or "unknown"}


def lint_plist(path, runner=None):
    """Run plutil -lint on path. Returns (ok, message)."""
    rc, out, err = (runner or RUNNER)([PLUTIL, "-lint", path])
    text = (out or err or "").strip()
    return rc == 0, text.splitlines()[0] if text else ("exit status %d" % rc)


def truncate_large(path, limit=LAUNCHD_MAX_BYTES):
    """Empty the file at path when it is larger than limit bytes. Returns True when it was truncated.
    A missing file is fine."""
    try:
        if os.path.getsize(path) <= limit:
            return False
    except FileNotFoundError:
        return False
    os.truncate(path, 0)
    return True


def prepare_launchd_logs(logs_dir=None, limit=LAUNCHD_MAX_BYTES):
    """Truncate launchd.out and launchd.err when either is above limit. Call it when serve starts.
    Returns the list of file names that were truncated."""
    folder = logs_dir or paths.logs_dir()
    cut = []
    for name in (LAUNCHD_OUT, LAUNCHD_ERR):
        if truncate_large(os.path.join(folder, name), limit):
            cut.append(name)
    return cut


def tail_lines(path, count=100):
    """The last count lines of path (a missing file gives an empty list)."""
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except FileNotFoundError:
        return []
    lines = data.decode("utf-8", "replace").splitlines()
    return lines[-count:] if count > 0 else lines


def follow(path, emit, should_stop, sleep=time.sleep, poll_s=0.5):
    """Print the lines appended to path after this call, through emit, until should_stop() is true.
    Starts at the end of the file; a file that shrinks (rotated) is read again from its start."""
    position = os.path.getsize(path) if os.path.exists(path) else 0
    pending = ""
    while not should_stop():
        try:
            size = os.path.getsize(path)
        except FileNotFoundError:
            size = 0
        if size < position:
            position = 0
            pending = ""
        if size > position:
            with open(path, "rb") as fh:
                fh.seek(position)
                chunk = fh.read(size - position)
            position += len(chunk)
            pending += chunk.decode("utf-8", "replace")
            *complete, pending = pending.split("\n")
            for line in complete:
                emit(line)
        else:
            sleep(poll_s)
