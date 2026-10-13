"""Number formatting cases shared with web/js/format.js (tests/fixtures/format_cases.json)."""

import json
import os
import unittest

from roadmap.core import format as fmt

CASES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures", "format_cases.json")


class FormatCaseTests(unittest.TestCase):
    def test_all_cases(self):
        with open(CASES, encoding="utf-8") as fh:
            cases = json.load(fh)
        self.assertGreater(len(cases), 30)
        for case in cases:
            with self.subTest(case=case):
                func = getattr(fmt, case["fn"])
                self.assertEqual(func(case["input"]), case["expected"])


if __name__ == "__main__":
    unittest.main()
