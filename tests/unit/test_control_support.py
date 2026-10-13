"""Shared fixture for the WP22 tests: a temp ROADMAP_HOME with one registered project (id demo) that has phases,
tasks with caps, and a budget file the tests fill in. Nothing touches the real home, the real projects or ~/.claude."""

import json
import os

from roadmap.store import config
from tests.unit.test_store_support import HomeCase

TASKS = {
    "schemaVersion": 1,
    "updated": "",
    "phases": [{"id": "P0", "name": "Core"}, {"id": "P1", "name": "Next"}],
    "tasks": [
        {"id": "P0.1", "phase": "P0", "title": "Parser", "status": "todo", "capK": 50},
        {"id": "P0.2", "phase": "P0", "title": "Writer", "status": "todo"},
        {"id": "P1.1", "phase": "P1", "title": "Later", "status": "todo"},
    ],
}
ROADMAP_CONFIG = {"schemaVersion": 1, "id": "demo", "title": "Demo", "hookDetectors": []}


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2)
        fh.write("\n")


def read_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


class ControlCase(HomeCase):
    def setUp(self):
        super().setUp()
        self.project = self.make_project("demo")
        self.docs = os.path.join(self.project, "docs")
        write_json(os.path.join(self.docs, "tasks.json"), TASKS)
        write_json(os.path.join(self.docs, "roadmap.config.json"), ROADMAP_CONFIG)
        write_json(os.path.join(self.docs, "autonomy.json"), {"schemaVersion": 2, "limit": {"kind": "weekly",
                                                                                          "stopAtPercent": 100}})
        config.add_project("Demo", self.project)
        self._env("ROADMAP_PROJECT", "demo")
        self._env("CLAUDECODE", None)

    def _env(self, key, value):
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

    @property
    def state_dir(self):
        return os.path.join(os.environ["ROADMAP_HOME"], "state")

    def sentinel_exists(self):
        return os.path.exists(os.path.join(self.state_dir, "block-demo"))

    def control(self):
        path = os.path.join(self.state_dir, "control-demo.json")
        return read_json(path) if os.path.exists(path) else None

    def set_budget(self, limits=None, spent=None):
        write_json(os.path.join(self.docs, "budget.json"), {
            "schemaVersion": 1,
            "limits": dict({"project": None, "phases": {}, "models": {}, "tasks": {}}, **(limits or {})),
            "spent": spent or {},
            "jobs": [],
        })

    def set_usage(self, weekly):
        write_json(os.path.join(self.state_dir, "usage.json"), {"schemaVersion": 1, "weeklyPercent": weekly})

    def read_tasks(self):
        return read_json(os.path.join(self.docs, "tasks.json"))
