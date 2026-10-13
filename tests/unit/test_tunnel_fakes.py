"""Shared fakes for the tunnel and phone command tests: a temporary ROADMAP_HOME, a fake ssh (spawn, ps and kill) and a
fake clock. No test built on this runs ssh, ps or kill for real. The module holds no test cases of its own."""

import os
import shutil
import tempfile
import unittest
from unittest import mock

from roadmap.services import tunnel
from roadmap.store import paths

FAKE_PID = 4242
SSH_COMMAND = "ssh -o ServerAliveInterval=30 -R 80:127.0.0.1:8766 nokey@localhost.run"
BANNER = "Connect to https://abc123.lhr.life to reach your local server\n"


class FakeSsh:
    """Stands in for tunnel.SPAWN, tunnel.PS and tunnel.KILL. banner is what ssh writes to its log file."""

    def __init__(self, banner=BANNER, pid=FAKE_PID, spawn_error=None):
        self.banner = banner
        self.pid = pid
        self.spawn_error = spawn_error
        self.table = {}
        self.spawned = []
        self.killed = []

    def spawn(self, argv, log_path):
        if self.spawn_error is not None:
            raise self.spawn_error
        self.spawned.append((list(argv), log_path))
        fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)  # the real spawn makes it 0600 too
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(self.banner)
        self.table[self.pid] = " ".join(argv)
        return self.pid

    def ps(self, pid):
        return self.table.get(pid)

    def kill(self, pid, signum):
        self.killed.append((pid, signum))
        self.table.pop(pid, None)


class FakeClock:
    """A clock that moves one second on every call, so the wait loop ends without real sleeps."""

    def __init__(self):
        self.now = 0.0

    def __call__(self):
        self.now += 1.0
        return self.now


class TunnelCase(unittest.TestCase):
    """A temporary ROADMAP_HOME and the fakes patched into services/tunnel.py for each test."""

    def setUp(self):
        self._saved_home = os.environ.get("ROADMAP_HOME")
        self.tmp = tempfile.mkdtemp(prefix="rb-tunnel-")
        os.environ["ROADMAP_HOME"] = os.path.join(self.tmp, "home")
        self.addCleanup(self._restore_env)
        self.ssh = FakeSsh()
        self.patch(tunnel, "SPAWN", self.ssh.spawn)
        self.patch(tunnel, "PS", self.ssh.ps)
        self.patch(tunnel, "KILL", self.ssh.kill)
        self.patch(tunnel, "SLEEP", lambda seconds: None)
        self.patch(tunnel, "CLOCK", FakeClock())

    def patch(self, module, name, value):
        patcher = mock.patch.object(module, name, value)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _restore_env(self):
        if self._saved_home is None:
            os.environ.pop("ROADMAP_HOME", None)
        else:
            os.environ["ROADMAP_HOME"] = self._saved_home
        shutil.rmtree(self.tmp, ignore_errors=True)

    def token_path(self):
        return paths.phone_token_file()

    def pid_path(self):
        return paths.tunnel_pid_file()
