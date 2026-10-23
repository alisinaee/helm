"""R2 review regressions (docs/reviews/R2-wp22-cursor-auto.md): one test per finding, each in a temp ROADMAP_HOME.

1 the gate resolves the project from the payload cwd only; 2 a stale limit block is recomputed before a deny, a failed
recompute fails open and drops the sentinel, and a limit write and the control file share one lock; 3 the shim derives
the state folder like paths.state_dir(); 4 while blocked only inbox, status, ask and rules show run, and any non-empty
CLAUDECODE is an agent; 5 rules sync refuses foreign text between the markers and a changed CLAUDE.md; 6 a budget raise
is compared with the limit read under the folder lock; 7 any truthy stop_hook_active and the pickup count per queue;
8 prompts, answers and secrets never reach logs or session context.
"""

import argparse
import datetime
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from roadmap.errors import RoadmapError
from roadmap.commands import hooks as hooks_cmd
from roadmap.services import agentguard, budget, control, hooks, hooks_install, jobs, limits_v2, questions, rules
from roadmap.store import config, lock, paths
from tests.unit.test_control_support import ControlCase, read_json, write_json
from tests.unit.test_hook_enforce import MOMENT, SHIM

TAIL = ". Run roadmap inbox, then end your turn."


class Base(ControlCase):
    def fire(self, tool="Edit", tool_input=None, now=None, cwd=None, env_project=None, clock=None):
        payload = {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input or {},
                   "cwd": self.project if cwd is None else cwd}
        saved = os.environ.get("ROADMAP_PROJECT")
        if env_project is None:
            os.environ["ROADMAP_PROJECT"] = "demo"
        else:
            os.environ["ROADMAP_PROJECT"] = env_project
        try:
            return hooks.run_hook(json.dumps(payload), now=(MOMENT.timestamp() if now is None else now), clock=clock)
        finally:
            if saved is None:
                os.environ.pop("ROADMAP_PROJECT", None)
            else:
                os.environ["ROADMAP_PROJECT"] = saved

    def reason(self, reply):
        self.assertIsNotNone(reply)
        self.assertEqual(reply["hookSpecificOutput"]["permissionDecision"], "deny")
        return reply["hookSpecificOutput"]["permissionDecisionReason"]

    def sentinel(self):
        return os.path.exists(control.sentinel_path("demo"))

    def log_text(self):
        path = os.path.join(os.environ["ROADMAP_HOME"], "logs", "hooks.log")
        if not os.path.exists(path):
            return ""
        with open(path, encoding="utf-8") as fh:
            return fh.read()


class Finding1ProjectFromCwdOnly(Base):
    def setUp(self):
        super().setUp()
        other = self.make_project("other")
        os.makedirs(os.path.join(other, "docs"), exist_ok=True)
        config.add_project("Other", other)

    def test_an_ambient_project_variable_does_not_pick_the_project(self):
        control.stop("demo", now=MOMENT)
        self.reason(self.fire("Edit", env_project="other"))  # cwd is demo: denied for demo

    def test_a_running_project_named_by_the_variable_does_not_lift_a_stop_in_the_cwd(self):
        control.stop("demo", now=MOMENT)
        other = config.get_project("other")["path"]
        self.assertIsNone(self.fire("Edit", env_project="demo", cwd=other))  # cwd is other: not stopped


class Finding2StaleLimitAndOneLock(Base):
    def test_a_limit_that_has_moved_is_recomputed_before_the_deny(self):
        limits_v2.set_window("week", {"on": True, "mode": "cap", "value": 100})
        self.set_usage(120)
        control.recompute("demo", now=MOMENT)
        self.assertTrue(self.sentinel())
        self.set_usage(50, updated=MOMENT.isoformat())  # the usage window reset, no recompute yet
        self.assertIsNone(self.fire("Edit"))
        self.assertFalse(self.sentinel())
        self.assertIsNone(control.read_state("demo")["block"])

    def test_a_recompute_that_fails_fails_open_and_removes_the_stale_sentinel(self):
        limits_v2.set_window("week", {"on": True, "mode": "cap", "value": 100})
        self.set_usage(120)
        control.recompute("demo", now=MOMENT)
        self.assertTrue(self.sentinel())
        with mock.patch("roadmap.services.control.recompute", side_effect=RoadmapError("locked", "busy", 4)):
            self.assertIsNone(self.fire("Edit"))
        self.assertFalse(self.sentinel())

    def test_an_expired_override_is_checked_against_a_fresh_recompute(self):
        limits_v2.set_window("week", {"on": True, "mode": "cap", "value": 100})
        self.set_usage(120)
        control.override("demo", 1, now=MOMENT)
        self.set_usage(120, updated=(MOMENT + datetime.timedelta(hours=2)).isoformat())
        self.reason(self.fire("Edit", now=(MOMENT + datetime.timedelta(hours=2)).timestamp()))

    def test_a_budget_limit_and_the_control_file_change_under_one_data_lock(self):
        seen = []
        real = control._mutate

        def probe(project, change, now, timeout=None):
            try:
                with lock.locked(self.docs, timeout=0):
                    seen.append("free")
            except RoadmapError:
                seen.append("held")
            return real(project, change, now, timeout=timeout)

        with mock.patch("roadmap.services.control._mutate", side_effect=probe):
            control.set_budget_limit("demo", "project", None, 500, now=MOMENT)
        self.assertEqual(seen, ["held"])
        self.assertEqual(budget.get(self.docs)["limits"]["project"], 500)


class Finding3ShimStateFolder(Base):
    def setUp(self):
        super().setUp()
        self.fakebin = os.path.join(self.tmp, "fakebin")
        os.makedirs(self.fakebin)
        self.marker = os.path.join(self.tmp, "python-started")
        fake = os.path.join(self.fakebin, "python3")
        with open(fake, "w", encoding="utf-8") as fh:
            fh.write("#!/bin/sh\ntouch '%s'\nexit 3\n" % self.marker)
        os.chmod(fake, 0o755)

    def shim(self, home_value, state_root):
        os.makedirs(os.path.join(state_root, "state"), exist_ok=True)
        open(os.path.join(state_root, "state", "block-demo"), "w").close()
        env = {"PATH": self.fakebin + os.pathsep + "/usr/bin:/bin", "HOME": os.environ["HOME"],
               "ROADMAP_HOME": home_value}
        proc = subprocess.run([SHIM, "hook", "pre"], input="{}", capture_output=True, text=True, env=env, timeout=30)
        return proc.returncode, os.path.exists(self.marker)

    def test_a_home_with_a_tilde_finds_the_sentinel(self):
        fake_home = os.path.join(self.tmp, "fakehome")
        os.makedirs(fake_home)
        os.environ["HOME"] = fake_home
        code, ran = self.shim("~/rb-home", os.path.join(fake_home, "rb-home"))
        self.assertTrue(ran)
        self.assertEqual(code, 3)

    def test_padding_around_the_home_is_stripped_before_the_test(self):
        root = os.path.join(self.tmp, "padded")
        code, ran = self.shim("  " + root + "  ", root)
        self.assertTrue(ran)
        self.assertEqual(code, 3)

    def test_a_relative_or_unnormalised_home_is_left_to_python(self):
        root = os.path.join(self.tmp, "norm")
        code, ran = self.shim(root + "/./", root)
        self.assertTrue(ran)


class Finding4BlockedAllowlist(Base):
    def setUp(self):
        super().setUp()
        self._env("CLAUDECODE", None)

    def bash(self, command, now=None):
        return self.fire("Bash", {"command": command}, now=now)

    def test_while_stopped_only_inbox_status_ask_and_rules_show_run(self):
        control.stop("demo", now=MOMENT)
        self.assertIsNone(self.bash("roadmap inbox"))
        self.assertIsNone(self.bash("roadmap status --json"))
        self.assertIsNone(self.bash('roadmap ask "is it ok?"'))
        self.assertIsNone(self.bash("roadmap rules show --for P0.1"))

    def test_while_stopped_loosening_and_other_roadmap_commands_are_denied(self):
        control.stop("demo", now=MOMENT)
        for command in ("roadmap resume", "roadmap override --hours 2", "roadmap limit budget project 99999",
                        "roadmap phase approve P0", "roadmap rules add all do x", "roadmap rules rm R1",
                        "roadmap rules sync", "roadmap hooks uninstall demo", "roadmap usage sync",
                        "roadmap task done P0.1"):
            self.reason(self.bash(command))

    def test_a_chained_roadmap_command_is_denied_while_blocked(self):
        control.stop("demo", now=MOMENT)
        self.reason(self.bash("roadmap status; roadmap resume"))

    def test_a_limit_block_applies_the_same_allowlist(self):
        limits_v2.set_window("week", {"on": True, "mode": "cap", "value": 100})
        self.set_usage(120)
        control.recompute("demo", now=MOMENT)
        self.assertIsNone(self.bash("roadmap status"))
        self.reason(self.bash("roadmap resume"))

    def test_any_non_empty_claudecode_is_an_agent(self):
        self.assertTrue(agentguard.is_agent(None, {"CLAUDECODE": "true"}))
        with self.assertRaises(RoadmapError) as ctx:
            agentguard.refuse_if_agent("control.resume", None, {"CLAUDECODE": "yes"})
        self.assertEqual(ctx.exception.code, "agent_refused")

    def test_uninstalling_the_hooks_is_refused_from_an_agent_and_leaves_the_settings(self):
        hooks_install.install("demo")
        settings = os.path.join(self.project, ".claude", "settings.local.json")
        before = read_json(settings)
        args = argparse.Namespace(project="demo", json=False)
        with mock.patch.dict(os.environ, {"CLAUDECODE": "1"}):
            with self.assertRaises(RoadmapError) as ctx:
                hooks_cmd._uninstall(args)
        self.assertEqual(ctx.exception.code, "agent_refused")
        self.assertEqual(read_json(settings), before)
        self.assertTrue(hooks_install.status("demo")["installed"])


class Finding5RulesSync(Base):
    def setUp(self):
        super().setUp()
        self._env("CLAUDECODE", None)
        with open(os.path.join(self.docs, "rules.txt"), "w", encoding="utf-8") as fh:
            fh.write("R1 all do | Run the tests before you finish.\n")
        self.claude = os.path.join(self.project, "CLAUDE.md")
        self.proj = config.get_project("demo")

    def test_foreign_text_between_the_markers_is_refused_and_kept(self):
        original = ("# Notes\n" + rules.BEGIN + "\nMy own instructions, not generated.\n" + rules.END + "\n")
        with open(self.claude, "w", encoding="utf-8") as fh:
            fh.write(original)
        with self.assertRaises(RoadmapError) as ctx:
            rules.sync(self.proj, self.docs)
        self.assertEqual(ctx.exception.code, "invalid_data")
        with open(self.claude, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), original)

    def test_generated_lines_between_the_markers_are_replaced(self):
        with open(self.claude, "w", encoding="utf-8") as fh:
            fh.write("# Notes\n" + rules.BEGIN + "\n" + rules.INTRO + "\n- R0 all do | old\n" + rules.END + "\n")
        result = rules.sync(self.proj, self.docs)
        self.assertTrue(result["written"])
        with open(self.claude, encoding="utf-8") as fh:
            self.assertIn("- R1 all do | Run the tests before you finish.", fh.read())

    def test_a_claude_md_changed_between_read_and_replace_is_not_overwritten(self):
        with open(self.claude, "w", encoding="utf-8") as fh:
            fh.write("# Notes\n")
        real = rules._read_bytes
        edited = b"# Notes\nedited by a person above the block\n"
        calls = []

        def racing(path):
            calls.append(path)
            if len(calls) == 2:  # the re-read before the replace sees a person's edit
                with open(path, "wb") as fh:
                    fh.write(edited)
            return real(path)

        with mock.patch.object(rules, "_read_bytes", side_effect=racing):
            with self.assertRaises(RoadmapError) as ctx:
                rules.sync(self.proj, self.docs)
        self.assertEqual(ctx.exception.code, "conflict")
        with open(self.claude, "rb") as fh:
            self.assertEqual(fh.read(), edited)


class Finding6BudgetRaiseUnderLock(Base):
    def test_an_agent_cannot_raise_a_limit_a_person_set_in_the_meantime(self):
        control.set_budget_limit("demo", "project", None, 10, now=MOMENT)  # the person's cap
        with mock.patch.dict(os.environ, {"CLAUDECODE": "1"}):
            with self.assertRaises(RoadmapError) as ctx:
                control.set_budget_limit("demo", "project", None, 99999, now=MOMENT)
        self.assertEqual(ctx.exception.code, "agent_refused")
        self.assertEqual(budget.get(self.docs)["limits"]["project"], 10)

    def test_an_agent_may_lower_a_limit(self):
        control.set_budget_limit("demo", "project", None, 100, now=MOMENT)
        with mock.patch.dict(os.environ, {"CLAUDECODE": "1"}):
            control.set_budget_limit("demo", "project", None, 50, now=MOMENT)
        self.assertEqual(budget.get(self.docs)["limits"]["project"], 50)


class Finding7PickupCap(Base):
    def stop_event(self, session="s1", active=False):
        return hooks.run_hook(json.dumps({"hook_event_name": "Stop", "cwd": self.project, "session_id": session,
                                          "stop_hook_active": active}), now=MOMENT.timestamp())

    def test_a_truthy_stop_hook_active_of_any_type_never_blocks(self):
        from roadmap.services import queue
        queue.enqueue(self.docs, "P0.1", by="lead", now=MOMENT)
        self.assertIsNone(self.stop_event(active=1))
        self.assertIsNone(self.stop_event(active="true"))

    def test_the_count_survives_a_new_session_id_on_each_continuation(self):
        from roadmap.services import queue
        queue.enqueue(self.docs, "P0.1", by="lead", now=MOMENT)
        blocks = 0
        for i in range(6):
            if self.stop_event(session="new-%d" % i) is not None:
                blocks += 1
            queue.dequeue(self.docs, "P0.1")
            queue.enqueue(self.docs, "P0.1", by="lead", now=MOMENT + datetime.timedelta(minutes=i + 1))
        self.assertEqual(blocks, 3)


class Finding8NoFreeTextInLogs(Base):
    def setUp(self):
        super().setUp()
        cfg = dict(read_json(os.path.join(self.docs, "roadmap.config.json")), hookDetectors=["agent", "cursor"])
        write_json(os.path.join(self.docs, "roadmap.config.json"), cfg)

    def test_a_prompt_and_its_secret_stay_out_of_the_log_and_the_job_title(self):
        secret = "sk-abcdefghijklmnop1234"
        prompt = "Please fix P0.1 and use token=" + secret + " then write a very long essay about everything " * 3
        payload = {"hook_event_name": "PostToolUse", "cwd": self.project, "tool_name": "Agent",
                   "tool_input": {"model": "haiku", "description": "fix P0.1", "prompt": prompt},
                   "tool_response": "agentId: abc12345678"}
        hooks.run_hook(json.dumps(payload), now=MOMENT.timestamp())
        log = self.log_text()
        self.assertNotIn(secret, log)
        self.assertNotIn("very long essay", log)
        self.assertIn("P0.1", log)
        titles = [j["title"] for j in jobs.list_jobs(self.docs)]
        self.assertTrue(titles)
        self.assertTrue(all(len(t) <= len("haiku: ") + 60 for t in titles))

    def test_a_cursor_prompt_is_summarised_and_redacted_in_the_title_only(self):
        command = 'cursor-review2.sh /tmp/out.md "check P0.1 with password=hunter2hunter2 and more text here"'
        payload = {"hook_event_name": "PostToolUse", "cwd": self.project, "tool_name": "Bash",
                   "tool_input": {"command": command}, "tool_response": ""}
        hooks.run_hook(json.dumps(payload), now=MOMENT.timestamp())
        self.assertNotIn("hunter2", self.log_text())

    def test_open_and_answered_questions_are_listed_by_id_and_task_only(self):
        questions.ask(self.docs, "P0.1", "The database password is hunter2?", now=MOMENT)
        q = questions.list_questions(self.docs)[0]
        questions.answer(self.docs, q["id"], "hunter2", now=MOMENT)
        lines = control.pending_lines(self.docs, limit=6, now=MOMENT)
        joined = "\n".join(lines)
        self.assertNotIn("hunter2", joined)
        self.assertNotIn("password", joined)
        self.assertIn("P0.1", joined)


class SummaryTests(unittest.TestCase):
    def test_summary_redacts_secret_shapes_and_caps_the_length(self):
        self.assertEqual(hooks._summary("use sk-abcdefghijk12345 now"), "use [redacted] now")
        self.assertEqual(hooks._summary("x " * 80), ("x " * 80).strip()[:60])


if __name__ == "__main__":
    unittest.main()
