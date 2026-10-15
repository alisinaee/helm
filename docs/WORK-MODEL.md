# Work model: Work items vs agent tasks (R7.101)

General product rule (the person): a Work item is how a human understands the work (Jira/Trello card). An agent
task is a machine package. One Work item has many agent tasks. An agent task never appears as a card.
Wrong way today: docs/tasks.json mixes both (R7.29 "Git section" next to R7.86 "store db.py", R7.98 "suite green");
asks, jobs and the Work board all bind to packages. This supersedes WORK-UNIFIED-SPEC section 1 (issues as kind).

## 1. Two entity types
| | Work item (human) | Agent task (machine) |
|---|---|---|
| id | `W12` (issues keep `I3`) | `R7.86` (existing ids kept) |
| words | plain title <= 60 chars, one-line outcome/acceptance; no file, model or wave names | package title, files, model, effort, done-check, deps |
| state | Backlog, Todo, Doing, Review, Done (+ Won't do) | todo, claimed, running, verify, done, failed, needs-you |
| fields | prio P0-P3, owner (you/head/agent role), kind task or issue (bug/risk/question/blocker, sev), phase, asks | `work_id` (required), jobs, commits, leases, tokens |
| who sees | Work board/List/Tree, Overview, Head, Inbox | Agents, Workflow map, timeline, Work item drawer (read-only rows) |

## 2. Status roll-up (derived; stored = only the person's intent)
- Backlog / Won't do: set by the person only; roll-up never moves an item out of them.
- Todo: no agent task started (or none yet).
- Doing: any agent task claimed/running/verify/failed, or some done and some open.
- Review: every non-cancelled agent task done (commit bound). Item goes to Inbox: "Review W12". Not Done.
- Done: only `work accept W12` (person, or head on the person's chat word). Stored `accepted` ts.
- Reopen: person rejects in Review or adds an agent task to a Done item -> Doing (note kept).
- Badges, not states: needs-you (any agent task needs-you), blocked (open issue blocks it), running dot.
- Progress bar = done / total agent tasks; tokens = sum of its agent tasks' jobs.
- Prio: agent tasks inherit the Work item prio for the supervisor queue (no own prio).

## 3. Where each appears
- Work board/List/Tree: Work items only (task + issue kinds), P column, progress bar n/m, owner, Accept in Review.
  Drawer: outcome, linked asks, agent task rows (status, model, job) linking to Agents.
- Agents, Workflow map, timeline: jobs and agent tasks grouped under their Work item header (`W12 title`).
- Head: asks bind to `work:W12`; the ask row shows the Work item status. Ask closes when its Work item is Done
  (or Won't do); it shows "review" while the Work item is in Review.
- Overview counts Work items; Agents counts jobs. No screen counts packages as "work".

## 4. Who creates what
- Person (Work "+ Add", Head chat) or head (from an ask, in the person's words) creates Work items.
- Head/planner splits a Work item into agent tasks (files, model, check). Agents never create Work items;
  an agent's found bug becomes an issue-kind Work item in Todo for the person to triage.
- Head ask triage: bind to an open Work item (title fingerprint, then Jaccard suggestion) or `head convert Hn work`.
- Wording lint on `work add`: refuse file paths, model names, "wave/P1/W2" jargon in the title.

## 5. Migration
Store v4 (roadmap/store/migrations.py):
- `work_items(id PK, kind, title, outcome, state, prio INT, owner, phase, position INT, accepted, alias, data)`
- `ALTER TABLE tasks RENAME TO agent_tasks`; `ADD COLUMN work_id TEXT REFERENCES work_items(id)`; index work_id;
  insert without work_id refused in code (old rows filled by the map below before the check is on).
- issues.json rows -> work_items kind=issue (id `I#` kept). jobs.task stays an agent task id.
- Ask binds `task:R7.x` rewritten to `work:<its W>` (old ref kept in data). Refs `rb:<p>/task/R7.x` still resolve.
- Export: docs/work.json (Work items) + docs/tasks.json gains `work` per task. Human-level todo rows with no package
  (R7.13, 7.24, 7.29, ...) become the Work item only, `alias` = old id, no agent task until split.
- Historical: Work items whose agent tasks are all done migrate as Done (accepted=migrate), not Review.

Phase R7 map (101 rows -> 15 Work items):
| W | Work item (human words) | agent tasks R7.x | state |
|---|---|---|---|
| W1 | Head: a ledger of everything I ask, bound to work | 31,32,34-37,43,44,46,49,66,80,81 | Doing |
| W2 | Any model can be the head, safely and cheaply | 64,67-73,89 | Doing |
| W3 | Reliable core: one database, nothing lost, work continues | 82-88,91-94,96,99,102 | Doing |
| W4 | Every screen shows the same live truth | 33,40,45,50-52,57,58,61 | Done |
| W5 | Work board like Trello/Jira, issues included | 3,22,24,25,78,97,101 | Doing |
| W6 | Agents screen: what runs, which model, full history | 2,38,39,41,60,90,95 | Done |
| W7 | Workflow map and timeline | 14,17,30,62,74 | Doing |
| W8 | Usage and limits I can trust | 27,28,63,76,77,100 | Doing |
| W9 | Clean, aligned UI on every screen and phone | 5,7,9,10,23,26,42,47,54,56,59,65 | Doing |
| W10 | Tests, lint and reviews stay green | 4,8,18,19,48,53,55,98 | Doing |
| W11 | Docs and architecture match the product | 6,21,79 | Doing |
| W12 | Git section | 29,75 | Doing |
| W13 | Event log, bug button, copy refs | 12,16 | Doing |
| W14 | Start work from the GUI | 1,11,20 | Done |
| W15 | Planner v2: project structure and plan tree | 13 | Todo |
Rows R7.13, 7.21, 7.22, 7.24, 7.26, 7.29, 7.30, 7.59 are human-level: keep as alias/umbrella, split later.

## 6. CLI / ops
- New ops: `work.add`, `work.set` (state backlog/wontfix, prio, owner, title, outcome), `work.accept`,
  `work.reopen`, `work.link`/`work.unlink` (ask), `work.move` (rank). Events + undo like task ops.
- CLI: `roadmap work add "title" --outcome ".." [--prio 1] [--kind bug --sev 2]`, `work list`, `work show W12`
  (agent tasks, jobs, asks; <= 15 lines), `work accept|reopen W12`, `work link W12 H40`.
- `task add` -> agent task: `roadmap task add "pkg" --work W12 --files a,b --model haiku --check "cmd"`;
  no `--work` -> refused. `task move R7.86 --work W3`. `job start --task R7.86` unchanged.
- `head convert Hn work` (new target); `head t Hn --bind work:W12`; `task:` binds still accepted, auto-lifted to work.
- `status`: one line per Doing/Review Work item with n/m, then running jobs.

## 7. Effect on v3 waves (HEAD-V3-PLAN)
- S1 fold: agent task done -> if all done, Work item Review + Inbox; ask closes on Work Done (not on task done).
- Queue: ready agent tasks ordered by Work item prio; needs-you shown on the Work item.
- Q1 prio and Q3 fingerprint move to Work items (agent task fingerprint = title + work_id).
- U3 P column, N1 `head next`: grouped by Work item. S2, S3, Q2, U1, U2 unchanged.

## 8. Build packages (ordered; disjoint files; done-check: unit suite + `make check`, UI adds `make check-ui`)
| # | Files | Done-check | After |
|---|---|---|---|
| M1 | store/migrations.py, store/schema.py, store/db.py (TABLES), store/work_db.py (new), store/tasks_db.py | tests/unit/test_work_db.py: v4 migrate twice same; agent task without work_id refused | - |
| M2 | core/workstatus.py (new, pure roll-up) | tests/unit/test_work_rollup.py: table of section 2 cases | ∥ M1 |
| M3 | store/migrate.py, docs/work-map-R7.json | tests/unit/test_migrate_work.py: every R7 row mapped, binds lifted, refs resolve | M1 |
| M4 | services/work.py (new), services/cmdops.py, services/tasks.py | tests/unit/test_work_ops.py: ops + undo + events | M1, M2 |
| M5 | commands/work.py (new), commands/task.py, commands/head.py, commands/__init__.py | tests/unit/test_cli_work.py: outputs <= 15 lines; wording lint | M4 |
| M6 | services/head.py, services/headops.py, services/supervisor.py | tests/unit/test_work_fold.py: all done -> Review; accept -> ask closed | M4 |
| M7 | core/snapshot.py, store/export.py | snapshot `work[]` with progress; export golden incl. docs/work.json | M4 |
| M8 | web/js/views/work.js, board.js, list.js, tree.js (+ css) | make check-ui; no agent task as card; Accept in Review | M7 |
| M9 | web/js/views/agents.js, workflow.js, head.js, inbox.js | make check-ui; grouped by Work item | M7, ∥ M8 |
| M10 | docs/HEAD-RUNBOOK.md, commands/agent_guide.py, head skill text | guide test; runbook says asks bind to W | M5 |

Open questions for the person: (1) small items auto-accept (skip Review)? (2) keep phases as milestones over
Work items? (3) confirm the 15-item R7 grouping and titles.

## Decisions (person, 2026-10-15)
- Every Work item goes through Review: only the person's accept makes it Done (no skip for small items).
- Phases (R1-R7) stay as milestones above Work items.
