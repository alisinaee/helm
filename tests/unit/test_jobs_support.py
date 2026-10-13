"""Shared fixture for the job and hook tests: a temp ROADMAP_HOME with one registered project (id demo).

The project folder has docs/tasks.json (P0.8, WP4) and docs/roadmap.config.json. Nothing touches the real home.
"""

import contextlib
import io
import json
import os
from unittest import mock

from roadmap.cli import main
from roadmap.store import config
from tests.unit.test_store_support import HomeCase

PROJECT_ID = "demo"
TASKS = {
    "schemaVersion": 1,
    "tasks": [
        {"id": "P0.8", "phase": "P0", "title": "Parser", "status": "todo"},
        {"id": "WP4", "phase": "P0", "title": "Jobs and hooks", "status": "todo"},
    ],
}
ROADMAP_CONFIG = {
    "schemaVersion": 1,
    "id": PROJECT_ID,
    "title": "Demo",
    "taskIdPattern": r"^[A-Z]+[0-9]+(\.[0-9]+)?$",
    "hookDetectors": ["agent", "agy", "cursor"],
}


def write_json(path, obj):
    """Write a JSON fixture file, creating its folder."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2)
        fh.write("\n")


def run_cli(argv, stdin_text=None):
    """Run the CLI in-process and return (exit code, stdout, stderr). stdin is replaced when stdin_text is given."""
    out = io.StringIO()
    err = io.StringIO()
    stdin = io.StringIO(stdin_text if stdin_text is not None else "")
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        if stdin_text is None:
            code = main(argv)
        else:
            with mock.patch("sys.stdin", stdin):
                code = main(argv)
    return code, out.getvalue(), err.getvalue()


class FixtureCase(HomeCase):
    """A registered fixture project with ROADMAP_PROJECT pointing at it."""

    def setUp(self):
        super().setUp()
        self.project = self.make_project(PROJECT_ID)
        self.docs = os.path.join(self.project, "docs")
        write_json(os.path.join(self.docs, "tasks.json"), TASKS)
        write_json(os.path.join(self.docs, "roadmap.config.json"), ROADMAP_CONFIG)
        config.add_project("Demo", self.project)
        self._set_env("ROADMAP_PROJECT", PROJECT_ID)

    def _set_env(self, key, value):
        saved = os.environ.get(key)

        def restore():
            if saved is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = saved

        self.addCleanup(restore)
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value

    def jobs_file(self):
        return os.path.join(self.docs, "jobs.json")

    def write_jobs(self, obj):
        write_json(self.jobs_file(), obj)

    def read_jobs(self):
        """The job list as stored, or [] when jobs.json does not exist yet."""
        if not os.path.exists(self.jobs_file()):
            return []
        with open(self.jobs_file(), encoding="utf-8") as fh:
            return json.load(fh)["jobs"]

    def log_text(self):
        path = os.path.join(os.environ["ROADMAP_HOME"], "logs", "hooks.log")
        if not os.path.exists(path):
            return ""
        with open(path, encoding="utf-8") as fh:
            return fh.read()

