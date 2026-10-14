"""Session presence service (R7.1 T1): the 30 s hook throttle, the 60 s watch and 10 min hook edges, the state file
kept in the state directory, corrupt files reading as none, and fail-open behaviour. A fake clock is passed as now."""

import os
from unittest import mock

from roadmap.services import presence
from roadmap.store import paths
from tests.unit.test_store_support import HomeCase

DATA = "/projects/demo/docs"


class PresenceTests(HomeCase):
    def stored(self, data_dir=DATA):
        with open(presence.file_for(data_dir), encoding="utf-8") as fh:
            return fh.read()

    def test_the_file_is_in_the_state_dir_not_the_data_dir(self):
        presence.touch_hook(DATA, now=1000)
        path = presence.file_for(DATA)
        self.assertTrue(path.startswith(paths.state_dir() + os.sep))
        self.assertFalse(path.startswith(DATA))
        self.assertTrue(os.path.isfile(path))

    def test_two_hook_touches_within_30_seconds_write_once(self):
        self.assertTrue(presence.touch_hook(DATA, now=1000))
        self.assertFalse(presence.touch_hook(DATA, now=1029))
        self.assertEqual(presence.state(DATA, now=1029), presence.OPEN)
        self.assertTrue(presence.touch_hook(DATA, now=1030))

    def test_throttle_is_per_project(self):
        self.assertTrue(presence.touch_hook(DATA, now=1000))
        self.assertTrue(presence.touch_hook("/projects/other/docs", now=1000))

    def test_no_file_reads_as_none(self):
        self.assertEqual(presence.state(DATA, now=1000), presence.NONE)

    def test_hook_is_open_until_10_minutes(self):
        presence.touch_hook(DATA, now=1000)
        self.assertEqual(presence.state(DATA, now=1599), presence.OPEN)
        self.assertEqual(presence.state(DATA, now=1600), presence.NONE)

    def test_watch_is_watching_until_60_seconds(self):
        presence.set_watch(DATA, 4242, now=1000)
        self.assertEqual(presence.state(DATA, now=1059), presence.WATCHING)
        self.assertEqual(presence.state(DATA, now=1060), presence.NONE)

    def test_watch_wins_over_hook_while_fresh_and_hook_shows_after(self):
        presence.touch_hook(DATA, now=1000)
        presence.set_watch(DATA, 4242, now=1000)
        self.assertEqual(presence.state(DATA, now=1030), presence.WATCHING)
        self.assertEqual(presence.state(DATA, now=1060), presence.OPEN)

    def test_clear_watch_drops_watching_but_keeps_the_hook(self):
        presence.touch_hook(DATA, now=1000)
        presence.set_watch(DATA, 4242, now=1000)
        self.assertTrue(presence.clear_watch(DATA))
        self.assertEqual(presence.state(DATA, now=1001), presence.OPEN)
        self.assertIn('"watchPid": null', self.stored())

    def test_set_watch_stores_the_pid_and_the_stamp(self):
        presence.set_watch(DATA, 4242, now=1000)
        self.assertIn('"watchPid": 4242', self.stored())
        self.assertIn('"watch": 1000.0', self.stored())

    def test_a_future_stamp_is_not_fresh(self):
        presence.set_watch(DATA, 1, now=5000)
        self.assertEqual(presence.state(DATA, now=1000), presence.NONE)

    def test_a_corrupt_file_reads_as_none(self):
        paths.ensure_dir(paths.state_dir())
        with open(presence.file_for(DATA), "w", encoding="utf-8") as fh:
            fh.write("{not json")
        self.assertEqual(presence.state(DATA, now=1000), presence.NONE)
        self.assertTrue(presence.touch_hook(DATA, now=1000))
        self.assertEqual(presence.state(DATA, now=1000), presence.OPEN)

    def test_a_non_object_file_reads_as_none(self):
        paths.ensure_dir(paths.state_dir())
        with open(presence.file_for(DATA), "w", encoding="utf-8") as fh:
            fh.write("[1, 2]")
        self.assertEqual(presence.state(DATA, now=1000), presence.NONE)

    def test_non_numeric_stamps_are_ignored(self):
        paths.ensure_dir(paths.state_dir())
        with open(presence.file_for(DATA), "w", encoding="utf-8") as fh:
            fh.write('{"hook": "soon", "watch": true}')
        self.assertEqual(presence.state(DATA, now=1000), presence.NONE)

    def test_a_failed_write_returns_false_and_never_raises(self):
        with mock.patch.object(presence.atomic, "write_json", side_effect=OSError("disk full")):
            self.assertFalse(presence.touch_hook(DATA, now=1000))
            self.assertFalse(presence.set_watch(DATA, 1, now=1000))
            self.assertFalse(presence.clear_watch(DATA))

    def test_state_and_touch_never_raise_on_unexpected_errors(self):
        with mock.patch.object(presence.atomic, "read_json", side_effect=RuntimeError("boom")):
            self.assertEqual(presence.state(DATA, now=1000), presence.NONE)
            self.assertTrue(presence.touch_hook(DATA, now=1000))  # an unreadable file counts as no stamps
        with mock.patch.object(presence.os.path, "abspath", side_effect=RuntimeError("boom")):
            self.assertEqual(presence.state(DATA, now=1000), presence.NONE)
            self.assertFalse(presence.set_watch(DATA, 1, now=1000))

    def test_default_clock_is_used_when_now_is_omitted(self):
        with mock.patch.object(presence.time, "time", return_value=1000.0):
            presence.set_watch(DATA, 7)
        self.assertEqual(presence.state(DATA, now=1010), presence.WATCHING)
