"""R11.2 panel to head (docs/PANEL-TO-HEAD.md): the panel ledger (record, take, ack, state with sent / seen / acted),
the hook delivery (UserPromptSubmit, PostToolUse, Stop block, SessionStart; once only; never to a subagent; off with
head.panel false), roadmap watch waking on a panel line, and `roadmap head panel`. Temp ROADMAP_HOME only."""

import datetime
import json
import os

from roadmap.commands import watch
from roadmap.services import activity, headpanel, hooks
from tests.unit.test_control_support import ControlCase, read_json, write_json
from tests.unit.test_jobs_support import run_cli

MOMENT = datetime.datetime(2026, 10, 17, 9, 30, tzinfo=datetime.timezone.utc)


class PanelCase(ControlCase):
    def setUp(self):
        super().setUp()
        self.ledger = os.path.join(self.docs, headpanel.FILE)

    def hook(self, event, **extra):
        payload = {"hook_event_name": event, "cwd": self.project, "session_id": "sess-1"}
        payload.update(extra)
        return hooks.run_hook(json.dumps(payload), now=MOMENT.timestamp())

    def add(self, op="question.answer", summary="Q1 answered yes", ref="Q1", src="gui"):
        return headpanel.record(self.docs, op, summary, src=src, ref=ref)


class LedgerTests(PanelCase):
    def test_record_numbers_lines_and_only_takes_person_sources(self):
        self.assertEqual(self.add()["id"], "P1")
        self.assertEqual(self.add(src="phone")["id"], "P2")
        self.assertIsNone(self.add(src="agent"))
        self.assertIsNone(self.add(src="cli"))
        self.assertEqual([o["id"] for o in headpanel.read(self.docs)], ["P1", "P2"])

    def test_summary_quotes_the_persons_free_text_once(self):
        text = headpanel.summary_of("head.set", {"id": "H1", "note": "do it today"}, "head.set H1 set note")
        self.assertEqual(text, 'head.set H1 set note: "do it today"')
        same = headpanel.summary_of("question.answer", {"id": "Q1", "value": "yes"}, "question.answer Q1 answered yes")
        self.assertEqual(same, "question.answer Q1 answered yes")
        self.assertIn("80%", headpanel.summary_of("limit.set", {"pct": 80}, "limit.set weekly stop"))

    def test_take_marks_seen_once_and_state_moves_sent_seen_acted(self):
        self.add()
        self.add(op="task.status", summary="P0.1 todo->done", ref="P0.1")
        self.assertEqual(headpanel.state(self.docs)["counts"], {"sent": 2, "seen": 0, "acted": 0})
        taken = headpanel.take(self.docs, "prompt", sid="abcd1234")
        self.assertEqual([o["id"] for o in taken], ["P1", "P2"])
        self.assertEqual(headpanel.take(self.docs, "prompt"), [])
        self.assertEqual(headpanel.state(self.docs)["counts"], {"sent": 0, "seen": 2, "acted": 0})
        self.assertEqual(headpanel.ack(self.docs, ["P1", "P9"]), ["P1"])
        rows = {r["id"]: r for r in headpanel.state(self.docs)["rows"]}
        self.assertEqual(rows["P1"]["state"], "acted")
        self.assertEqual(rows["P2"]["state"], "seen")
        self.assertEqual(rows["P2"]["via"], "prompt")

    def test_a_later_head_write_naming_the_ref_counts_as_acted(self):
        self.add(op="task.status", summary="P0.1 todo->done", ref="P0.1")
        headpanel.take(self.docs, "tool")
        activity.append(self.docs, "agent", "head.set", "P0.1 reopened after review")
        self.assertEqual(headpanel.state(self.docs)["rows"][0]["state"], "acted")

    def test_a_person_write_naming_the_ref_is_not_acted(self):
        self.add(op="task.status", summary="P0.1 todo->done", ref="P0.1")
        headpanel.take(self.docs, "tool")
        activity.append(self.docs, "gui", "task.status", "P0.1 done->todo")
        self.assertEqual(headpanel.state(self.docs)["rows"][0]["state"], "seen")

    def test_take_caps_lines_and_the_text_names_the_rest(self):
        for n in range(headpanel.TAKE_LINES + 2):
            self.add(summary="answer %d" % n)
        text = headpanel.take_text(self.docs, "prompt")
        self.assertIn("panel P1 ", text)
        self.assertNotIn("panel P7 ", text)
        self.assertIn("2 more: roadmap head panel", text)
        self.assertIn("roadmap head panel ack P1", text)

    def test_broken_files_fail_open(self):
        with open(self.ledger, "w", encoding="utf-8") as fh:
            fh.write("not json\n")
        with open(os.path.join(self.docs, headpanel.SEEN_FILE), "w", encoding="utf-8") as fh:
            fh.write("[")
        self.assertEqual(headpanel.take(self.docs, "prompt"), [])
        self.assertEqual(headpanel.state(self.docs)["rows"], [])
        self.assertEqual(self.add()["id"], "P1")


class HookTests(PanelCase):
    def test_nothing_new_keeps_the_hooks_silent(self):
        self.assertIsNone(self.hook("UserPromptSubmit", prompt="what is next on the board today"))
        self.assertIsNone(self.hook("PostToolUse", tool_name="Bash", tool_input={"command": "ls"}))

    def test_prompt_gets_the_panel_lines_once(self):
        self.add()
        reply = self.hook("UserPromptSubmit", prompt="ok")
        text = reply["hookSpecificOutput"]["additionalContext"]
        self.assertTrue(text.startswith("panel: the person acted on the board"))
        self.assertIn("panel P1 ", text)
        self.assertIn("Q1 answered yes", text)
        self.assertIsNone(self.hook("UserPromptSubmit", prompt="ok"))
        seen = read_json(os.path.join(self.docs, headpanel.SEEN_FILE))["seen"]["P1"]
        self.assertEqual(seen["via"], "prompt")
        self.assertEqual(len(seen["sid"]), 8)  # the session key, never the raw id

    def test_panel_lines_come_before_the_capture_triage_line(self):
        data = read_json(os.path.join(self.docs, "roadmap.config.json"))
        data["headCapture"] = True
        write_json(os.path.join(self.docs, "roadmap.config.json"), data)
        self.add()
        text = self.hook("UserPromptSubmit", prompt="please look at the board now")[
            "hookSpecificOutput"]["additionalContext"]
        self.assertLess(text.index("panel P1"), text.index("head: logged"))

    def test_post_tool_use_carries_the_lines_mid_turn(self):
        self.add()
        reply = self.hook("PostToolUse", tool_name="Bash", tool_input={"command": "ls"}, tool_response="")
        self.assertEqual(reply["hookSpecificOutput"]["hookEventName"], "PostToolUse")
        self.assertIn("panel P1 ", reply["hookSpecificOutput"]["additionalContext"])

    def test_a_subagent_never_takes_the_lines(self):
        self.add()
        self.assertIsNone(self.hook("PostToolUse", tool_name="Bash", tool_input={"command": "ls"},
                                    agent_id="a1b2c3d4"))
        self.assertEqual(len(headpanel.unseen(self.docs)), 1)

    def test_stop_blocks_once_with_the_lines(self):
        self.add()
        reply = self.hook("Stop")
        self.assertEqual(reply["decision"], "block")
        self.assertIn("panel P1 ", reply["reason"])
        self.assertIsNone(self.hook("Stop"))

    def test_a_continued_stop_is_not_blocked_again(self):
        self.add()
        self.assertIsNone(self.hook("Stop", stop_hook_active=True))
        self.assertEqual(len(headpanel.unseen(self.docs)), 1)

    def test_with_panel_block_joins_an_existing_block(self):
        joined = hooks._with_panel_block({"decision": "block", "reason": "gate"}, "panel: x")
        self.assertEqual(joined["reason"], "panel: x\ngate")
        self.assertIsNone(hooks._with_panel_block(None, ""))

    def test_session_start_carries_the_lines(self):
        self.add()
        reply = self.hook("SessionStart", source="startup")
        self.assertIn("panel P1 ", reply["hookSpecificOutput"]["additionalContext"])

    def test_head_panel_false_turns_delivery_off(self):
        data = read_json(os.path.join(self.docs, "roadmap.config.json"))
        data["head"] = {"panel": False}
        write_json(os.path.join(self.docs, "roadmap.config.json"), data)
        self.add()
        self.assertIsNone(self.hook("UserPromptSubmit", prompt="ok"))
        self.assertEqual(len(headpanel.unseen(self.docs)), 1)


class WatchAndCliTests(PanelCase):
    def test_watch_wakes_on_a_new_panel_line_and_marks_it_seen(self):
        self.add(summary="old one")  # before the watch starts: not news
        clock = [0.0]

        def sleep(seconds):
            if clock[0] == 0.0:
                self.add(op="rules.accept", summary='rules.accept RP1 accepted: "run make check"', ref="RP1")
                stamp = 2e9
                os.utime(self.ledger, (stamp, stamp))
            clock[0] += seconds

        event = watch.wait(self.docs, 10, sleep=sleep, clock=lambda: clock[0])
        self.assertEqual(event["event"], "panel")
        self.assertTrue(event["line"].startswith("panel P2 rules.accept RP1"))
        self.assertEqual(headpanel.state(self.docs)["counts"]["seen"], 1)  # only P2 was announced
        self.assertEqual([o["id"] for o in headpanel.unseen(self.docs)], ["P1"])  # P1 still reaches the next hook

    def test_cli_lists_marks_seen_and_acks(self):
        self.add()
        code, out, _ = run_cli(["head", "panel", "--project", "demo"])
        self.assertEqual(code, 0)
        self.assertIn("P1 seen", out)
        code, out, _ = run_cli(["head", "panel", "ack", "P1", "--project", "demo"])
        self.assertEqual(code, 0)
        self.assertIn("panel acked: P1", out)
        self.assertEqual(headpanel.state(self.docs)["rows"][0]["state"], "acted")
        code, _, _ = run_cli(["head", "panel", "ack", "--project", "demo"])
        self.assertNotEqual(code, 0)
