"""Parser and extras error paths: bad input gives an errors entry and never raises."""

import json
import unittest
from datetime import datetime, timezone

from roadmap.core.extras import parse_extras
from roadmap.core.parsers import parse_autonomy, parse_jobs, parse_tasks
from roadmap.core.snapshot import build_snapshot

NOW = datetime(2026, 10, 13, 12, 0, 0, tzinfo=timezone.utc)
GOOD_TASKS = json.dumps({
    "updated": "2026-10-13",
    "phases": [{"id": "P1", "name": "Engine", "status": "partial"}],
    "tasks": [
        {"id": "P1.1", "phase": "P1", "title": "a", "status": "done", "tokensK": 40, "model": "haiku"},
        {"id": "P1.2", "phase": "P1", "title": "b", "status": "hold", "note": "Deferred by rule"},
    ],
})


class TasksParserTests(unittest.TestCase):
    def test_good_tasks(self):
        data, errors = parse_tasks(GOOD_TASKS)
        self.assertEqual(errors, [])
        self.assertEqual(data["updated"], "2026-10-13")
        self.assertEqual([t["state"] for t in data["tasks"]], ["done", "deferred"])

    def test_phase_approved_only_false_blocks(self):
        raw = json.dumps({"phases": [{"id": "A"}, {"id": "B", "approved": False}, {"id": "C", "approved": True}],
                          "tasks": []})
        data, _ = parse_tasks(raw)
        self.assertEqual([p["approved"] for p in data["phases"]], [True, False, True])

    def test_bad_json_gives_error(self):
        data, errors = parse_tasks("{not json")
        self.assertEqual(data, {"updated": "", "phases": [], "tasks": []})
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["file"], "tasks.json")
        self.assertIn("JSONDecodeError", errors[0]["error"])

    def test_wrong_shape_gives_error(self):
        _, errors = parse_tasks('{"phases": {}, "tasks": []}', name="x.json")
        self.assertEqual(errors[0]["file"], "x.json")
        self.assertIn("ValueError", errors[0]["error"])

    def test_missing_phase_id_gives_error(self):
        _, errors = parse_tasks('{"phases": [{"name": "no id"}], "tasks": []}')
        self.assertEqual(len(errors), 1)


class JobsParserTests(unittest.TestCase):
    def test_bad_json_gives_error_and_no_jobs(self):
        jobs, errors = parse_jobs("[", NOW)
        self.assertEqual(jobs, [])
        self.assertEqual(errors[0]["file"], "jobs.json")

    def test_no_jobs_array_gives_error(self):
        jobs, errors = parse_jobs('{"jobs": 3}', NOW)
        self.assertEqual((jobs, len(errors)), ([], 1))

    def test_invalid_items_are_skipped_silently(self):
        text = json.dumps({"jobs": [5, {"id": "j", "status": "weird"}, {"id": "ok", "status": "running"}]})
        jobs, errors = parse_jobs(text, NOW)
        self.assertEqual(errors, [])
        self.assertEqual([j["id"] for j in jobs], ["ok"])


class AutonomyParserTests(unittest.TestCase):
    def test_bad_json_gives_none_and_error(self):
        data, errors = parse_autonomy("{")
        self.assertIsNone(data)
        self.assertEqual(errors[0]["file"], "autonomy.json")

    def test_non_object_gives_error(self):
        data, errors = parse_autonomy("[1, 2]")
        self.assertIsNone(data)
        self.assertEqual(len(errors), 1)


class ExtrasErrorTests(unittest.TestCase):
    def test_unknown_extra_is_reported(self):
        outputs, errors = parse_extras({"mystery": "x.md"}, {})
        self.assertEqual(outputs["spikes"], [])
        self.assertIn("unknown extra 'mystery'", errors[0]["error"])

    def test_configured_file_missing(self):
        _, errors = parse_extras({"spikes": "10.md"}, {"10.md": None})
        self.assertEqual(errors[0]["file"], "10.md")

    def test_entry_without_file(self):
        _, errors = parse_extras({"testing": {"section": "7.9"}}, {})
        self.assertEqual(len(errors), 1)

    def test_spikes_without_table_is_error_not_exception(self):
        outputs, errors = parse_extras({"spikes": "10.md"}, {"10.md": "no table here\n"})
        self.assertEqual(outputs["spikes"], [])
        self.assertIn("no spike rows", errors[0]["error"])

    def test_bad_extra_does_not_stop_others(self):
        roadmap = "## Next up\n1. Do it\n"
        outputs, errors = parse_extras(
            {"spikes": "10.md", "roadmap": {"file": "05.md", "next": "Next up"}},
            {"10.md": "junk", "05.md": roadmap},
        )
        self.assertEqual(outputs["next"], ["Do it"])
        self.assertEqual(len(errors), 1)


class SnapshotNeverRaisesTests(unittest.TestCase):
    def test_all_bad_inputs_give_errors(self):
        files = {"tasks.json": "{", "jobs.json": "{", "autonomy.json": "[", "05.md": None}
        config = {"extras": {"roadmap": {"file": "05.md", "next": "Next up"}}}
        new = build_snapshot(files, config, NOW)
        self.assertEqual(sorted(e["file"] for e in new["errors"]),
                         ["05.md", "autonomy.json", "jobs.json", "tasks.json"])
        self.assertIsNone(new["summary"]["autonomy"])
        self.assertEqual(new["summary"]["tasks_left"], 0)


if __name__ == "__main__":
    unittest.main()
