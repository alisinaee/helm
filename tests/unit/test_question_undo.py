"""Undo of question.answer (WP34): the inverse reopens the question, clears its answer and, for a blocking question,
makes ask wait see it open again. Also: the internal reopen op is refused from callers, and reopening a question that
is already open is a conflict and changes nothing."""

from roadmap.commands import ask as ask_cmd
from roadmap.errors import EXIT_CONFLICT, RoadmapError
from roadmap.services import commands, questions
from tests.unit.test_cmd_support import CmdCase, at


class QuestionUndoTests(CmdCase):
    def ask(self, **extra):
        payload = {"text": "deploy now?", "opts": ["yes", "no"], "default": "yes"}
        payload.update(extra)
        return self.op("question.ask", payload, now=at(0))["data"]["id"]

    def answer(self, qid, value="no", seconds=10):
        return self.op("question.answer", {"id": qid, "value": value}, now=at(seconds))

    def test_answer_reports_an_undo_and_undo_reopens_the_question(self):
        qid = self.ask()
        reply = self.answer(qid)
        self.assertTrue(reply["undo"])
        back = self.op("undo", {"activity": reply["activity"]}, now=at(20))
        self.assertEqual(back["data"]["op"], "question.reopen")
        question = questions.get(self.data, qid)
        self.assertEqual(question["status"], "open")
        self.assertIsNone(question["answer"])
        self.assertIsNone(question["answered"])

    def test_undo_of_a_blocking_question_makes_ask_wait_see_it_open(self):
        qid = self.ask(block=True)
        reply = self.answer(qid)
        self.op("undo", {"activity": reply["activity"]}, now=at(20))
        question = questions.get(self.data, qid)
        self.assertEqual(ask_cmd.line_of(question), qid + " open")

    def test_the_undo_record_and_the_activity_line_are_written(self):
        qid = self.ask()
        reply = self.answer(qid)
        self.op("undo", {"activity": reply["activity"]}, now=at(20))
        undo_rows = self.read_lines("undo.jsonl")
        self.assertEqual(undo_rows[0]["op"], "question.reopen")
        self.assertEqual(undo_rows[0]["args"], {"id": qid})
        self.assertEqual(undo_rows[-1]["undid"], reply["activity"])
        self.assertTrue(any(line["op"] == "undo" for line in self.read_lines("activity.jsonl")))

    def test_undo_twice_is_a_conflict_and_changes_nothing(self):
        qid = self.ask()
        reply = self.answer(qid)
        self.op("undo", {"activity": reply["activity"]}, now=at(20))
        with self.assertRaises(RoadmapError) as ctx:
            self.op("undo", {"activity": reply["activity"]}, now=at(21))
        self.assertEqual(ctx.exception.exit, EXIT_CONFLICT)
        self.assertEqual(questions.get(self.data, qid)["status"], "open")

    def test_reopen_of_an_open_question_is_a_conflict(self):
        qid = self.ask()
        with self.assertRaises(RoadmapError) as ctx:
            questions.reopen(self.data, qid)
        self.assertEqual(ctx.exception.exit, EXIT_CONFLICT)
        self.assertEqual(questions.get(self.data, qid)["status"], "open")

    def test_the_reopen_op_is_internal(self):
        self.assertNotIn("question.reopen", commands.public_ops())
        with self.assertRaises(RoadmapError) as ctx:
            self.op("question.reopen", {"id": "Q1"})
        self.assertEqual(ctx.exception.code, "usage")
