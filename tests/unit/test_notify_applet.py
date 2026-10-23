"""R11.163: the Helm.app applet path, the per-kind switches, the test notification and the question text. Every
subprocess call goes through an injected runner; no real osascript, open, osacompile or sips runs here."""

import json
import os
from unittest import mock

from roadmap.services import notify, questions
from roadmap.store import atomic, config, paths
from tests.unit.test_store_support import HomeCase


class AppletRunner:
    """Records argv lists and fakes the build: osacompile makes the bundle, sips makes the icns."""

    def __init__(self, fail=None):
        self.calls = []
        self.fail = fail

    def __call__(self, argv):
        self.calls.append(argv)
        if argv[0] == self.fail:
            return False
        if argv[0] == "osacompile":
            res = os.path.join(argv[2], "Contents", "Resources")
            os.makedirs(res)
            with open(os.path.join(argv[2], "Contents", "Info.plist"), "wb") as handle:
                import plistlib
                plistlib.dump({"CFBundleName": "applet"}, handle)
        if argv[0] == "sips":
            with open(argv[-1], "wb") as handle:
                handle.write(b"icns")
        return True

    def names(self):
        return [c[0] for c in self.calls]


class AppletTests(HomeCase):
    def test_first_call_builds_the_applet_then_opens_it_with_the_message_file(self):
        run = AppletRunner()
        self.assertTrue(notify.notify("start", "Helm · split-net", "Hi", "demo", runner=run, now=1000, applet=True))
        self.assertEqual(run.names(), ["osacompile", "sips", "codesign", "open"])
        app = os.path.join(paths.state_dir(), "Helm.app")
        self.assertEqual(run.calls[-1], ["open", "-g", "-j", "-a", app])
        msg = atomic.read_json(os.path.join(paths.state_dir(), notify.MESSAGE_FILE))
        self.assertEqual(msg, {"title": "Helm · split-net", "body": "Hi"})
        import plistlib
        with open(os.path.join(app, "Contents", "Info.plist"), "rb") as handle:
            info = plistlib.load(handle)
        self.assertEqual(info["CFBundleIdentifier"], "dev.helm.notify")
        self.assertEqual(info["CFBundleName"], "Helm")
        self.assertTrue(os.path.exists(os.path.join(app, "Contents", "Resources", "applet.icns")))

    def test_the_applet_is_cached_and_rebuilt_when_the_stamp_changes(self):
        run = AppletRunner()
        notify.notify("start", "T", "B", "demo", runner=run, now=1000, applet=True)
        run.calls.clear()
        notify.notify("start", "T", "B", "demo", runner=run, now=2000, applet=True)
        self.assertEqual(run.names(), ["open"])
        run.calls.clear()
        with mock.patch.object(notify, "APPLET_VERSION", 99):
            notify.notify("start", "T", "B", "demo", runner=run, now=3000, applet=True)
        self.assertEqual(run.names()[0], "osacompile")

    def test_a_failed_build_falls_back_to_osascript(self):
        run = AppletRunner(fail="osacompile")
        self.assertTrue(notify.notify("start", "T", "B", "demo", runner=run, now=1000, applet=True))
        self.assertEqual(run.calls[-1][:2], ["osascript", "-e"])
        self.assertNotIn("open", run.names())

    def test_a_failed_open_falls_back_to_osascript(self):
        run = AppletRunner(fail="open")
        self.assertTrue(notify.notify("start", "T", "B", "demo", runner=run, now=1000, applet=True))
        self.assertEqual(run.names()[-1], "osascript")

    def test_an_injected_runner_alone_keeps_the_osascript_path(self):
        run = AppletRunner()
        notify.notify("start", "T", "B", "demo", runner=run, now=1000)
        self.assertEqual(run.names(), ["osascript"])

    def test_the_script_reads_a_json_file_and_never_embeds_the_text(self):
        script = notify._applet_script("/x/notify-message.json")
        self.assertIn("plutil -extract title raw", script)
        self.assertIn('"/x/notify-message.json"', script)


class KindTests(HomeCase):
    def setUp(self):
        super().setUp()
        self.calls = []

    def runner(self, argv):
        self.calls.append(argv)
        return True

    def test_a_kind_switched_off_shows_nothing_and_the_others_still_do(self):
        notify.set_kind("start", False)
        self.assertFalse(notify.notify("start", "T", "B", "demo", runner=self.runner, now=1000))
        self.assertTrue(notify.notify("question", "T", "B", "demo", runner=self.runner, now=1000))
        self.assertEqual(len(self.calls), 1)
        saved = config.load()
        self.assertEqual(saved["notifyKinds"], {"start": False})

    def test_settings_lists_every_kind_on_by_default_and_refuses_an_unknown_one(self):
        view = notify.settings()
        self.assertTrue(view["enabled"])
        self.assertEqual([k["id"] for k in view["kinds"]],
                         ["question", "start", "limit", "head-needs-you", "head-review"])
        self.assertTrue(all(k["on"] for k in view["kinds"]))
        with self.assertRaises(ValueError):
            notify.set_kind("nope", True)

    def test_master_switch_round_trips(self):
        self.assertFalse(notify.set_enabled(False)["enabled"])
        self.assertFalse(notify.notify("start", "T", "B", "demo", runner=self.runner, now=1000))
        self.assertTrue(notify.set_enabled(True)["enabled"])

    def test_test_notification_bypasses_the_rate_limit_but_not_the_master_switch(self):
        self.assertTrue(notify.send_test(runner=self.runner))
        self.assertTrue(notify.send_test(runner=self.runner))
        self.assertEqual(len(self.calls), 2)
        self.assertIn("Test", self.calls[0][2])
        notify.set_enabled(False)
        self.assertFalse(notify.send_test(runner=self.runner))
        self.assertEqual(len(self.calls), 2)

    def test_test_notification_ignores_a_kind_switch(self):
        notify.set_kind("start", False)
        self.assertTrue(notify.send_test(runner=self.runner))


class TextTests(HomeCase):
    def test_question_text_names_the_full_project_in_the_title(self):
        project = self.make_project("split-net")
        config.add_project("split-net", project)
        data = os.path.join(project, "docs")
        os.makedirs(data)
        with mock.patch.object(notify, "notify") as fake, \
                mock.patch.object(notify, "_under_tests", return_value=False), \
                mock.patch.object(notify, "_macos", return_value=True):
            questions.ask(data, "P0.1", "go?", opts=["y", "n"], default="n", block=True)
        args = fake.call_args[0]
        self.assertEqual(args[1], "Helm · split-net")
        self.assertEqual(args[2], "Q1 on P0.1 needs you. Answer it in Helm (Inbox) or run: roadmap inbox")
        self.assertEqual(args[3], "split-net")

    def test_a_long_project_name_is_not_cut_at_the_summary_limit(self):
        name = "n" * 70
        self.assertEqual(notify.display_name({"name": name, "id": "x"}), name)
