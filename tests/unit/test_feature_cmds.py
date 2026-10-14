"""WP52: the `roadmap feature` CLI (roadmap/commands/feature.py) and the status features line.

Output lines, the --json envelope, exit codes and next: hints, the agent refusal for accept (CLAUDECODE set in this
process only), and the status budget (at most 8 lines and 700 characters).
"""

import datetime
import json
import os
import re
from unittest import mock

from roadmap.core import planfmt
from tests.unit.test_cmd_support import CmdCase

ROW = re.compile(r"^F\d+ (todo|doing|done|hold|uncovered) \d+/\d+ \d+K/\d+K blk\d+ .+$")


class FeatureCli(CmdCase):
    def setUp(self):
        super().setUp()
        patch = mock.patch.dict(os.environ, {})
        patch.start()
        self.addCleanup(patch.stop)
        os.environ.pop("CLAUDECODE", None)

    def add(self, title="Roadmap visual", *extra):
        code, out, err = self.cli(["feature", "add", title, "--acc", "reads at 375 px"] + list(extra))
        self.assertEqual(code, 0, err)
        return out.strip()


class Output(FeatureCli):
    def test_add_prints_the_new_id_and_lists_one_line_per_feature(self):
        self.assertEqual(self.add("Roadmap visual"), "F1 added: Roadmap visual")
        code, out, err = self.cli(["feature", "list"])
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(out.splitlines(), ["F1 uncovered 0/0 0K/0K blk0 Roadmap visual"])

    def test_list_is_empty_with_a_plain_message(self):
        code, out, _ = self.cli(["feature", "list"])
        self.assertEqual((code, out.strip()), (0, "no features yet"))

    def test_link_then_list_and_show(self):
        self.add("Roadmap visual")
        code, out, err = self.cli(["feature", "link", "F1", "P1.1", "P1.2"])
        self.assertEqual(code, 0, err)
        self.assertEqual(out.splitlines(), ["F1 linked to P1.1", "F1 linked to P1.2"])
        code, out, _ = self.cli(["feature", "list"])
        self.assertEqual(out.splitlines(), ["F1 todo 0/2 30K/0K blk0 Roadmap visual"])
        code, out, _ = self.cli(["feature", "show", "F1"])
        lines = out.splitlines()
        self.assertEqual(lines[0], "F1 todo 0/2 30K/0K blk0 Roadmap visual")
        self.assertEqual(lines[1], "acc: reads at 375 px")
        self.assertEqual(lines[2:], ["  P1.1 todo 20K | First task", "  P1.2 todo 10K | Second task"])

    def test_list_lines_are_within_the_budget(self):
        self.add("A feature with a title of reasonable length for the planner")
        self.cli(["feature", "link", "F1", "P1.1"])
        _, out, _ = self.cli(["feature", "list"])
        for line in out.splitlines():
            self.assertLessEqual(len(line), 120, line)
            self.assertRegex(line, ROW)

    def test_unlink_removes_the_link_and_says_so(self):
        self.add("Visual")
        self.cli(["feature", "link", "F1", "P1.1"])
        code, out, err = self.cli(["feature", "unlink", "F1", "P1.1"])
        self.assertEqual((code, out.strip()), (0, "F1 unlinked from P1.1"), err)
        code, out, _ = self.cli(["feature", "unlink", "F1", "P1.1"])
        self.assertEqual(out.strip(), "F1 was not linked to P1.1")

    def test_rm_removes_a_feature_with_no_tasks(self):
        self.add("Visual")
        code, out, _ = self.cli(["feature", "rm", "F1"])
        self.assertEqual((code, out.strip()), (0, "removed F1"))
        self.assertEqual(self.cli(["feature", "list"])[1].strip(), "no features yet")


class Json(FeatureCli):
    def test_json_envelope_for_list_and_add(self):
        code, out = self.envelope(["feature", "add", "Visual", "--acc", "ok"])
        self.assertEqual(code, 0)
        self.assertTrue(out["ok"])
        self.assertEqual(out["data"]["id"], "F1")
        self.assertIn("activity", out["data"])
        code, out = self.envelope(["feature", "list"])
        self.assertEqual(out["data"]["features"][0]["id"], "F1")
        self.assertEqual(out["data"]["features"][0]["state"], "uncovered")

    def test_json_error_has_code_and_next(self):
        code, out = self.envelope(["feature", "show", "F9"])
        self.assertEqual(code, 3)
        self.assertFalse(out["ok"])
        self.assertEqual((out["error"]["code"], out["error"]["next"]), ("not_found", "roadmap feature list"))


class Errors(FeatureCli):
    def test_a_bad_id_is_a_usage_error_with_a_next(self):
        code, _, err = self.cli(["feature", "show", "X1"])
        self.assertEqual(code, 2)
        self.assertIn("must look like F3", err)
        self.assertIn("next: roadmap feature list", err)

    def test_an_unknown_feature_is_not_found(self):
        code, _, err = self.cli(["feature", "link", "F7", "P1.1"])
        self.assertEqual(code, 3)
        self.assertIn("no feature F7", err)

    def test_parent_depth_is_reported_as_usage(self):
        self.add("Top")
        self.cli(["feature", "add", "Child", "--parent", "F1"])
        code, _, err = self.cli(["feature", "add", "Grandchild", "--parent", "F2"])
        self.assertEqual(code, 2)
        self.assertIn("one level only", err)


class Accept(FeatureCli):
    def test_an_agent_shell_cannot_accept_and_is_told_to_ask(self):
        self.add("Visual")
        with mock.patch.dict(os.environ, {"CLAUDECODE": "1"}):
            code, _, err = self.cli(["feature", "accept", "F1"])
        self.assertEqual(code, 4)
        self.assertIn("next: ask the person", err)
        self.assertNotIn("accepted", self.cli(["feature", "show", "F1"])[1].splitlines()[0])

    def test_a_person_accepts_a_done_feature_and_it_shows_in_show_not_list(self):
        self.add("Visual")
        self.cli(["feature", "link", "F1", "P1.1"])
        self.cli(["task", "done", "P1.1"])
        code, out, err = self.cli(["feature", "accept", "F1"])
        self.assertEqual((code, out.strip()), (0, "F1 accepted " + planfmt.today()), err)

    def test_accept_of_an_unfinished_feature_needs_yes(self):
        self.add("Visual")
        code, _, err = self.cli(["feature", "accept", "F1"])
        self.assertEqual(code, 4)
        self.assertIn("--yes", err)
        code, out, _ = self.cli(["feature", "accept", "F1", "--yes"])
        self.assertEqual(code, 0)
        code, out, _ = self.cli(["feature", "accept", "F1", "--off"])
        self.assertEqual(out.strip(), "F1 not accepted")


class StatusLine(FeatureCli):
    def test_a_project_without_features_keeps_its_status_unchanged(self):
        code, out, err = self.cli(["status"])
        self.assertEqual(code, 0, err)
        self.assertNotIn("features:", out)

    def test_status_gains_one_features_line_within_the_budget(self):
        self.add("Visual")
        self.add("Ops")
        self.cli(["feature", "link", "F1", "P1.1"])
        code, out, err = self.cli(["status"])
        self.assertEqual(code, 0, err)
        lines = out.splitlines()
        feature_lines = [line for line in lines if line.startswith("features:")]
        self.assertEqual(len(feature_lines), 1)
        self.assertRegex(feature_lines[0], r"^features: 2 \(\d+ done, \d+ doing, \d+ todo, 1 uncovered; \d+ orphan tasks\)$")
        self.assertLessEqual(len(lines), 8)
        self.assertLessEqual(len(out.rstrip("\n")), 700)

    def test_the_counts_follow_the_derive_rules(self):
        self.add("Visual")
        self.add("Ops")
        self.cli(["feature", "link", "F1", "P1.1"])
        _, out, _ = self.cli(["status"])
        self.assertIn("features: 2 (0 done, 0 doing, 1 todo, 1 uncovered; 3 orphan tasks)", out.splitlines())


if __name__ == "__main__":
    import unittest
    unittest.main()
