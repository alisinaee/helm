"""Flow 1: an agent asks a blocking question, the GUI answers it over /api/v1/cmd, the agent reads the answer, the
activity log has the lines, and Undo from the GUI reopens the question."""

import json
import unittest

from tests.integration.harness import stack


class QuestionFlowTests(unittest.TestCase):
    def test_agent_asks_gui_answers_agent_reads_and_undo_reopens(self):
        sandbox, server = stack(self)
        asked = sandbox.cli_json(["ask", "Use the staging key?", "--task", "P0.1", "--opt", "yes", "--opt", "no",
                                  "--block"], agent=True)
        qid = asked["id"]
        self.assertEqual((asked["status"], asked["block"], asked["task"]), ("open", True, "P0.1"))

        got = sandbox.cli(["ask", "get", qid], agent=True)
        self.assertEqual((got.returncode, got.stdout.strip()), (0, qid + " open"))
        waited = sandbox.cli(["ask", "wait", qid, "--timeout", "0"], agent=True)
        self.assertEqual((waited.returncode, waited.stdout.strip()), (0, qid + " open"))

        reply = server.cmd("question.answer", {"id": qid, "value": "yes"})
        self.assertTrue(reply["ok"])
        self.assertEqual(reply["data"]["status"], "answered")
        self.assertTrue(reply["undo"])
        answered_at = reply["activity"]

        got = sandbox.cli(["ask", "get", qid], agent=True)
        self.assertEqual(got.stdout.strip(), qid + " answered yes")
        waited = sandbox.cli_json(["ask", "wait", qid, "--timeout", "0"], agent=True)
        self.assertEqual((waited["question"]["answer"], waited["still_open"]), ("yes", False))

        lines = server.snapshot(sandbox.pid)["activity"]
        ops = [(line["op"], line["src"]) for line in lines]
        self.assertIn(("question.ask", "cli"), ops)  # the asking line (src is 'cli' today, see the expected failure)
        self.assertIn(("question.answer", "gui"), ops)
        self.assertIn("Q1 answered yes", [line["sum"] for line in lines if line["op"] == "question.answer"])

        undone = server.cmd("undo", {"activity": answered_at})
        self.assertTrue(undone["ok"])
        got = sandbox.cli(["ask", "get", qid], agent=True)
        self.assertEqual(got.stdout.strip(), qid + " open")
        self.assertIn(qid, json.dumps(server.snapshot(sandbox.pid)["questions"]))

    @unittest.expectedFailure
    def test_agent_shell_writes_are_logged_with_source_agent(self):
        """Known bug, see changes/WP38.md: commands.write hard-codes source 'cli', so an ask from an agent shell is
        logged as src 'cli' (roadmap/services/commands.py:590)."""
        sandbox, server = stack(self)
        sandbox.cli_json(["ask", "Which region?"], agent=True)
        lines = server.snapshot(sandbox.pid)["activity"]
        self.assertEqual([line["src"] for line in lines if line["op"] == "question.ask"], ["agent"])


if __name__ == "__main__":
    unittest.main()
