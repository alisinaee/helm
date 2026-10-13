"""Shared base for store tests: every test gets its own ROADMAP_HOME under a temp dir, and HOME is restored."""

import os
import shutil
import stat
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def mode_of(path):
    """Return the permission bits of path, e.g. 0o600."""
    return stat.S_IMODE(os.stat(path).st_mode)


class HomeCase(unittest.TestCase):
    """Points ROADMAP_HOME (and HOME) at a temp directory so the real home is never touched."""

    def setUp(self):
        self._saved = {key: os.environ.get(key) for key in ("ROADMAP_HOME", "HOME")}
        self.tmp = tempfile.mkdtemp(prefix="rb-store-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.addCleanup(self._restore_env)
        os.environ["ROADMAP_HOME"] = os.path.join(self.tmp, "home")
        os.environ["HOME"] = os.path.join(self.tmp, "fakehome")

    def _restore_env(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def make_project(self, name="demo"):
        """Create an existing project folder and return its absolute path."""
        path = os.path.join(self.tmp, "projects", name)
        os.makedirs(path, exist_ok=True)
        return path
