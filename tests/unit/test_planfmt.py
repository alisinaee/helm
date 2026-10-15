"""Tests for the plan text format and the bulk set lines: grammar, '-' semantics, errors, round trips, fenced blocks."""

import unittest

from roadmap.core import planfmt
from roadmap.errors import EXIT_ERROR, RoadmapError

EXAMPLE = """P M1 todo | Foundations
T M1.1 todo 20 haiku/low | Scaffold repo, CI and lint
T M1.2 todo 40 sonnet/medium c:sonnet/8 | Data model and storage layer
T M1.3 todo 5 haiku/low ! | Create hosting account and API key # needs your login
T M1.4 todo 80 opus/high c:opus/15 | Sync engine design and spike
T M1.5 todo 10 haiku/low | README quick start
"""


class ParsePlanTests(unittest.TestCase):
    def test_example_parses_to_six_records_without_errors(self):
        records, errors = planfmt.parse_plan(EXAMPLE)
        self.assertEqual(errors, [])
        self.assertEqual([r["kind"] for r in records], ["phase"] + ["task"] * 5)
        phase = records[0]
        self.assertEqual((phase["id"], phase["name"], phase["status"]), ("M1", "Foundations", "todo"))

    def test_task_fields_and_defaults_for_absent_optionals(self):
        records, _ = planfmt.parse_plan(EXAMPLE)
        plain = records[1]
        self.assertEqual((plain["id"], plain["phase"], plain["tokensK"]), ("M1.1", "M1", 20))
        self.assertEqual((plain["model"], plain["thinking"]), ("haiku", "low"))
        self.assertIsNone(plain["needsUser"])
        self.assertIsNone(plain["check"])
        self.assertIsNone(plain["checkK"])
        self.assertIsNone(plain["note"])

    def test_check_bang_and_note_are_read(self):
        records, _ = planfmt.parse_plan(EXAMPLE)
        check = records[2]
        self.assertEqual((check["check"], check["checkK"]), ("sonnet", 8))
        bang = records[3]
        self.assertIs(bang["needsUser"], True)
        self.assertEqual(bang["title"], "Create hosting account and API key")
        self.assertEqual(bang["note"], "needs your login")

    def test_dash_means_keep_or_default(self):
        records, errors = planfmt.parse_plan("P M1 - | Name\nT M1.1 - - -/- | Title\n")
        self.assertEqual(errors, [])
        phase, task = records
        self.assertIsNone(phase["status"])
        self.assertIsNone(task["status"])
        self.assertIsNone(task["tokensK"])
        self.assertIsNone(task["model"])
        self.assertIsNone(task["thinking"])

    def test_check_none_and_zero_is_explicit(self):
        records, errors = planfmt.parse_plan("T M1.1 todo 1 haiku/low c:none/0 | x\n")
        self.assertEqual(errors, [])
        self.assertEqual((records[0]["check"], records[0]["checkK"]), ("none", 0))

    def test_title_may_contain_a_bar_and_note_is_after_first_hash(self):
        records, errors = planfmt.parse_plan("T M1.1 todo 1 haiku/low | A | B # first # second\n")
        self.assertEqual(errors, [])
        self.assertEqual(records[0]["title"], "A | B")
        self.assertEqual(records[0]["note"], "first # second")

    def test_comments_blank_lines_and_indent_are_ignored(self):
        text = "# header comment\n\n   P M1 todo | Name  \n\t# indented comment\n  T M1.1 todo 1 haiku/low | x\n"
        records, errors = planfmt.parse_plan(text)
        self.assertEqual(errors, [])
        self.assertEqual([r["id"] for r in records], ["M1", "M1.1"])
        self.assertEqual(records[0]["name"], "Name")
        self.assertEqual(records[1]["line"], 5)

    def test_every_error_names_the_line_and_the_allowed_values(self):
        cases = {
            "P M1 doing | X": "status 'doing' is not valid (allowed: todo|partial|done|hold|-)",
            "T M1.1 todo 5 gpt/low | x": "model 'gpt' is not valid (allowed: haiku|sonnet|opus|cursor|agy|head|-)",
            "T M1.1 todo 5 haiku/max | x": "thinking 'max' is not valid (allowed: low|medium|high|-)",
            "T M1.1 todo five haiku/low | x": "tokensK 'five' is not a whole number",
            "T M1 todo 5 haiku/low | x": "task id 'M1' must look like P1.2",
            "P M1.2 todo | x": "phase id 'M1.2' has a dot or a symbol",
            "T M1.1 todo 5 haiku/low": "task line needs an id, status, tokensK",
            "P M1 todo": "phase line needs an id, a status and '| name'",
            "T M1.1 todo 5 haiku/low | ": "task title is empty",
            "T M1.1 todo 5 haiku/low | x #": "note is empty",
            "T M1.1 todo 5 haiku/low | x # ": "note is empty",
            "X M1.1 todo": "unknown record 'X' (allowed: P, T, #, blank)",
            "T M1.1 todo 5 haiku/low ? | x": "unexpected '?' (allowed: !, c:<check>/<checkK>)",
            "T M1.1 todo 5 haiku/low c:gpt/3 | x": "check 'gpt' is not valid (allowed: none|sonnet|opus|-)",
            "T M1.1 todo 5 haiku/low c:sonnet/x | x": "checkK 'x' is not a whole number",
            "T M1.1 todo 5 haiku | x": "model/thinking 'haiku' needs a slash",
            "P  | x": "phase line needs an id",
        }
        for text, problem in cases.items():
            with self.subTest(text=text):
                records, errors = planfmt.parse_plan(text + "\n")
                self.assertEqual(records, [])
                self.assertEqual(len(errors), 1)
                self.assertTrue(errors[0].startswith("line 1: "), errors[0])
                self.assertIn(problem, errors[0])
                self.assertIn("(allowed:", errors[0])

    def test_parsing_continues_after_an_error_and_keeps_line_numbers(self):
        text = ("P M1 todo | ok\nT M1.1 todo x haiku/low | bad\nT M1.2 todo 1 haiku/low | good\n"
                "T M1.3 todo 1 gpt/low | bad\n")
        records, errors = planfmt.parse_plan(text)
        self.assertEqual([r["id"] for r in records], ["M1", "M1.2"])
        self.assertEqual(len(errors), 2)
        self.assertTrue(errors[0].startswith("line 2: "))
        self.assertTrue(errors[1].startswith("line 4: "))

    def test_duplicate_ids_in_one_input_are_errors(self):
        records, errors = planfmt.parse_plan("P M1 todo | a\nP M1 todo | b\nT M1.1 todo 1 haiku/low | x\n"
                                             "T M1.1 done 1 haiku/low | y\n")
        self.assertEqual([r["id"] for r in records], ["M1", "M1.1"])
        self.assertEqual(len(errors), 2)
        self.assertIn("duplicate phase id M1 (first on line 1)", errors[0])
        self.assertIn("duplicate task id M1.1 (first on line 3)", errors[1])

    def test_no_records_and_no_errors_for_empty_text(self):
        self.assertEqual(planfmt.parse_plan(""), ([], []))
        self.assertEqual(planfmt.parse_plan("# only a comment\n\n"), ([], []))


class ExtractBlockTests(unittest.TestCase):
    def test_first_roadmap_plan_block_is_returned(self):
        md = ("intro\n```python\nprint(1)\n```\n```roadmap-plan\nP M1 todo | A\n```\n"
              "```roadmap-plan\nP M2 todo | B\n```\n")
        self.assertEqual(planfmt.extract_block(md), "P M1 todo | A\n")

    def test_other_blocks_are_skipped_even_when_they_mention_the_tag(self):
        md = "```text\n```roadmap-plan\nP X todo | not this\n```\n```roadmap-plan-old\nP Y todo | no\n```\n"
        self.assertIsNone(planfmt.extract_block(md))

    def test_tilde_fence_works(self):
        self.assertEqual(planfmt.extract_block("~~~roadmap-plan\nP X todo | y\n~~~\n"), "P X todo | y\n")

    def test_no_block_gives_none(self):
        self.assertIsNone(planfmt.extract_block("# Research note\n\nNo plan here.\n"))


class ParseSetLineTests(unittest.TestCase):
    def test_key_values_and_quoted_note(self):
        record, problem = planfmt.parse_set_line('P2.4 status=done tokensK=35 note="wired; tests green"')
        self.assertIsNone(problem)
        self.assertEqual(record["kind"], "set")
        self.assertEqual(record["id"], "P2.4")
        self.assertEqual(record["fields"], {"status": "done", "tokensK": 35, "note": "wired; tests green"})

    def test_booleans_and_numbers(self):
        record, _ = planfmt.parse_set_line("V.3 needsUser=false checkK=0 check=opus")
        self.assertEqual(record["fields"], {"needsUser": False, "checkK": 0, "check": "opus"})
        record, _ = planfmt.parse_set_line("V.3 needsUser=true")
        self.assertEqual(record["fields"], {"needsUser": True})

    def test_empty_note_is_kept_as_clear(self):
        record, _ = planfmt.parse_set_line('P2.4 note=""')
        self.assertEqual(record["fields"], {"note": ""})
        record, _ = planfmt.parse_set_line("P2.4 note=")
        self.assertEqual(record["fields"], {"note": ""})

    def test_dash_values_are_left_out_so_the_current_value_stays(self):
        record, problem = planfmt.parse_set_line("P2.4 status=- tokensK=- model=sonnet")
        self.assertIsNone(problem)
        self.assertEqual(record["fields"], {"model": "sonnet"})

    def test_errors_name_the_problem_and_the_allowed_values(self):
        cases = {
            "P2.4 status=finished": "status 'finished' is not valid (allowed: todo|partial|done|hold|backlog|-)",
            "P2.4 colour=red": "unknown key 'colour' (allowed: status, tokensK",
            "P2.4 status=done status=todo": "key 'status' is given twice",
            "P2.4": "no fields to change",
            'P2.4 status="done': "cannot read this line",
            "P2.4 done": "'done' is not key=value",
            "P2.4 tokensK=-3": "tokensK '-3' is not a whole number",
            "P2.4 needsUser=yes": "needsUser 'yes' is not valid (allowed: true|false)",
            "P2.4 title=   ": "title is empty",
            "P2.4 model=gpt": "model 'gpt' is not valid (allowed: haiku|sonnet|opus|cursor|agy|head|-)",
            "P2.4! status=done": "'P2.4!' is not a task id",
        }
        for text, problem in cases.items():
            with self.subTest(text=text):
                record, message = planfmt.parse_set_line(text, lineno=7)
                self.assertIsNone(record)
                self.assertTrue(message.startswith("line 7: "), message)
                self.assertIn(problem, message)

    def test_parse_set_text_skips_comments_and_collects_errors(self):
        records, errors = planfmt.parse_set_text("# note\nP2.4 status=done\n\nV.3 status=bogus\nP2.5 status=partial\n")
        self.assertEqual([r["id"] for r in records], ["P2.4", "P2.5"])
        self.assertEqual(len(errors), 1)
        self.assertTrue(errors[0].startswith("line 4: "))


class FormatTests(unittest.TestCase):
    def test_task_round_trips_through_parse_plan(self):
        task = {"id": "M1.3", "phase": "M1", "title": "Create x", "status": "partial", "tokensK": 5,
                "thinking": "low", "model": "haiku", "needsUser": True, "check": "sonnet", "checkK": 8,
                "note": "ask me"}
        line = planfmt.format_task(task)
        self.assertEqual(line, "T M1.3 partial 5 haiku/low ! c:sonnet/8 | Create x # ask me")
        records, errors = planfmt.parse_plan("P M1 todo | m\n" + line + "\n")
        self.assertEqual(errors, [])
        rec = records[1]
        self.assertEqual((rec["status"], rec["tokensK"], rec["model"], rec["thinking"]),
                         ("partial", 5, "haiku", "low"))
        self.assertIs(rec["needsUser"], True)
        self.assertEqual((rec["check"], rec["checkK"], rec["note"]), ("sonnet", 8, "ask me"))

    def test_plain_task_omits_optional_parts(self):
        line = planfmt.format_task({"id": "M1.1", "title": "Plain", "status": "todo", "tokensK": 0,
                                    "thinking": "low", "model": "haiku", "needsUser": False,
                                    "check": "none", "checkK": 0})
        self.assertEqual(line, "T M1.1 todo 0 haiku/low | Plain")

    def test_missing_fields_print_as_dashes(self):
        self.assertEqual(planfmt.format_task({"id": "V.1", "title": "x"}), "T V.1 - - -/- | x")

    def test_phase_round_trips(self):
        phase = {"id": "M1", "name": "Foundations", "status": "hold"}
        self.assertEqual(planfmt.format_phase(phase), "P M1 hold | Foundations")
        records, errors = planfmt.parse_plan(planfmt.format_phase(phase) + "\n")
        self.assertEqual(errors, [])
        self.assertEqual((records[0]["id"], records[0]["name"], records[0]["status"]), ("M1", "Foundations", "hold"))

    def test_today_is_an_iso_date(self):
        self.assertRegex(planfmt.today(), r"^\d{4}-\d{2}-\d{2}$")


class ErrorNextTests(unittest.TestCase):
    def test_next_defaults_to_none_and_is_kept_when_given(self):
        self.assertIsNone(RoadmapError("x", "y").next)
        self.assertEqual(RoadmapError("x", "y").exit, EXIT_ERROR)
        self.assertEqual(RoadmapError("x", "y", next="roadmap status").next, "roadmap status")


if __name__ == "__main__":
    unittest.main()
