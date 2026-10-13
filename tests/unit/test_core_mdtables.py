"""Markdown helpers: escaped pipes, ragged rows, separators, sections and status classification."""

import unittest

from roadmap.core.mdtables import cell, classify, iter_tables, section, split_row


class SplitRowTests(unittest.TestCase):
    def test_plain_row(self):
        self.assertEqual(split_row("| a | b | c |"), ["a", "b", "c"])

    def test_escaped_pipe_stays_in_cell(self):
        self.assertEqual(split_row(r"| a \| b | c |"), ["a | b", "c"])

    def test_escaped_pipe_at_row_end_is_not_a_closer(self):
        self.assertEqual(split_row(r"| a | b \|"), ["a", r"b |"])

    def test_row_without_edge_pipes(self):
        self.assertEqual(split_row("a | b"), ["a", "b"])


class CellTests(unittest.TestCase):
    def test_ragged_short_row_gives_empty(self):
        self.assertEqual(cell(["x"], 3), "")
        self.assertEqual(cell([], 0), "")

    def test_negative_index_gives_empty(self):
        self.assertEqual(cell(["x", "y"], -1), "")


class IterTablesTests(unittest.TestCase):
    def test_table_with_ragged_rows(self):
        text = "| A | B | C |\n|---|---|---|\n| 1 | 2 |\n| 1 | 2 | 3 | 4 |\n\nafter\n"
        tables = list(iter_tables(text))
        self.assertEqual(len(tables), 1)
        head, rows = tables[0]
        self.assertEqual(head, ["A", "B", "C"])
        self.assertEqual(rows, [["1", "2"], ["1", "2", "3", "4"]])

    def test_header_without_separator_is_not_a_table(self):
        self.assertEqual(list(iter_tables("| A | B |\n| 1 | 2 |\n")), [])

    def test_alignment_colons_accepted(self):
        tables = list(iter_tables("| A | B |\n|:---|---:|\n| 1 | 2 |\n"))
        self.assertEqual(tables[0][1], [["1", "2"]])


class SectionTests(unittest.TestCase):
    def test_prefix_match_stops_at_next_heading(self):
        text = "## 7.9 RH checks\nbody\n## 8. Other\nno\n"
        self.assertEqual(section(text, "7.9"), "body")

    def test_missing_section_is_empty(self):
        self.assertEqual(section("## A\nx\n", "B"), "")


class ClassifyTests(unittest.TestCase):
    def test_emoji_wins_by_position(self):
        self.assertEqual(classify("✅ passed"), "done")
        self.assertEqual(classify("\U0001F7E1 partial ✅"), "partial")
        self.assertEqual(classify("⬜"), "todo")
        self.assertEqual(classify("⏸ hold"), "hold")

    def test_word_fallbacks(self):
        self.assertEqual(classify("Parked for later"), "hold")
        self.assertEqual(classify("Researched"), "done")
        self.assertEqual(classify("in progress"), "partial")
        self.assertEqual(classify("nothing yet"), "todo")


if __name__ == "__main__":
    unittest.main()
