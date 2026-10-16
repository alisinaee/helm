# AGY Core State & Sync Audit

| Problem | Evidence file:line | Root Cause | Fix Idea | Size |
|---|---|---|---|---|
| Running tasks not shown in UI/CLI | `roadmap/core/snapshot.py:506,564,622`, `roadmap/commands/status.py:66-70,88`, `roadmap/services/supervisor.py:38,325`, `roadmap/services/jobs.py:189-199` | Snapshot and CLI status check `status == "running"`. Supervisor sets claimed jobs to `"claimed"`, not `"running"`. Tasks linked to running jobs are set to `"partial"` in `tasks.json` (no `"running"` task state exists), and `status.py` hides running line when `<= 2` jobs. | Include `"claimed"` in active job filter in `snapshot.py` and `status.py`; roll up active running badge to tasks/Work items; show running jobs in status CLI regardless of count. | S |
| Split-brain store (JSON vs SQLite) | `roadmap/store/db.py:18,76`, `roadmap/services/jobs.py:42-57`, `roadmap/services/head.py:68-83`, `roadmap/services/loader.py:103-106,182-198`, `roadmap/services/supervisor.py:276` | Supervisor hardcodes SQLite (`db.open_project`), while CLI/jobs/head/loader default to JSON unless `ROADMAP_STORE=sqlite`. Supervisor state mutations in `roadmap.db` are invisible to JSON readers, and CLI mutations to `.json` files bypass SQLite. | Make SQLite the default authoritative backend across all CLI and daemon services; remove split-brain dual storage paths. | L |
| Work items omitted from snapshot & loader | `roadmap/services/work.py:7-9,48-60`, `roadmap/services/loader.py:28-29,69-75,182-198`, `roadmap/store/db.py:58-73` | `work.py` writes to `docs/work.json` without updating SQLite `work_items`. `loader.py` omits `work.json` from `BASE_FILES` and `revision()`, and `_read_store` never queries `work_items`. Snapshot has no `work` key; dashboard cannot sync with `work add/accept`. | Add `work.json` to `loader.BASE_FILES` and `revision()`; expose `snap["work"]` from `work.json` or SQLite `work_items`. | M |
| Head asks out of sync with Work items | `docs/WORK-MODEL.md:32,85`, `roadmap/services/head.py:494-506`, `roadmap/services/supervisor.py:238-245`, `roadmap/http/routes.py:654-662` | `head.py:fold_asks` and `supervisor.py:_fold_asks` only inspect `task:*` links in `tasks.json`/`tasks` table. `routes.py:project_head` only indexes `task:` and `job:` refs. `work:W#` links are ignored and never auto-close when Work items reach Done. | Add `work:` link indexing in `routes.py`; update `fold_asks` in `head.py` and `supervisor.py` to resolve Work items and close asks when Work item is Done. | M |
| Plan import bypasses Work items & SQLite | `roadmap/commands/plan.py:132-144`, `roadmap/services/tasks.py:173-201`, `roadmap/store/db.py:69`, `docs/WORK-MODEL.md:46-47` | `plan import` parses text only into `tasks.json` with no `work_id` and no SQLite write. Tasks imported without parent Work items violate WORK-MODEL section 5 and leave SQLite `tasks` stale. | Require/infer `--work` on plan import; sync imported phases and tasks into SQLite `tasks` with required `work_id`. | M |
| HTTP writes do not tick supervisor | `roadmap/http/routes.py:315`, `roadmap/services/supervisor.py:15,270-294` | `POST /api/v1/cmd` invokes `control.after_write` but not `supervisor.tick()`. `supervisor.next_launches()` is not wired into the service daemon (`supervisor.py:15`), causing state lag between CLI, service, and UI. | Trigger `supervisor.tick()` inside `after_write()`; wire `next_launches` into background service event loop. | S |

## How a new user inits a project with /head

**Current flow**:
1. User registers project via `roadmap project new <path>` or `project add` (`commands/project.py:155`).
2. User runs `roadmap service install && roadmap service start` to load launchd daemon (`commands/service.py:16`).
3. User runs `roadmap hooks install <pid>` to configure agent hooks (`commands/hooks.py:29`).
4. User runs `roadmap phase approve P1` because template plan is unapproved by default (`commands/project.py:168`).
5. User must manually set `ROADMAP_STORE=sqlite` or config to match supervisor (`services/jobs.py:45`).
6. User launches `/head`, which fails or desyncs if backend flags, phases, or task binds are missing.

**Proposed simple flow**:
1. Single command `roadmap init`: registers project in config, starts background service if stopped, installs hooks, and creates clean empty board state in SQLite v4 (`work_items` table, empty Work board).
2. Board empty state displays welcoming zero-state with "+ Add Work" and `/head` ready indicator.
3. User runs `/head "Build X"`: head creates Work item `W1`, splits into tasks, binds asks to `work:W1`, and ticks supervisor seamlessly.
