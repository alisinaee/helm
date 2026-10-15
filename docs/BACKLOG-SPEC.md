# R7.22 Backlog spec

## 1. Meaning and lifecycle
Backlog = known ideas or work, **not committed, not scheduled**. To do = committed, next. Hold = committed but blocked or paused. Deferred (hold with note "Deferred…") = parked by project rule.

Flow: `backlog -> todo (promote) -> partial (doing) -> done`. Hold stays as is; `todo -> backlog` (demote) is allowed.
- Person: add, promote, demote, delete.
- Agents: may add to backlog and **propose** promotion (activity log entry "proposed promote T…"), never promote or start.

Deferred: **sits beside** backlog for now (no migration). Optional later: `roadmap task backlog` on a deferred task converts it (question 1).

## 2. Data model
- New task state `backlog` in `parsers.STATES`, `planfmt.TASK_STATUSES` (not `PHASE_STATUSES`: a phase is never backlog), `mdtables` mark `💡`/"backlog", `graph/model.js` status map.
- Compatible: old files have no `backlog`, parse unchanged. No schema version bump (additive enum value); snapshot gains fields only.
- Placement (cheapest): backlog tasks live in a phase like any task. Tasks with no phase go to a reserved phase `BL` "Backlog" (auto-created on first `backlog add` without `--phase`, sorted last, hidden from phase lists when empty). No separate store.
- Counts: backlog excluded from `left`, `tasks_total`, progress %, phase progress, token totals (same rule as deferred). Shown separately: `backlog_count`, `backlog_tokens_k` (top-level and per phase). A phase with only backlog tasks shows "backlog", no percent.
- Caps: existing title and note caps apply; backlog has no own cap beyond the task cap.

## 3. Plan format and CLI
- T line status `backlog` valid; `plan template` lists `todo|partial|done|hold|backlog|-` with one example line.
- `roadmap task backlog <id>` -> `ok T12 -> backlog. next: roadmap task promote T12`
- `roadmap task promote <id>` -> `ok T12 -> todo. next: roadmap task start T12` (person only; agent caller gets `refused: promote is person-only. next: roadmap task note T12 "propose promote"`)
- `roadmap backlog add "<title>" [--phase P]` -> `ok T41 backlog in BL. next: roadmap task promote T41`
- `roadmap task list --status backlog` works via existing filter.
- `roadmap status`: fold into an existing line, e.g. `tasks: 34 left, 12 done, backlog 7` (keeps the 8-line cap).
- Start guard: `task start` on backlog -> `refused: T41 is backlog. next: ask the person to promote`.

## 4. GUI
- Board: Backlog column leftmost, collapsed by default (narrow rail with count badge; state per viewer in localStorage). Quick-add input "Add to backlog" at its top. Drag to To do, or a Promote button per card (fixed action column, UI rule 0).
- List/tree: filter chip "Backlog" (off by default: backlog hidden, count shown on chip).
- Planner v2: a "Backlog" section in items.
- Overview: one count line "Backlog 7".
- Workflow map: backlog hidden by default; toggle "Show backlog" draws them dimmed, outside the main flow.
- Next up and agent pickups ignore backlog.
- Copy ref kind `task` unchanged.
- Phone: read-only (count + list, no quick-add, no drag).

## 5. Budget
Snapshot: +2 top fields, +2 per phase, tasks carry state only: <1 KB on this repo. CSS: column rail, badge, chip, dim class: target <=1.2 KB of the ~4 KB free under the 72 KB cap; reuse tokens, no new colors except one `--st-backlog`.

## 6. Breakdown (Haiku, in order, non-overlapping)
1. **Core+format+CLI+tests**: `roadmap/core/parsers.py`, `roadmap/core/mdtables.py`, `roadmap/core/planfmt.py`, `roadmap/core/guide.py`, `roadmap/cli/*task*` + backlog subcommand file, `tests/unit/test_backlog_core.py`. **Wait for Planner v2 H1/H2 (holds planfmt.py).**
2. **Ops**: `roadmap/services/commands*` (ops `task.backlog`, `task.promote`, `backlog.add`, undo entries, activity log, person-only guard, start guard), `tests/unit/test_backlog_ops.py`. Wait for `roadmap/log.py` worker.
3. **Snapshot+status**: `roadmap/core/snapshot.py`, status line code, `tests/unit/test_backlog_snapshot.py`. Not `features.py` (held; if it needs backlog exclusion, a follow-up after its owner finishes).
4. **Web work views**: `web/js/views/work.js`, `board.js`, then `list.js`, `tree.js`, `overview.js`, `web/css/work.css`. **After row alignment B** (holds tree/list/overview and CSS).
5. **Graph**: `web/js/graph/model.js` + workflow toggle file only.
6. **Docs+skills**: `docs/AGENT-INTERFACE.md`, `docs/UI-SPEC.md`, `docs/PRODUCT-SPEC.md`, `roadmap/templates/skills/roadmap-{lead,worker}/SKILL.md`, `CHANGELOG.md`.

Steps 1→2→3 serial; 5 after 3; 4 after 3 and row alignment B; 6 last.

agy audits (read-only, verified by head): A) every place that counts "left"/progress/tokens excludes backlog (grep `ACTIVE`, `deferred`, `state ==`); B) no agent path (pickup, next up, start, bulk start) can start a backlog task.

## 7. Risks and questions
Risks: missed count site inflates progress (audit A); agents bypassing promote via bulk start (audit B); reserved `BL` phase colliding with a user phase id; CSS budget; merge conflicts with held files (sequence above).

Questions:
1. Should deferred tasks become backlog (one-time convert), or stay separate?
2. Reserved `BL` phase for unphased items OK, or must every backlog item pick a phase?
3. Backlog column collapsed by default, or open?
