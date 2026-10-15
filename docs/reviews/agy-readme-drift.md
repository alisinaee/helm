# Job staffer-mv9h7ux8-b0faae75 (staffer, done)

### Missing Top-Level Commands in [README.md](file:///Users/ali/Works/roadmap-board/README.md) (present in `bin/roadmap --help` / [roadmap/cli.py](file:///Users/ali/Works/roadmap-board/roadmap/cli.py)):
- `backlog`: `roadmap backlog add "<title>" [--phase P]`
- `head`: `roadmap head <action>` (ask ledger: `log`, `t`, `list`, `show`, `set`, `bind`, `split`, `brief`, `review`, etc.)
- `ref`: `roadmap ref <ref>` (resolves board references like `rb:<project>/<kind>/<id>`)
- `logs`: `roadmap logs [summary|marks|status]` (standalone debug event log; README only lists `service logs`)

### Missing Subcommands:
- `project`: `new` (`roadmap project new <path> [--name N] [--research]`)
- `job`: `progress` (`roadmap job progress <id> --tokens <K>`)
- `task`: `backlog`, `promote` (`roadmap task backlog|promote <id>`)
- `feature`: `tree`, `set`, `move` (README line 232 only lists `add|list|show|link|unlink|accept|rm`)
- `limit`: `rm`, `show` omitted in main command table at [README.md#L221-L222](file:///Users/ali/Works/roadmap-board/README.md#L221-L222) (only `set` and `budget` shown)

### Wrong Commands in [README.md](file:///Users/ali/Works/roadmap-board/README.md):
- None: all command names and invocations documented in [README.md](file:///Users/ali/Works/roadmap-board/README.md) map to valid commands in [roadmap/cli.py](file:///Users/ali/Works/roadmap-board/roadmap/cli.py).

[unrestricted] agy modified the working tree during this staffer run — verify the task asked for it. Delta (`git status --porcelain` entries that appeared or changed during the run):
  M docs/activity.jsonl
   M docs/head-text.jsonl
   M docs/head.jsonl
   M docs/jobs.json
   M roadmap/core/head.py
   M roadmap/core/snapshot.py
   M roadmap/services/headops.py
   M tests/unit/test_head_core.py
   M tests/unit/test_head_snapshot.py
   M web/css/admin.css
   M web/css/components.css
   M web/css/flow.css
   M web/css/map.css
   M web/css/work.css
   M web/js/views/agents.js
   M web/js/views/head.js
   M web/js/views/limits.js
   M web/js/views/tokens.js
   M web/js/views/workflow.js
  ?? docs/reviews/agy-api-drift.md
  ?? tests/unit/test_r753_head_fixes.py
  ?? tests/web/test_r754_rows.py
ACTION FOR THE CALLING AGENT: inspect these changes (`git diff`) before trusting this staffer. Rollback: `git checkout -- <path>` for tracked files, delete the new untracked ones.
