"""R7.53 regressions from docs/reviews/cursor-commits-review.md: an umbrella-only bind is refused by head.set and
head.review (the same rule as head.bind), and the bind suggestion never offers an umbrella task alone. Pure: the
store and the person check are patched, no file is written."""

import unittest
from unittest import mock

from roadmap.core import head
from roadmap.errors import RoadmapError
from roadmap.services import headops

TASKS = [{"id": "R7.31", "title": "Head section design"}, {"id": "R7.40", "title": "Export button map"}]


def _row(status, links):
    return {"id": "H5", "status": status, "links": links, "manual": None}


class UmbrellaBindGuards(unittest.TestCase):
    def setUp(self):
        self.person = mock.patch.object(headops, "_person_only")
        self.person.start()
        self.guard = mock.patch.object(headops, "_guard_status")
        self.guard.start()
        self.update = mock.patch.object(headops.store, "update")
        self.store_update = self.update.start()

    def tearDown(self):
        mock.patch.stopall()

    def test_set_to_needs_you_refused_when_only_bound_to_umbrella(self):
        with mock.patch.object(headops, "_row", return_value=_row("done", ["task:R7.31"])):
            with self.assertRaises(RoadmapError):
                headops._h_set("/tmp/unused", {"id": "H5", "status": "needs-you", "kind": None, "sum": None,
                                               "note": None}, None)
        self.store_update.assert_not_called()

    def test_set_to_needs_you_allowed_with_a_real_task_bound(self):
        with mock.patch.object(headops, "_row", return_value=_row("done", ["task:R7.31", "task:R7.40"])):
            headops._h_set("/tmp/unused", {"id": "H5", "status": "needs-you", "kind": None, "sum": None,
                                           "prio": None, "note": None}, None)
        self.store_update.assert_called_once()

    def test_review_reopen_refused_when_only_bound_to_umbrella(self):
        with mock.patch.object(headops, "_row", return_value=_row("done", ["task:R7.31"])):
            with self.assertRaises(RoadmapError):
                headops._h_review("/tmp/unused", {"id": "H5", "action": "reopen"}, None)
        self.store_update.assert_not_called()

    def test_review_confirm_is_not_a_bind_check(self):
        with mock.patch.object(headops, "_row", return_value=_row("open", ["task:R7.31"])):
            headops._h_review("/tmp/unused", {"id": "H5", "action": "confirm"}, None)
        self.store_update.assert_called_once()


class UmbrellaSuggestion(unittest.TestCase):
    def test_umbrella_alone_is_not_suggested(self):
        self.assertEqual(head.suggest_binds("ship R7.31 today", TASKS, []), [])

    def test_umbrella_kept_next_to_a_real_task(self):
        self.assertEqual(head.suggest_binds("ship R7.31 and the R7.40 export", TASKS, []),
                         ["task:R7.31", "task:R7.40"])


if __name__ == "__main__":
    unittest.main()
