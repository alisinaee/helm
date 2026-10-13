"""Tests for atomic writes, strict reads, the directory lock (with two real processes) and file modes."""

import json
import os
import subprocess
import sys
import unittest
from unittest import mock

from roadmap.errors import RoadmapError
from roadmap.store import atomic, lock, paths
from tests.unit.test_store_support import REPO, HomeCase, mode_of

CHILD = r"""
import os, sys, time
_, repo, directory, target, barrier, count, tag = sys.argv
sys.path.insert(0, repo)
from roadmap.store import atomic, lock
while not os.path.exists(barrier):
    time.sleep(0.005)
for _ in range(int(count)):
    with lock.locked(directory):
        data = atomic.read_json(target, default={"count": 0, "writers": []})
        data["count"] += 1
        data["writers"].append(tag)
        atomic.write_json(target, data)
"""


class AtomicWriteTests(HomeCase):
    def test_crash_before_replace_leaves_original_intact(self):
        directory = os.path.join(self.tmp, "data")
        path = os.path.join(directory, "jobs.json")
        atomic.write_json(path, {"v": 1})
        with mock.patch.object(atomic.os, "replace", side_effect=OSError("simulated crash")):
            with self.assertRaises(OSError):
                atomic.write_json(path, {"v": 2})
        self.assertEqual(atomic.read_json(path), {"v": 1})
        self.assertEqual(os.listdir(directory), ["jobs.json"])

    def test_new_file_is_0600_and_new_dir_is_0700(self):
        directory = os.path.join(self.tmp, "config")
        paths.ensure_dir(directory)
        path = os.path.join(directory, "x.json")
        atomic.write_json(path, {"a": 1})
        self.assertEqual(mode_of(path), 0o600)
        self.assertEqual(mode_of(directory), 0o700)

    def test_existing_file_keeps_its_mode(self):
        path = os.path.join(self.tmp, "shared.json")
        atomic.write_json(path, {"a": 1})
        os.chmod(path, 0o644)
        atomic.write_json(path, {"a": 2})
        self.assertEqual(mode_of(path), 0o644)
        self.assertEqual(atomic.read_json(path), {"a": 2})

    def test_bad_json_raises_invalid_data_and_leaves_file(self):
        path = os.path.join(self.tmp, "broken.json")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("{not json")
        with self.assertRaises(RoadmapError) as cm:
            atomic.read_json(path)
        self.assertEqual(cm.exception.code, "invalid_data")
        self.assertEqual(cm.exception.exit, 5)
        with open(path, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "{not json")

    def test_missing_file_uses_default_or_not_found(self):
        path = os.path.join(self.tmp, "absent.json")
        self.assertEqual(atomic.read_json(path, default={"d": 1}), {"d": 1})
        with self.assertRaises(RoadmapError) as cm:
            atomic.read_json(path)
        self.assertEqual(cm.exception.exit, 3)


class LockTests(HomeCase):
    def test_second_holder_times_out_with_locked_error(self):
        directory = os.path.join(self.tmp, "data")
        with lock.locked(directory):
            with self.assertRaises(RoadmapError) as cm:
                with lock.locked(directory, timeout=0.2):
                    pass
        self.assertEqual(cm.exception.code, "locked")
        self.assertEqual(cm.exception.exit, 4)

    def test_lock_leaves_no_file_behind(self):
        directory = os.path.join(self.tmp, "data")
        with lock.locked(directory):
            pass
        self.assertEqual(os.listdir(directory), [])

    def test_two_processes_under_lock_never_corrupt_json(self):
        directory = os.path.join(self.tmp, "data")
        os.makedirs(directory)
        target = os.path.join(directory, "tasks.json")
        barrier = os.path.join(self.tmp, "go")
        procs = [
            subprocess.Popen(
                [sys.executable, "-c", CHILD, REPO, directory, target, barrier, "40", tag],
                env=os.environ.copy(), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            for tag in ("a", "b")
        ]
        with open(barrier, "w", encoding="utf-8") as fh:
            fh.write("go")
        for proc in procs:
            _, err = proc.communicate(timeout=120)
            self.assertEqual(proc.returncode, 0, err.decode("utf-8", "replace"))
        with open(target, encoding="utf-8") as fh:
            data = json.load(fh)
        self.assertEqual(data["count"], 80)
        self.assertEqual(data["writers"].count("a"), 40)
        self.assertEqual(data["writers"].count("b"), 40)


if __name__ == "__main__":
    unittest.main()
