"""The phone tunnel: rotate the phone token, start ssh to localhost.run, read the tunnel URL, keep the pid file,
and stop only our own ssh. WP13.

The phone token lives in phone.token (mode 0600, written atomically). The tunnel pid lives in tunnel.pid in the state
folder, and ssh's own output goes to tunnel.log (0600) so the URL can be read back. The tunnel host is saved as config
phoneHost, which the phone listener uses for its Host check.

Every process call goes through an injectable callable so tests never run ssh or ps:
SPAWN(argv, log_path) starts a detached process and returns its pid, PS(pid) returns its command line or None, and
KILL(pid, signum) sends a signal. Tests replace all three.
"""

import os
import re
import secrets
import signal
import subprocess
import tempfile
import time

from roadmap.errors import EXIT_CONFLICT, EXIT_EXTERNAL, EXIT_NOT_FOUND, RoadmapError
from roadmap.store import config as config_store
from roadmap.store import lock, paths, schema

TUNNEL_TARGET = "nokey@localhost.run"
TOKEN_BYTES = 32
TOKEN_FILE_MODE = 0o600
START_TIMEOUT_S = 30
POLL_S = 0.2
TUNNEL_LOG = "tunnel.log"
DEFAULT_PHONE_PORT = 8766
TUNNEL_TOOL = "localhost.run"
_URL_RE = re.compile(r"https://((?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)", re.I)
_HOST_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*$")


def _default_spawn(argv, log_path):
    """Start argv detached from this process, with stdin closed and stdout and stderr in log_path (mode 0600).
    Returns the child's pid. No shell is involved."""
    fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, TOKEN_FILE_MODE)
    try:
        proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=fd, stderr=subprocess.STDOUT,
                                start_new_session=True, close_fds=True)
    finally:
        os.close(fd)
    return proc.pid


def _default_ps(pid):
    """The command line of pid from ps, or None when no such process is running."""
    try:
        proc = subprocess.run(["ps", "-o", "command=", "-p", str(int(pid))], capture_output=True, text=True,
                              timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    text = proc.stdout.strip() if proc.returncode == 0 else ""
    return text or None


# Replaced by tests with fakes. Read at call time, so mock.patch on these module attributes takes effect.
SPAWN = _default_spawn
PS = _default_ps
KILL = os.kill
SLEEP = time.sleep
CLOCK = time.monotonic


def new_token():
    """A new phone token: secrets.token_urlsafe(32)."""
    return secrets.token_urlsafe(TOKEN_BYTES)


def _write_private(path, text):
    """Replace path with text atomically, with mode 0600 (the temp file is created 0600 and fsynced before replace)."""
    folder = paths.ensure_dir(os.path.dirname(path))
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            os.fchmod(fh.fileno(), TOKEN_FILE_MODE)
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        _remove_quiet(tmp)
        raise


def _remove_quiet(path):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def read_token():
    """The stored phone token, or None when there is no token file."""
    try:
        with open(paths.phone_token_file(), "r", encoding="utf-8") as fh:
            return fh.read().strip() or None
    except FileNotFoundError:
        return None


def read_pid():
    """The pid recorded in tunnel.pid, or None."""
    try:
        with open(paths.tunnel_pid_file(), "r", encoding="utf-8") as fh:
            text = fh.read().strip()
    except FileNotFoundError:
        return None
    return int(text) if text.isdigit() else None


def is_our_tunnel(command):
    """True when a process command line is an ssh to localhost.run, the only kind of process stop may kill."""
    return bool(command) and "ssh" in command and TUNNEL_TOOL in command


def running_pid():
    """The recorded tunnel pid when that process is still our ssh to localhost.run, else None."""
    pid = read_pid()
    if pid is None:
        return None
    return pid if is_our_tunnel(PS(pid)) else None


def configured_host():
    """The saved tunnel host (config phoneHost), or None."""
    value = config_store.load().get("phoneHost")
    return value if isinstance(value, str) and _HOST_RE.match(value) else None


def _save_host(host):
    """Write phoneHost into config.json under the config lock (host None removes it)."""
    folder = paths.ensure_dir(paths.config_dir())
    with lock.locked(folder):
        cfg = config_store.load()
        if host is None:
            cfg.pop("phoneHost", None)
        else:
            cfg["phoneHost"] = host
        schema.write_data("config", paths.config_file(), cfg)


def _forget_token():
    _remove_quiet(paths.phone_token_file())


def _forget_pid():
    _remove_quiet(paths.tunnel_pid_file())


def _phone_port():
    value = config_store.load().get("phonePort", DEFAULT_PHONE_PORT)
    return value if isinstance(value, int) and not isinstance(value, bool) else DEFAULT_PHONE_PORT


def find_tunnel_host(text):
    """The first https host in ssh's output that is not localhost.run itself, or None."""
    for match in _URL_RE.finditer(text):
        host = match.group(1).lower()
        if host == TUNNEL_TOOL or host.endswith("." + TUNNEL_TOOL):
            continue
        return host
    return None


def _wait_for_host(pid, log_path, timeout_s):
    """Poll the tunnel log for the host. Stops early when the ssh process is gone. Returns the host or None."""
    deadline = CLOCK() + timeout_s
    while True:
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as fh:
                host = find_tunnel_host(fh.read())
        except FileNotFoundError:
            host = None
        if host:
            return host
        if PS(pid) is None or CLOCK() >= deadline:
            return None
        SLEEP(POLL_S)


def start(phone_port=None, timeout_s=START_TIMEOUT_S):
    """Rotate the phone token, start the tunnel and save its host. Refuses when a tunnel is already running (exit 4).
    A tunnel that gives no URL in time is killed, and the new token is removed again (exit 6)."""
    if running_pid() is not None:
        raise RoadmapError("conflict", "the phone tunnel is already running; run roadmap phone stop first",
                           EXIT_CONFLICT)
    port = _phone_port() if phone_port is None else phone_port
    _forget_pid()
    token = new_token()
    _write_private(paths.phone_token_file(), token)
    log_path = os.path.join(paths.state_dir(), TUNNEL_LOG)
    argv = ["ssh", "-o", "ServerAliveInterval=30", "-R", "80:127.0.0.1:%d" % port, TUNNEL_TARGET]
    paths.ensure_dir(paths.state_dir())
    try:
        pid = SPAWN(argv, log_path)
    except OSError:
        _forget_token()
        raise RoadmapError("external", "ssh is not available, so the phone tunnel cannot start", EXIT_EXTERNAL)
    host = _wait_for_host(pid, log_path, timeout_s)
    if host is None:
        try:
            KILL(pid, signal.SIGTERM)
        except OSError:
            pass
        _forget_token()
        raise RoadmapError("external", "the tunnel gave no address within %d seconds (see tunnel.log)" % timeout_s,
                           EXIT_EXTERNAL)
    _write_private(paths.tunnel_pid_file(), str(pid))
    _save_host(host)
    return {"running": True, "pid": pid, "url": "https://" + host, "host": host}


def stop():
    """Stop our tunnel, delete the token and the saved host. A pid that is not our ssh is never signalled: the call
    then fails with exit 4 and the pid file is kept. The token and host are removed in every case."""
    pid = read_pid()
    stopped_pid = None
    refused = False
    if pid is not None:
        command = PS(pid)
        if command is None:
            pass
        elif is_our_tunnel(command):
            KILL(pid, signal.SIGTERM)
            stopped_pid = pid
        else:
            refused = True
    _forget_token()
    _save_host(None)
    if refused:
        raise RoadmapError("conflict", "pid %d is not our phone tunnel, so it was not stopped; tunnel.pid is kept"
                           % pid, EXIT_CONFLICT)
    _forget_pid()
    return {"stopped": True, "pid": stopped_pid, "tokenDeleted": True}


def status():
    """Whether the tunnel runs, its pid and its saved address. The token is never part of the result."""
    pid = running_pid()
    host = configured_host()
    return {
        "running": pid is not None,
        "pid": pid,
        "url": None if host is None else "https://" + host,
        "tokenFile": read_token() is not None,
    }


def link():
    """The private link: https://<host>/?k=<token>. It grants read access, so it must be kept private."""
    token = read_token()
    if token is None:
        raise RoadmapError("not_found", "there is no phone token yet; run roadmap phone start", EXIT_NOT_FOUND)
    host = configured_host()
    if host is None:
        raise RoadmapError("not_found", "no tunnel address is saved yet; run roadmap phone start", EXIT_NOT_FOUND)
    return {"url": "https://%s/?k=%s" % (host, token), "running": running_pid() is not None}
