"""R3.4a: one test group per Cursor R7.1 finding (docs/reviews/cursor-r71.md). 1: the presence touch never stalls a
hook (mtime fast path, budget check, bounded reads and lock wait). 4: the launcher gate is atomic and a failed launch
releases its claim. 6: stamp files are never read through a symlink. 7: presence read-modify-write does not clobber.
8: the idle Start notification names the project id only. 9: a damaged launch stamp fails closed. 10: the launch stamp
is per project. Every test runs under its own ROADMAP_HOME; nothing is launched (runners are injected)."""

import json
import os
import shutil
import tempfile
import threading
import time
import unittest
from unittest import mock

from roadmap.services import hooks, launcher, notify, presence, queue
from roadmap.store import config, lock, paths
from tests.unit.test_store_support import HomeCase


class PresenceTouchBudgetTests(HomeCase):
    """Finding 1: a PreToolUse never waits on presence I/O it does not need."""

    def test_a_throttled_touch_reads_nothing(self):
        now = time.time()
        self.assertTrue(presence.touch_hook("/p/docs", now=now))
        with mock.patch.object(presence, "read_plain", side_effect=AssertionError("must not read")) as read:
            self.assertFalse(presence.touch_hook("/p/docs", now=now + 5))
        read.assert_not_called()

    def test_a_stamp_older_than_the_throttle_is_read_and_written(self):
        now = time.time()
        self.assertTrue(presence.touch_hook("/p/docs", now=now))
        self.assertTrue(presence.touch_hook("/p/docs", now=now + presence.HOOK_THROTTLE_S + 1))

    def test_an_oversize_stamp_file_is_unreadable_and_bounded(self):
        path = presence.file_for("/p/docs")
        os.makedirs(paths.state_dir(), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(" " * (presence.MAX_BYTES + 10) + "{}")
        self.assertEqual(presence.state("/p/docs", now=1000), presence.NONE)
        with self.assertRaises(presence.Unreadable):
            presence.read_plain(path)

    def test_a_busy_state_lock_is_skipped_quickly_and_fails_open(self):
        started = time.monotonic()
        with lock.locked(paths.state_dir()):
            self.assertFalse(presence.touch_hook("/p/docs", now=1000))
            self.assertFalse(presence.set_watch("/p/docs", 1, now=1000))
        self.assertLess(time.monotonic() - started, 2.0)

    def test_the_hook_skips_presence_when_little_of_the_budget_is_left(self):
        project = {"id": "demo", "path": self.make_project("demo"), "dataDir": "docs"}
        with mock.patch.object(presence, "touch_hook") as touch:
            hooks._touch_presence(project, 1000, lambda: 0.15, 0.0)
        touch.assert_not_called()

    def test_the_hook_stamps_presence_when_the_budget_is_fresh(self):
        project = {"id": "demo", "path": self.make_project("demo"), "dataDir": "docs"}
        with mock.patch.object(presence, "touch_hook") as touch:
            hooks._touch_presence(project, 1000, lambda: 0.01, 0.0)
        touch.assert_called_once()

    def test_a_failing_clock_does_not_break_the_hook(self):
        project = {"id": "demo", "path": self.make_project("demo"), "dataDir": "docs"}

        def broken():
            raise RuntimeError("clock")
        self.assertIsNone(hooks._touch_presence(project, 1000, broken, 0.0))


class PresenceRaceTests(HomeCase):
    """Finding 7: hook and watch stamps are read-modify-written under the state lock, so neither clobbers the other."""

    def test_concurrent_hook_and_watch_stamps_keep_both_fields(self):
        data = "/race/docs"
        results = []
        with mock.patch.object(presence, "LOCK_WAIT_S", 10.0):
            def worker(index):
                for step in range(10):
                    base = 1000 + index * 100 + step * 40
                    results.append(presence.set_watch(data, 100 + index, now=base))
                    presence.touch_hook(data, now=base + 31)  # may be throttled; only the watch writes must land
            threads = [threading.Thread(target=worker, args=(i,)) for i in range(6)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        self.assertTrue(all(results))
        with open(presence.file_for(data), encoding="utf-8") as fh:
            doc = json.load(fh)
        self.assertIsNotNone(doc["watch"])
        self.assertIsNotNone(doc["hook"])
        self.assertIsNotNone(doc["watchPid"])

    def test_a_watch_write_keeps_a_hook_stamp_written_just_before(self):
        self.assertTrue(presence.touch_hook("/race/docs", now=1000))
        self.assertTrue(presence.set_watch("/race/docs", 9, now=1001))
        self.assertTrue(presence.clear_watch("/race/docs"))
        self.assertEqual(presence.state("/race/docs", now=1002), presence.OPEN)


class PresenceSymlinkTests(HomeCase):
    """Finding 6: a stamp file that is a symlink is unreadable, never followed."""

    def setUp(self):
        super().setUp()
        self.data = "/sym/docs"
        self.target = os.path.join(self.tmp, "forged.json")
        with open(self.target, "w", encoding="utf-8") as fh:
            fh.write('{"hook": 1000, "watch": null, "watchPid": null}')
        os.makedirs(paths.state_dir(), exist_ok=True)
        os.symlink(self.target, presence.file_for(self.data))

    def test_a_symlinked_presence_file_reads_as_none(self):
        self.assertEqual(presence.state(self.data, now=1001), presence.NONE)
        self.assertFalse(presence.readable(self.data))

    def test_a_symlinked_presence_file_is_never_written_through(self):
        self.assertFalse(presence.touch_hook(self.data, now=1001))
        self.assertFalse(presence.set_watch(self.data, 1, now=1001))
        self.assertTrue(os.path.islink(presence.file_for(self.data)))
        with open(self.target, encoding="utf-8") as fh:
            self.assertIn('"hook": 1000', fh.read())

    def test_a_symlinked_launch_stamp_fails_closed_even_when_old(self):
        stamp = launcher.stamp_file_for(self.data)
        os.symlink(self.target, stamp)
        self.assertTrue(launcher._recent(self.data, 10 ** 9))


class LauncherAtomicTests(HomeCase):
    """Finding 4: check, stamp and the launch decision are one atomic step, and a failed launch releases its claim."""

    def setUp(self):
        super().setUp()
        self.project = self.make_project("app")
        self.data = os.path.join(self.project, "docs")
        os.makedirs(self.data)
        self.config = {"projects": [{"id": "app", "path": self.project, "dataDir": "docs", "launchOnStart": True}]}
        patcher = mock.patch.object(launcher.config, "load", side_effect=lambda: self.config)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.calls = []

    def runner(self, argv):
        self.calls.append(argv)
        return True

    def test_two_concurrent_starts_launch_once(self):
        barrier = threading.Barrier(2)
        launched = []

        def start():
            barrier.wait()
            launched.append(launcher.maybe_launch(self.data, runner=self.runner, now=1000))
        threads = [threading.Thread(target=start) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sorted(launched), [False, True])
        self.assertEqual(len(self.calls), 1)

    def test_the_stamp_is_written_before_the_command_runs(self):
        seen = []

        def runner(argv):
            seen.append(os.path.exists(launcher.stamp_file_for(self.data)))
            return True
        self.assertTrue(launcher.maybe_launch(self.data, runner=runner, now=1000))
        self.assertEqual(seen, [True])

    def test_a_non_zero_exit_releases_the_claim_for_an_immediate_retry(self):
        self.assertTrue(launcher.maybe_launch(self.data, runner=lambda argv: False, now=1000))
        self.assertFalse(os.path.exists(launcher.stamp_file_for(self.data)))
        self.assertTrue(launcher.maybe_launch(self.data, runner=self.runner, now=1001))
        self.assertEqual(len(self.calls), 1)

    def test_an_exception_releases_the_claim_and_reports_no_launch(self):
        def broken(argv):
            raise OSError("no osascript")
        self.assertFalse(launcher.maybe_launch(self.data, runner=broken, now=1000))
        self.assertTrue(launcher.maybe_launch(self.data, runner=self.runner, now=1001))

    def test_a_successful_launch_keeps_the_ten_minute_window(self):
        self.assertTrue(launcher.maybe_launch(self.data, runner=self.runner, now=1000))
        self.assertFalse(launcher.maybe_launch(self.data, runner=self.runner, now=1000 + launcher.RATE_S - 1))
        self.assertEqual(len(self.calls), 1)

    def test_a_failed_stamp_write_means_no_launch(self):
        with mock.patch.object(launcher.atomic, "write_json", side_effect=OSError("disk full")):
            self.assertFalse(launcher.maybe_launch(self.data, runner=self.runner, now=1000))
        self.assertEqual(self.calls, [])

    def test_a_busy_launch_lock_means_no_launch(self):
        with mock.patch.object(launcher, "LOCK_WAIT_S", 0.05), lock.locked(paths.state_dir()):
            self.assertFalse(launcher.maybe_launch(self.data, runner=self.runner, now=1000))
        self.assertEqual(self.calls, [])

    def test_an_untrusted_presence_file_means_no_launch(self):
        os.makedirs(paths.state_dir(), exist_ok=True)
        target = os.path.join(self.tmp, "forged.json")
        with open(target, "w", encoding="utf-8") as fh:
            fh.write("{}")
        os.symlink(target, presence.file_for(self.data))
        self.assertFalse(launcher.maybe_launch(self.data, runner=self.runner, now=1000))
        self.assertEqual(self.calls, [])

    def make_project(self, name):
        path = os.path.join(self.tmp, "projects", name)
        os.makedirs(path, exist_ok=True)
        return path


class LauncherDamagedStampTests(HomeCase):
    """Finding 9: a damaged launch stamp fails closed; a damaged regular file heals after the window."""

    def setUp(self):
        super().setUp()
        self.project = self.make_project("app")
        self.data = os.path.join(self.project, "docs")
        os.makedirs(self.data)
        self.config = {"projects": [{"id": "app", "path": self.project, "dataDir": "docs", "launchOnStart": True}]}
        patcher = mock.patch.object(launcher.config, "load", side_effect=lambda: self.config)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.calls = []

    def runner(self, argv):
        self.calls.append(argv)
        return True

    def make_project(self, name):
        path = os.path.join(self.tmp, "projects", name)
        os.makedirs(path, exist_ok=True)
        return path

    def damage(self, text, age_s):
        os.makedirs(paths.state_dir(), exist_ok=True)
        path = launcher.stamp_file_for(self.data)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        mtime = time.time() - age_s
        os.utime(path, (mtime, mtime))
        return mtime

    def test_a_corrupt_stamp_blocks_the_launch_inside_the_window(self):
        mtime = self.damage("{not json", 0)
        self.assertFalse(launcher.maybe_launch(self.data, runner=self.runner, now=mtime + 1))
        self.assertEqual(self.calls, [])

    def test_a_corrupt_stamp_heals_after_the_window(self):
        mtime = self.damage("{not json", 0)
        self.assertTrue(launcher.maybe_launch(self.data, runner=self.runner, now=mtime + launcher.RATE_S + 1))
        self.assertEqual(len(self.calls), 1)

    def test_a_non_object_stamp_is_damaged(self):
        mtime = self.damage("[1000]", 0)
        self.assertFalse(launcher.maybe_launch(self.data, runner=self.runner, now=mtime + 1))
        self.assertEqual(self.calls, [])

    def test_a_missing_stamp_is_a_clean_state(self):
        self.assertFalse(launcher._recent(self.data, 1000))
        self.assertTrue(launcher.maybe_launch(self.data, runner=self.runner, now=1000))


class LauncherPerProjectTests(HomeCase):
    """Finding 10: each project has its own launch stamp, named like its presence file."""

    def setUp(self):
        super().setUp()
        self.a = self.make_project("alpha")
        self.b = self.make_project("beta")
        self.config = {"projects": [
            {"id": "alpha", "path": self.a, "dataDir": "docs", "launchOnStart": True},
            {"id": "beta", "path": self.b, "dataDir": "docs", "launchOnStart": True},
        ]}
        patcher = mock.patch.object(launcher.config, "load", side_effect=lambda: self.config)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.calls = []

    def runner(self, argv):
        self.calls.append(argv)
        return True

    def make_project(self, name):
        path = os.path.join(self.tmp, "projects", name)
        os.makedirs(os.path.join(path, "docs"), exist_ok=True)
        return path

    def test_one_project_does_not_rate_limit_another(self):
        self.assertTrue(launcher.maybe_launch(os.path.join(self.a, "docs"), runner=self.runner, now=1000))
        self.assertTrue(launcher.maybe_launch(os.path.join(self.b, "docs"), runner=self.runner, now=1001))
        self.assertEqual(len(self.calls), 2)

    def test_the_stamp_is_named_like_the_presence_file(self):
        name = os.path.basename(launcher.stamp_file_for(os.path.join(self.a, "docs")))
        self.assertEqual(name, "launch-" + presence.digest(os.path.join(self.a, "docs")) + ".json")
        self.assertTrue(name.startswith("launch-"))
        self.assertNotEqual(launcher.stamp_file_for(os.path.join(self.a, "docs")),
                            launcher.stamp_file_for(os.path.join(self.b, "docs")))

    def test_the_global_launch_json_is_no_longer_used(self):
        self.assertTrue(launcher.maybe_launch(os.path.join(self.a, "docs"), runner=self.runner, now=1000))
        self.assertFalse(os.path.exists(os.path.join(paths.state_dir(), "launch.json")))


class IdleNotificationTests(HomeCase):
    """Finding 8: the idle Start notification names the project id, never the absolute folder."""

    def setUp(self):
        super().setUp()
        self.project = self.make_project("demo")
        self.data = os.path.join(self.project, "docs")
        os.makedirs(self.data)
        self.bodies = []

    def make_project(self, name):
        path = os.path.join(self.tmp, "projects", name)
        os.makedirs(path, exist_ok=True)
        return path

    def test_the_idle_text_has_no_absolute_path(self):
        def capture(data_dir, kind, title, body_for, **kwargs):
            self.bodies.append(body_for("demo"))
            return True
        with mock.patch.object(notify, "notify_dir", side_effect=capture), \
                mock.patch.object(queue, "_spawn"):
            queue.enqueue(self.data, "P1.1", by="lead")
        self.assertEqual(len(self.bodies), 1)
        self.assertNotIn(self.project, self.bodies[0])
        self.assertNotIn("cd ", self.bodies[0])
        self.assertIn("demo", self.bodies[0])


if __name__ == "__main__":
    unittest.main()
