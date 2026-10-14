"""Issue commands on the CLI: new, list, show, close, link.
Output shape, error exits with next:, and the undo of close."""

from roadmap.services import issues
from tests.unit.test_cmd_support import CmdCase


class IssueCliTests(CmdCase):
    def test_new_prints_the_id_and_status(self):
        code, out, err = self.cli(["issue", "new", "Login fails", "--kind", "bug", "--sev", "1", "--task", "P1.1"])
        self.assertEqual((code, out.strip()), (0, "I1 open"), err)
        issue = issues.get(self.data, "I1")
        self.assertEqual((issue["sev"], issue["tasks"]), (1, ["P1.1"]))

    def test_new_with_a_bad_kind_or_sev_is_refused_with_next(self):
        code, _, err = self.cli(["issue", "new", "x", "--kind", "chaos"])
        self.assertEqual(code, 2)
        self.assertIn("next:", err)
        code, _, err = self.cli(["issue", "new", "x", "--sev", "high"])
        self.assertEqual(code, 2)
        self.assertIn("next:", err)
        self.assertEqual(issues.list_issues(self.data), [])

    def test_list_shows_open_issues_and_closed_only_with_all(self):
        self.cli(["issue", "new", "one"])
        self.cli(["issue", "new", "two"])
        self.cli(["issue", "close", "I1"])
        _, out, _ = self.cli(["issue", "list"])
        self.assertIn("I2 open", out)
        self.assertNotIn("I1", out)
        _, out, _ = self.cli(["issue", "list", "--all"])
        self.assertIn("I1 closed", out)

    def test_list_is_at_most_twenty_lines(self):
        for n in range(25):
            self.cli(["issue", "new", "item %d" % n])
        _, out, _ = self.cli(["issue", "list"])
        self.assertLessEqual(len(out.splitlines()), 20)

    def test_show_is_one_line(self):
        self.cli(["issue", "new", "Slow sync", "--kind", "risk", "--note", "seen twice"])
        code, out, _ = self.cli(["issue", "show", "I1"])
        self.assertEqual(code, 0)
        self.assertEqual(len(out.splitlines()), 1)
        self.assertIn("seen twice", out)

    def test_show_of_an_unknown_issue_is_not_found_with_next(self):
        code, _, err = self.cli(["issue", "show", "I9"])
        self.assertEqual(code, 3)
        self.assertIn("next: roadmap issue list", err)

    def test_close_then_close_again_says_already_closed(self):
        self.cli(["issue", "new", "one"])
        code, out, _ = self.cli(["issue", "close", "I1"])
        self.assertEqual((code, out.strip()), (0, "I1 closed"))
        _, out, _ = self.cli(["issue", "close", "I1"])
        self.assertEqual(out.strip(), "I1 already closed")

    def test_link_adds_tasks_without_duplicates_and_refuses_unknown_tasks(self):
        self.cli(["issue", "new", "one"])
        code, out, err = self.cli(["issue", "link", "I1", "P1.1", "P1.2"])
        self.assertEqual((code, out.strip()), (0, "I1 links P1.1 P1.2"), err)
        _, out, _ = self.cli(["issue", "link", "I1", "P1.2"])
        self.assertEqual(out.strip(), "I1 links P1.1 P1.2")
        code, _, err = self.cli(["issue", "link", "I1", "P9.9"])
        self.assertEqual(code, 3)
        self.assertIn("next:", err)

    def test_new_with_an_unknown_task_is_not_found_with_next(self):
        code, _, err = self.cli(["issue", "new", "one", "--task", "P9.9"])
        self.assertEqual(code, 3)
        self.assertIn("next:", err)
        self.assertEqual(issues.list_issues(self.data), [])

    def test_more_than_five_linked_tasks_is_refused_with_next(self):
        six = ["--task", "P1.1", "--task", "P1.2", "--task", "P1.3", "--task", "P2.1",
               "--task", "P1.1", "--task", "P1.2"]
        code, _, err = self.cli(["issue", "new", "too many"] + six)
        self.assertEqual(code, 2)
        self.assertIn("next:", err)
        self.assertEqual(issues.list_issues(self.data), [])

    def test_undo_reverses_close(self):
        self.cli(["issue", "new", "one"])
        code, body = self.envelope(["issue", "close", "I1"])
        self.assertEqual(code, 0)
        self.assertTrue(body["data"]["undo"])
        code, out, err = self.cli(["undo", body["data"]["activity"]])
        self.assertEqual(code, 0, err)
        self.assertEqual(issues.get(self.data, "I1")["status"], "open")
        self.assertTrue(out.startswith("undid A"))

    def test_json_envelope_for_list(self):
        self.cli(["issue", "new", "one"])
        code, body = self.envelope(["issue", "list"])
        self.assertEqual(code, 0)
        self.assertEqual(body["data"]["issues"][0]["id"], "I1")
