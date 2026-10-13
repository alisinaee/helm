"""Shared helpers for the WP11 tests: a temp ROADMAP_HOME and LaunchAgents folder, and a fake runner that stands in
for launchctl, lsof, security and plutil. No test here runs launchctl, and the real home is never touched."""

import contextlib
import io
import json
import os
from unittest import mock

from roadmap.cli import main
from roadmap.services import launchd
from tests.unit.test_store_support import HomeCase

SAMPLE_PRINT = """gui/501/com.roadmap-board.agent = {
\tactive count = 1
\tpath = /Users/test/Library/LaunchAgents/com.roadmap-board.agent.plist
\ttype = LaunchAgent
\tstate = running
\tprogram = /usr/bin/python3
\truns = 3
\tpid = 4242
\tlast exit code = 0
}
"""


class FakeRunner:
    """Records every argv and answers with handler(argv) -> (returncode, stdout, stderr). Default: success."""

    def __init__(self, handler=None):
        self.calls = []
        self.handler = handler or (lambda argv: (0, "", ""))

    def __call__(self, argv):
        argv = list(argv)
        self.calls.append(argv)
        return self.handler(argv)


def answer_for(**kw):
    """A handler that answers by tool name. kw: a dict per tool name: {"rc", "out", "err"}; unknown tools rc 1."""

    def handler(argv):
        spec = kw.get(argv[0])
        if spec is None:
            return (1, "", "unexpected tool " + argv[0])
        return (spec.get("rc", 0), spec.get("out", ""), spec.get("err", ""))

    return handler


def run_cli(argv):
    """Run the CLI in-process and return (exit code, stdout, stderr). SystemExit is returned as its code."""
    out = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = main(argv)
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue(), err.getvalue()


def envelope(argv):
    """Run the CLI with --json and return (exit code, parsed envelope)."""
    code, out, _ = run_cli(list(argv) + ["--json"])
    return code, json.loads(out)


class LaunchdCase(HomeCase):
    """ROADMAP_HOME in a temp folder and ROADMAP_LAUNCH_AGENTS in a temp folder, both restored afterwards."""

    def setUp(self):
        super().setUp()
        self.agents = os.path.join(self.tmp, "LaunchAgents")
        self._saved_agents = os.environ.get(launchd.LAUNCH_AGENTS_ENV)
        os.environ[launchd.LAUNCH_AGENTS_ENV] = self.agents
        self.addCleanup(self._restore_agents)
        self.logs = os.path.join(self.tmp, "home", "logs")

    def _restore_agents(self):
        if self._saved_agents is None:
            os.environ.pop(launchd.LAUNCH_AGENTS_ENV, None)
        else:
            os.environ[launchd.LAUNCH_AGENTS_ENV] = self._saved_agents

    def use_runner(self, fake):
        """Make launchd.RUNNER the fake for the rest of the test, so commands never reach a real tool."""
        patcher = mock.patch.object(launchd, "RUNNER", fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        return fake

    def target(self):
        return launchd.service_target()

    def domain(self):
        return launchd.domain()
