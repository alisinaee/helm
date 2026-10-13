"""Shared helpers for the WP10 tests: a temp ROADMAP_HOME, a project folder and in-process CLI runs.

Nothing here touches the real home, the real projects or the network.
"""

import contextlib
import io
import json
import os

from roadmap.cli import main
from tests.unit.test_store_support import HomeCase

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(os.path.abspath(__file__)))))
SHIM = os.path.join(REPO, "bin", "roadmap")
HOOK_CMD = SHIM + " hook"


def run_cli(argv):
    """Run the CLI in-process and return (exit code, stdout, stderr)."""
    out = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


def read_text(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2)
        fh.write("\n")


class ProjectCase(HomeCase):
    """A ROADMAP_HOME with a project folder named demo (not yet initialised or registered)."""

    def setUp(self):
        super().setUp()
        self.folder = self.make_project("demo")
        self.data = os.path.join(self.folder, "docs")

    def init_and_add(self, folder=None, name=None):
        """Run project init and project add for a folder (default: demo). Returns the json data of add."""
        folder = folder or self.folder
        code, _, err = run_cli(["project", "init", folder])
        assert code == 0, err
        argv = ["project", "add", folder, "--json"]
        if name:
            argv += ["--name", name]
        code, out, err = run_cli(argv)
        assert code == 0, err
        return json.loads(out)["data"]["project"]

    def envelope(self, argv):
        """Run a command with --json and return (exit code, parsed envelope)."""
        code, out, _ = run_cli(argv + ["--json"])
        return code, json.loads(out)

    def settings_path(self, folder=None):
        return os.path.join(folder or self.folder, ".claude", "settings.local.json")
