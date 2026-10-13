"""The demo projects under fixtures/demo load through the real parsers with no errors, and their counts match the
demo brief: alpha is the busy one, beta is medium, gamma is the empty start. Nothing is written; the files are read
from the repo, never copied into a real home."""

import datetime
import os
import unittest

from roadmap.core import parsers
from tests.unit.test_store_support import REPO

DEMO = os.path.join(REPO, "fixtures", "demo")
NOW = datetime.datetime(2026, 10, 13, 18, 0).astimezone()


def read_docs(project, name):
    with open(os.path.join(DEMO, project, "docs", name), encoding="utf-8") as fh:
        return fh.read()


class DemoFixtureTests(unittest.TestCase):
    def test_alpha_has_forty_tasks_in_five_phases_with_three_running_jobs(self):
        tasks, errors = parsers.parse_tasks(read_docs("alpha", "tasks.json"))
        self.assertEqual(errors, [])
        self.assertEqual(len(tasks["phases"]), 5)
        self.assertEqual(len(tasks["tasks"]), 40)
        jobs, errors = parsers.parse_jobs(read_docs("alpha", "jobs.json"), NOW)
        self.assertEqual(errors, [])
        self.assertEqual(sum(1 for job in jobs if job["status"] == "running"), 3)

    def test_alpha_has_four_open_issues_one_of_them_a_blocker(self):
        issues, errors = parsers.parse_issues(read_docs("alpha", "issues.json"))
        self.assertEqual(errors, [])
        self.assertEqual(sum(1 for issue in issues if issue["status"] in parsers.ISSUE_OPEN), 4)
        self.assertEqual(sum(1 for issue in issues if issue["kind"] == "blocker"), 1)

    def test_alpha_has_two_open_questions(self):
        questions, errors = parsers.parse_questions(read_docs("alpha", "questions.json"))
        self.assertEqual(errors, [])
        self.assertEqual(sum(1 for q in questions if q["status"] == "open"), 2)

    def test_beta_has_fifteen_tasks_in_three_phases_and_no_errors(self):
        tasks, errors = parsers.parse_tasks(read_docs("beta", "tasks.json"))
        self.assertEqual(errors, [])
        self.assertEqual(len(tasks["phases"]), 3)
        self.assertEqual(len(tasks["tasks"]), 15)
        jobs, errors = parsers.parse_jobs(read_docs("beta", "jobs.json"), NOW)
        self.assertEqual(errors, [])
        self.assertEqual(len(jobs), 3)
        issues, errors = parsers.parse_issues(read_docs("beta", "issues.json"))
        self.assertEqual((issues, errors), ([], []))
        questions, errors = parsers.parse_questions(read_docs("beta", "questions.json"))
        self.assertEqual((questions, errors), ([], []))

    def test_gamma_has_one_phase_and_three_todo_tasks(self):
        tasks, errors = parsers.parse_tasks(read_docs("gamma", "tasks.json"))
        self.assertEqual(errors, [])
        self.assertEqual(len(tasks["phases"]), 1)
        self.assertEqual([t["state"] for t in tasks["tasks"]], ["todo", "todo", "todo"])
        jobs, errors = parsers.parse_jobs(read_docs("gamma", "jobs.json"), NOW)
        self.assertEqual((jobs, errors), ([], []))
        issues, errors = parsers.parse_issues(read_docs("gamma", "issues.json"))
        self.assertEqual((issues, errors), ([], []))
        questions, errors = parsers.parse_questions(read_docs("gamma", "questions.json"))
        self.assertEqual((questions, errors), ([], []))


if __name__ == "__main__":
    unittest.main()
