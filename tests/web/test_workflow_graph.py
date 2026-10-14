"""The workflow graph model and layout (WP71), run in node by tests/web/render_graph.mjs over
tests/fixtures/graph/*.json.

Checks: buildGraph and layout give byte-identical output for the same input, in one run and across two runs; no two
nodes in a lane overlap; every edge has a cubic path; each node sits inside its lane band; the 350-task fixture is
capped at 300 nodes after the collapse; the cycle fixture finishes and reports its back edge; the empty fixture gives
an empty graph; the chain, fan-in, blocker and filter cases hold their shape. The node checks are skipped when node is
not installed.
"""

import json
import os
import re
import shutil
import subprocess
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
WEB = os.path.join(REPO, "web")
RENDER = os.path.join(TESTS, "web", "render_graph.mjs")
FIXTURES = os.path.join(TESTS, "fixtures", "graph")
NODE = shutil.which("node")
NUM = r"-?\d+(?:\.\d+)?"
PATH_RE = re.compile(r"^M%s %sC%s %s %s %s %s %s$" % ((NUM, NUM) + (NUM,) * 6))
EXPECTED = {"empty", "chain", "fan-in", "with-blockers", "cycle", "350-tasks"}


def render():
    proc = subprocess.run([NODE, "--experimental-default-type=module", RENDER, WEB, FIXTURES],
                          capture_output=True, text=True, check=False, timeout=120)
    if proc.returncode != 0:
        raise AssertionError("render_graph.mjs failed: " + proc.stderr[-800:])
    return json.loads(proc.stdout)


def overlaps(a, b):
    return (a["x"] < b["x"] + b["w"] and b["x"] < a["x"] + a["w"] and
            a["y"] < b["y"] + b["h"] and b["y"] < a["y"] + a["h"])


@unittest.skipUnless(NODE, "node is not installed")
class WorkflowGraphTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = render()

    def test_fixtures_present(self):
        self.assertEqual(EXPECTED, set(self.out))

    def test_deterministic_within_one_run(self):
        for name, case in self.out.items():
            with self.subTest(fixture=name):
                self.assertEqual(case["graphText"], case["graphAgainText"])
                self.assertEqual(case["depText"], case["depAgainText"])
                self.assertEqual(case["timeText"], case["timeAgainText"])

    def test_deterministic_across_runs(self):
        again = render()
        self.assertEqual(json.dumps(self.out, sort_keys=True), json.dumps(again, sort_keys=True))

    def test_no_overlaps_within_a_lane(self):
        for name, case in self.out.items():
            for mode in ("dep", "time", "timeAll"):
                layout = case[mode]
                lane_of = {n["id"]: n["lane"] for n in case["graph"]["nodes"]}
                with self.subTest(fixture=name, mode=mode):
                    by_lane = {}
                    for node_id, box in layout["pos"].items():
                        self.assertIn(node_id, lane_of, "every placed box belongs to a node")
                        by_lane.setdefault(lane_of[node_id], []).append((node_id, box))
                    for lane, rows in by_lane.items():
                        for i, (id_a, a) in enumerate(rows):
                            for id_b, b in rows[i + 1:]:
                                self.assertFalse(overlaps(a, b), "%s and %s overlap in %s" % (id_a, id_b, lane))

    def test_every_node_has_a_box_inside_its_lane_band(self):
        for name, case in self.out.items():
            layout = case["dep"]
            bands = {band["id"]: band for band in layout["lanes"]}
            with self.subTest(fixture=name):
                for node in case["graph"]["nodes"]:
                    box = layout["pos"].get(node["id"])
                    self.assertIsNotNone(box, node["id"])
                    band = bands[node["lane"]]
                    self.assertGreaterEqual(box["y"], band["y"])
                    self.assertLessEqual(box["y"] + box["h"], band["y"] + band["h"])

    def test_every_edge_has_a_cubic_path(self):
        for name, case in self.out.items():
            for mode in ("dep", "time"):
                layout = case[mode]
                with self.subTest(fixture=name, mode=mode):
                    for edge in case["graph"]["edges"]:
                        self.assertIn(edge["id"], layout["paths"])
                        self.assertRegex(layout["paths"][edge["id"]], PATH_RE)
                    self.assertEqual(len(case["graph"]["edges"]), len(layout["paths"]))

    def test_350_tasks_collapse_to_300_or_fewer(self):
        case = self.out["350-tasks"]
        self.assertEqual(350, sum(1 for n in case["expanded"]["nodes"] if n["type"] == "task"))
        self.assertGreater(len(case["expanded"]["nodes"]), 300)
        self.assertLessEqual(len(case["graph"]["nodes"]), 300)
        self.assertEqual(["P1", "P2", "P3", "P4", "P5"], case["graph"]["stats"]["collapsed"])
        labels = {n["id"]: n["label"] for n in case["graph"]["nodes"]}
        self.assertEqual("Phase P1: 50 done", labels["collapse:P1"])

    def test_cycle_finishes_and_reports_its_back_edge(self):
        case = self.out["cycle"]
        self.assertEqual(["task:P1.3>task:P1.1"], case["dep"]["cycles"])
        self.assertEqual(4, len(case["dep"]["paths"]))

    def test_empty_fixture_is_empty(self):
        case = self.out["empty"]
        self.assertEqual([], case["graph"]["nodes"])
        self.assertEqual([], case["graph"]["edges"])
        self.assertEqual([], case["graph"]["lanes"])
        self.assertEqual({}, case["dep"]["pos"])
        self.assertEqual({}, case["dep"]["paths"])
        self.assertEqual([], case["dep"]["cycles"])
        self.assertGreater(case["dep"]["width"], 0)
        self.assertGreater(case["dep"]["height"], 0)

    def test_chain_ranks_increase_left_to_right(self):
        pos = self.out["chain"]["dep"]["pos"]
        xs = [pos["task:P1.%d" % k]["x"] for k in range(1, 5)]
        self.assertEqual(sorted(xs), xs)
        self.assertEqual(len(set(xs)), 4)

    def test_fan_in_merge_sits_right_of_all_inputs(self):
        pos = self.out["fan-in"]["dep"]["pos"]
        merge = pos["task:P1.4"]["x"]
        for k in (1, 2, 3):
            self.assertLess(pos["task:P1.%d" % k]["x"], merge)
        self.assertGreater(pos["task:P2.1"]["x"], merge)

    def test_time_mode_has_ticks_and_a_now_line(self):
        time = self.out["chain"]["time"]
        self.assertEqual("time", time["mode"])
        self.assertGreater(len(time["ticks"]), 0)
        self.assertIsNotNone(time["nowX"])
        xs = [t["x"] for t in time["ticks"]]
        self.assertEqual(sorted(xs), xs)

    def test_more_than_three_jobs_collapse_into_a_plus_pill(self):
        graph = self.out["with-blockers"]["graph"]
        more = [n for n in graph["nodes"] if n["id"] == "job+:P1.1"]
        self.assertEqual(1, len(more))
        self.assertEqual("+3", more[0]["label"])
        shown = [n["id"] for n in graph["nodes"] if n["type"] == "job" and n["task"] == "P1.1"]
        self.assertEqual(["job+:P1.1", "job:J4", "job:J5"], shown)

    def test_blocker_issue_sits_in_the_column_of_the_task_it_blocks(self):
        case = self.out["with-blockers"]
        pos = case["dep"]["pos"]
        for edge in case["graph"]["edges"]:
            if edge["type"] != "blocker":
                continue
            with self.subTest(edge=edge["id"]):
                issue, task = pos[edge["from"]], pos[edge["to"]]
                self.assertEqual(task["x"], issue["x"])
                self.assertLess(issue["y"], task["y"])

    def test_queue_pill_is_in_column_zero(self):
        pos = self.out["with-blockers"]["dep"]["pos"]
        self.assertEqual(min(box["x"] for k, box in pos.items() if not k.startswith("phase:")), pos["queue"]["x"])

    def test_status_filter_keeps_only_done_tasks(self):
        graph = self.out["chain"]["status"]
        tasks = [n for n in graph["nodes"] if n["type"] == "task"]
        self.assertEqual(["P1.1"], [n["task"] for n in tasks])

    def test_agent_filter_keeps_only_matching_jobs(self):
        graph = self.out["chain"]["agent"]
        jobs = [n for n in graph["nodes"] if n["type"] == "job"]
        self.assertTrue(jobs)
        self.assertTrue(all(n["model"] == "haiku" for n in jobs))
        self.assertTrue(all(e["type"] != "handoff" or e["from"] in {n["id"] for n in jobs} for e in graph["edges"]))

    def test_phase_filter_keeps_only_that_phase(self):
        graph = self.out["with-blockers"]["phase"]
        self.assertEqual(["P1"], [lane["id"] for lane in graph["lanes"]])
        self.assertTrue(all(n["lane"] == "P1" for n in graph["nodes"]))



if __name__ == "__main__":
    unittest.main()
