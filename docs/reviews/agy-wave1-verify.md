# Job staffer-mv9hkmgf-7af65dcd (staffer, done)

### R6.18
- `project new --research` flag: **BUILT** ([`roadmap/commands/project.py:55`](file:///Users/ali/Works/roadmap-board/roadmap/commands/project.py#L55) + `test_research_flag_creates_note_01_plan_and_registration` in [`tests/unit/test_project_new.py:23`](file:///Users/ali/Works/roadmap-board/tests/unit/test_project_new.py#L23))
- Live job progress tokens: **BUILT** ([`roadmap/commands/job.py:46`](file:///Users/ali/Works/roadmap-board/roadmap/commands/job.py#L46), [`roadmap/services/jobs.py:132`](file:///Users/ali/Works/roadmap-board/roadmap/services/jobs.py#L132) + `test_progress_updates_snapshot_fields_of_a_running_job` in [`tests/unit/test_job_progress.py:28`](file:///Users/ali/Works/roadmap-board/tests/unit/test_job_progress.py#L28))
- Stale-usage pill: **MISSING** (planned under WP62.3 for `agents.js` / `topbar.js`, but never implemented; no UI code or tests exist)

### R6.19
- Cmd-K palette: **BUILT** ([`web/js/views/palette.js:1`](file:///Users/ali/Works/roadmap-board/web/js/views/palette.js#L1), [`web/js/keys.js:108`](file:///Users/ali/Works/roadmap-board/web/js/keys.js#L108) + `test_cmd_or_ctrl_k_opens_and_nothing_else` in [`tests/web/test_palette.py:50`](file:///Users/ali/Works/roadmap-board/tests/web/test_palette.py#L50))

### R6.22
- Workflow section light mode: **BUILT** ([`web/css/map.css:1`](file:///Users/ali/Works/roadmap-board/web/css/map.css#L1), [`web/css/graph.css:1`](file:///Users/ali/Works/roadmap-board/web/css/graph.css#L1) via [`tokens.css:92`](file:///Users/ali/Works/roadmap-board/web/css/tokens.css#L92) + `test_graph_css_is_within_budget_and_uses_tokens_only` in [`tests/web/test_workflow_diagram.py:92`](file:///Users/ali/Works/roadmap-board/tests/web/test_workflow_diagram.py#L92), `test_smoke_section_list_equals_router_registry` in [`tests/web/test_ui_smoke_sections.py:44`](file:///Users/ali/Works/roadmap-board/tests/web/test_ui_smoke_sections.py#L44))
- Workflow section 500px layout: **BUILT** ([`web/css/graph.css:62,70`](file:///Users/ali/Works/roadmap-board/web/css/graph.css#L62-L70), [`web/js/views/workflow.js:251`](file:///Users/ali/Works/roadmap-board/web/js/views/workflow.js#L251) + `test_minimap_mounts_above_640_and_chips_replace_it_below` in [`tests/web/test_workflow_view.py:249`](file:///Users/ali/Works/roadmap-board/tests/web/test_workflow_view.py#L249), `test_smoke_section_list_equals_router_registry` in [`tests/web/test_ui_smoke_sections.py:44`](file:///Users/ali/Works/roadmap-board/tests/web/test_ui_smoke_sections.py#L44))
- Workflow section keyboard: **BUILT** ([`web/js/views/workflow.js:1120`](file:///Users/ali/Works/roadmap-board/web/js/views/workflow.js#L1120), [`web/js/graph/viewport.js:424`](file:///Users/ali/Works/roadmap-board/web/js/graph/viewport.js#L424) + `test_n_and_s_keys_and_the_arrows_are_wired` in [`tests/web/test_workflow_view.py:244`](file:///Users/ali/Works/roadmap-board/tests/web/test_workflow_view.py#L244), `test_key_plan_mapping` in [`tests/web/test_graph_keys.py:57`](file:///Users/ali/Works/roadmap-board/tests/web/test_graph_keys.py#L57))
- Workflow section Start/Stop click: **BUILT** ([`web/js/views/workflow.js:1030,1075`](file:///Users/ali/Works/roadmap-board/web/js/views/workflow.js#L1030-L1075) + `test_stop_and_start_use_the_command_path` in [`tests/web/test_workflow_view.py:128`](file:///Users/ali/Works/roadmap-board/tests/web/test_workflow_view.py#L128))

[unrestricted] agy modified the working tree during this staffer run — verify the task asked for it. Delta (`git status --porcelain` entries that appeared or changed during the run):
   M docs/head-gate.json
   M roadmap/services/limits.py
   M roadmap/services/usage.py
   M web/css/components.css
   M web/css/flow.css
   M web/css/work.css
   M web/index.html
   M web/js/routes.js
   M web/js/views/limits.js
   M web/js/views/list.js
   M web/js/views/overview.js
   M web/js/views/tokens.js
   M web/js/views/topbar.js
  ?? docs/reviews/agy-ux-agents.md
  ?? docs/reviews/agy-ux-roadmap.md
  ?? docs/reviews/agy-ux-settings.md
  ?? docs/reviews/agy-ux-workflow.md
  ?? docs/reviews/agy-wf-sync.prompt.txt
  ?? tests/web/test_r756_rows.py
  ?? web/css/git.css
  ?? web/js/views/git.js
ACTION FOR THE CALLING AGENT: inspect these changes (`git diff`) before trusting this staffer. Rollback: `git checkout -- <path>` for tracked files, delete the new untracked ones.
