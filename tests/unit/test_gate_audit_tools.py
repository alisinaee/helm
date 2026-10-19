"""head.auditTools in roadmap.config.json, and board runtime files left out of the gate's uncommitted count."""

import unittest

from roadmap.services import head, hooks


class AuditToolsTest(unittest.TestCase):
    def test_default_nags_for_cursor_and_agy(self):
        items = head.gate([], dirty=2)
        self.assertTrue(any("cursor idle" in i for i in items))
        self.assertTrue(any("agy idle" in i for i in items))

    def test_empty_list_drops_the_tool_lines(self):
        items = head.gate([], dirty=2, audit_tools=[])
        self.assertEqual(items, ["2 uncommitted files"])

    def test_only_listed_tools(self):
        items = head.gate([], dirty=1, audit_tools=["agy"])
        self.assertFalse(any("cursor" in i for i in items))
        self.assertTrue(any("agy idle" in i for i in items))

    def test_config_reader(self):
        self.assertIsNone(hooks.audit_tools(None))
        self.assertIsNone(hooks.audit_tools({}))
        self.assertEqual(hooks.audit_tools({"auditTools": []}), [])


class BoardFileTest(unittest.TestCase):
    def test_board_files_are_not_work(self):
        self.assertTrue(hooks._board_file("docs/autonomy.json", "docs"))
        self.assertTrue(hooks._board_file("docs/head.jsonl", "docs"))
        self.assertFalse(hooks._board_file("docs/HANDOVER.md", "docs"))
        self.assertFalse(hooks._board_file("docs/reviews/x.json", "docs"))
        self.assertFalse(hooks._board_file("roadmap/cli.py", "docs"))


if __name__ == "__main__":
    unittest.main()
