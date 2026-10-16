"""R10.2: the list rows carry the first characters of the person's text and of the head's reply. The service reads
head-text.jsonl once for a page (previews_of); the paged route adds them on the same-origin page only, never to the
phone listener or a cross-origin read. Runs in temp ROADMAP_HOME folders and on an ephemeral port (ServerCase)."""

import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from roadmap.services import head as svc
from tests.api.support import PROJECT_ID, ServerCase

BASE = datetime(2026, 10, 15, 10, 0, tzinfo=timezone.utc)
LONG = "Please check the board export and the snapshot pages, " * 4


class PreviewService(unittest.TestCase):
    def setUp(self):
        self._saved_home = os.environ.get("ROADMAP_HOME")
        self.root = tempfile.mkdtemp(prefix="head-previews-")
        os.environ["ROADMAP_HOME"] = os.path.join(self.root, "home")
        self.data = os.path.join(self.root, "docs")
        os.makedirs(self.data)

    def tearDown(self):
        if self._saved_home is None:
            os.environ.pop("ROADMAP_HOME", None)
        else:
            os.environ["ROADMAP_HOME"] = self._saved_home
        shutil.rmtree(self.root, ignore_errors=True)

    def test_text_and_reply_previews_are_short_and_cut_with_an_ellipsis(self):
        out = svc.capture(self.data, LONG, src="cli", now=BASE, timeout=5)
        svc.set_reply(self.data, out["id"], "Done.  The export\n is fixed.", timeout=5)
        got = svc.previews_of(self.data, [out["id"]])[out["id"]]
        self.assertTrue(got["text"].endswith("…"))
        self.assertLessEqual(len(got["text"]), svc.PREVIEW_TEXT)
        self.assertTrue(got["text"].startswith("Please check the board export"))
        self.assertEqual(got["reply"], "Done. The export is fixed.")

    def test_missing_text_and_reply_are_none_and_unknown_ids_are_left_out(self):
        out = svc.capture(self.data, "short ask", src="cli", now=BASE, timeout=5)
        got = svc.previews_of(self.data, [out["id"], "H999"])
        self.assertEqual(got[out["id"]], {"text": "short ask", "reply": None})
        self.assertEqual(got["H999"], {"text": None, "reply": None})

    def test_no_ids_reads_nothing(self):
        self.assertEqual(svc.previews_of(self.data, []), {})


class PreviewRoute(ServerCase):
    def setUp(self):
        super().setUp()
        self.data = os.path.join(self.project_root, "docs")
        out = svc.capture(self.data, "Hook budget stays at 0.3 s", src="cli", now=BASE, timeout=5)
        svc.set_reply(self.data, out["id"], "Kept at 0.3 s.", timeout=5)
        self.path = "/api/v1/projects/%s/head?f=all&offset=0&limit=5" % PROJECT_ID

    def test_the_same_origin_page_gets_the_previews(self):
        res = self.request("GET", self.path, headers={"Sec-Fetch-Site": "same-origin"})
        self.assertEqual(res.status, 200, res.body[:200])
        row = res.json()["rows"][0]
        self.assertEqual(row["preview"], "Hook budget stays at 0.3 s")
        self.assertEqual(row["replyPreview"], "Kept at 0.3 s.")

    def test_a_cross_origin_read_gets_no_text(self):
        res = self.request("GET", self.path, headers={"Sec-Fetch-Site": "cross-site"})
        self.assertEqual(res.status, 200)
        row = res.json()["rows"][0]
        self.assertNotIn("preview", row)
        self.assertNotIn("replyPreview", row)


if __name__ == "__main__":
    unittest.main()
