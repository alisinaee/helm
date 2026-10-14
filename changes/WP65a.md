# WP65a: hooks and control gap tests

Tests only. roadmap/ was not changed. Sources of the rows: docs/reviews/agy-g1-hooks.md (roadmap/services/hooks.py)
and docs/reviews/agy-g2-control.md (roadmap/services/control.py). The agy claims were checked one by one: each cited
line was read and tests/ was searched for the branch before a test was written.

## Rows accepted (test written)

hooks.py
- 85 AgentDetector.reap, no watch file and missing watch file, age over MAX_AGE_S (tests/unit/test_hooks_gaps.py)
- 85 AgentDetector.reap, output quiet past IDLE_S, recent output kept
- 103 _FileDetector.reap, error first line is failed, clean file is done, timeout without a file is failed
- 174 _first_line_has_error, missing file gives False; only the first line is read
- 190 task_regex, uncompilable pattern is invalid_data (the agy example "[" compiles, so "a(" is used)
- 205 project_settings, config from a newer build is newer_schema
- 212 project_settings, hookDetectors that is not a list is invalid_data
- 214 project_settings, non-string detector names are dropped
- 228 run_hook, an unexpected handler error is logged by type and returns None
- 251 _handle, data folder missing is logged and skipped
- 260 _handle, unknown detector name is logged and the known ones still run
- 446 _task_of_agent, mapped agent, unmapped agent, empty agent id, no state file
- 514 _stop_pickup, empty queue clears a recorded pickup count
- 696 _close and _close_some, a busy lock keeps the entry and stops the loop at once
- 712 _read_state, active that is not a list is invalid_data and the file is left alone

control.py
- 45 _checked, a bad project id is invalid_input (usage exit) in control_path and sentinel_path
- 64 parse_time and clock_text, malformed or non-string times
- 75 _number, bool, string, NaN and None give None
- 84 _pct, zero or negative limit (100 when spent, else 0)
- 109 read_state, a control file that is not an object is invalid_data and left alone
- 155, 159 _sentinel_text, and the sentinel file after a project stop and a task stop
- 177 _load_budget, unreadable budget is a warning and the recompute still saves
- 212 phase cap reached, the taskBlocks text (not asserted before)
- 225 task cap reached, the taskBlocks text (not asserted before)
- 233 model over its cap, warning only
- 307, 316, 328 pickup_record, record_pickup and clear_pickup (directly, no test before)
- 89 _task_id, the usage error, added as a direct check next to the existing stop test

## Rows discarded

- hooks 116 AgyDetector.on_tool with result file: covered by test_hooks.py (agy registers and closes)
- hooks 236, 239 invalid JSON and non-object stdin: covered by test_hooks.py ResilienceTests
- hooks 296, 302 SubagentStop close and reap during an event: covered by test_hooks.py
- hooks 358 PreToolUse with a tool outside PRE_TOOLS: covered by test_hook_enforce.py (Read, Grep, Glob)
- hooks 431 stopped-task deny: covered by test_hook_enforce.py (task P0.2 stopped by user)
- hooks 471 denial logged at most once a minute: covered by test_hook_enforce.py
- hooks 488 SessionStart stop line: covered by test_hook_enforce.py
- hooks 492 SessionStart with nothing pending: covered by test_hook_enforce.py (nothing pending is silent)
- hooks 506 pickupOnStop false: covered by test_hook_enforce.py
- hooks 510 Stop while stopped or blocked: covered by test_hook_enforce.py (no pickup while stopped)
- control 187 tasks.json unreadable: covered by test_control.py (a broken tasks file is a warning)
- control 348 after_write: covered by test_control.py (never raises)
- control 363 stop, 384 resume, 470 set_budget_limit: covered by test_control.py
- commands/control.py rows (registration, _emit, _stop, _resume, _override): out of the scope of this WP
  (services/control.py only) and covered by tests/unit/test_control_cli.py

## Real bugs

None found. No test is marked expectedFailure.

## Tests

- tests/unit/test_hooks_gaps.py: 23 tests, all pass
- tests/unit/test_control_gaps.py: 13 tests, all pass
- Full discover run: only web failures remain (tests/web/test_assets.py CSP scan, tests/web/test_workflow_view.py
  setUpClass). Both are outside this WP. In one run a non-web test (tests/api/test_logging.py AccessLog) failed once
  and passed when run alone and on the next full run.
