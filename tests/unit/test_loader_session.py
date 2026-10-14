"""roadmap/services/loader.py passes the presence session and the project path into the snapshot, fail-open."""

import os
import sys
import tempfile
import unittest
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from roadmap.services import loader, presence  # noqa: E402


class LoaderSession(unittest.TestCase):

    def test_session_view_reads_presence_of_the_data_folder(self):
        with tempfile.TemporaryDirectory(prefix="rb-session-") as folder:
            self.assertEqual(loader._session_view(folder), presence.NONE)
            with mock.patch.object(presence, "state", return_value=presence.WATCHING) as state:
                self.assertEqual(loader._session_view(folder), presence.WATCHING)
            state.assert_called_once_with(folder)

    def test_presence_error_gives_none_so_the_key_is_omitted(self):
        with mock.patch.object(presence, "state", side_effect=RuntimeError("boom")):
            self.assertIsNone(loader._session_view("/nonexistent-folder"))

    def test_project_path_is_the_registered_root(self):
        self.assertEqual(loader._project_path({"path": "/work/proj", "dataDir": "docs"}), "/work/proj")
        self.assertIsNone(loader._project_path({}))
        self.assertIsNone(loader._project_path(None))


if __name__ == "__main__":
    unittest.main()
