"""Flow 6: rules. Rules are added from the CLI, shown to an agent, and synced into the project's CLAUDE.md between the
roadmap markers. A second sync changes nothing and prints +0 ~0 -0; the hand-written text around the block is kept."""

import unittest

from tests.integration.harness import stack

BEGIN = "<!-- roadmap:rules -->"
END = "<!-- /roadmap:rules -->"
HAND_WRITTEN = "# Split\n\nHand written notes that must survive a sync.\n"


class RulesFlowTests(unittest.TestCase):
    def test_add_show_and_sync_twice_keeps_the_hand_written_text(self):
        sandbox, _ = stack(self)
        claude_md = sandbox.project + "/CLAUDE.md"
        with open(claude_md, "w", encoding="utf-8") as fh:
            fh.write(HAND_WRITTEN)

        self.assertIn("R1 all do", sandbox.cli(["rules", "add", "all", "do", "Run the test suite before done"]).stdout)
        self.assertIn("R2 claude dont", sandbox.cli(["rules", "add", "claude", "dont", "Never commit secrets"]).stdout)

        shown = sandbox.cli(["rules", "show"], agent=True)
        self.assertEqual(shown.returncode, 0, shown.stderr)
        self.assertIn("Run the test suite before done", shown.stdout)
        self.assertLessEqual(len(shown.stdout.splitlines()), 12)

        first = sandbox.cli(["rules", "sync"])
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(first.stdout.strip(), "+2 ~0 -0")
        second = sandbox.cli(["rules", "sync"])
        self.assertEqual(second.stdout.strip(), "+0 ~0 -0")

        with open(claude_md, encoding="utf-8") as fh:
            text = fh.read()
        self.assertTrue(text.startswith(HAND_WRITTEN))
        self.assertEqual(text.count(BEGIN), 1)
        self.assertEqual(text.count(END), 1)
        self.assertIn("- R1 all do | Run the test suite before done", text)
        self.assertIn("- R2 claude dont | Never commit secrets", text)


if __name__ == "__main__":
    unittest.main()
