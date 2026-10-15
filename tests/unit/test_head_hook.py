"""HEAD H6: the UserPromptSubmit capture (skip rules, config gate, redaction, reply length, lock busy spools, fail-open
budget, no text in the log), the head lines at SessionStart, and the installer table entry. Each test runs in a temp
ROADMAP_HOME through ControlCase; nothing touches the real home, the service or port 8780."""

import datetime
import json
import os
import unittest
from unittest import mock

from roadmap.errors import RoadmapError
from roadmap.services import hooks, hooks_install
from roadmap.services import head as head_svc
from roadmap.store import lock
from tests.unit.test_control_support import ControlCase, read_json, write_json

MOMENT = datetime.datetime(2026, 10, 15, 9, 30, tzinfo=datetime.timezone.utc)
SECRET = "sk-abcdef1234567890XYZ"


class HeadHookCase(ControlCase):
    def setUp(self):
        super().setUp()
        self.set_config(headCapture=True)
        self.head_file = os.path.join(self.docs, "head.jsonl")
        self.text_file = os.path.join(self.docs, "head-text.jsonl")
        self.spool_file = os.path.join(self.docs, "head-spool.jsonl")

    def set_config(self, **keys):
        path = os.path.join(self.docs, "roadmap.config.json")
        data = read_json(path)
        data.update(keys)
        write_json(path, data)

    def prompt(self, text, session="sess-1", clock=None, now=None):
        payload = {"hook_event_name": "UserPromptSubmit", "cwd": self.project, "session_id": session,
                   "prompt": text, "permission_mode": "default"}
        return hooks.run_hook(json.dumps(payload), now=(MOMENT.timestamp() if now is None else now), clock=clock)

    def context(self, reply):
        self.assertIsNotNone(reply)
        return reply["hookSpecificOutput"]["additionalContext"]

    def entries(self):
        if not os.path.exists(self.head_file):
            return []
        with open(self.head_file, encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]

    def text_lines(self):
        with open(self.text_file, encoding="utf-8") as fh:
            return [json.loads(x) for x in fh if x.strip()]

    def log_text(self):
        path = os.path.join(os.environ["ROADMAP_HOME"], "logs", "hooks.log")
        if not os.path.exists(path):
            return ""
        with open(path, encoding="utf-8") as fh:
            return fh.read()


class GateTests(HeadHookCase):
    def test_capture_is_off_without_the_config_flag(self):
        self.set_config(headCapture=False)
        self.assertIsNone(self.prompt("please fix the broken export button today"))
        self.assertEqual(self.entries(), [])

    def test_capture_is_off_when_the_config_has_no_flag(self):
        path = os.path.join(self.docs, "roadmap.config.json")
        data = read_json(path)
        data.pop("headCapture", None)
        write_json(path, data)
        self.assertIsNone(self.prompt("please fix the broken export button today"))
        self.assertFalse(os.path.exists(self.head_file))


class SkipRuleTests(HeadHookCase):
    def test_empty_and_short_acks_are_not_logged(self):
        for text in ("", "   ", "ok", "yes", "go on", "thanks a lot", "continue"):
            self.assertIsNone(self.prompt(text), text)
        self.assertEqual(self.entries(), [])

    def test_injected_markup_is_not_logged(self):
        for text in ("<task-notification>done</task-notification> the job finished now",
                     "<system-reminder>be brief and fast for everything</system-reminder>",
                     "<command-name>/head</command-name> please look at the list now"):
            self.assertIsNone(self.prompt(text), text)
        self.assertEqual(self.entries(), [])

    def test_terminal_echo_prompts_are_skipped(self):
        echoes = ("<bash-input>ls -la</bash-input>", "<bash-stdout>file.txt</bash-stdout>",
                  "<bash-stderr>permission denied</bash-stderr>",
                  "<local-command-caveat>Caveat: the messages below were generated locally</local-command-caveat>",
                  "<command-name>/head</command-name> <command-message>head</command-message>",
                  "<command-message>head is running</command-message> <command-args>save</command-args>",
                  "<local-command-stdout>Goodbye, the session ended now</local-command-stdout>",
                  "<system-reminder>keep the answer short for this session</system-reminder>")
        for text in echoes:
            self.assertIsNone(self.prompt(text), text)
        self.assertEqual(self.entries(), [])

    def test_a_normal_message_after_echoes_is_logged(self):
        self.assertIsNone(self.prompt("<bash-stdout>noise from the terminal</bash-stdout>"))
        reply = self.prompt("please fix the broken export button on the board")
        self.assertIn("head: logged H1 (bug?)", self.context(reply))
        self.assertEqual([r["id"] for r in self.entries() if r.get("t") == "e"], ["H1"])

    def test_nolog_prefix_is_not_logged(self):
        self.assertIsNone(self.prompt("//nolog we talked about the export button at length"))
        self.assertEqual(self.entries(), [])

    def test_a_bare_slash_command_is_logged_as_a_session_start(self):
        self.assertIsNone(self.prompt("/head"))
        rows = self.entries()
        self.assertEqual([r.get("t") for r in rows], ["s"])
        self.assertEqual(rows[0].get("ev"), "start")

    def test_a_normal_prompt_is_logged_with_a_kind(self):
        reply = self.prompt("please fix the broken export button on the board")
        self.assertIn("head: logged H1 (bug?)", self.context(reply))
        rows = self.entries()
        self.assertEqual([r["id"] for r in rows if r.get("t") == "e"], ["H1"])


class ReplyTests(HeadHookCase):
    def test_reply_line_is_one_line_of_at_most_120_chars(self):
        long_text = "please fix the broken export button " + ("and the matching import flow " * 40)
        reply = self.prompt(long_text)
        line = self.context(reply)
        self.assertLessEqual(len(line), 120)
        self.assertNotIn("\n", line)
        self.assertTrue(line.startswith("head: logged H1 (bug?). triage: roadmap head t H1 bug "))

    def test_untriaged_count_is_added_when_others_wait(self):
        self.prompt("please fix the broken export button on the board")
        reply = self.prompt("we should add an import check for every single new board row", session="sess-2")
        self.assertIn("1 untriaged", self.context(reply))

    def test_hint_false_keeps_the_capture_and_drops_the_reply(self):
        self.set_config(head={"hint": False})
        self.assertIsNone(self.prompt("please fix the broken export button on the board"))
        self.assertEqual(len(self.entries()), 1)

    def test_the_hook_never_blocks_the_prompt(self):
        reply = self.prompt("please fix the broken export button on the board")
        self.assertNotIn("decision", reply["hookSpecificOutput"])
        self.assertNotIn("block", json.dumps(reply))


class PrivacyTests(HeadHookCase):
    def test_secrets_are_masked_before_the_write(self):
        self.prompt("fix the export, the key is " + SECRET + " and mail a@b.com about it")
        with open(self.text_file, encoding="utf-8") as fh:
            stored = fh.read()
        self.assertNotIn(SECRET, stored)
        self.assertNotIn("a@b.com", stored)
        self.assertIn("[email]", stored)

    def test_no_prompt_text_reaches_the_debug_log(self):
        self.prompt("fix the export, the key is " + SECRET + " and the board rows")
        log = self.log_text()
        self.assertIn("head.capture H1", log)
        self.assertNotIn(SECRET, log)
        self.assertNotIn("export", log)


class BudgetTests(HeadHookCase):
    def test_a_busy_lock_spools_the_capture_without_waiting(self):
        calls = []

        def busy(directory, timeout=None):
            calls.append(timeout)
            raise RoadmapError("locked", "busy", 4)

        with mock.patch.object(lock, "locked", side_effect=busy):
            reply = self.prompt("please fix the broken export button on the board")
        self.assertIn("queued (bug?)", self.context(reply))
        self.assertTrue(os.path.exists(self.spool_file))
        self.assertFalse(os.path.exists(self.head_file))
        self.assertTrue(all(t is not None and t <= hooks.PRE_TIMEOUT_S for t in calls))

    def test_no_budget_left_spools_at_once_and_still_fails_open(self):
        ticks = iter([0.0] + [1.0] * 50)
        reply = self.prompt("please fix the broken export button on the board", clock=lambda: next(ticks))
        self.assertIsNotNone(reply)
        self.assertTrue(os.path.exists(self.spool_file) or os.path.exists(self.head_file))

    def test_a_malformed_payload_is_skipped_quietly(self):
        self.assertIsNone(hooks.run_hook("{not json", now=MOMENT.timestamp()))
        self.assertFalse(os.path.exists(self.head_file))


class SessionStartTests(HeadHookCase):
    def start(self):
        return hooks.run_hook(json.dumps({"hook_event_name": "SessionStart", "cwd": self.project}),
                              now=MOMENT.timestamp())

    def test_session_start_lists_the_open_asks_and_needs_you(self):
        self.prompt("please fix the broken export button on the board", session="a")
        self.prompt("add a csv import check for every new board row", session="b")
        context = self.context(self.start())
        last = context.split("\n")[-1]
        self.assertTrue(last.startswith("head: 2 open asks (H1 "), last)
        self.assertIn("H2 ", last)
        self.assertLessEqual(len(last), 120)
        self.assertTrue(last.endswith("Run roadmap head brief."))

    def test_session_start_adds_nothing_when_capture_is_off(self):
        self.prompt("please fix the broken export button on the board", session="a")
        self.set_config(headCapture=False)
        self.assertIsNone(self.start())


class ModelClaimTests(HeadHookCase):
    def run_event(self, event, model=None, session="sess-1", clock=None):
        payload = {"hook_event_name": event, "cwd": self.project, "session_id": session}
        if model is not None:
            payload["model"] = model
        if event == "UserPromptSubmit":
            payload["prompt"] = "please fix the broken export button on the board"
        return hooks.run_hook(json.dumps(payload), now=MOMENT.timestamp(), clock=clock)

    def claims(self):
        return [r for r in self.entries() if r.get("t") == "s" and r.get("ev") == "claim"]

    def test_model_name_shortens_ids_and_reads_objects(self):
        self.assertEqual(hooks.model_name("claude-sonnet-5-5"), "Sonnet 5.5")
        self.assertEqual(hooks.model_name("claude-haiku-5-5-20251001"), "Haiku 5.5")
        self.assertEqual(hooks.model_name({"id": "claude-opus-5-5", "display_name": "Opus 5.5"}), "Opus 5.5")
        self.assertEqual(hooks.model_name({"id": "claude-opus-5-5"}), "Opus 5.5")
        self.assertEqual(hooks.model_name("Sonnet 5.5"), "Sonnet 5.5")
        self.assertIsNone(hooks.model_name(None))
        self.assertIsNone(hooks.model_name("   "))
        self.assertIsNone(hooks.model_name(42))

    def test_session_start_records_a_claim_from_a_string_model(self):
        self.run_event("SessionStart", model="claude-sonnet-5-5")
        claims = self.claims()
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0]["model"], "Sonnet 5.5")
        self.assertIsNotNone(claims[0].get("sid"))
        self.assertNotIn("sess-1", json.dumps(claims[0]))

    def test_session_start_records_a_claim_from_an_object_model(self):
        self.run_event("SessionStart", model={"id": "claude-haiku-5-5", "display_name": "Haiku 5.5"})
        self.assertEqual([c["model"] for c in self.claims()], ["Haiku 5.5"])

    def test_same_model_and_session_do_not_spam_claims(self):
        for _ in range(3):
            self.run_event("SessionStart", model="claude-sonnet-5-5")
            self.run_event("UserPromptSubmit", model="claude-sonnet-5-5")
        self.assertEqual(len(self.claims()), 1)

    def test_a_model_change_or_a_new_session_claims_again(self):
        self.run_event("SessionStart", model="claude-sonnet-5-5")
        self.run_event("UserPromptSubmit", model="claude-opus-5-5")
        self.run_event("UserPromptSubmit", model="claude-opus-5-5", session="sess-2")
        self.assertEqual([c["model"] for c in self.claims()], ["Sonnet 5.5", "Opus 5.5", "Opus 5.5"])

    def test_no_model_means_no_claim(self):
        self.run_event("SessionStart")
        self.run_event("UserPromptSubmit")
        self.assertEqual(self.claims(), [])

    def test_nothing_is_claimed_when_capture_is_off(self):
        self.set_config(headCapture=False)
        self.run_event("SessionStart", model="claude-sonnet-5-5")
        self.assertFalse(os.path.exists(self.head_file))

    def test_a_busy_lock_does_not_break_the_session_start_reply(self):
        def busy(directory, timeout=None):
            raise RoadmapError("locked", "busy", 4)

        with mock.patch.object(lock, "locked", side_effect=busy):
            reply = self.run_event("SessionStart", model="claude-sonnet-5-5")
        self.assertIsNone(reply)  # no inbox or head lines in an empty project: the hook still returns cleanly
        self.assertIn("head.claim skipped", self.log_text())


class TranscriptModelTests(HeadHookCase):
    """A payload with no model: the model is read from the transcript_path JSONL (last 64 KB, last 50 lines)."""

    def setUp(self):
        super().setUp()
        self.transcript = os.path.join(self.docs, "session-transcript.jsonl")

    def write_lines(self, lines):
        with open(self.transcript, "w", encoding="utf-8") as fh:
            for line in lines:
                fh.write(line if isinstance(line, str) else json.dumps(line))
                fh.write("\n")

    def assistant(self, model):
        return {"type": "assistant", "message": {"model": model, "role": "assistant", "content": "ok"}}

    def run_event(self, event, transcript=None, model=None, session="sess-1"):
        payload = {"hook_event_name": event, "cwd": self.project, "session_id": session}
        if transcript is not None:
            payload["transcript_path"] = transcript
        if model is not None:
            payload["model"] = model
        if event == "UserPromptSubmit":
            payload["prompt"] = "please fix the broken export button on the board"
        return hooks.run_hook(json.dumps(payload), now=MOMENT.timestamp())

    def claims(self):
        return [r["model"] for r in self.entries() if r.get("t") == "s" and r.get("ev") == "claim"]

    def test_session_start_reads_the_model_from_the_transcript(self):
        self.write_lines([{"type": "user"}, self.assistant("claude-haiku-5-5")])
        self.run_event("SessionStart", transcript=self.transcript)
        self.assertEqual(self.claims(), ["Haiku 5.5"])

    def test_a_model_switch_is_picked_up_at_the_next_prompt(self):
        self.write_lines([self.assistant("claude-sonnet-5-5")])
        self.run_event("SessionStart", transcript=self.transcript)
        self.write_lines([self.assistant("claude-sonnet-5-5"), self.assistant("claude-haiku-5-5")])
        self.run_event("UserPromptSubmit", transcript=self.transcript)
        self.run_event("UserPromptSubmit", transcript=self.transcript)  # same model again: no new claim
        self.assertEqual(self.claims(), ["Sonnet 5.5", "Haiku 5.5"])

    def test_the_payload_model_wins_over_the_transcript(self):
        self.write_lines([self.assistant("claude-haiku-5-5")])
        self.run_event("SessionStart", transcript=self.transcript, model="claude-opus-5-5")
        self.assertEqual(self.claims(), ["Opus 5.5"])

    def test_malformed_lines_and_non_claude_models_are_skipped(self):
        self.write_lines(["{not json", self.assistant("claude-sonnet-5-5"), self.assistant("<synthetic>"),
                          '["list"]', "", "   "])
        self.run_event("SessionStart", transcript=self.transcript)
        self.assertEqual(self.claims(), ["Sonnet 5.5"])

    def test_only_the_last_50_lines_are_scanned(self):
        self.write_lines([self.assistant("claude-opus-5-5")] + [{"type": "user", "n": i} for i in range(55)])
        self.run_event("SessionStart", transcript=self.transcript)
        self.assertEqual(self.claims(), [])

    def test_only_the_last_64_kb_are_read(self):
        filler = "x" * 1000
        self.write_lines([self.assistant("claude-opus-5-5")] + [{"type": "user", "pad": filler}] * 80)
        self.assertGreater(os.path.getsize(self.transcript), 64 * 1024)
        self.run_event("SessionStart", transcript=self.transcript)
        self.assertEqual(self.claims(), [])

    def test_a_missing_or_odd_transcript_path_is_fail_open(self):
        for path in (os.path.join(self.docs, "nope.jsonl"), "", 42, self.docs):
            self.assertIsNone(hooks._transcript_model(path), repr(path))
        self.run_event("SessionStart", transcript=os.path.join(self.docs, "nope.jsonl"))
        self.assertEqual(self.claims(), [])

    def test_helper_reads_only_the_named_file(self):
        self.write_lines([self.assistant("claude-haiku-5-5")])
        self.assertEqual(hooks._transcript_model(self.transcript), "Haiku 5.5")


class InstallTableTests(unittest.TestCase):
    def test_user_prompt_submit_is_in_the_event_table_without_a_matcher(self):
        rows = {event: (matcher, suffix) for event, matcher, suffix in hooks_install.EVENTS}
        self.assertEqual(rows["UserPromptSubmit"], (None, ""))


if __name__ == "__main__":
    unittest.main()


class AssetTests(HeadHookCase):
    """HEAD-SPEC section 13: the attachment names of a prompt are stored with the text (names only, at most 20)."""

    def test_prompt_assets_finds_names_paths_and_at_refs(self):
        names = hooks.prompt_assets("see @docs/plan.md and the shot.png, then /tmp/out/build.log and https://x.io/a.png")
        self.assertEqual(names, ["docs/plan.md", "shot.png", "/tmp/out/build.log"])

    def test_prompt_assets_is_empty_for_plain_text_and_non_text(self):
        self.assertEqual(hooks.prompt_assets("version 1.5 is out, no files here"), [])
        self.assertEqual(hooks.prompt_assets(None), [])

    def test_prompt_assets_keeps_at_most_twenty(self):
        text = " ".join("file%d.png" % i for i in range(30))
        self.assertEqual(len(hooks.prompt_assets(text)), 20)

    def test_the_capture_stores_the_assets_with_the_text(self):
        self.prompt("please check the attached shot.png and @docs/plan.md for the board")
        line = self.text_lines()[-1]
        self.assertEqual(line["assets"], ["shot.png", "docs/plan.md"])
        self.assertIn("please check the attached", line["text"])

    def test_a_prompt_without_files_has_no_assets_key(self):
        self.prompt("please fix the broken export button on the board")
        line = self.text_lines()[-1]
        self.assertNotIn("assets", line)


def _line(kind, text, stamp, meta=False):
    entry = {"type": kind, "timestamp": stamp, "message": {"role": kind, "content": text}}
    if meta:
        entry["isMeta"] = True
    return json.dumps(entry)


class ReplyCaptureTests(HeadHookCase):
    """HEAD-SPEC section 13: the Stop hook stores the turn's last assistant text on the session's newest hook entry."""

    def setUp(self):
        super().setUp()
        self.transcript = os.path.join(self.docs, "transcript.jsonl")

    def write_transcript(self, lines):
        with open(self.transcript, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")

    def stop(self, session="sess-1", path=None):
        payload = {"hook_event_name": "Stop", "cwd": self.project, "session_id": session,
                   "transcript_path": self.transcript if path is None else path, "stop_hook_active": False}
        return hooks.run_hook(json.dumps(payload), now=MOMENT.timestamp())

    def reply_of(self, eid):
        return head_svc.details_of(self.docs, eid)["reply"]

    def turn(self, prompt, reply_text, stamp="2026-10-15T09:30:00.000Z"):
        return [_line("user", prompt, stamp),
                _line("assistant", [{"type": "text", "text": "Let me look."}], "2026-10-15T09:30:01.000Z"),
                _line("user", [{"type": "tool_result", "content": "ok"}], "2026-10-15T09:30:02.000Z"),
                _line("assistant", [{"type": "text", "text": reply_text}], "2026-10-15T09:30:03.000Z")]

    def test_stop_stores_the_last_assistant_text_of_the_turn(self):
        self.prompt("please fix the broken export button on the board")
        eid = self.entries()[-1]["id"]
        self.write_transcript(self.turn("please fix the broken export button on the board", "Fixed the export button."))
        self.stop()
        self.assertEqual(self.reply_of(eid), "Fixed the export button.")

    def test_a_turn_with_no_capture_gets_no_reply(self):
        self.prompt("please fix the broken export button on the board")
        eid = self.entries()[-1]["id"]
        # the next turn is an ack that the hook did not log: its reply must not reach the older entry
        self.write_transcript(self.turn("ok", "Done.", stamp="2026-10-15T10:00:00.000Z"))
        self.stop()
        self.assertIsNone(self.reply_of(eid))

    def test_a_reply_is_redacted_and_capped(self):
        self.prompt("please fix the broken export button on the board")
        eid = self.entries()[-1]["id"]
        text = "key " + SECRET + " mail ann@example.com " + ("x" * 9000)
        self.write_transcript(self.turn("please fix the broken export button on the board", text))
        self.stop()
        reply = self.reply_of(eid)
        self.assertNotIn(SECRET, reply)
        self.assertNotIn("ann@example.com", reply)
        self.assertLessEqual(len(reply), 8000)

    def test_a_missing_transcript_fails_open(self):
        self.prompt("please fix the broken export button on the board")
        eid = self.entries()[-1]["id"]
        self.stop(path=os.path.join(self.docs, "nope.jsonl"))  # the Stop gate may answer; no exception
        self.assertIsNone(self.reply_of(eid))

    def test_a_large_transcript_is_read_from_its_end_only(self):
        self.prompt("please fix the broken export button on the board")
        eid = self.entries()[-1]["id"]
        old = [_line("assistant", [{"type": "text", "text": "old"}], "2026-10-14T08:00:00.000Z")] * 6000
        turn = self.turn("please fix the broken export button on the board", "Fixed it at the end.")
        self.write_transcript(old + turn)
        self.assertGreater(os.path.getsize(self.transcript), hooks.REPLY_TAIL_BYTES)
        self.stop()
        self.assertEqual(self.reply_of(eid), "Fixed it at the end.")

    def test_no_reply_is_read_when_capture_is_off(self):
        self.set_config(headCapture=False)
        self.write_transcript(self.turn("please fix the broken export button on the board", "Fixed."))
        self.stop()
        self.assertFalse(os.path.exists(self.text_file))
