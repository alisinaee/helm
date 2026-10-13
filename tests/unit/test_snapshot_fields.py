"""WP33b: the snapshot's meters.limits[].action and the snapshot's rules list.

Every test runs under a temp ROADMAP_HOME with a temp project (ControlCase), never the real config or home.
"""

import datetime
import os

from roadmap.core.snapshot import build_snapshot
from roadmap.services import limits, loader, rules
from roadmap.store import config
from tests.unit.test_control_support import ControlCase, write_json

OLD_LIMIT_KEYS = {"id", "scope", "window", "kind", "used", "limit", "state", "est", "paceAt", "src"}


def at(hour=14, minute=2, day=13):
    return datetime.datetime(2026, 10, day, hour, minute).astimezone()


class LimitActionTests(ControlCase):
    def setUp(self):
        super().setUp()
        self.now = at()
        self.project = config.get_project("demo")

    def limit_rows(self):
        snap = loader.load_snapshot("demo", now=self.now)
        return snap["meters"]["limits"]

    def test_every_row_kind_carries_its_action(self):
        limits.add(self.project, "global", "day", "pct", 2, action="warn")          # config row, warn
        limits.add(self.project, "project", "week", "tok", 100, action="block")     # stored project row, block
        limits.add(self.project, "project", "week", "tok", 50, action="warn")       # same key replaces: warn
        limits.add(self.project, "project", "total", "tok", 200, action="warn")     # BUD, read from budget.json
        write_json(os.path.join(self.docs, "autonomy.json"), {"schemaVersion": 2, "limit": {
            "kind": "weekly", "stopAtPercent": 90, "action": "warn"}})               # AUTO, warn
        rows = {r["id"]: r for r in self.limit_rows()}
        self.assertEqual(rows["L1"]["action"], "warn")
        self.assertEqual(rows["L2"]["action"], "warn")
        self.assertEqual(rows["BUD"]["action"], "warn")
        self.assertEqual(rows["AUTO"]["action"], "warn")
        for row in rows.values():
            self.assertIn(row["action"], ("block", "warn"))

    def test_autonomy_and_budget_rows_default_to_block(self):
        limits.add(self.project, "project", "total", "tok", 200)                    # default action block
        rows = {r["id"]: r for r in self.limit_rows()}
        self.assertEqual(rows["BUD"]["action"], "block")
        self.assertEqual(rows["AUTO"]["action"], "block")   # ControlCase writes stopAtPercent 100, no action key

    def test_old_fields_are_unchanged_and_action_is_added(self):
        limits.add(self.project, "global", "day", "pct", 2, action="block")
        limits.add(self.project, "project", "total", "tok", 200, action="warn")
        for row in self.limit_rows():
            self.assertEqual(set(row), OLD_LIMIT_KEYS | {"action"}, row["id"])
        by_id = {r["id"]: r for r in self.limit_rows()}
        self.assertEqual(by_id["L1"]["limit"], 2)
        self.assertEqual(by_id["L1"]["window"], "day")
        self.assertEqual(by_id["L1"]["kind"], "pct")
        self.assertEqual(by_id["L1"]["scope"], "global")
        self.assertEqual(by_id["BUD"]["src"], "budget")
        self.assertEqual(by_id["AUTO"]["src"], "autonomy")
        self.assertEqual(by_id["BUD"]["limit"], 200)


class RulesFieldTests(ControlCase):
    def setUp(self):
        super().setUp()
        self.now = at()
        self.path = os.path.join(self.docs, "rules.txt")

    def write_rules(self, text):
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write(text)

    def snapshot_rules(self):
        return loader.load_snapshot("demo", now=self.now)["rules"]

    def test_a_missing_file_gives_an_empty_list_and_no_error(self):
        snap = loader.load_snapshot("demo", now=self.now)
        self.assertEqual(snap["rules"], [])
        self.assertNotIn("rules.txt", [e["file"] for e in snap["errors"]])

    def test_rules_are_parsed_into_id_scope_kind_value_text(self):
        self.write_rules("# header\nR1 all do | run the tests first\nR2 haiku dont | never push\n"
                         "R3 all budget 500 | keep the spend low\n")
        self.assertEqual(self.snapshot_rules(), [
            {"id": "R1", "scope": "all", "kind": "do", "value": None, "text": "run the tests first"},
            {"id": "R2", "scope": "haiku", "kind": "dont", "value": None, "text": "never push"},
            {"id": "R3", "scope": "all", "kind": "budget", "value": 500, "text": "keep the spend low"},
        ])

    def test_an_undecodable_file_gives_an_empty_list_and_never_raises(self):
        with open(self.path, "wb") as fh:
            fh.write(b"\xff\xfe\x00 not utf-8 \x81")
        self.assertEqual(self.snapshot_rules(), [])

    def test_a_directory_in_place_of_the_file_gives_an_empty_list(self):
        os.mkdir(self.path)
        self.assertEqual(self.snapshot_rules(), [])

    def test_invalid_lines_are_skipped_and_the_valid_rules_kept(self):
        self.write_rules("R1 all do | good one\nthis is not a rule\nR2 nowhere do | bad scope\nR3 all do | fine\n")
        self.assertEqual([r["id"] for r in self.snapshot_rules()], ["R1", "R3"])

    def test_a_missing_docs_folder_gives_an_empty_list(self):
        self.assertEqual(rules.MAX_RULES, 60)
        self.assertEqual(loader._rules_view(os.path.join(self.tmp, "no-such-folder")), [])

    def test_at_most_sixty_rules_are_returned(self):
        self.write_rules("".join("R%d all do | rule %d\n" % (i, i) for i in range(1, 71)))
        got = self.snapshot_rules()
        self.assertEqual(len(got), 60)
        self.assertEqual(got[0]["id"], "R1")
        self.assertEqual(got[-1]["id"], "R60")

    def test_text_of_exactly_160_characters_is_kept_and_longer_text_is_dropped(self):
        ok = "a" * 160
        self.write_rules("R1 all do | %s\nR2 all do | %s\n" % (ok, "b" * 161))
        got = self.snapshot_rules()
        self.assertEqual([r["id"] for r in got], ["R1"])
        self.assertEqual(len(got[0]["text"]), 160)


class SnapshotRulesKeyTests(ControlCase):
    def test_a_snapshot_without_rules_has_no_rules_key(self):
        plain = build_snapshot({}, {}, at())
        self.assertNotIn("rules", plain)
        with_rules = build_snapshot({}, {}, at(), rules=[])
        self.assertEqual(with_rules["rules"], [])
        self.assertEqual(set(with_rules) - {"rules"}, set(plain))

    def test_the_golden_fixture_is_unchanged_without_rules(self):
        from tests.unit.test_core_golden import PINNED_NOW, load_fixture
        files, config_doc = load_fixture()
        self.assertNotIn("rules", build_snapshot(files, config_doc, PINNED_NOW))
