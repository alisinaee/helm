"""Tests for schema versions: newer files are refused and never overwritten, the autonomy v1 to v2 migration."""

import json
import os
import unittest

from roadmap.errors import RoadmapError
from roadmap.store import atomic, migrations, schema
from tests.unit.test_store_support import HomeCase, mode_of


def _write(path, data):
    atomic.write_json(path, data)
    with open(path, "rb") as fh:
        return fh.read()


class NewerSchemaTests(HomeCase):
    def setUp(self):
        super().setUp()
        self.path = os.path.join(self.tmp, "docs", "autonomy.json")
        self.raw = _write(self.path, {"schemaVersion": 3, "limit": {"stopAtPercent": 72}})

    def test_read_reports_newer_schema_entry_and_returns_no_data(self):
        data, error = schema.read_data("autonomy", self.path)
        self.assertIsNone(data)
        self.assertEqual(error["code"], "newer_schema")
        self.assertEqual(error["path"], self.path)

    def test_write_refuses_newer_file_and_keeps_bytes(self):
        with self.assertRaises(RoadmapError) as cm:
            schema.write_data("autonomy", self.path, {"limit": {}})
        self.assertEqual(cm.exception.code, "newer_schema")
        self.assertEqual(cm.exception.exit, 5)
        with open(self.path, "rb") as fh:
            self.assertEqual(fh.read(), self.raw)

    def test_unknown_data_kind_is_refused(self):
        with self.assertRaises(RoadmapError):
            schema.read_data("nope", self.path)


class MigrationTests(HomeCase):
    def setUp(self):
        super().setUp()
        self.path = os.path.join(self.tmp, "docs", "autonomy.json")
        self.v1 = {
            "limit": {"kind": "weekly", "stopAtPercent": 72},
            "usage": {"weeklyPercent": 63, "fiveHourPercent": 26, "updated": "2026-10-13T17:30:03+0330"},
        }
        self.raw = _write(self.path, self.v1)  # no schemaVersion: counts as v1

    def test_v1_upgrades_in_memory_to_v2_keeping_only_limit(self):
        data, error = schema.read_data("autonomy", self.path)
        self.assertIsNone(error)
        self.assertEqual(data, {"schemaVersion": 2, "limit": self.v1["limit"]})

    def test_read_never_writes_the_file(self):
        schema.read_data("autonomy", self.path)
        with open(self.path, "rb") as fh:
            self.assertEqual(fh.read(), self.raw)

    def test_split_usage_returns_the_usage_block_for_the_global_store(self):
        upgraded, usage = migrations.split_usage(self.v1)
        self.assertEqual(usage, self.v1["usage"])
        self.assertEqual(upgraded, {"schemaVersion": 2, "limit": self.v1["limit"]})

    def test_write_saves_the_newest_version(self):
        data, _ = schema.read_data("autonomy", self.path)
        schema.write_data("autonomy", self.path, data)
        with open(self.path, encoding="utf-8") as fh:
            saved = json.load(fh)
        self.assertEqual(saved["schemaVersion"], 2)
        self.assertNotIn("usage", saved)
        self.assertEqual(mode_of(self.path), 0o600)

    def test_missing_step_is_an_error(self):
        with self.assertRaises(RoadmapError) as cm:
            migrations.upgrade("tasks", {"x": 1}, 1, 3)
        self.assertEqual(cm.exception.code, "invalid_data")

    def test_schema_version_must_be_a_whole_number(self):
        _write(self.path, {"schemaVersion": "two"})
        with self.assertRaises(RoadmapError) as cm:
            schema.read_data("autonomy", self.path)
        self.assertEqual(cm.exception.code, "invalid_data")


if __name__ == "__main__":
    unittest.main()
