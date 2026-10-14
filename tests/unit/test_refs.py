"""Tests for roadmap.core.refs: the ref text (parse, format, round trip), the record for each kind, the 10-line cap and
the rule that no record carries an absolute path. Pure: no files, no ROADMAP_HOME."""

import unittest

from roadmap.core import refs

SNAP = {
    "project": {"id": "roadmap-board", "title": "Roadmap board"},
    "phases": [{"id": "P1", "name": "Engine", "state": "partial", "done": 1, "total": 3}],
    "tasks": [
        {"id": "P1.1", "phase": "P1", "title": "Planner filters", "state": "partial", "feats": ["F7"],
         "subs": [{"t": "one", "d": True}, {"t": "two", "d": False}, {"t": "three", "d": False}]},
        {"id": "P1.2", "phase": "P1", "title": "Orphan task", "state": "todo"},
    ],
    "features": {"rows": [{"id": "F7", "title": "Filters", "state": "doing", "done": 0, "total": 1, "prio": 2,
                           "blocked": 0, "phase": "P1"}],
                 "orphans": ["P1.2"], "uncovered": [], "counts": {}},
    "jobs": [{"id": "j12", "title": "Write filter", "status": "running", "model": "opus", "task": "P1.1",
              "tokensK": 20.5}],
}


class ParseTests(unittest.TestCase):
    def test_round_trip_for_every_kind(self):
        cases = [("roadmap-board", "phase", "R3"), ("roadmap-board", "task", "R3.2"),
                 ("roadmap-board", "sub", "R3.2.s1"), ("roadmap-board", "feature", "F7"),
                 ("roadmap-board", "issue", "I1"), ("roadmap-board", "question", "Q1"),
                 ("roadmap-board", "job", "j12"), ("roadmap-board", "research", "01"),
                 ("roadmap-board", "section", "planner.orphans"), ("roadmap-board", "view", "workflow")]
        for project, kind, ident in cases:
            with self.subTest(kind=kind):
                text = refs.format_ref(project, kind, ident)
                self.assertEqual(refs.parse(text), (project, kind, ident))
                self.assertRegex(text, refs.REF_RE)

    def test_project_only_ref(self):
        self.assertEqual(refs.format_ref("roadmap-board", refs.PROJECT), "rb:roadmap-board")
        self.assertEqual(refs.parse("rb:roadmap-board"), ("roadmap-board", "project", "roadmap-board"))

    def test_examples_from_the_spec(self):
        self.assertEqual(refs.parse("rb:roadmap-board/task/R3.2"), ("roadmap-board", "task", "R3.2"))
        self.assertEqual(refs.parse("rb:roadmap-board/section/planner.orphans"),
                         ("roadmap-board", "section", "planner.orphans"))

    def test_surrounding_space_is_ignored(self):
        self.assertEqual(refs.parse("  rb:roadmap-board/feature/F7\n"), ("roadmap-board", "feature", "F7"))

    def test_malformed_refs_are_refused(self):
        bad = ["", "task/R3.2", "rb:", "rb:Roadmap/task/R3.2", "rb:x/task", "rb:x/task/", "rb:x/rule/R1",
               "rb:x/project/y", "rb:x/task/R3 2", "rb:x/task/R3/2", "rb:x/Task/R3", "https://x", None]
        for text in bad:
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    refs.parse(text)

    def test_format_refuses_unknown_kind_and_bad_id(self):
        with self.assertRaises(ValueError):
            refs.format_ref("x", "rule", "R1")
        with self.assertRaises(ValueError):
            refs.format_ref("x", "task", "R3 2")


class BuildTests(unittest.TestCase):
    def test_task_record_shows_status_feature_and_subtasks(self):
        rows, nxt = refs.build(SNAP, "roadmap-board", "task", "P1.1")
        lines = refs.lines("rb:roadmap-board/task/P1.1", rows, nxt)
        self.assertEqual(lines[0], "ref: rb:roadmap-board/task/P1.1")
        self.assertIn("title: Planner filters", lines)
        self.assertIn("status: partial  phase: P1  feature: F7  orphan: no", lines)
        self.assertIn("subs: 1/3 done", lines)
        self.assertEqual(lines[-1], "next: roadmap task show P1.1")

    def test_orphan_task_is_flagged(self):
        rows, _ = refs.build(SNAP, "roadmap-board", "task", "P1.2")
        self.assertIn("orphan: yes", refs.lines("rb:x/task/P1.2", rows, "roadmap task show P1.2")[2])

    def test_sub_record_points_at_its_task(self):
        rows, nxt = refs.build(SNAP, "roadmap-board", "sub", "P1.1.s2")
        lines = refs.lines("rb:roadmap-board/sub/P1.1.s2", rows, nxt)
        self.assertIn("title: two", lines)
        self.assertIn("status: open  task: P1.1", lines)
        self.assertEqual(lines[-1], "next: roadmap task show P1.1")

    def test_sub_index_out_of_range_is_unknown(self):
        self.assertIsNone(refs.build(SNAP, "roadmap-board", "sub", "P1.1.s9"))
        self.assertIsNone(refs.build(SNAP, "roadmap-board", "sub", "P1.1.sx"))

    def test_feature_phase_job_project_and_section_records(self):
        rows, nxt = refs.build(SNAP, "roadmap-board", "feature", "F7")
        self.assertIn("status: doing  tasks: 0/1 done  prio: 2", refs.lines("r", rows, nxt))
        self.assertEqual(nxt, "roadmap feature show F7")
        rows, nxt = refs.build(SNAP, "roadmap-board", "phase", "P1")
        self.assertIn("status: partial  tasks: 1/3 done", refs.lines("r", rows, nxt))
        rows, nxt = refs.build(SNAP, "roadmap-board", "job", "j12")
        self.assertIn("state: running  model: opus  tokens: 20.5k", refs.lines("r", rows, nxt))
        self.assertEqual(nxt, "roadmap job list")
        rows, nxt = refs.build(SNAP, "roadmap-board", "project", "roadmap-board")
        self.assertEqual(refs.lines("r", rows, nxt)[1], "title: Roadmap board")
        rows, nxt = refs.build(SNAP, "roadmap-board", "section", "planner.orphans")
        self.assertIn("view: planner  section: orphans", refs.lines("r", rows, nxt))
        self.assertEqual(nxt, "roadmap status")

    def test_items_outside_the_snapshot_use_the_looked_up_item(self):
        rows, nxt = refs.build(SNAP, "p", "issue", "I9", {"title": "Login fails", "status": "closed", "kind": "bug",
                                                          "sev": 1, "tasks": ["P1.1"], "note": None})
        self.assertIn("status: closed  kind: bug  sev: 1  tasks: P1.1", refs.lines("r", rows, nxt))
        self.assertEqual(nxt, "roadmap issue show I9")
        rows, nxt = refs.build(SNAP, "p", "question", "Q2", {"text": "Which db?", "status": "answered",
                                                            "block": True, "task": ""})
        self.assertIn("status: answered  block: yes  task: -", refs.lines("r", rows, nxt))
        self.assertEqual(nxt, "roadmap ask get Q2")
        rows, nxt = refs.build(SNAP, "p", "research", "01", {"title": "first", "file": "research/01-first.md"})
        self.assertIn("file: research/01-first.md", refs.lines("r", rows, nxt))

    def test_missing_items_are_none(self):
        self.assertIsNone(refs.build(SNAP, "p", "task", "R9.9"))
        self.assertIsNone(refs.build(SNAP, "p", "feature", "F99"))
        self.assertIsNone(refs.build(SNAP, "p", "issue", "I1"))
        self.assertIsNone(refs.build(SNAP, "p", "section", "planner"))


class LinesTests(unittest.TestCase):
    def test_at_most_ten_lines_and_next_stays_last(self):
        rows = [[("k%d" % n, "v")] for n in range(30)]
        lines = refs.lines("rb:x/task/R1", rows, "roadmap task show R1")
        self.assertEqual(len(lines), refs.LINE_MAX)
        self.assertEqual(lines[0], "ref: rb:x/task/R1")
        self.assertEqual(lines[-1], "next: roadmap task show R1")

    def test_values_are_one_line(self):
        lines = refs.lines("r", [[("title", "two\nlines")]], "n")
        self.assertEqual(lines[1], "title: two lines")

    def test_data_object_has_every_key_and_next(self):
        rows, nxt = refs.build(SNAP, "roadmap-board", "task", "P1.1")
        obj = refs.data("rb:roadmap-board/task/P1.1", rows, nxt)
        self.assertEqual(obj["title"], "Planner filters")
        self.assertEqual(obj["feature"], "F7")
        self.assertEqual(obj["orphan"], "no")
        self.assertEqual(obj["next"], "roadmap task show P1.1")

    def test_no_record_has_an_absolute_path_or_home_marker(self):
        for kind, ident in (("task", "P1.1"), ("feature", "F7"), ("phase", "P1"), ("job", "j12"),
                            ("project", "roadmap-board"), ("section", "planner.orphans")):
            rows, nxt = refs.build(SNAP, "roadmap-board", kind, ident)
            text = "\n".join(refs.lines("rb:roadmap-board/%s/%s" % (kind, ident), rows, nxt))
            with self.subTest(kind=kind):
                self.assertNotIn("/Users/", text)
                self.assertNotIn("~", text)


if __name__ == "__main__":
    unittest.main()
