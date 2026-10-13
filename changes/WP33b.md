# WP33b: snapshot action and rules fields

- `roadmap/services/limits.py` `meters()`: each `meters.limits[]` item gets `"action"` (the row's own action, block or warn). The other fields are unchanged.
- `roadmap/core/snapshot.py` `build_snapshot()`: new optional `rules` argument; the `rules` key is added only when given, so snapshots built without it (including the golden fixture) are unchanged.
- `roadmap/services/loader.py` `load_snapshot()`: passes `rules` from `_rules_view()`, which reads `docs/rules.txt` with `roadmap/services/rules.py`. Missing or unreadable file gives `[]`; invalid lines are skipped; at most 60 rules. `rulesSynced` is omitted because `rules.py` has no public cheap check.
- `docs/API.md`: the snapshot field notes for `action` and `rules`.
- Tests: `tests/unit/test_snapshot_fields.py` (13 tests: action per row kind, old fields unchanged, rules parsing incl. missing, undecodable, directory, invalid lines, caps, 160-char limit, no-`rules` compatibility). The golden test is unchanged and passes.
