# agy output verification (WP12)

Verification of three pieces of agy (Gemini Flash) output. Every claim was checked against the code, the fixtures
or the test run. Nothing was pushed. The service code (roadmap/services/*.py) was not changed.

## 1. Demo fixtures (fixtures/demo/{alpha,beta,gamma})

- All 12 files are valid JSON. Top-level shapes match tests/fixtures/splitnet (tasks, jobs) and roadmap/templates
  (issues, questions). Every task model, check and thinking value is inside the parser allowlists.
- Registered as copies in a temp ROADMAP_HOME (`project add`), `project check` reports tasks.json and jobs.json ok.
  The loader snapshot has no errors for any of the three.
- Counts found: alpha 40 tasks, 5 phases, 3 running jobs, 4 open issues (1 blocker), 2 open questions;
  beta 15 tasks, 3 phases; gamma 1 phase, 3 todo. All as asked.
- Accepted as written, nothing fixed. New test: tests/unit/test_demo_fixtures.py (5 tests, passing).
- Not run: the HTTP API on port 8801. The same snapshot was read through roadmap.services.loader.load_snapshot.

## 2. CHANGELOG.md and docs/ARCHITECTURE.md

CHANGELOG (11 agy bullets checked against changes/WP*.md):
- Accepted as written (8): WP16, WP17, WP20, WP21, WP23, the WP22 uninstall change (5 entries, not 3), R1 (WP14),
  R2 (WP22-fixes).
- Corrected (3):
  - WP28 "tokens" changed to "design tokens". The WP28 tokens are CSS design tokens, not a token feature.
  - WP22 "PreToolUse and SessionStart hook gating" changed to "PreToolUse hook gating, and SessionStart inbox lines".
    SessionStart does not gate anything; it prints inbox lines.
  - WP27 "multi-window limit row evaluations" changed to the real windows (day, week, total) and states.

ARCHITECTURE table (11 rows checked against the constants and writers):
- Accepted as written (5): issues.json, questions.json, comments.json, budget.json, ledger.json. All constants match.
- Corrected (6):
  - config.json location was "global state dir". It is the global config dir (paths.config_file()).
  - issues-archive, questions-archive and comments-archive had "see code". Replaced with the real rule
    (CLOSED_KEEP, ANSWERED_KEEP, PER_TARGET and FILE_MAX_BYTES).
  - activity.jsonl: ACTIVITY_SUM_MAX lives in roadmap/core/parsers.py, not in the activity service. Location noted.
  - queue.json: the file also holds stop requests (op "stop", commands.py:152), not only start requests.
  - Table header said "copy the real constants from the code": replaced with "module constants".
- Added (2): undo.jsonl (UNDO_KEEP = 500, roadmap/services/commands.py) and control-<project>.json and
  block-<project> (roadmap/services/control.py). Both were written in WP21/WP22 and were missing from the table.

## 3. Test gaps (agy list a8-test-gaps.md, 25 rows)

Each row was grepped against tests/unit and rechecked against the code.
- Already covered, no new test (3):
  - ledger.py:187 reset adds w: test_a_reset_of_43_then_1_adds_one (existing).
  - ledger.py:256 rate under 200k: test_an_estimate_needs_two_hundred_thousand_tracked_tokens (existing).
  - ledger.py:183 first reading adds 0: implicit in existing tests. An explicit return assertion was added anyway.
- New tests in tests/unit/test_limits_gaps.py (22 rows): all others. The row text was accurate for all of them.
  Two rows were phrased slightly loosely (ledger 183 says "added", the code returns the day's points), but the
  expected values are right.
- Rejected as wrong: none of the 25 rows had a wrong expectation. Two rows were not really "untested" at the
  branch level (add, ledger 183); they are listed above as covered or as explicit assertions.

## Real bugs found (expectedFailure in tests/unit/test_limits_gaps.py)

1. roadmap/services/limits.py:541-545 (remove_row, project rows): a stored row with a matching id but a malformed
   body is popped and saved, then the call raises not_found. The file changes even though the call failed.
   Test: test_rm_that_raises_not_found_leaves_the_budget_file_unchanged.
2. roadmap/services/limits.py:532 (remove_row, BUD): the prior row is built with action "block" even when the budget
   stores limitAction "warn". The undo of `limit rm BUD` would restore a blocking budget.
   Test: test_removing_a_warning_budget_returns_it_with_its_warn_action.

Both tests fail for exactly the stated reason (checked by running the bodies without the decorator).

## Test run

`python3 -m unittest discover -s tests -t . -q` on the working tree: 1122 tests. My files pass. Two web tests
(tests/web/test_shell.py: CSS budget and the "module: null" registry check) fail because other workers are editing
web/css and web/js/routes.js. They are not in my files.
