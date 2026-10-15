"""Table test for the Work item status roll-up (docs/WORK-MODEL.md section 2)."""

import unittest

from roadmap.core.workstatus import (
    BACKLOG, DOING, DONE, REVIEW, TODO, WONT_DO, rollup,
)


def t(state):
    return {"state": state}


# (case, work_item, agent_tasks, person_accepted, expected status, expected badges, expected (done, total))
CASES = [
    # Backlog / Won't do: person-set, roll-up never moves them
    ("backlog stays with running task", {"state": "backlog"}, [t("running")], False, BACKLOG, ["running"], (0, 1)),
    ("backlog stays with all done", {"state": "backlog"}, [t("done")], False, BACKLOG, [], (1, 1)),
    ("wontfix with no tasks", {"state": "wontfix"}, [], False, WONT_DO, [], (0, 0)),
    ("wontfix with running task", {"state": "wontfix"}, [t("running")], False, WONT_DO, ["running"], (0, 1)),
    # Todo: no agent task started
    ("no agent tasks", {}, [], False, TODO, [], (0, 0)),
    ("all tasks todo", {}, [t("todo"), t("todo")], False, TODO, [], (0, 2)),
    ("only cancelled tasks", {}, [t("cancelled")], False, TODO, [], (0, 0)),
    ("only needs-you, none started", {}, [t("needs-you")], False, TODO, ["needs-you"], (0, 1)),
    # Doing: claimed / running / verify / failed, or some done and some open
    ("one running", {}, [t("running")], False, DOING, ["running"], (0, 1)),
    ("one claimed", {}, [t("claimed")], False, DOING, ["running"], (0, 1)),
    ("one verify", {}, [t("verify")], False, DOING, ["running"], (0, 1)),
    ("one failed", {}, [t("failed")], False, DOING, [], (0, 1)),
    ("done and todo", {}, [t("done"), t("todo")], False, DOING, [], (1, 2)),
    ("done and needs-you", {}, [t("done"), t("needs-you")], False, DOING, ["needs-you"], (1, 2)),
    ("done and cancelled is still review", {}, [t("done"), t("cancelled")], False, REVIEW, [], (1, 1)),
    # Review: every non-cancelled agent task done; not Done without accept
    ("all done", {}, [t("done"), t("done")], False, REVIEW, [], (2, 2)),
    ("single done task", {}, [t("done")], False, REVIEW, [], (1, 1)),
    # Done: only the person's accept
    ("accepted, all done", {}, [t("done")], True, DONE, [], (1, 1)),
    ("accepted, no tasks", {}, [], True, DONE, [], (0, 0)),
    ("accepted, cancelled and done", {}, [t("cancelled"), t("done")], True, DONE, [], (1, 1)),
    ("accepted but still running", {}, [t("done"), t("running")], True, DOING, ["running"], (1, 2)),
    # Reopen: new agent task on a Done item, or person rejects in Review
    ("accepted, new todo task reopens", {}, [t("done"), t("todo")], True, DOING, [], (1, 2)),
    ("rejected in review", {"reopened": True}, [t("done")], False, DOING, [], (1, 1)),
    # Legacy: already-finished items migrate to Done
    ("legacy stored done", {"state": "done"}, [t("done")], False, DONE, [], (1, 1)),
    ("legacy stored done, no tasks", {"state": "done"}, [], False, DONE, [], (0, 0)),
    # Badges: blocked by an open issue, not by a closed one
    ("blocked by open issue", {"blocked_by": [{"state": "Todo"}]}, [t("todo")], False, TODO, ["blocked"], (0, 1)),
    ("blocked by doing issue", {"blocked_by": [{"state": "Doing"}]}, [], False, TODO, ["blocked"], (0, 0)),
    ("closed issue does not block", {"blocked_by": [{"state": "Done"}, {"state": "Won't do"}]},
     [t("todo")], False, TODO, [], (0, 1)),
    # Badge order is fixed: needs-you, blocked, running
    ("all three badges", {"blocked_by": [{"state": "Todo"}]}, [t("running"), t("needs-you")], False, DOING,
     ["needs-you", "blocked", "running"], (0, 2)),
    # Progress counts non-cancelled tasks only
    ("progress ignores cancelled", {}, [t("done"), t("cancelled"), t("todo"), t("todo")], False, DOING, [],
     (1, 3)),
]


class WorkRollupTest(unittest.TestCase):
    def test_section2_table(self):
        for name, item, tasks, accepted, status, badges, progress in CASES:
            with self.subTest(case=name):
                got = rollup(item, tasks, accepted, now=None)
                self.assertEqual(got["status"], status)
                self.assertEqual(got["badges"], badges)
                self.assertEqual((got["progress"]["done"], got["progress"]["total"]), progress)

    def test_now_does_not_change_result(self):
        self.assertEqual(rollup({}, [t("done")], False, now=0), rollup({}, [t("done")], False, now="later"))

    def test_inputs_not_mutated(self):
        item = {"state": "backlog", "blocked_by": [{"state": "Todo"}]}
        tasks = [t("running")]
        rollup(item, tasks, False)
        self.assertEqual(item, {"state": "backlog", "blocked_by": [{"state": "Todo"}]})
        self.assertEqual(tasks, [{"state": "running"}])


if __name__ == "__main__":
    unittest.main()
