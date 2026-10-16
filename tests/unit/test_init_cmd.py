"""Tests for R10.11: roadmap init sets a project up in one idempotent step. launchd and hooks are faked."""

import json
import os
from unittest import mock

from roadmap.services import hooks_install, launchd
from roadmap.store import config
from tests.unit.test_jobs_support import run_cli
from tests.unit.test_store_support import HomeCase


class InitTests(HomeCase):
    def setUp(self):
        super().setUp()
        self.project = self.make_project("fresh")
        self.hooks = mock.Mock(return_value={"changed": True})
        self.state = {"plistInstalled": False, "loaded": False}
        self.install = mock.Mock(side_effect=lambda: self.state.update(plistInstalled=True))
        self.start = mock.Mock(side_effect=lambda: self.state.update(loaded=True))
        for target, fake in ((hooks_install, ("install", self.hooks)), (launchd, ("install", self.install)),
                             (launchd, ("start", self.start)),
                             (launchd, ("status", lambda: dict(self.state)))):
            patch = mock.patch.object(target, fake[0], fake[1])
            patch.start()
            self.addCleanup(patch.stop)

    def read(self, path):
        with open(path) as fh:
            return fh.read()

    def run_init(self, *extra):
        code, out = run_cli(["init", self.project, "--json"] + list(extra))[:2]
        return code, out

    def test_sets_up_and_is_idempotent(self):
        code, out = self.run_init()
        self.assertEqual(code, 0, out)
        self.assertIn("fresh", [p["id"] for p in config.list_projects()])
        docs = os.path.join(self.project, "docs")
        with open(os.path.join(docs, "tasks.json")) as fh:
            tasks = json.load(fh)
        self.assertEqual((tasks["phases"], tasks["tasks"]), ([], []))
        with open(os.path.join(docs, "work.json")) as fh:
            self.assertEqual(json.load(fh)["items"], [])
        self.assertEqual(self.hooks.call_count, 1)
        self.assertEqual((self.install.call_count, self.start.call_count), (1, 1))
        before = self.read(os.path.join(docs, "tasks.json"))
        code, out = self.run_init()
        self.assertEqual(code, 0, out)
        self.assertEqual(len(config.list_projects()), 1)
        self.assertEqual(self.read(os.path.join(docs, "tasks.json")), before)
        self.assertEqual((self.install.call_count, self.start.call_count), (1, 1))

    def test_no_service(self):
        code, out = self.run_init("--no-service")
        self.assertEqual(code, 0, out)
        self.assertEqual((self.install.call_count, self.start.call_count), (0, 0))
