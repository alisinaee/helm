# WP4: jobs and hooks

- `roadmap/services/jobs.py`: the job registry in each project's `jobs.json` (ported from split-net `jobs.py`): start, finish (done or failed, `tokensK`, note), list, prune (keeps running jobs and the newest 30 finished). Writes take the directory lock, re-read inside it and save atomically at `schemaVersion` 1. A corrupt or newer file stops with exit 5 and is never overwritten. Also `resolve_project` (`--project`, then `$ROADMAP_PROJECT`, then the registered project containing the cwd).
- `roadmap/services/hooks.py`: the hook driver (ported from `jobs_auto.py`). Detector registry `agent`, `agy`, `cursor`, chosen per project by `hookDetectors` in `roadmap.config.json`. Task ids come from `taskIdPattern` and must exist in `tasks.json`. Per-project state in `hooks-<project>.json` (atomic, locked). Log lines in `logs/hooks.log`. `run_hook` never raises.
- `roadmap/commands/job.py`: `job start|done|fail|list|prune`, each with `--project` and `--json`. Exit codes: 2 usage, 3 not found, 4 conflict, 5 invalid data.
- `roadmap/commands/hook.py`: reads the hook JSON on stdin, exits 0, prints nothing.
- Differences from `jobs_auto.py`: state is per project, not a file in the tool folder. An agent with no output file is closed after 2 h (it used to stay open). A file-based job with no result file is closed as failed after 2 h.
- Tests: `tests/unit/test_jobs*.py`, `tests/unit/test_hooks*.py`.
