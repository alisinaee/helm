"""Gap tests for the session presence service (R7.1 T1): path normalisation, odd stored values, write failures,
backward clocks and boundary stamps. Every time is a fake clock passed as now (or a patched time.time). Each
test lives under its own temp ROADMAP_HOME through HomeCase, so the real state directory is never touched."""

import json
import os
import pathlib
import unittest
from unittest import mock

from roadmap.services import presence
from roadmap.store import paths
from tests.unit.test_store_support import HomeCase

DATA = "/projects/demo/docs"


class PresenceGapTests(HomeCase):
    def write_raw(self, text, data_dir=DATA):
        os.makedirs(paths.state_dir(), exist_ok=True)
        with open(presence.file_for(data_dir), "w", encoding="utf-8") as fh:
            fh.write(text)

    def stored(self, data_dir=DATA):
        with open(presence.file_for(data_dir), encoding="utf-8") as fh:
            return json.load(fh)

    def test_file_for_relative_and_absolute_paths_match(self):
        relative = "demo/docs"
        self.assertEqual(presence.file_for(relative), presence.file_for(os.path.abspath(relative)))
        self.assertNotEqual(presence.file_for(relative), presence.file_for("/projects/other/docs"))

    def test_file_for_accepts_a_path_object(self):
        self.assertEqual(presence.file_for(pathlib.Path(DATA)), presence.file_for(DATA))

    def test_a_numeric_string_time_is_read_as_a_float(self):
        self.assertTrue(presence.touch_hook(DATA, now="1000.5"))
        self.assertEqual(self.stored()["hook"], 1000.5)
        self.assertEqual(presence.state(DATA, now="1000.5"), presence.OPEN)

    def test_scalar_json_in_the_file_reads_as_no_presence(self):
        for text in ('"foo"', "123", "true", "null"):
            with self.subTest(text=text):
                self.write_raw(text)
                self.assertEqual(presence.state(DATA, now=1000), presence.NONE)
                self.assertTrue(presence.touch_hook(DATA, now=1000))
                self.assertEqual(self.stored()["hook"], 1000.0)

    def test_a_failed_directory_create_is_not_an_error(self):
        with mock.patch.object(paths, "ensure_dir", side_effect=OSError("read-only file system")):
            self.assertFalse(presence.set_watch(DATA, 4242, now=1000))
            self.assertFalse(presence.touch_hook(DATA, now=1000))
            self.assertFalse(presence.clear_watch(DATA))
        self.assertFalse(os.path.exists(presence.file_for(DATA)))

    def test_a_boolean_hook_stamp_is_no_stamp(self):
        self.write_raw('{"hook": false}')
        # with now=0, a boolean read as 0.0 would look fresh; it must read as no stamp
        self.assertEqual(presence.state(DATA, now=0), presence.NONE)
        self.assertTrue(presence.touch_hook(DATA, now=0))

    def test_a_zero_hook_stamp_is_a_real_timestamp(self):
        self.write_raw('{"hook": 0}')
        self.assertEqual(presence.state(DATA, now=5), presence.OPEN)
        self.assertFalse(presence.touch_hook(DATA, now=10))

    def test_a_backward_clock_jump_is_not_throttled(self):
        # the throttle only applies to moment - last in [0, 30); a negative delta writes and resets the stamp
        self.assertTrue(presence.touch_hook(DATA, now=2000))
        self.assertTrue(presence.touch_hook(DATA, now=1000))
        self.assertEqual(self.stored()["hook"], 1000.0)

    def test_touch_hook_without_now_uses_the_wall_clock(self):
        with mock.patch.object(presence.time, "time", return_value=5000.0):
            self.assertTrue(presence.touch_hook(DATA))
        self.assertEqual(self.stored()["hook"], 5000.0)

    def test_touch_hook_keeps_watch_fields(self):
        self.assertTrue(presence.set_watch(DATA, 4242, now=100))
        self.assertTrue(presence.touch_hook(DATA, now=200))
        doc = self.stored()
        self.assertEqual((doc["watch"], doc["watchPid"], doc["hook"]), (100.0, 4242, 200.0))

    def test_touch_hook_with_an_invalid_time_fails_open(self):
        self.assertFalse(presence.touch_hook(DATA, now="invalid"))
        self.assertFalse(os.path.exists(presence.file_for(DATA)))

    def test_set_watch_stores_none_for_a_non_int_pid(self):
        for pid in ("1234", None, 1.5):
            with self.subTest(pid=pid):
                self.assertTrue(presence.set_watch(DATA, pid, now=100))
                self.assertIsNone(self.stored()["watchPid"])

    def test_set_watch_stores_none_for_a_bool_pid(self):
        for pid in (True, False):
            with self.subTest(pid=pid):
                self.assertTrue(presence.set_watch(DATA, pid, now=100))
                self.assertIsNone(self.stored()["watchPid"])

    def test_set_watch_keeps_an_existing_hook_stamp(self):
        self.assertTrue(presence.touch_hook(DATA, now=100))
        self.assertTrue(presence.set_watch(DATA, 4242, now=200))
        self.assertEqual(self.stored()["hook"], 100.0)

    def test_set_watch_with_an_invalid_time_fails_open(self):
        self.assertFalse(presence.set_watch(DATA, 4242, now={}))
        self.assertFalse(os.path.exists(presence.file_for(DATA)))

    def test_clear_watch_without_a_file_writes_all_three_stamps_as_none(self):
        self.assertTrue(presence.clear_watch(DATA))
        self.assertEqual(self.stored(), {"watch": None, "watchPid": None, "hook": None})

    def test_clear_watch_fails_open_when_loading_raises(self):
        with mock.patch.object(presence, "_load", side_effect=RuntimeError("boom")):
            self.assertFalse(presence.clear_watch(DATA))

    def test_a_hook_stamp_in_the_future_is_not_open(self):
        self.write_raw('{"hook": 2000}')
        self.assertEqual(presence.state(DATA, now=1000), presence.NONE)

    def test_a_future_watch_falls_through_to_a_fresh_hook(self):
        presence.touch_hook(DATA, now=990)
        presence.set_watch(DATA, 4242, now=2000)
        self.assertEqual(presence.state(DATA, now=1000), presence.OPEN)

    def test_a_watch_stamp_at_exactly_zero_age_is_watching(self):
        presence.set_watch(DATA, 4242, now=1000)
        self.assertEqual(presence.state(DATA, now=1000), presence.WATCHING)

    def test_a_hook_stamp_at_exactly_zero_age_is_open(self):
        presence.touch_hook(DATA, now=1000)
        self.assertEqual(presence.state(DATA, now=1000), presence.OPEN)

    def test_state_without_now_reads_the_wall_clock(self):
        presence.set_watch(DATA, 4242, now=1000)
        with mock.patch.object(presence.time, "time", return_value=1030.0):
            self.assertEqual(presence.state(DATA), presence.WATCHING)
        with mock.patch.object(presence.time, "time", return_value=1100.0):
            self.assertEqual(presence.state(DATA), presence.NONE)

    def test_state_with_an_invalid_time_is_none(self):
        presence.set_watch(DATA, 4242, now=1000)
        self.assertEqual(presence.state(DATA, now="invalid"), presence.NONE)

    def test_expired_watch_and_hook_together_are_none(self):
        presence.touch_hook(DATA, now=400)
        presence.set_watch(DATA, 4242, now=940)
        self.assertEqual(presence.state(DATA, now=1000), presence.NONE)


if __name__ == "__main__":
    unittest.main()
