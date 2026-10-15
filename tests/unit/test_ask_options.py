"""Question options (R7.90): the CLI takes 2 to 6 options as "Label" or "Label: description", one may be marked
"(recommended)", labels are at most 60 characters, and every question also accepts a free-text answer. The old --opt
form still works (same flag)."""

from roadmap.services import questions
from tests.unit.test_cmd_support import CmdCase


class AskOptionsCli(CmdCase):
    def test_option_flag_and_legacy_opt_flag_both_record_options(self):
        self.cli(["ask", "ship?", "--option", "Yes", "--opt", "No"])
        code, body = self.envelope(["ask", "get", "Q1"])
        self.assertEqual(code, 0)
        self.assertEqual(body["data"]["question"]["opts"], ["Yes", "No"])

    def test_six_options_with_descriptions_are_stored_as_given(self):
        args = ["ask", "pick?"]
        for n in range(6):
            args += ["--option", "Opt %d: why %d" % (n, n)]
        code, _, err = self.cli(args)
        self.assertEqual(code, 0, err)
        code, body = self.envelope(["ask", "get", "Q1"])
        self.assertEqual(body["data"]["question"]["opts"][0], "Opt 0: why 0")
        self.assertEqual(len(body["data"]["question"]["opts"]), 6)

    def test_seven_options_are_refused(self):
        args = ["ask", "pick?"]
        for n in range(7):
            args += ["--option", "O%d" % n]
        code, _, err = self.cli(args)
        self.assertEqual(code, 2)
        self.assertIn("2 to 6 options", err)

    def test_one_option_is_refused(self):
        code, _, err = self.cli(["ask", "pick?", "--option", "Only"])
        self.assertEqual(code, 2)
        self.assertIn("2 to 6 options", err)

    def test_label_over_60_characters_is_refused(self):
        code, _, err = self.cli(["ask", "pick?", "--option", "x" * 61, "--option", "No"])
        self.assertEqual(code, 2)
        self.assertIn("limit is 60", err)

    def test_free_text_answer_is_accepted_when_options_exist(self):
        self.cli(["ask", "ok?", "--option", "Yes", "--option", "No"])
        code, out, err = self.cli(["answer", "Q1", "maybe later", "please"])
        self.assertEqual((code, out.strip()), (0, "Q1 answered maybe later please"), err)

    def test_an_option_label_answer_is_stored_as_the_label(self):
        self.cli(["ask", "ok?", "--option", "Yes: ship it", "--option", "No: wait"])
        code, out, err = self.cli(["answer", "Q1", "No"])
        self.assertEqual((code, out.strip()), (0, "Q1 answered No"), err)

    def test_recommended_marker_is_stored_and_default_matches_the_label(self):
        code, _, err = self.cli(["ask", "ok?", "--option", "Yes (recommended): ship it", "--option", "No",
                                 "--default", "Yes"])
        self.assertEqual(code, 0, err)
        code, body = self.envelope(["ask", "get", "Q1"])
        self.assertEqual(body["data"]["question"]["opts"][0], "Yes (recommended): ship it")
        self.assertEqual(body["data"]["question"]["def"], "Yes")

    def test_two_recommended_options_are_refused(self):
        code, _, err = self.cli(["ask", "ok?", "--option", "A (recommended)", "--option", "B (recommended)"])
        self.assertEqual(code, 2)
        self.assertIn("only one option can be recommended", err)

    def test_duplicate_labels_are_refused(self):
        code, _, err = self.cli(["ask", "ok?", "--option", "Yes: a", "--option", "Yes: b"])
        self.assertEqual(code, 2)
        self.assertIn("must be different", err)


class AskOptionsService(CmdCase):
    def test_parse_option_splits_label_description_and_recommended(self):
        self.assertEqual(questions.parse_option("Yes (recommended): ship it"), ("Yes", "ship it", True))
        self.assertEqual(questions.parse_option("No"), ("No", "", False))

    def test_option_label_is_the_text_before_the_colon(self):
        self.assertEqual(questions.option_label("Yes (recommended): ship: now"), "Yes")
        self.assertEqual(questions.option_label("Plain"), "Plain")


if __name__ == "__main__":
    import unittest

    unittest.main()
