# Job staffer-mv7pg8rk-b660ccea (staffer, done)

|function or branch file:line|missing case|what a test should assert|
|---|---|---|
|/Users/ali/Works/roadmap-board/roadmap/services/hooks.py:85|Reaping an agent job when watch file is missing or quiet time exceeds IDLE_S|Returns 'done' when quiet > IDLE_S or age > MAX_AGE_S, else None|
|/Users/ali/Works/roadmap-board/roadmap/services/hooks.py:103|Reaping a file detector job when result file exists or timeout is reached|Returns 'failed' if file has error or timed out, 'done' if file exists without error|
|/Users/ali/Works/roadmap-board/roadmap/services/hooks.py:116|PostToolUse Bash command invoking agy-companion with result file in response|Returns dictionary with title, model 'agy', kind 'file', and watch pointing to result file|
|/Users/ali/Works/roadmap-board/roadmap/services/hooks.py:174|Reading first line of result file to check for error string|Returns True when first line contains 'error', False otherwise or on OSError|
|/Users/ali/Works/roadmap-board/roadmap/services/hooks.py:190|Compiling an invalid taskIdPattern regex from project configuration|Raises RoadmapError with code 'invalid_data' and exit code EXIT_INVALID_DATA|
|/Users/ali/Works/roadmap-board/roadmap/services/hooks.py:205|Reading roadmap.config.json with a schema error|Raises RoadmapError with code 'newer_schema' and exit code EXIT_INVALID_DATA|
|/Users/ali/Works/roadmap-board/roadmap/services/hooks.py:212|Reading roadmap.config.json where hookDetectors is not a list|Raises RoadmapError with code 'invalid_data' and exit code EXIT_INVALID_DATA|
|/Users/ali/Works/roadmap-board/roadmap/services/hooks.py:228|Unexpected exception raised during hook execution in _handle|Catches exception, logs error to hooks.log, and returns None|
|/Users/ali/Works/roadmap-board/roadmap/services/hooks.py:236|Hook payload passed to stdin is invalid JSON|Logs skip message and returns None|
|/Users/ali/Works/roadmap-board/roadmap/services/hooks.py:239|Hook payload passed to stdin is valid JSON but not an object|Logs skip message and returns None|
|/Users/ali/Works/roadmap-board/roadmap/services/hooks.py:251|Project resolved but data_dir does not exist on disk|Logs missing data folder skip message and returns None|
|/Users/ali/Works/roadmap-board/roadmap/services/hooks.py:260|Project config contains a detector name not registered in DETECTORS|Logs skip message for unknown detector name and proceeds with valid detectors|
|/Users/ali/Works/roadmap-board/roadmap/services/hooks.py:296|SubagentStop hook event with an agent_id matching an active subagent job|Closes matching job with status 'done' and removes it from active state|
|/Users/ali/Works/roadmap-board/roadmap/services/hooks.py:302|Reaping finished or failed background jobs during an event run|Closes reaped jobs and removes them from active state|
|/Users/ali/Works/roadmap-board/roadmap/services/hooks.py:358|PreToolUse hook event with a tool not present in PRE_TOOLS|Returns None immediately without performing control or sentinel checks|
|/Users/ali/Works/roadmap-board/roadmap/services/hooks.py:431|PreToolUse check when an agent's task is present in state stopTasks|Returns deny decision with reason citing the task and its block text|
|/Users/ali/Works/roadmap-board/roadmap/services/hooks.py:446|Resolving task for an agent_id from active jobs in hooks state|Returns task ID matching agent_id or None if unmapped|
|/Users/ali/Works/roadmap-board/roadmap/services/hooks.py:471|Denial logging when another denial for the project was logged within 60s|Suppresses duplicate log write to hooks.log|
|/Users/ali/Works/roadmap-board/roadmap/services/hooks.py:488|SessionStart hook event when the project is stopped by user|additionalContext begins with 'roadmap: stopped by user at ...'|
|/Users/ali/Works/roadmap-board/roadmap/services/hooks.py:492|SessionStart hook event when there is no stop and inbox is empty|Returns None|
|/Users/ali/Works/roadmap-board/roadmap/services/hooks.py:506|Stop hook event when pickupOnStop is set to false in config|Returns None without surfacing queued task|
|/Users/ali/Works/roadmap-board/roadmap/services/hooks.py:510|Stop hook event when project is stopped or limit-blocked|Returns None without surfacing queued task|
|/Users/ali/Works/roadmap-board/roadmap/services/hooks.py:514|Stop hook event when queue is empty but a previous pickup record exists|Calls clear_pickup and returns None|
|/Users/ali/Works/roadmap-board/roadmap/services/hooks.py:696|Closing a job when acquiring project lock fails with code 'locked'|Returns False so the entry remains in active state for retry|
|/Users/ali/Works/roadmap-board/roadmap/services/hooks.py:712|Reading hook state file where 'active' is not a list|Raises RoadmapError with code 'invalid_data'|

DONE

[unrestricted] agy modified the working tree during this staffer run — verify the task asked for it. Delta (`git status --porcelain` entries that appeared or changed during the run):
   M roadmap/core/planfmt.py
   M roadmap/services/tasks.py
  ?? changes/WP58b.md
  ?? docs/facts/
  ?? tests/unit/test_gen_facts.py
  ?? tests/unit/test_plan_export_features.py
  ?? tests/unit/test_planfmt_models.py
  ?? tools/gen_facts.py
ACTION FOR THE CALLING AGENT: inspect these changes (`git diff`) before trusting this staffer. Rollback: `git checkout -- <path>` for tracked files, delete the new untracked ones.
