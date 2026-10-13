"""Questions on the CLI: ask, ask get, ask wait (fake clock and fake sleep), ask list, answer. Round trip, error exits
with a next: line, and the output budgets."""

from roadmap.commands import ask as ask_cmd
from tests.unit.test_cmd_support import CmdCase, at


class AskRoundTripTests(CmdCase):
    def test_block_ask_then_answer_then_get_prints_the_answer(self):
        code, out, err = self.cli(["ask", "ok?", "--opt", "yes", "--opt", "no", "--default", "yes", "--block"])
        self.assertEqual((code, out.strip()), (0, "Q1 open"), err)
        code, out, err = self.cli(["answer", "Q1", "no"])
        self.assertEqual((code, out.strip()), (0, "Q1 answered no"), err)
        code, out, err = self.cli(["ask", "get", "Q1"])
        self.assertEqual((code, out.strip()), (0, "Q1 answered no"), err)

    def test_ask_records_a_task_and_the_block_flag(self):
        self.cli(["ask", "which db?", "--task", "P1.1", "--opt", "pg", "--opt", "sqlite", "--block"])
        code, body = self.envelope(["ask", "get", "Q1"])
        self.assertEqual(code, 0)
        self.assertEqual(body["data"]["question"]["task"], "P1.1")
        self.assertTrue(body["data"]["question"]["block"])

    def test_answer_outside_the_options_is_refused_with_next(self):
        self.cli(["ask", "ok?", "--opt", "yes", "--opt", "no"])
        code, _, err = self.cli(["answer", "Q1", "maybe"])
        self.assertEqual(code, 2)
        self.assertIn("answer must be one of yes|no", err)
        self.assertIn("next:", err)

    def test_answering_twice_is_a_conflict_with_next(self):
        self.cli(["ask", "ok?", "--opt", "yes", "--opt", "no"])
        self.cli(["answer", "Q1", "yes"])
        code, _, err = self.cli(["answer", "Q1", "no"])
        self.assertEqual(code, 4)
        self.assertIn("next:", err)

    def test_default_must_be_one_of_the_options(self):
        code, _, err = self.cli(["ask", "ok?", "--opt", "yes", "--default", "maybe"])
        self.assertEqual(code, 2)
        self.assertIn("next:", err)

    def test_get_of_an_unknown_question_is_not_found_with_next(self):
        code, _, err = self.cli(["ask", "get", "Q9"])
        self.assertEqual(code, 3)
        self.assertIn("next: roadmap ask list", err)

    def test_list_shows_only_open_questions_and_ten_at_most(self):
        for n in range(12):
            self.cli(["ask", "question %d" % n])
        code, out, _ = self.cli(["ask", "list"])
        self.assertEqual(code, 0)
        self.assertLessEqual(len(out.splitlines()), 10)
        self.cli(["answer", "Q1", "done"])
        _, out, _ = self.cli(["ask", "list"])
        self.assertNotIn("Q1 open", out)

    def test_ask_json_envelope_carries_activity_and_undo(self):
        code, body = self.envelope(["ask", "ok?", "--opt", "yes", "--opt", "no"])
        self.assertEqual(code, 0)
        self.assertTrue(body["ok"])
        self.assertEqual(body["data"]["id"], "Q1")
        self.assertEqual(body["data"]["activity"], "A1")
        self.assertFalse(body["data"]["undo"])

    def test_an_ask_with_no_text_is_refused_with_next(self):
        code, _, err = self.cli(["ask"])
        self.assertNotEqual(code, 0)
        self.assertIn("next:", err)


class AskWaitTests(CmdCase):
    def ask(self, **extra):
        payload = {"text": "deploy now?", "opts": ["yes", "no"], "default": "yes"}
        payload.update(extra)
        return self.op("question.ask", payload, now=at(0))["data"]["id"]

    def test_answered_during_the_wait_prints_the_answer(self):
        qid = self.ask()
        state = {"t": 0}

        def sleep(seconds):
            state["t"] += seconds
            if state["t"] == 10:
                self.op("question.answer", {"id": qid, "value": "no"}, now=at(state["t"]))

        question, still_open = ask_cmd.wait_for(self.data, qid, sleep=sleep, clock=lambda: at(state["t"]))
        self.assertEqual(ask_cmd.line_of(question), "Q1 answered no")
        self.assertFalse(still_open)
        self.assertEqual(state["t"], 10)

    def test_timeout_takes_the_default(self):
        qid = self.ask(timeout=20)
        state = {"t": 0}
        question, still_open = ask_cmd.wait_for(self.data, qid,
                                                sleep=lambda s: state.__setitem__("t", state["t"] + s),
                                                clock=lambda: at(state["t"]))
        self.assertEqual(ask_cmd.line_of(question), "Q1 defaulted yes")
        self.assertFalse(still_open)
        self.assertEqual(state["t"], 20)

    def test_wait_stops_at_its_own_limit_and_says_still_open(self):
        qid = self.ask()
        state = {"t": 0}
        question, still_open = ask_cmd.wait_for(self.data, qid, timeout_s=30,
                                                sleep=lambda s: state.__setitem__("t", state["t"] + s),
                                                clock=lambda: at(state["t"]))
        self.assertTrue(still_open)
        self.assertEqual(ask_cmd.line_of(question), "Q1 open")
        self.assertEqual(state["t"], 30)

    def test_wait_polls_every_five_seconds(self):
        qid = self.ask()
        sleeps = []
        ask_cmd.wait_for(self.data, qid, timeout_s=20, sleep=sleeps.append, clock=lambda: at(sum(sleeps)))
        self.assertEqual(sleeps, [5, 5, 5, 5])

    def test_wait_longer_than_1800_seconds_is_refused_with_next(self):
        self.ask()
        code, _, err = self.cli(["ask", "wait", "Q1", "--timeout", "1801"])
        self.assertEqual(code, 2)
        self.assertIn("next:", err)

    def test_ask_wait_on_the_cli_prints_one_line(self):
        self.cli(["ask", "ok?", "--opt", "yes", "--opt", "no", "--default", "yes", "--timeout", "0"])
        code, out, err = self.cli(["ask", "wait", "Q1", "--timeout", "0"])
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "Q1 defaulted yes")
        self.assertEqual(len(out.splitlines()), 1)
