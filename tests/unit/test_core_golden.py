"""Golden test: the split-net fixture through core.snapshot must equal the old server's build() output.

The golden file was captured once from split_net/tools/roadmap-web/server.py (see changes/WP3.md).
Only three keys are additive and left out of the comparison: server_time, project and schemaVersion.
"""

import json
import os
import unittest
from datetime import datetime, timezone

from roadmap.core.snapshot import build_snapshot

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(TESTS, "fixtures")
SPLITNET = os.path.join(FIXTURES, "splitnet")
GOLDEN = os.path.join(FIXTURES, "golden_snapshot.json")
PINNED_NOW = datetime(2026, 10, 13, 12, 0, 0, tzinfo=timezone.utc)
ADDITIVE_KEYS = ("server_time", "project", "schemaVersion")


def load_fixture():
    """The fixture's data files as name -> text, and its parsed roadmap.config.json."""
    files = {}
    for name in sorted(os.listdir(SPLITNET)):
        if name != "roadmap.config.json":
            with open(os.path.join(SPLITNET, name), encoding="utf-8") as fh:
                files[name] = fh.read()
    with open(os.path.join(SPLITNET, "roadmap.config.json"), encoding="utf-8") as fh:
        config = json.load(fh)
    return files, config


class GoldenSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.files, self.config = load_fixture()
        with open(GOLDEN, encoding="utf-8") as fh:
            self.golden = json.load(fh)

    def test_matches_old_server_output(self):
        new = build_snapshot(self.files, self.config, PINNED_NOW)
        for key in ADDITIVE_KEYS:
            new.pop(key, None)
        self.assertEqual(set(new), set(self.golden))
        self.assertEqual(new, self.golden)

    def test_additive_keys_present(self):
        new = build_snapshot(self.files, self.config, PINNED_NOW)
        self.assertEqual(new["schemaVersion"], 1)
        self.assertEqual(new["project"], {"id": "splitnet", "title": "split-net"})
        self.assertEqual(new["server_time"], "2026-10-13T12:00:00+00:00")
        self.assertEqual(new["errors"], [])

    def test_missing_files_give_errors_not_exceptions(self):
        files = dict(self.files)
        files["tasks.json"] = None
        files["10-spike-results.md"] = None
        new = build_snapshot(files, self.config, PINNED_NOW)
        names = sorted(e["file"] for e in new["errors"])
        self.assertEqual(names, ["10-spike-results.md", "tasks.json"])
        self.assertEqual(new["tasks"], [])
        self.assertEqual(new["spikes"], [])


if __name__ == "__main__":
    unittest.main()
