"""The status line budget with many running jobs: the features line keeps its place, and more than two running jobs
collapse into one 'running N: id,id,...' line. Two or fewer jobs keep their own run lines."""

from unittest import mock

from roadmap.commands import status as status_cmd
from tests.unit.test_cmd_support import CmdCase

FEATURES = "features: 3 (1 done, 1 doing, 1 todo, 0 uncovered)"


class RunningLineTests(CmdCase):
    def test_features_line_survives_four_running_jobs(self):
        for n in range(1, 5):
            self.cli(["job", "start", "Work %d" % n, "haiku", "P1.1"])
        with mock.patch.object(status_cmd.features, "status_line", return_value=FEATURES):
            code, out, err = self.cli(["status"])
        self.assertEqual(code, 0, err)
        lines = out.splitlines()
        self.assertLessEqual(len(lines), 8)
        self.assertLessEqual(len(out), 700)
        self.assertIn(FEATURES, lines)
        self.assertIn("running 4: j1,j2,j3,j4", lines)
        self.assertFalse(any(line.startswith("run: ") for line in lines))

    def test_two_running_jobs_keep_their_own_lines(self):
        self.cli(["job", "start", "Work 1", "haiku", "P1.1"])
        self.cli(["job", "start", "Work 2", "sonnet", "P2.1"])
        code, out, _ = self.cli(["status"])
        self.assertEqual(code, 0)
        self.assertIn("run: j1 haiku P1.1", out)
        self.assertIn("run: j2 sonnet P2.1", out)
        self.assertNotIn("running 2:", out)

    def test_compose_collapses_many_run_lines_into_one(self):
        base = ["demo  updated x", "left 1", "P1 0%", "run: j1 haiku P1.1 1m", "run: j2 haiku P1.2 1m"]
        extras = {"ask": "ask: none open", "queue": "queue: empty", "issues": "issues: none open",
                  "budget": "budget: 0k spent, no project limit", "features": FEATURES,
                  "running": "running 3: j1,j2,j3"}
        lines = status_cmd.compose(base, extras)
        self.assertEqual(lines, ["demo  updated x", "left 1", "P1 0%", "running 3: j1,j2,j3", "ask: none open",
                                 "queue: empty", "issues: none open", FEATURES])

    def test_running_line_is_none_for_two_or_fewer(self):
        jobs = [{"id": "j1", "status": "running"}, {"id": "j2", "status": "running"}, {"id": "j3", "status": "done"}]
        self.assertIsNone(status_cmd.running_line(jobs))
        jobs.append({"id": "j4", "status": "running"})
        self.assertEqual(status_cmd.running_line(jobs), "running 3: j1,j2,j4")
