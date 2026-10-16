"""Gap tests for the desktop notifications (services/notify.py), the watch command (commands/watch.py) and the skill
templates command (commands/skills.py): the platform and osascript helpers, the once-a-minute log, a config error, the
title fallback, the project lookup, the body callback failure, the watch bounds and a file change with no news, the
answer cap, the template folder missing, and the plain-text output of skills list and install.

Everything runs under a temp ROADMAP_HOME with temp project folders. osascript is never run: notify is driven through
an injected runner, and the platform checks are patched. Nothing touches the real home or the launchd service."""

import json
import os
import subprocess
from unittest import mock

from roadmap.commands import skills, watch
from roadmap.errors import RoadmapError
from roadmap.services import notify, questions, queue, records
from roadmap.store import config
from tests.unit.test_jobs_support import run_cli
from tests.unit.test_project_support import ProjectCase
from tests.unit.test_store_support import HomeCase
from tests.unit.test_watch import FakeTime


def _json(argv):
    code, out, err = run_cli(argv + ["--json"])
    return code, json.loads(out) if out.strip() else None, err


class NotifyHelperTests(HomeCase):
    def setUp(self):
        super().setUp()
        self.calls = []
        saved = list(notify._last_log)
        self.addCleanup(lambda: notify._last_log.__setitem__(slice(None), saved))

    def runner(self, argv):
        self.calls.append(argv)
        return True

    def test_macos_is_true_only_on_darwin(self):
        with mock.patch.object(notify.sys, "platform", "darwin"):
            self.assertTrue(notify._macos())
        with mock.patch.object(notify.sys, "platform", "linux"):
            self.assertFalse(notify._macos())

    def test_run_osascript_is_true_only_for_exit_zero_and_takes_an_argv_list(self):
        argv = ["osascript", "-e", 'display notification "B" with title "T"']
        with mock.patch.object(notify.subprocess, "run", return_value=subprocess.CompletedProcess(argv, 0)) as run:
            self.assertTrue(notify._run_osascript(argv))
        self.assertIsInstance(run.call_args[0][0], list)
        self.assertNotIn("shell", run.call_args[1])
        with mock.patch.object(notify.subprocess, "run", return_value=subprocess.CompletedProcess(argv, 1)):
            self.assertFalse(notify._run_osascript(argv))

    def test_a_second_problem_within_a_minute_is_not_logged_again(self):
        notify._last_log[0] = 0.0
        with mock.patch.object(notify.log, "warning") as warning, \
                mock.patch.object(notify.time, "time", side_effect=[1000.0, 1010.0, 1100.0]):
            notify._log_once("first")
            notify._log_once("within the minute")
            notify._log_once("after the minute")
        self.assertEqual(warning.call_count, 2)
        self.assertEqual(warning.call_args_list[0][0][1], "first")
        self.assertEqual(warning.call_args_list[1][0][1], "after the minute")

    def test_a_config_that_cannot_be_read_turns_notifications_off(self):
        with mock.patch.object(notify.config, "load", side_effect=ValueError("broken config")):
            self.assertFalse(notify._enabled())
            self.assertFalse(notify.notify("start", "T", "B", "demo", runner=self.runner, now=1000))
        self.assertEqual(self.calls, [])

    def test_an_empty_or_missing_title_falls_back_to_the_app_name(self):
        notify.notify("start", "", "B", "demo", runner=self.runner, now=1000)
        notify.notify("question", None, "B", "demo", runner=self.runner, now=1000)
        self.assertEqual(len(self.calls), 2)
        for argv in self.calls:
            self.assertIn('with title "Helm"', argv[2])

    def test_project_of_is_none_for_a_folder_that_is_not_registered(self):
        self.assertIsNone(notify.project_of(os.path.join(self.tmp, "nowhere", "docs")))


class NotifyDirTests(HomeCase):
    def setUp(self):
        super().setUp()
        self.project = self.make_project("demo")
        config.add_project("Demo", self.project)
        self.data = os.path.join(self.project, "docs")
        os.makedirs(self.data)

    def test_without_a_runner_under_the_test_runner_it_returns_before_looking_up_the_project(self):
        with mock.patch.object(notify, "project_of", side_effect=AssertionError("must not look up")):
            self.assertFalse(notify.notify_dir(self.data, "start", "T", lambda p: "B"))

    def test_an_unregistered_folder_is_not_notified(self):
        runner = mock.Mock(return_value=True)
        other = os.path.join(self.tmp, "elsewhere", "docs")
        self.assertFalse(notify.notify_dir(other, "start", "T", lambda p: "B", runner=runner, now=1000))
        runner.assert_not_called()

    def test_a_body_callback_that_raises_is_logged_and_returns_false(self):
        runner = mock.Mock(return_value=True)

        def broken(project):
            raise ValueError("no body")

        with mock.patch.object(notify, "_log_once") as logged:
            self.assertFalse(notify.notify_dir(self.data, "start", "T", broken, runner=runner, now=1000))
        logged.assert_called_once_with("ValueError")
        runner.assert_not_called()


class WatchGapTests(HomeCase):
    def setUp(self):
        super().setUp()
        self.project = self.make_project("demo")
        config.add_project("Demo", self.project)
        self.data = os.path.join(self.project, "docs")
        os.makedirs(self.data)
        self.fake = FakeTime()
        self.bumps = 0

    def bump(self, name):
        self.bumps += 1
        stamp = 1e9 + 100 + self.bumps
        os.utime(os.path.join(self.data, name), (stamp, stamp))

    def run_watch(self, max_s, during=None):
        def sleep(seconds):
            if during is not None:
                during(len(self.fake.sleeps))
            self.fake.sleep(seconds)

        return watch.wait(self.data, max_s, sleep=sleep, clock=self.fake.clock)

    def test_a_max_above_a_day_is_a_usage_error_before_any_wait(self):
        code, _, err = run_cli(["watch", "--project", "demo", "--max", str(watch.MAX_LIMIT_S + 1)])
        self.assertEqual(code, 2)
        self.assertIn("--max takes 1 to 86400 seconds", err)

    def test_a_file_change_with_no_news_keeps_polling_until_the_timeout(self):
        records.save("queue", self.data, queue.FILE, {"schemaVersion": 1, "entries": []})

        def touch(poll):
            if poll == 0:
                self.bump(queue.FILE)

        event = self.run_watch(max_s=5, during=touch)
        self.assertEqual(event, {"event": "timeout", "line": "timeout"})
        self.assertEqual(self.fake.sleeps, [2, 2, 1])

    def test_a_long_answer_is_cut_to_sixty_characters_on_the_line(self):
        questions.ask(self.data, "P1.0", "explain?", opts=[], now=None)
        questions.ask(self.data, "P1.0", "why?", opts=[], now=None)

        def answer(poll):
            if poll == 0:
                questions.answer(self.data, "Q2", "x" * 100)
                self.bump(questions.FILE)

        event = self.run_watch(max_s=10, during=answer)
        self.assertEqual(event["event"], "answer")
        self.assertEqual(event["line"], "answer Q2 " + "x" * watch.ANSWER_MAX)


class SkillsGapTests(ProjectCase):
    def setUp(self):
        super().setUp()
        self.target = os.path.join(self.tmp, "proj")
        os.makedirs(self.target)
        self.dest = os.path.join(os.path.realpath(self.target), ".claude", "skills")
        self.missing_templates = os.path.join(self.tmp, "no-templates")

    def test_templates_is_empty_when_the_template_folder_is_missing(self):
        with mock.patch.object(skills, "TEMPLATE_DIR", self.missing_templates):
            self.assertEqual(skills.templates(), [])

    def test_install_with_no_templates_is_not_found(self):
        with mock.patch.object(skills, "TEMPLATE_DIR", self.missing_templates):
            code, body, _ = _json(["skills", "install", "--target", self.target])
        self.assertEqual(code, 3)
        self.assertEqual(body["error"]["code"], "not_found")

    def test_plain_list_says_not_installed_for_a_project_without_the_skills(self):
        self.init_and_add()
        code, out, _ = run_cli(["skills", "list", "--project", "demo"])
        self.assertEqual(code, 0)
        lines = [line for line in out.splitlines() if line.strip()]
        self.assertEqual(len(lines), 2)
        self.assertTrue(all(line.endswith("not installed") for line in lines), lines)

    def test_plain_dry_run_prints_a_conflict_line_and_writes_nothing(self):
        os.makedirs(os.path.join(self.dest, "roadmap-lead"))
        code, out, _ = run_cli(["skills", "install", "--target", self.target, "--dry-run"])
        self.assertEqual(code, 0)
        self.assertIn("conflict: %s exists (not written; add --yes)" % os.path.join(self.dest, "roadmap-lead"), out)
        self.assertIn("dry run: nothing written", out)
        self.assertFalse(os.path.exists(os.path.join(self.dest, "roadmap-worker")))

    def test_plain_yes_prints_the_backup_line_then_the_replace_line(self):
        lead = os.path.join(self.dest, "roadmap-lead")
        os.makedirs(lead)
        code, out, err = run_cli(["skills", "install", "--target", self.target, "--yes"])
        self.assertEqual(code, 0, err)
        lines = out.splitlines()
        backup = [line for line in lines if line.startswith("backup: " + lead + " -> ")]
        self.assertEqual(len(backup), 1, out)
        self.assertIn(".bak-", backup[0])
        self.assertIn("replace: " + lead, lines)
        self.assertTrue(os.path.isfile(os.path.join(lead, "SKILL.md")))

    def test_plain_install_prints_create_without_the_would_prefix(self):
        code, out, _ = run_cli(["skills", "install", "--target", self.target])
        self.assertEqual(code, 0)
        self.assertIn("create: " + os.path.join(self.dest, "roadmap-lead"), out)
        self.assertNotIn("would", out)
        self.assertNotIn("dry run", out)

    def test_a_conflict_with_a_project_suggests_the_install_with_that_project(self):
        self.init_and_add()
        code, _, err = run_cli(["skills", "install", "--project", "demo"])
        self.assertEqual(code, 0, err)
        code, body, _ = _json(["skills", "install", "--project", "demo"])
        self.assertEqual(code, 4)
        self.assertEqual(body["error"]["code"], "conflict")
        self.assertIn("--project demo", body["error"]["next"])


if __name__ == "__main__":
    import unittest
    unittest.main()
