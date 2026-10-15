"""Tests for the model words the plan format accepts on T lines and set lines (WP59b).

The plan format takes the same model words as the jobs service: haiku, sonnet, opus, cursor, agy and head.
"""

import unittest

from roadmap.core import planfmt


class PlanModelWordTests(unittest.TestCase):
    def test_models_list_matches_the_job_model_words(self):
        self.assertEqual(planfmt.MODELS, ("haiku", "sonnet", "opus", "cursor", "agy", "opencode", "head"))

    def test_task_line_accepts_each_model_word(self):
        for model in planfmt.MODELS:
            text = "T M1.1 todo 5 " + model + "/low | Scaffold\n"
            records, errors = planfmt.parse_plan(text)
            self.assertEqual(errors, [], model)
            self.assertEqual(records[0]["model"], model)

    def test_cursor_and_agy_round_trip_through_format_task(self):
        for model in ("cursor", "agy"):
            text = "T M1.1 todo 5 " + model + "/high | Scaffold # note"
            records, errors = planfmt.parse_plan(text + "\n")
            self.assertEqual(errors, [])
            task = {"id": "M1.1", "status": "todo", "tokensK": 5, "model": model, "thinking": "high",
                    "title": "Scaffold", "note": "note"}
            self.assertEqual(planfmt.format_task(task), text)

    def test_set_line_accepts_cursor_and_agy(self):
        for model in ("cursor", "agy"):
            record, problem = planfmt.parse_set_line("M1.1 model=" + model)
            self.assertIsNone(problem)
            self.assertEqual(record["fields"], {"model": model})

    def test_unknown_model_error_lists_the_allowed_words(self):
        records, errors = planfmt.parse_plan("T M1.1 todo 5 gpt/low | Scaffold\n")
        self.assertEqual(records, [])
        self.assertEqual(len(errors), 1)
        self.assertTrue(errors[0].startswith("line 1: model 'gpt' is not valid"), errors[0])
        self.assertIn("haiku|sonnet|opus|cursor|agy|opencode|head|-", errors[0])


if __name__ == "__main__":
    unittest.main()
