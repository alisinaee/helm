"""Tests for hooks install, uninstall and status: merge, idempotence, legacy removal, backups and bad files."""

import json
import os
import shutil
from unittest import mock

from roadmap.services import hooks_install
from tests.unit.test_project_support import HOOK_CMD, ProjectCase, read_text, run_cli, write_json


class HooksInstallTests(ProjectCase):
    def setUp(self):
        super().setUp()
        self.init_and_add()
        self.settings = self.settings_path()

    def install(self, *extra):
        return self.envelope(["hooks", "install", "demo"] + list(extra))

    def events(self):
        return json.loads(read_text(self.settings))["hooks"]

    def test_install_twice_gives_identical_bytes(self):
        code, body = self.install()
        self.assertEqual(code, 0)
        self.assertIs(body["data"]["changed"], True)
        first = read_text(self.settings)
        code, body = self.install()
        self.assertEqual(code, 0)
        self.assertIs(body["data"]["changed"], False)
        self.assertEqual(read_text(self.settings), first)

    def test_second_install_makes_no_new_backup(self):
        self.install()
        self.install()
        self.assertFalse(os.path.isdir(os.path.join(os.environ["ROADMAP_HOME"], "state", "backups", "demo")))

    def test_entries_use_absolute_shim_timeout_and_matchers(self):
        self.install()
        events = self.events()
        post = events["PostToolUse"]
        self.assertEqual(len(post), 1)
        self.assertEqual(post[0]["matcher"], "Agent|Task|Bash")
        self.assertEqual(post[0]["hooks"], [{"type": "command", "command": HOOK_CMD, "timeout": 10}])
        for event in ("SubagentStop", "Stop"):
            self.assertNotIn("matcher", events[event][0])
            self.assertEqual(events[event][0]["hooks"][0]["command"], HOOK_CMD)
        self.assertTrue(os.path.isabs(HOOK_CMD.split(" ")[0]))

    def test_install_preserves_unrelated_settings_and_permissions(self):
        write_json(self.settings, {
            "permissions": {"allow": ["Bash(npm test)"], "deny": []},
            "env": {"KEEP": "1"},
            "hooks": {
                "Stop": [{"hooks": [{"type": "command", "command": "say done", "timeout": 5}]}],
                "PostToolUse": [{"matcher": "Write", "hooks": [{"type": "command", "command": "lint.sh"}]}],
            },
        })
        code, _ = self.install()
        self.assertEqual(code, 0)
        settings = json.loads(read_text(self.settings))
        self.assertEqual(settings["permissions"], {"allow": ["Bash(npm test)"], "deny": []})
        self.assertEqual(settings["env"], {"KEEP": "1"})
        stop = settings["hooks"]["Stop"]
        self.assertEqual(stop[0]["hooks"][0]["command"], "say done")
        self.assertEqual(len(stop), 2)
        post = settings["hooks"]["PostToolUse"]
        self.assertEqual(post[0]["matcher"], "Write")
        self.assertEqual(post[1]["matcher"], "Agent|Task|Bash")

    def test_backup_is_taken_before_changing_an_existing_file(self):
        original = {"permissions": {"allow": []}}
        write_json(self.settings, original)
        code, body = self.install()
        backup_dir = body["data"]["backup"]
        self.assertTrue(os.path.isdir(backup_dir))
        self.assertEqual(json.loads(read_text(os.path.join(backup_dir, "settings.local.json"))), original)

    def test_replace_legacy_removes_only_jobs_auto_entries(self):
        legacy = {"hooks": [{"type": "command", "command": "python3 /old/jobs_auto.py hook"}]}
        write_json(self.settings, {
            "hooks": {
                "PostToolUse": [{"matcher": "Agent", "hooks": [{"type": "command",
                                                                 "command": "python3 /old/jobs_auto.py hook"}]},
                                {"matcher": "Bash", "hooks": [{"type": "command", "command": "make test"}]}],
                "SubagentStop": [{"hooks": legacy["hooks"]}],
            },
        })
        code, _ = self.install()
        after_plain = json.loads(read_text(self.settings))["hooks"]
        self.assertIn("jobs_auto.py", json.dumps(after_plain))
        code, body = self.install("--replace-legacy")
        self.assertEqual(body["data"]["legacyRemoved"], 2)
        after = json.loads(read_text(self.settings))["hooks"]
        self.assertNotIn("jobs_auto.py", json.dumps(after))
        self.assertIn("make test", json.dumps(after))
        self.assertEqual(after["SubagentStop"][0]["hooks"][0]["command"], HOOK_CMD)

    def test_install_keeps_bad_settings_file_untouched(self):
        os.makedirs(os.path.dirname(self.settings), exist_ok=True)
        with open(self.settings, "w", encoding="utf-8") as fh:
            fh.write("{broken")
        code, body = self.install()
        self.assertEqual(code, 5)
        self.assertEqual(read_text(self.settings), "{broken")

    def test_install_refuses_non_object_hooks(self):
        write_json(self.settings, {"hooks": ["nope"]})
        code, _ = self.install()
        self.assertEqual(code, 5)

    def test_install_unknown_project_is_not_found(self):
        code, _ = self.envelope(["hooks", "install", "ghost"])
        self.assertEqual(code, 3)


class HooksUninstallStatusTests(ProjectCase):
    def setUp(self):
        super().setUp()
        self.init_and_add()
        self.settings = self.settings_path()

    def test_status_before_install_reports_missing(self):
        code, out, _ = run_cli(["hooks", "status", "demo"])
        self.assertEqual(code, 0)
        self.assertIn("missing", out)
        code, body = self.envelope(["hooks", "status", "demo"])
        self.assertIs(body["data"]["installed"], False)
        self.assertEqual({r["state"] for r in body["data"]["events"].values()}, {"missing"})

    def test_status_after_install_reports_installed(self):
        run_cli(["hooks", "install", "demo"])
        code, body = self.envelope(["hooks", "status", "demo"])
        self.assertEqual(code, 0)
        self.assertIs(body["data"]["installed"], True)
        self.assertEqual({r["state"] for r in body["data"]["events"].values()}, {"installed"})

    def test_status_flags_an_entry_with_another_path_as_stale(self):
        write_json(self.settings, {"hooks": {"Stop": [{"hooks": [{"type": "command",
                                                                  "command": "/elsewhere/bin/roadmap hook"}]}]}})
        code, body = self.envelope(["hooks", "status", "demo"])
        self.assertEqual(body["data"]["events"]["Stop"]["state"], "stale")

    def test_uninstall_removes_only_our_entries(self):
        write_json(self.settings, {"permissions": {"allow": ["x"]},
                                   "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "say"}]}]}})
        run_cli(["hooks", "install", "demo"])
        code, body = self.envelope(["hooks", "uninstall", "demo"])
        self.assertEqual(code, 0)
        self.assertEqual(body["data"]["removed"], 5)  # one entry per event: PreToolUse, SessionStart and the 3 older
        settings = json.loads(read_text(self.settings))
        self.assertEqual(settings, {"permissions": {"allow": ["x"]},
                                    "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "say"}]}]}})

    def test_uninstall_drops_the_hooks_key_it_added(self):
        run_cli(["hooks", "install", "demo"])
        run_cli(["hooks", "uninstall", "demo"])
        self.assertEqual(json.loads(read_text(self.settings)), {})

    def test_uninstall_without_a_settings_file_changes_nothing(self):
        code, body = self.envelope(["hooks", "uninstall", "demo"])
        self.assertEqual(code, 0)
        self.assertEqual(body["data"]["removed"], 0)
        self.assertFalse(os.path.exists(self.settings))

    def test_install_then_uninstall_then_install_restores_same_bytes(self):
        run_cli(["hooks", "install", "demo"])
        first = read_text(self.settings)
        run_cli(["hooks", "uninstall", "demo"])
        run_cli(["hooks", "install", "demo"])
        self.assertEqual(read_text(self.settings), first)


class SharedHelperTests(ProjectCase):
    def test_shim_path_is_the_repo_bin_roadmap(self):
        self.assertEqual(hooks_install.shim_path(), os.path.join(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.realpath(hooks_install.__file__)))), "bin", "roadmap"))


class SettingsSafetyTests(ProjectCase):
    def setUp(self):
        super().setUp()
        self.init_and_add()
        self.settings = self.settings_path()
        self.claude = os.path.dirname(self.settings)
        self.outside = os.path.join(self.tmp, "outside")
        os.makedirs(self.outside)
        self.target = os.path.join(self.outside, "settings.local.json")
        write_json(self.target, {"env": {"KEEP": "1"}})
        self.before = read_text(self.target)

    def test_symlinked_claude_folder_is_refused_and_the_target_is_untouched(self):
        if os.path.isdir(self.claude):
            shutil.rmtree(self.claude)
        os.symlink(self.outside, self.claude)
        code, _ = self.envelope(["hooks", "install", "demo"])
        self.assertNotEqual(code, 0)
        self.assertEqual(read_text(self.target), self.before)
        self.assertEqual(os.listdir(self.outside), ["settings.local.json"])

    def test_settings_changed_by_claude_between_read_and_replace_are_kept(self):
        write_json(self.settings, {"permissions": {"allow": ["Bash(ls)"]}})
        real_read = hooks_install._read_raw
        calls = []

        def racing_read(path):
            calls.append(path)
            if len(calls) == 2:  # Claude Code saves its own settings after our first read
                write_json(path, {"permissions": {"allow": ["Bash(ls)"]}, "env": {"NEW": "1"}})
            return real_read(path)

        with mock.patch.object(hooks_install, "_read_raw", side_effect=racing_read):
            code, _ = self.envelope(["hooks", "install", "demo"])
        self.assertEqual(code, 0)
        data = json.loads(read_text(self.settings))
        self.assertEqual(data["env"], {"NEW": "1"})
        self.assertIn("Stop", data["hooks"])
