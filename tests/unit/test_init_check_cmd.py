"""Tests for `roadmap init`: read-only --check, idempotent init and the never-overwritten project skill."""

import json
import os
from unittest import mock

from roadmap.commands import init as init_cmd
from roadmap.store import config
from tests.unit.test_jobs_support import run_cli
from tests.unit.test_store_support import HomeCase


def tree(root):
    """Every file path under root, relative and sorted."""
    return sorted(os.path.relpath(os.path.join(d, f), root) for d, _, fs in os.walk(root) for f in fs)


class InitCmdTest(HomeCase):
    def setUp(self):
        super().setUp()
        self.proj = self.make_project("newp")
        template = os.path.join(self.tmp, "SKILL.md")
        with open(template, "w", encoding="utf-8") as fh:
            fh.write("template\n")
        patcher = mock.patch.object(init_cmd, "SKILL_TEMPLATE", template)
        patcher.start()
        self.addCleanup(patcher.stop)

    def init(self):
        return run_cli(["init", self.proj, "--no-service", "--json"])

    def test_check_writes_and_registers_nothing(self):
        before = tree(self.tmp)
        code, out, _ = run_cli(["init", self.proj, "--check", "--json"])
        self.assertEqual(code, 0)
        text = out[out.index("{"):]
        data = json.loads(text)["data"]
        self.assertFalse(data["registered"])
        self.assertFalse(data["skill"])
        self.assertEqual(data["dataFiles"], [])
        self.assertEqual(tree(self.tmp), before)
        self.assertEqual(config.list_projects(), [])

    def test_init_twice_is_idempotent(self):
        self.assertEqual(self.init()[0], 0)
        first = tree(self.proj)
        self.assertIn(os.path.join(".claude", "skills", "helm", "SKILL.md"), first)
        self.assertEqual(self.init()[0], 0)
        self.assertEqual(tree(self.proj), first)
        self.assertEqual(len(config.list_projects()), 1)
        code, out, _ = run_cli(["init", self.proj, "--check", "--json"])
        data = json.loads(out)["data"]
        self.assertTrue(data["registered"])
        self.assertTrue(data["skill"])
        self.assertIn("tasks.json", data["dataFiles"])

    def test_existing_skill_not_overwritten(self):
        target = os.path.join(self.proj, ".claude", "skills", "helm", "SKILL.md")
        os.makedirs(os.path.dirname(target))
        with open(target, "w", encoding="utf-8") as fh:
            fh.write("mine\n")
        self.assertEqual(self.init()[0], 0)
        with open(target, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "mine\n")
