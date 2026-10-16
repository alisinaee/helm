# core-verified (R10.10 step 1): agy-core-audit.md checked against code

## 1. Claims
| # | claim | verdict | real evidence | real root cause |
|---|---|---|---|---|
| 1 | running tasks not shown (claimed vs running) | PARTIAL | snapshot.py:223-224,506 only "running"; supervisor.py:325 sets "claimed" but next_launches is called nowhere (grep) | "claimed" jobs never occur today, so that is not the live cause. Real: task rows stay `partial` (jobs.py:189-199 `_mark_partial`, JSON only); running only shows via job state (snapshot.py:223). status.py:62-66 hides jobs when <=2 BY DESIGN (own lines). In sqlite mode `_read_store` (loader.py:182-198) shows jobs from db, but hook/CLI start_job writes JSON (jobs.py:103-137) unless backend=sqlite |
| 2 | split-brain JSON vs SQLite | TRUE | supervisor.py:276 `db.open_project` always; jobs.py:42-57, head.py:68-83 use `store_backend` (default json); loader.py:146-150 | tick (server.py:46-49 every 30s, commands/tick.py) opens/creates docs/roadmap.db even for JSON projects, folds asks/tasks against EMPTY tables: auto-close of asks and reap never see tasks.json/jobs.json. head.py:fold_asks is a second, JSON copy of supervisor._fold_asks |
| 3 | work.json not in loader/snapshot | PARTIAL | snapshot.py:649-651 builds `snap["work"]` from `files["work.json"]`; loader.py:28-29 BASE_FILES lacks work.json (reached only if in config extras); revision() loader.py:60-84 omits it; work.py:7-10 says file is the store in both backends | snapshot DOES support work; loader never reads/stamps the file, so no `work` key and no cache bust. work_items table is unused by work.py (documented, not a bug) |
| 4 | head asks ignore work: links | TRUE | head.py:494-506, supervisor.py:238-245 and routes.py project_head only look at `task:` refs | no `work:` resolution anywhere in fold |
| 5 | plan import bypasses Work/SQLite | PARTIAL | plan.py:132-144 -> apply_records -> tasks.json; no work_id | no work_id on imported tasks (true); SQLite write only matters in sqlite mode (backend-split, see 2) |
| 6 | HTTP writes do not tick supervisor | PARTIAL | routes.py:315 only `control.after_write`; server.py:35-60 supervisor_loop ticks every 30s | "not wired into daemon" FALSE for tick (loop exists); TRUE that next_launches is unwired and writes do not tick (<=30s lag) |
| 7 | init flow steps (project new/add, service install+start, hooks install, phase approve, ROADMAP_STORE) | PARTIAL | commands/project.py:144-162 (`new`), :91 (`init`); service.py:36 install; hooks.py:29 `_install`; no top-level `roadmap init` | steps real; "must set ROADMAP_STORE" true only for claim (jobs.py:62); `phase approve` needed only because template P1 approved:false (project.py:172-184) |

Counts: TRUE 2, PARTIAL 4, FALSE 0 (sub-claims false: "not wired" tick, "claimed" as live cause, "no work key").

## 2. Fix packages (one Haiku worker each, disjoint files)
**C1 one backend, no phantom db** — goal: tick must not create/read roadmap.db for JSON projects. Edit: roadmap/services/supervisor.py (tick: if `head_store.sqlite_db(data_dir) is None` return `{"ran": False, "reason": "json store"}`... then do JSON fold: call `head.fold_asks(data_dir)` and return report keys empty lists), roadmap/http/server.py only if report shape breaks. Test: tests/unit/test_supervisor_json.py (JSON project, tick creates no docs/roadmap.db; ask bound to done task closes). Done: unittest on that file + tests/unit supervisor tests pass.
**C2 work.json in loader** — Edit: roadmap/services/loader.py (add "work.json" to BASE_FILES; revision picks it up). Test: tests/unit/test_loader_work.py (write work.json, snap has "work", revision changes after edit). Done: test + `make check-ui` unaffected.
**C3 work: links close asks** — Edit: roadmap/services/head.py (fold_asks), roadmap/services/supervisor.py (_fold_asks), roadmap/http/routes.py (project_head index). Rule: ref `work:W#` counts done when work.json item status Done (read via services/work.py reader, no db). Test: tests/unit/test_fold_work_links.py. Done: ask with only work:W1 closes after accept. (Needs C1 first only for supervisor.py; keep C3 after C1.)
**C4 tick after write** — Edit: roadmap/http/routes.py (cmd handler line ~315: after `control.after_write`, best-effort `supervisor_pass`-style tick of that project in try/except). NOT in same run as C3 (routes.py shared): run after C3. Test: tests/web/test_cmd_tick.py. Done: ask closes without waiting 30s.
**C5 running visibility** — Edit: roadmap/core/snapshot.py (lines 506/223: treat status in ("running","claimed")), roadmap/commands/status.py (running_line same set; always print running ids, drop <=2 hide only if lines duplicate). Test: tests/unit/test_snapshot_running.py. Done: claimed job appears in agents.running and task state. (Dashboard "running tasks not shown" check: also confirm web/js reads snap.agents.running; separate UI audit if still hidden.)
**C6 plan import work_id** — Edit: roadmap/commands/plan.py (`--work W#` optional, set work.link via services/work.py op), test tests/unit/test_plan_work.py. Low priority.

## 3. R10.11 init flow package
Goal: `roadmap init [path]` (also what /head runs) does everything, idempotent.
Files: new roadmap/commands/init.py (register in roadmap/cli.py command list), skill ~/.claude/skills/head/SKILL.md step 0 (call `roadmap init`; person-side edit, not worker), tests/unit/test_init_cmd.py.
Steps in handler:
1. `projects.init_project(path)` + `add_project` if unregistered (reuse project.py `_new` logic, factor into services/projects.new_project).
2. Write empty board: tasks.json with NO template phase (or P1 approved:true) so no `phase approve` step; empty work.json.
3. `hooks_install.install(project_id, False)`.
4. Service: `launchd.status()`; if not installed -> `launchd.install()`, then start if not loaded (skip with `--no-service`; print one line "service: running on :PORT").
5. Print `ready: <id> http://localhost:PORT/#<id>`; with --json return the same fields.
Tests: temp ROADMAP_HOME, monkeypatch launchd and hooks_install; assert idempotent second run, registered, hooks called once, empty board. Done: unittest + `make check`.
Depends on: C1 (so the fresh JSON project is not given a phantom db).
