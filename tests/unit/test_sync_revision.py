"""R7.50 (server half): one revision per project state, one cached build per revision.

Checks: loader.revision changes when a data file or the usage file changes and not otherwise; load_snapshot carries
rev (the revision) and usage; a second load at the same revision is a cache hit (no build); a changed file builds
again; now= never uses the cache; the route answers 304 for a matching revision without building. Runs in a temp
ROADMAP_HOME (ControlCase) with the registered project demo.
"""

import datetime
import json
import os
import unittest
from unittest import mock

from roadmap.http import routes
from roadmap.services import loader
from roadmap.store import paths
from tests.unit.test_control_support import ControlCase, write_json


class _Req:
    """A request stand-in: headers plus the raw query string (the snapshot route reads ?since=, R7.x 53952bc)."""

    def __init__(self, if_none_match=None, query=""):
        self.headers = {"If-None-Match": if_none_match} if if_none_match else {}
        self.query = query


class RevisionCase(ControlCase):
    def setUp(self):
        super().setUp()
        self.tasks = os.path.join(self.docs, "tasks.json")
        loader._CACHE.clear()

    def build_count(self):
        return self._build_mock.call_count

    def start_counting(self):
        patcher = mock.patch.object(loader, "_build", wraps=loader._build)
        self._build_mock = patcher.start()
        self.addCleanup(patcher.stop)

    def edit_tasks(self):
        with open(self.tasks, encoding="utf-8") as fh:
            data = json.load(fh)
        data["tasks"] = data.get("tasks", []) + [{"id": "T-extra", "title": "extra", "state": "todo"}]
        write_json(self.tasks, data)


class RevisionTests(RevisionCase):
    def test_revision_is_stable_when_nothing_changes(self):
        first = loader.project_revision("demo")
        self.assertEqual(first, loader.project_revision("demo"))
        self.assertEqual(len(first), 16)

    def test_revision_changes_when_a_data_file_changes(self):
        before = loader.project_revision("demo")
        self.edit_tasks()
        self.assertNotEqual(before, loader.project_revision("demo"))

    def test_revision_changes_when_the_usage_file_appears(self):
        before = loader.project_revision("demo")
        write_json(paths.usage_file(), {"weeklyPercent": 12, "updated": "2026-10-15T10:00:00+00:00"})
        self.assertNotEqual(before, loader.project_revision("demo"))

    def test_revision_covers_the_head_file_even_when_absent_before(self):
        before = loader.project_revision("demo")
        with open(os.path.join(self.docs, "head.jsonl"), "w", encoding="utf-8") as fh:
            fh.write("")
        self.assertNotEqual(before, loader.project_revision("demo"))

    def test_revision_of_no_folder_still_hashes_usage_and_control(self):
        self.assertEqual(len(loader.revision(None, "demo")), 16)


class SnapshotRevisionTests(RevisionCase):
    def test_snapshot_carries_rev_and_usage(self):
        snap = loader.load_snapshot("demo")
        self.assertEqual(snap["rev"], loader.project_revision("demo"))
        self.assertIsInstance(snap["usage"], dict)
        for key in ("stale", "ageS", "updated"):
            self.assertIn(key, snap["usage"])

    def test_same_revision_is_a_cache_hit(self):
        self.start_counting()
        loader.load_snapshot("demo")
        loader.load_snapshot("demo")
        self.assertEqual(self.build_count(), 1)

    def test_a_changed_file_builds_once_more(self):
        self.start_counting()
        first = loader.load_snapshot("demo")
        self.edit_tasks()
        second = loader.load_snapshot("demo")
        self.assertEqual(self.build_count(), 2)
        self.assertNotEqual(first["rev"], second["rev"])

    def test_cache_hit_refreshes_server_time_and_usage(self):
        first = loader.load_snapshot("demo")
        self.start_counting()
        later = loader.load_snapshot("demo")
        self.assertEqual(self.build_count(), 0)
        self.assertGreaterEqual(later["server_time"], first["server_time"])
        self.assertIn("stale", later["usage"])

    def test_now_argument_always_builds_and_does_not_cache(self):
        self.start_counting()
        moment = datetime.datetime(2026, 10, 13, 14, 2).astimezone()
        loader.load_snapshot("demo", now=moment)
        loader.load_snapshot("demo", now=moment)
        self.assertEqual(self.build_count(), 2)
        self.assertNotIn("demo", loader._CACHE)

    def test_snapshot_reply_is_304_without_a_build(self):
        rev = loader.project_revision("demo")
        loader._CACHE.clear()
        self.start_counting()
        reply = routes._snapshot_reply(_Req('"%s"' % rev), "demo")
        self.assertEqual(reply.status, 304)
        self.assertEqual(self.build_count(), 0)

    def test_snapshot_reply_etag_is_the_snapshot_rev(self):
        reply = routes._snapshot_reply(_Req(), "demo")
        self.assertEqual(reply.status, 200)
        header = dict(reply.headers)["ETag"]
        self.assertEqual(header, '"%s"' % json.loads(reply.body)["rev"])

    def test_projects_etag_is_the_joined_revisions(self):
        reply = routes.projects(None, _Req(), None)
        self.assertEqual(dict(reply.headers)["ETag"], '"%s"' % loader.project_revision("demo"))
        again = routes.projects(None, _Req('"%s"' % loader.project_revision("demo")), None)
        self.assertEqual(again.status, 304)


if __name__ == "__main__":
    unittest.main()
