"""Desktop notifications (services/notify.py): one per 60 s per (project, kind), the config switch, the no-osascript and
non-macOS no-ops, AppleScript escaping, the 120-character cap, and the hooks in queue, questions and control. No test
runs the real osascript: each one injects a runner, or the test runner guard is what keeps the call a no-op."""

import os
from unittest import mock

from roadmap.services import control, notify, presence, questions, queue
from roadmap.store import atomic, config, paths
from tests.unit.test_store_support import HomeCase


class NotifyTests(HomeCase):
    def setUp(self):
        super().setUp()
        self.calls = []

    def runner(self, argv):
        self.calls.append(argv)
        return True

    def test_one_notification_then_rate_limited_for_60_seconds(self):
        self.assertTrue(notify.notify("start", "T", "B", "demo", runner=self.runner, now=1000))
        self.assertFalse(notify.notify("start", "T", "B", "demo", runner=self.runner, now=1059))
        self.assertEqual(len(self.calls), 1)
        self.assertTrue(notify.notify("start", "T", "B", "demo", runner=self.runner, now=1061))
        self.assertEqual(len(self.calls), 2)

    def test_the_limit_is_per_project_and_kind(self):
        notify.notify("start", "T", "B", "demo", runner=self.runner, now=1000)
        notify.notify("start", "T", "B", "other", runner=self.runner, now=1001)
        notify.notify("question", "T", "B", "demo", runner=self.runner, now=1002)
        self.assertEqual(len(self.calls), 3)

    def test_the_state_file_is_written_in_the_state_dir(self):
        notify.notify("start", "T", "B", "demo", runner=self.runner, now=1000)
        saved = atomic.read_json(os.path.join(paths.state_dir(), notify.STATE_FILE))
        self.assertEqual(saved, {"last": {"demo/start": 1000}})

    def test_config_switch_off_shows_nothing(self):
        data = config.default_config()
        data["notify"] = False
        paths.ensure_dir(paths.config_dir())
        atomic.write_json(paths.config_file(), data)
        self.assertFalse(notify.notify("start", "T", "B", "demo", runner=self.runner, now=1000))
        self.assertEqual(self.calls, [])
        self.assertFalse(os.path.exists(os.path.join(paths.state_dir(), notify.STATE_FILE)))

    def test_without_osascript_it_is_a_no_op_and_does_not_raise(self):
        with mock.patch.object(notify, "_under_tests", return_value=False), \
                mock.patch.object(notify, "_macos", return_value=True), \
                mock.patch.object(notify.shutil, "which", return_value=None), \
                mock.patch.object(notify.subprocess, "run", side_effect=AssertionError("must not run")):
            self.assertFalse(notify.notify("start", "T", "B", "demo", now=1000))

    def test_a_failing_osascript_returns_false_and_does_not_raise(self):
        def missing(argv):
            raise FileNotFoundError("osascript")

        self.assertFalse(notify.notify("start", "T", "B", "demo", runner=missing, now=1000))
        self.assertFalse(notify.notify("start", "T", "B", "demo", runner=lambda argv: False, now=2000))

    def test_off_macos_it_is_a_no_op(self):
        with mock.patch.object(notify, "_under_tests", return_value=False), \
                mock.patch.object(notify, "_macos", return_value=False), \
                mock.patch.object(notify.subprocess, "run", side_effect=AssertionError("must not run")):
            self.assertFalse(notify.notify("start", "T", "B", "demo", now=1000))

    def test_under_the_test_runner_without_an_injected_runner_nothing_is_shown(self):
        with mock.patch.object(notify.subprocess, "run", side_effect=AssertionError("must not run")):
            self.assertFalse(notify.notify("start", "T", "B", "demo", now=1000))
        self.assertFalse(os.path.exists(os.path.join(paths.state_dir(), notify.STATE_FILE)))

    def test_quotes_and_backslashes_are_escaped_and_the_argv_is_a_list(self):
        notify.notify("start", 'Say "go" \\ now', 'Start P2.4 "x"\nqueued', "demo", runner=self.runner, now=1000)
        argv = self.calls[0]
        self.assertEqual(argv[:2], ["osascript", "-e"])
        self.assertEqual(argv[2], 'display notification "Start P2.4 \\"x\\" queued" with title '
                                 '"Say \\"go\\" \\\\ now"')

    def test_title_and_body_are_capped_at_120_characters(self):
        notify.notify("start", "T" * 300, "B" * 300, "demo", runner=self.runner, now=1000)
        script = self.calls[0][2]
        self.assertIn('"' + "B" * 120 + '"', script)
        self.assertNotIn("B" * 121, script)
        self.assertIn('"' + "T" * 120 + '"', script)

    def test_notify_dir_names_the_registered_project_in_the_body(self):
        project = self.make_project("demo")
        config.add_project("Demo", project)
        data_dir = os.path.join(project, "docs")
        os.makedirs(data_dir)
        with mock.patch.object(notify, "notify", return_value=True) as fake, \
                mock.patch.object(notify, "_under_tests", return_value=False), \
                mock.patch.object(notify, "_macos", return_value=True):
            notify.notify_dir(data_dir, "start", "Start queued",
                              lambda p: "Start P2.4 queued. Open a Claude session in " + p + " or run: roadmap watch")
        self.assertEqual(fake.call_args[0][3], "demo")
        self.assertEqual(fake.call_args[0][1], "Helm \u00b7 Demo")
        self.assertIn("in Demo or run: roadmap watch", fake.call_args[0][2])


class NotifyHookTests(HomeCase):
    """The hooks call notify once per event. notify itself is replaced here, so no osascript can run."""

    def setUp(self):
        super().setUp()
        self.project = self.make_project("demo")
        config.add_project("Demo", self.project)
        self.data = os.path.join(self.project, "docs")
        os.makedirs(self.data)
        for patcher in (mock.patch.object(notify, "_under_tests", return_value=False),
                        mock.patch.object(notify, "_macos", return_value=True),
                        mock.patch.object(notify, "notify", return_value=True)):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.fake = notify.notify

    def test_a_queue_add_calls_notify_once_with_the_start_text(self):
        queue.enqueue(self.data, "P2.4", by="lead", now=None)
        self.assertEqual(self.fake.call_count, 1)
        args = self.fake.call_args[0]
        self.assertEqual(args[0], "start")
        self.assertEqual(args[3], "demo")
        self.assertEqual(args[2], "Start P2.4 queued; no session open. Open a Claude session or run: "
                         "roadmap watch")
        self.assertEqual(args[1], "Helm \u00b7 Demo")
        self.assertNotIn(self.project, args[2])

    def test_with_a_session_open_the_text_says_so_and_nothing_is_launched(self):
        presence.touch_hook(self.data)
        with mock.patch.object(queue, "_spawn") as spawn:
            queue.enqueue(self.data, "P2.4", by="lead")
        self.assertEqual(self.fake.call_args[0][2], "Start P2.4 queued. Open a Claude session or run: "
                         "roadmap watch")
        spawn.assert_not_called()

    def test_with_no_session_the_launch_is_requested_once_and_a_failure_does_not_break_enqueue(self):
        with mock.patch.object(queue, "_spawn", side_effect=lambda target, arg: target(arg)), \
                mock.patch.object(queue.launcher, "maybe_launch", return_value=False) as launch:
            entry = queue.enqueue(self.data, "P2.4", by="lead")
            self.assertEqual(entry["task"], "P2.4")
            launch.assert_called_once_with(self.data)
        with mock.patch.object(queue, "_spawn", side_effect=lambda target, arg: target(arg)), \
                mock.patch.object(queue.launcher, "maybe_launch", side_effect=RuntimeError("boom")):
            self.assertEqual(queue.enqueue(self.data, "P2.5")["task"], "P2.5")
        self.assertEqual([e["task"] for e in queue.list_queue(self.data)], ["P2.4", "P2.5"])

    def test_a_broken_notification_still_queues_the_task(self):
        self.fake.side_effect = RuntimeError("osascript broke")
        with mock.patch.object(queue, "_spawn") as spawn:
            self.assertEqual(queue.enqueue(self.data, "P2.6")["task"], "P2.6")
        self.assertEqual([e["task"] for e in queue.list_queue(self.data)], ["P2.6"])
        spawn.assert_called_once()

    def test_a_blocking_question_notifies_and_a_plain_one_does_not(self):
        questions.ask(self.data, "P2.4", "deploy now?", opts=["yes", "no"], default="no")
        self.assertEqual(self.fake.call_count, 0)
        questions.ask(self.data, "P2.4", "deploy now?", opts=["yes", "no"], default="no", block=True)
        self.assertEqual(self.fake.call_count, 1)
        self.assertEqual(self.fake.call_args[0][0], "question")
        self.assertIn("Q2 on P2.4 needs you", self.fake.call_args[0][2])

    def test_the_first_limit_block_notifies_and_a_repeat_does_not(self):
        project = {"id": "demo", "path": os.path.dirname(self.data), "dataDir": "docs"}
        blocked = {"stop": False, "stopTasks": [], "block": {"reason": "weekly stop reached", "scope": "global",
                                                             "overridable": True}, "pickup": {}}
        with mock.patch.object(control, "_evaluate", return_value=dict(blocked, taskBlocks={})):
            control._mutate(project, lambda manual: None, None)
            control._mutate(project, lambda manual: None, None)
            self.assertEqual(self.fake.call_count, 1)
            self.assertEqual(self.fake.call_args[0][0], "limit")
            self.assertIn("weekly stop reached", self.fake.call_args[0][2])
            # a hook recompute (timeout given) never notifies
            control._mutate(project, lambda manual: None, None, timeout=0.2)
            self.assertEqual(self.fake.call_count, 1)
