"""R7.44: the paged read of the full head ledger. Checks the service page() (newest first, numeric id tie-break,
scope f=open and f=all, counts over the whole ledger, accepted ids), the query parser (offset and limit bounds), and
the route GET /api/v1/projects/<slug>/head?offset=&limit=&f= (total, rows in the snapshot row shape, deduped ids,
paging to the end). Runs in temp ROADMAP_HOME folders and on an ephemeral port (ServerCase)."""

import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from roadmap.errors import RoadmapError
from roadmap.http import routes
from roadmap.services import head as svc
from tests.api.support import PROJECT_ID, ServerCase

BASE = datetime(2026, 10, 15, 10, 0, tzinfo=timezone.utc)


def _capture(data_dir, n, minutes_offset=None, text=None):
    """Log message n. Each one gets its own minute unless minutes_offset says otherwise."""
    when = BASE + timedelta(minutes=n if minutes_offset is None else minutes_offset)
    return svc.capture(data_dir, text or ("ask number %d: please check item %d" % (n, n)), src="cli", now=when,
                       timeout=5)


class PageService(unittest.TestCase):
    def setUp(self):
        self._saved_home = os.environ.get("ROADMAP_HOME")
        self.root = tempfile.mkdtemp(prefix="head-paging-")
        os.environ["ROADMAP_HOME"] = os.path.join(self.root, "home")
        self.data = os.path.join(self.root, "docs")
        os.makedirs(self.data)

    def tearDown(self):
        if self._saved_home is None:
            os.environ.pop("ROADMAP_HOME", None)
        else:
            os.environ["ROADMAP_HOME"] = self._saved_home
        shutil.rmtree(self.root, ignore_errors=True)

    def test_pages_walk_the_whole_ledger_newest_first(self):
        ids = [_capture(self.data, n)["id"] for n in range(1, 8)]
        seen = []
        offset = 0
        while True:
            page = svc.page(self.data, f="all", offset=offset, limit=3)
            self.assertEqual(page["total"], 7)
            if not page["rows"]:
                break
            seen.extend(e["id"] for e in page["rows"])
            offset += 3
        self.assertEqual(seen, list(reversed(ids)))

    def test_ties_on_ts_break_on_the_numeric_id(self):
        same = BASE + timedelta(minutes=5)
        for n in range(1, 4):
            svc.capture(self.data, "same minute message %d" % n, src="cli", now=same, timeout=5)
        page = svc.page(self.data, f="all", offset=0, limit=10)
        self.assertEqual([e["id"] for e in page["rows"]], ["H3", "H2", "H1"])

    def test_open_scope_leaves_out_closed_rows_and_counts_the_whole_ledger(self):
        for n in range(1, 61):
            _capture(self.data, n)
        svc.update(self.data, "H1", by="person", sets={"status": "done"}, now=BASE + timedelta(hours=2))
        page = svc.page(self.data, f="open", offset=0, limit=50)
        self.assertEqual(page["total"], 59)
        self.assertEqual(len(page["rows"]), 50)
        self.assertEqual(page["rows"][0]["id"], "H60")
        self.assertEqual(page["counts"]["open"], 59)
        self.assertEqual(page["counts"]["doneUnacc"], 0)  # H1 is done by the person: accepted
        second = svc.page(self.data, f="open", offset=50, limit=50)["rows"]
        self.assertEqual((second[0]["id"], second[-1]["id"]), ("H10", "H2"))

    def test_offset_past_the_end_is_an_empty_page_with_the_total(self):
        _capture(self.data, 1)
        page = svc.page(self.data, f="all", offset=40, limit=50)
        self.assertEqual(page["rows"], [])
        self.assertEqual(page["total"], 1)

    def test_accepted_ids_follow_the_person_done_rule(self):
        _capture(self.data, 1)
        self.assertEqual(svc.page(self.data, f="all")["accepted"], set())
        svc.update(self.data, "H1", by="person", sets={"status": "done"}, now=BASE + timedelta(hours=1))
        self.assertEqual(svc.page(self.data, f="all")["accepted"], {"H1"})


class QueryParsing(unittest.TestCase):
    def test_offset_and_limit_defaults_and_bounds(self):
        self.assertEqual(routes._head_page_query(""), (0, routes.HEAD_LIMIT_DEFAULT))
        self.assertEqual(routes._head_page_query("offset=50&limit=200"), (50, 200))
        for bad in ("offset=-1", "offset=x", "offset=1000001", "limit=0", "limit=201", "limit=ten"):
            with self.assertRaises(RoadmapError, msg=bad):
                routes._head_page_query(bad)

    def test_paged_mode_only_when_offset_or_limit_is_given(self):
        self.assertTrue(routes._head_is_paged("offset=0"))
        self.assertTrue(routes._head_is_paged("f=all&limit=10"))
        self.assertFalse(routes._head_is_paged("f=all&n=100"))
        self.assertFalse(routes._head_is_paged(""))

    def test_the_query_keys_are_checked(self):
        f, n, full = routes._head_query("f=all&offset=5&limit=10")
        self.assertEqual((f, full), ("all", None))
        with self.assertRaises(RoadmapError):
            routes._head_query("f=all&page=2")


class PagedRoute(ServerCase):
    def setUp(self):
        super().setUp()
        self.data = os.path.join(self.project_root, "docs")
        for n in range(1, 66):
            _capture(self.data, n)

    def page(self, query):
        res = self.request("GET", "/api/v1/projects/%s/head?%s" % (PROJECT_ID, query))
        self.assertEqual(res.status, 200, res.body[:200])
        return res.json()

    def test_pages_cover_every_row_once_with_the_full_total(self):
        ids = []
        offset = 0
        while True:
            body = self.page("f=all&offset=%d&limit=20" % offset)
            self.assertEqual(body["total"], 65)
            self.assertEqual(body["limit"], 20)
            if not body["rows"]:
                break
            ids.extend(row["id"] for row in body["rows"])
            offset += 20
        self.assertEqual(ids, ["H%d" % n for n in range(65, 0, -1)])
        self.assertEqual(len(set(ids)), 65)

    def test_rows_have_the_snapshot_row_shape(self):
        row = self.page("f=open&offset=0&limit=1")["rows"][0]
        for key in ("id", "kind", "sum", "status", "age", "ts"):
            self.assertIn(key, row)
        self.assertEqual(row["id"], "H65")

    def test_counts_come_from_the_whole_ledger(self):
        body = self.page("f=open&offset=0&limit=1")
        self.assertEqual(body["counts"]["open"], 65)

    def test_bad_paging_is_a_400(self):
        res = self.request("GET", "/api/v1/projects/%s/head?offset=-3" % PROJECT_ID)
        self.assertEqual(res.status, 400)

    def test_the_old_n_read_still_works(self):
        res = self.request("GET", "/api/v1/projects/%s/head?f=all&n=5" % PROJECT_ID)
        self.assertEqual(res.status, 200)
        self.assertEqual(len(res.json()["rows"]), 5)


if __name__ == "__main__":
    unittest.main()
