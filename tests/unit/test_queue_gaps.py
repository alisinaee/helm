"""Gap tests for the Start notification (roadmap/services/queue.py: presence and launcher) and for the loader's
session, folder and project path (roadmap/services/loader.py). Current behaviour: the notification names the project
id only, the launch runs on a daemon thread, and the notify call is made outside the queue lock. Nothing notifies or
launches for real: notify.notify, queue._spawn and launcher.maybe_launch are replaced, and ROADMAP_HOME is a temp
folder. The empty and null project path cases (loader.py project_folder) are covered too."""

import os
import pathlib
import tempfile
import unittest
from contextlib import contextmanager
from unittest import mock

from roadmap.services import loader, notify, presence, queue
from roadmap.store import config, lock
from tests.unit.test_store_support import HomeCase

REAL_SPAWN = queue._spawn


class QueueGapTests(HomeCase):
    def setUp(self):
        super().setUp()
        self.project = self.make_project("demo")
        config.add_project("Demo", self.project)
        self.data = os.path.join(self.project, "docs")
        os.makedirs(self.data)
        patches = (mock.patch.object(notify, "_under_tests", return_value=False),
                   mock.patch.object(notify, "_macos", return_value=True),
                   mock.patch.object(notify, "notify", return_value=True),
                   mock.patch.object(queue, "_spawn"),
                   mock.patch.object(queue.launcher, "maybe_launch", return_value=False))
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.fake = notify.notify
        self.spawn = queue._spawn
        self.launch = queue.launcher.maybe_launch

    def test_a_watching_session_gets_the_open_session_text_and_no_launch(self):
        with mock.patch.object(presence, "state", return_value=presence.WATCHING):
            queue.enqueue(self.data, "P2.7", by="lead")
        self.assertEqual(self.fake.call_args[0][2], "Start P2.7 queued. Open a Claude session in demo or run: "
                         "roadmap watch")
        self.spawn.assert_not_called()

    def test_the_start_notification_has_the_start_kind_and_title(self):
        queue.enqueue(self.data, "P2.7", by="lead")
        self.assertEqual(self.fake.call_args[0][:2], ("start", "Start queued"))

    def test_a_presence_error_still_queues_and_shows_nothing(self):
        with mock.patch.object(presence, "state", side_effect=RuntimeError("boom")):
            entry = queue.enqueue(self.data, "P2.8")
        self.assertEqual(entry["task"], "P2.8")
        self.assertEqual([e["task"] for e in queue.list_queue(self.data)], ["P2.8"])
        self.fake.assert_not_called()
        self.spawn.assert_not_called()

    def test_a_launch_that_reports_true_ends_quietly(self):
        self.spawn.side_effect = lambda target, arg: target(arg)
        self.launch.return_value = True
        self.assertEqual(queue.enqueue(self.data, "P2.9")["task"], "P2.9")
        self.launch.assert_called_once_with(self.data)

    def test_the_real_spawn_starts_a_daemon_thread_for_the_launch(self):
        with mock.patch.object(queue.threading, "Thread") as thread:
            REAL_SPAWN(queue._launch_quietly, self.data)
        thread.assert_called_once_with(target=queue._launch_quietly, args=(self.data,), daemon=True)
        thread.return_value.start.assert_called_once_with()

    def test_the_notification_is_sent_after_the_queue_lock_is_released(self):
        real_locked = lock.locked
        held = [False]

        @contextmanager
        def tracked(directory, timeout=None):
            held[0] = True
            try:
                with real_locked(directory, timeout):
                    yield
            finally:
                held[0] = False

        seen = []
        with mock.patch.object(lock, "locked", tracked), \
                mock.patch.object(queue, "_notify_start", side_effect=lambda d, t: seen.append(held[0])):
            queue.enqueue(self.data, "P2.10")
        self.assertEqual(seen, [False])


class LoaderGapTests(HomeCase):
    def setUp(self):
        super().setUp()
        self.project = self.make_project("demo")
        config.add_project("Demo", self.project)

    def test_load_snapshot_passes_the_session_and_the_project_root(self):
        with mock.patch.object(presence, "state", return_value=presence.OPEN), \
                mock.patch.object(loader, "build_snapshot", wraps=loader.build_snapshot) as build:
            snap = loader.load_snapshot("demo")
        self.assertEqual(build.call_args.kwargs["session"], presence.OPEN)
        self.assertEqual(build.call_args.kwargs["folder"], self.project)
        self.assertEqual(snap["session"], "open")

    def test_a_presence_error_omits_the_session_key(self):
        with mock.patch.object(presence, "state", side_effect=RuntimeError("boom")), \
                mock.patch.object(loader, "build_snapshot", wraps=loader.build_snapshot) as build:
            snap = loader.load_snapshot("demo")
        self.assertIsNone(build.call_args.kwargs["session"])
        self.assertNotIn("session", snap)

    def test_session_view_gives_open_when_a_session_is_open(self):
        with mock.patch.object(presence, "state", return_value=presence.OPEN):
            self.assertEqual(loader._session_view(self.project), "open")

    def test_project_path_treats_an_empty_path_as_none_and_a_path_object_as_text(self):
        self.assertIsNone(loader._project_path({"path": ""}))
        self.assertEqual(loader._project_path({"path": pathlib.PurePosixPath("/work/proj")}), "/work/proj")

    def test_project_path_of_a_non_dict_entry_is_none(self):
        self.assertIsNone(loader._project_path(123))

    def test_an_empty_registered_path_does_not_read_the_working_directory(self):
        # BUG (roadmap/services/loader.py:28): os.path.join("", "docs") is the relative "docs", so the snapshot reads
        # whatever docs/ the process's working directory holds.
        workdir = tempfile.TemporaryDirectory(prefix="rb-cwd-")
        self.addCleanup(workdir.cleanup)
        os.makedirs(os.path.join(workdir.name, "docs"))
        with open(os.path.join(workdir.name, "docs", "tasks.json"), "w", encoding="utf-8") as fh:
            fh.write("{}")
        old = os.getcwd()
        os.chdir(workdir.name)
        self.addCleanup(os.chdir, old)
        entry = {"id": "demo", "name": "Demo", "path": ""}
        with mock.patch.object(loader.config_store, "get_project", return_value=entry), \
                mock.patch.object(loader, "build_snapshot", wraps=loader.build_snapshot) as build:
            loader.load_snapshot("demo")
        self.assertIsNone(build.call_args.args[0]["tasks.json"])

    def test_a_null_registered_path_does_not_raise(self):
        # BUG (roadmap/services/loader.py:28): project_folder() joins a None path and raises TypeError before the
        # fail-open _project_path() is reached, so load_snapshot is not fail-open for such an entry.
        entry = {"id": "demo", "name": "Demo", "path": None}
        with mock.patch.object(loader.config_store, "get_project", return_value=entry):
            try:
                loader.load_snapshot("demo")
            except Exception as exc:
                self.fail("load_snapshot raised " + type(exc).__name__ + ": " + str(exc))


if __name__ == "__main__":
    unittest.main()
