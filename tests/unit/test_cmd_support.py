"""Shared base for the WP21 command tests: a temp ROADMAP_HOME, a project named demo with a small plan, and CLI helpers.

Nothing here touches the real home, the real projects, the network or the keychain.
"""

import datetime
import json
import os

from roadmap.services import commands
from tests.unit.test_project_support import ProjectCase, run_cli

PLAN = """P P1 todo | Engine
T P1.1 todo 20 haiku/low | First task
T P1.2 todo 10 sonnet/medium | Second task
T P1.3 todo 5 haiku/low ! | Needs a login
P P2 todo | Surface
T P2.1 todo 30 opus/high | Third task
"""

T0 = datetime.datetime(2026, 10, 13, 9, 0, 0, tzinfo=datetime.timezone.utc)


def at(seconds):
    return T0 + datetime.timedelta(seconds=seconds)


class CmdCase(ProjectCase):
    """A project demo with the PLAN imported. cli() adds --project demo; op() runs the command layer directly."""

    def setUp(self):
        super().setUp()
        self.init_and_add()
        self.plan_file = os.path.join(self.tmp, "plan.txt")
        with open(self.plan_file, "w", encoding="utf-8") as fh:
            fh.write(PLAN)
        code, _, err = run_cli(["plan", "import", self.plan_file, "--project", "demo"])
        assert code == 0, err

    def cli(self, argv):
        """Run the CLI for project demo and return (exit code, stdout, stderr)."""
        return run_cli(list(argv) + ["--project", "demo"])

    def envelope(self, argv):
        """Run with --json and return (exit code, parsed envelope)."""
        code, out, _ = self.cli(list(argv) + ["--json"])
        return code, json.loads(out)

    def op(self, name, args, now=None):
        """Run one op through the command layer, as the CLI does (source cli)."""
        return commands.run(name, args, "cli", self.data, now=now)

    def read_lines(self, name):
        path = os.path.join(self.data, name)
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]

    def read_json(self, name):
        with open(os.path.join(self.data, name), encoding="utf-8") as fh:
            return json.load(fh)
