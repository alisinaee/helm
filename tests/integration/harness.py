"""Shared helper for the WP38 end-to-end tests.

A Sandbox is a temp root with its own ROADMAP_HOME, its own HOME and a temp project (a copy of tests/fixtures/splitnet
in <root>/project/docs), registered once through the CLI. Every subprocess gets a fresh environment built from scratch,
so nothing leaks from the test runner: CLAUDECODE is set only for agent-style calls (agent=True).

A Server is `bin/roadmap serve --port 0 --no-usage-loop --no-phone --json` in a subprocess. The bound port is read from
the envelope on its first stdout line. It is always terminated by a cleanup registered on the test case.
Nothing here touches the real ~/.config/roadmap-board, the running service, the keychain or the network: the server
listens on 127.0.0.1 only, and every HTTP call goes to that loopback address.
"""

import json
import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import urllib.error
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SHIM = os.path.join(REPO, "bin", "roadmap")
FIXTURE = os.path.join(REPO, "tests", "fixtures", "splitnet")
START_TIMEOUT_S = 10
CALL_TIMEOUT_S = 30
CSRF_META = re.compile(r'<meta name="csrf" content="([^"]+)">')


class Sandbox(object):
    """Temp ROADMAP_HOME, temp HOME and one registered temp project. Removed by the case's cleanup."""

    def __init__(self, case):
        self.root = tempfile.mkdtemp(prefix="roadmap-wp38-")
        case.addCleanup(shutil.rmtree, self.root, True)
        self.home = os.path.join(self.root, "roadmap-home")
        self.user_home = os.path.join(self.root, "user-home")
        self.project = os.path.join(self.root, "project")
        os.makedirs(self.user_home)
        shutil.copytree(FIXTURE, os.path.join(self.project, "docs"))
        self.pid = None
        added = self.cli_json(["project", "add", self.project, "--name", "Split"])
        self.pid = added["project"]["id"]

    @property
    def data_dir(self):
        return os.path.join(self.project, "docs")

    @property
    def state_dir(self):
        return os.path.join(self.home, "state")

    @property
    def sentinel(self):
        return os.path.join(self.state_dir, "block-" + self.pid)

    def env(self, agent=False):
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": self.user_home,
               "ROADMAP_HOME": self.home}
        if self.pid:
            env["ROADMAP_PROJECT"] = self.pid
        if agent:
            env["CLAUDECODE"] = "1"
        return env

    def cli(self, args, agent=False, stdin=None):
        """Run bin/roadmap with the given arguments. Human style by default; agent=True sets CLAUDECODE=1."""
        return subprocess.run([SHIM] + list(args), input=stdin, capture_output=True, text=True,
                              env=self.env(agent), cwd=self.project, timeout=CALL_TIMEOUT_S)

    def cli_json(self, args, agent=False, stdin=None):
        """Run with --json, check exit 0 and return the envelope's data."""
        proc = self.cli(list(args) + ["--json"], agent=agent, stdin=stdin)
        if proc.returncode != 0:
            raise AssertionError("roadmap %s exited %d: %s" % (" ".join(args), proc.returncode, proc.stderr))
        return json.loads(proc.stdout)["data"]

    def hook(self, tool, tool_input=None):
        """Feed a PreToolUse payload to `bin/roadmap hook pre` the way the agent's hook does. Returns the parsed reply,
        or None when the gate lets the call through (empty stdout)."""
        payload = {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input or {},
                   "cwd": self.project}
        proc = subprocess.run([SHIM, "hook", "pre"], input=json.dumps(payload), capture_output=True, text=True,
                              env=self.env(agent=True), cwd=self.project, timeout=CALL_TIMEOUT_S)
        if proc.returncode != 0:
            raise AssertionError("hook pre exited %d: %s" % (proc.returncode, proc.stderr))
        return json.loads(proc.stdout) if proc.stdout.strip() else None

    def write_doc(self, name, obj):
        with open(os.path.join(self.data_dir, name), "w", encoding="utf-8") as fh:
            json.dump(obj, fh, indent=2)
            fh.write("\n")

    def read_doc(self, name):
        with open(os.path.join(self.data_dir, name), encoding="utf-8") as fh:
            return json.load(fh)


class Server(object):
    """One `roadmap serve --port 0` process. Use it through Stack or call start() yourself; close() always stops it."""

    def __init__(self, case, sandbox, extra_args=()):
        self.sandbox = sandbox
        self.stderr_path = os.path.join(sandbox.root, "serve.err")
        self._stderr = open(self.stderr_path, "w", encoding="utf-8")
        self.proc = subprocess.Popen([SHIM, "serve", "--port", "0", "--no-usage-loop", "--no-phone", "--json"]
                                     + list(extra_args), stdout=subprocess.PIPE, stderr=self._stderr, text=True,
                                     env=sandbox.env(), cwd=sandbox.project)
        case.addCleanup(self.close)
        lines = queue.Queue()
        threading.Thread(target=lambda: lines.put(self.proc.stdout.readline()), daemon=True).start()
        try:
            first = lines.get(timeout=START_TIMEOUT_S)
        except queue.Empty:
            self.close()
            raise AssertionError("serve printed no envelope within %d s" % START_TIMEOUT_S)
        data = json.loads(first)["data"]
        self.port = data["port"]
        self.base = "http://127.0.0.1:%d" % self.port
        self.csrf = self._page_csrf()

    def _page_csrf(self):
        status, _, body = self.request("GET", "/")
        found = CSRF_META.search(body.decode("utf-8"))
        if status != 200 or not found:
            raise AssertionError("the index page did not carry a csrf meta (status %d)" % status)
        return found.group(1)

    def close(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=5)
        if not self._stderr.closed:
            self._stderr.close()
        if self.proc.stdout and not self.proc.stdout.closed:
            self.proc.stdout.close()

    def request(self, method, path, body=None, headers=None, host=None):
        """(status, headers, body bytes). Error statuses are returned, not raised. Host overrides the Host header."""
        data = None
        if body is not None:
            data = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        req = urllib.request.Request(self.base + path, data=data, method=method)
        for name, value in (headers or {}).items():
            req.add_header(name, value)
        if host is not None:
            req.add_header("Host", host)
        try:
            resp = urllib.request.urlopen(req, timeout=CALL_TIMEOUT_S)
            return resp.status, dict(resp.headers), resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers), exc.read()

    def write_headers(self, **overrides):
        """The headers a same-origin page sends with a write: CSRF, Sec-Fetch-Site, Origin and the JSON type."""
        headers = {"Content-Type": "application/json", "Sec-Fetch-Site": "same-origin", "Origin": self.base,
                   "X-Roadmap-CSRF": self.csrf}
        headers.update(overrides)
        return {name: value for name, value in headers.items() if value is not None}

    def cmd(self, op, args=None, expect=200):
        """POST /api/v1/cmd as the page does. Returns the parsed reply; asserts the status when expect is set."""
        status, _, body = self.request("POST", "/api/v1/cmd", {"op": op, "args": args or {}}, self.write_headers())
        reply = json.loads(body.decode("utf-8"))
        if expect is not None and status != expect:
            raise AssertionError("cmd %s answered %d: %s" % (op, status, reply))
        return reply

    def get_json(self, path, expect=200):
        status, _, body = self.request("GET", path)
        if expect is not None and status != expect:
            raise AssertionError("GET %s answered %d: %s" % (path, status, body[:200]))
        return json.loads(body.decode("utf-8"))

    def snapshot(self, pid):
        return self.get_json("/api/v1/projects/%s/snapshot" % pid)


def stack(case, extra_args=()):
    """A sandbox and a running server for one test."""
    sandbox = Sandbox(case)
    return sandbox, Server(case, sandbox, extra_args)
