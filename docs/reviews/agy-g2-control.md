# Job staffer-mv7pgaa8-7ee487f0 (staffer, done)

|function or branch file:line|missing case|what a test should assert|
|---|---|---|
|~/Works/roadmap-board/roadmap/commands/control.py:9|registering CLI subcommands 'stop', 'resume', 'override'|parser registers 'stop', 'resume', and 'override' subcommands with expected arguments and handler functions|
|~/Works/roadmap-board/roadmap/commands/control.py:26|formatting output in _emit when args.json is True or False|returns dict with project summary and state when json=True, prints summary and returns None when json=False|
|~/Works/roadmap-board/roadmap/commands/control.py:36|executing CLI 'stop' command with or without --task|calls control.stop with resolved project and task argument and emits formatted output|
|~/Works/roadmap-board/roadmap/commands/control.py:42|executing CLI 'resume' command|calls control.resume with resolved project and emits formatted output|
|~/Works/roadmap-board/roadmap/commands/control.py:48|executing CLI 'override' command with --hours|calls control.override with resolved project and hours value and emits formatted output|
|~/Works/roadmap-board/roadmap/services/control.py:45|project_id validation fails in _checked|raises RoadmapError with code 'invalid_input' and EXIT_USAGE|
|~/Works/roadmap-board/roadmap/services/control.py:64|malformed non-ISO timestamp string passed to parse_time|returns None when datetime.fromisoformat raises ValueError|
|~/Works/roadmap-board/roadmap/services/control.py:75|boolean, non-numeric, or NaN value passed to _number|returns None instead of float|
|~/Works/roadmap-board/roadmap/services/control.py:84|limit is zero or negative in _pct calculation|returns 100.0 if spent > 0 else 0.0|
|~/Works/roadmap-board/roadmap/services/control.py:89|invalid task ID format passed to _task_id|raises RoadmapError with code 'usage' and EXIT_USAGE|
|~/Works/roadmap-board/roadmap/services/control.py:109|control state JSON file content is not a dict in read_state|raises RoadmapError with code 'invalid_data' and EXIT_INVALID_DATA|
|~/Works/roadmap-board/roadmap/services/control.py:155|sentinel text generation when state has stop=True|returns 'stopped by user'|
|~/Works/roadmap-board/roadmap/services/control.py:159|sentinel text generation when only specific tasks are stopped|returns 'stopped tasks: ' followed by comma-separated task IDs|
|~/Works/roadmap-board/roadmap/services/control.py:177|budget.get raises RoadmapError in _load_budget|appends 'budget unreadable: ...' to warns and returns None|
|~/Works/roadmap-board/roadmap/services/control.py:187|tasks.load raises RoadmapError in _load_tasks|appends unreadable warning to warns and returns empty list|
|~/Works/roadmap-board/roadmap/services/control.py:212|phase spending reaches or exceeds 100% of phase cap|marks all tasks in the phase blocked with 'phase <id> cap reached' in taskBlocks|
|~/Works/roadmap-board/roadmap/services/control.py:225|individual task spend reaches or exceeds capK|marks task blocked with 'task <id> cap reached' in taskBlocks|
|~/Works/roadmap-board/roadmap/services/control.py:233|spend for a model exceeds its limit in budget limits|appends 'model <model> over its cap (warning only)' to warns|
|~/Works/roadmap-board/roadmap/services/control.py:307|retrieving existing pickup record via pickup_record|returns dict with 'key' and 'blocks' count or empty dict|
|~/Works/roadmap-board/roadmap/services/control.py:316|recording pickup blocks via record_pickup|increments blocks for matching key or sets count to 1 for a new key in state['pickup']|
|~/Works/roadmap-board/roadmap/services/control.py:328|clearing pickup record via clear_pickup|clears state['pickup'] to an empty dict|
|~/Works/roadmap-board/roadmap/services/control.py:348|running after_write recompute fan-out|returns updated state for project_id or None on failure without raising exceptions|
|~/Works/roadmap-board/roadmap/services/control.py:363|stopping project or specific task via stop|sets stop flag or adds task to manualTasks, writes activity log entry, and updates state|
|~/Works/roadmap-board/roadmap/services/control.py:384|resuming project via resume|clears stop flag and manual tasks, writes activity log entry, and removes block sentinel|
|~/Works/roadmap-board/roadmap/services/control.py:470|setting or clearing budget limit via set_budget_limit|updates budget.json, refuses limit increases from agent source, logs activity, and returns state|

DONE

[unrestricted] agy modified the working tree during this staffer run — verify the task asked for it. Delta (`git status --porcelain` entries that appeared or changed during the run):
   M roadmap/core/planfmt.py
   M roadmap/services/tasks.py
   M tools/ui_smoke.py
   M web/js/routes.js
  ?? tests/unit/test_plan_export_features.py
  ?? tests/unit/test_planfmt_models.py
ACTION FOR THE CALLING AGENT: inspect these changes (`git diff`) before trusting this staffer. Rollback: `git checkout -- <path>` for tracked files, delete the new untracked ones.
