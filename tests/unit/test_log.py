"""Tests for roadmap/log.py: the rotating server.log at 1 MB x 5 with mode 0600, the redaction filter, and the
access-log line (method, path without the query, status, ms)."""

import logging
import os
import shutil
import stat
import tempfile
import unittest
import uuid

from roadmap import log

SECRET = "SECRET-VALUE-123"


class LogCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="rb-log-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.logger = logging.getLogger("roadmap-test-" + uuid.uuid4().hex)
        self.logger.propagate = False
        self.logger.setLevel(logging.INFO)
        self.addCleanup(self._detach)

    def _detach(self):
        for handler in list(self.logger.handlers):
            self.logger.removeHandler(handler)
            handler.close()

    def mode(self, path):
        return stat.S_IMODE(os.stat(path).st_mode)

    def read(self, name):
        with open(os.path.join(self.tmp, name), "r", encoding="utf-8") as fh:
            return fh.read()


class RotationTests(LogCase):
    def test_server_log_rolls_over_at_one_megabyte(self):
        path = log.setup_file_logging(self.tmp, logger=self.logger)
        line = "x" * 999
        for _ in range(1500):  # about 1.5 MB in total
            self.logger.info(line)
        self.assertEqual(path, os.path.join(self.tmp, "server.log"))
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "server.log.1")))
        self.assertLessEqual(os.path.getsize(path), log.MAX_BYTES)

    def test_at_most_five_backups_are_kept(self):
        log.setup_file_logging(self.tmp, logger=self.logger)
        for _ in range(8000):  # about 8 MB, which would make a sixth backup
            self.logger.info("y" * 999)
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "server.log.5")))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "server.log.6")))

    def test_server_log_and_rolled_files_are_mode_0600(self):
        log.setup_file_logging(self.tmp, logger=self.logger)
        for _ in range(1200):
            self.logger.info("z" * 999)
        for name in ("server.log", "server.log.1"):
            self.assertEqual(self.mode(os.path.join(self.tmp, name)), 0o600, name)

    def test_setup_twice_adds_one_handler(self):
        log.setup_file_logging(self.tmp, logger=self.logger)
        log.setup_file_logging(self.tmp, logger=self.logger)
        files = [h for h in self.logger.handlers if getattr(h, "roadmap_file", None)]
        self.assertEqual(len(files), 1)


class RedactionTests(LogCase):
    def test_bearer_sk_ant_and_k_values_never_reach_the_file(self):
        log.setup_file_logging(self.tmp, logger=self.logger)
        self.logger.info("auth Bearer abc.def-GHI999 done")
        self.logger.info("key sk-ant-api03-%s end", SECRET)
        self.logger.info("GET /x?k=%s&y=1", SECRET)
        self.logger.info("bare k=%s", SECRET)
        text = self.read("server.log")
        self.assertNotIn("abc.def-GHI999", text)
        self.assertNotIn(SECRET, text)
        self.assertIn("Bearer [redacted]", text)
        self.assertIn("sk-ant-[redacted]", text)
        self.assertIn("k=[redacted]", text)

    def test_redact_function_on_plain_text(self):
        self.assertEqual(log.redact("Bearer tok1"), "Bearer [redacted]")
        self.assertEqual(log.redact("sk-ant-XYZ99"), "sk-ant-[redacted]")
        self.assertEqual(log.redact("/a?k=abc&b=2"), "/a?k=[redacted]")
        self.assertEqual(log.redact("nothing here"), "nothing here")


class AccessLineTests(unittest.TestCase):
    def test_line_has_method_path_status_and_ms_without_query(self):
        line = log.access_line("GET", "/api/v1/health?k=%s&x=1" % SECRET, 200, 12)
        self.assertEqual(line, "GET /api/v1/health 200 12ms")
        self.assertNotIn(SECRET, line)
        self.assertNotIn("?", line)

    def test_fragment_is_dropped_too(self):
        self.assertEqual(log.access_line("POST", "/api/v1/usage/sync#x", 403, 3), "POST /api/v1/usage/sync 403 3ms")


if __name__ == "__main__":
    unittest.main()
