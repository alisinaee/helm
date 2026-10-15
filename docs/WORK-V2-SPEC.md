# R7.24 Work v2 spec (Trello-informed, not a clone)

Work is the bridge between agents and the person. Agents read and write it in a few lines; the person sees who does what and steers order and limits. Reuse existing fields.

## 1. Missing now (screenshots + code)
- Filter bar wraps to 4 rows (long phase names); no search, no owner filter.
- Cards: variable height, empty space, free-text meta (no fixed tracks); no owner, feature chip or description.
- Column head "Todo11": no gap, no WIP. Done (20) dominates, no collapse.
- No quick add (`task.add`), no in-column reorder (`task.move`): priority cannot be expressed.
- Drawer: note not editable, no task activity, no owner. No board swimlanes.
- List copy button wraps under the title (rule 0; row-alignment B owner).

## 2. Verdicts
| Trello | Verdict | Reason |
|---|---|---|
| Colour labels | NOW (derived) | Chips from model/phase/feature; agents set these already |
| Free labels | SKIP | Agents would invent an inconsistent taxonomy |
| Quick add | NOW | Fastest way to hand agents work |
| Drag across columns | HAVE | Buttons + keys exist |
| Reorder in column | NOW (same phase) | Todo order = agent pickup order |
| Checklist badge | NOW | Subtasks exist; `3/5` track |
| Description | NOW | Reuse `# note`, the agent's brief |
| Comments | HAVE | — |
| Card activity | NOW | Existing log filtered by task |
| Members | NOW (derived) | Owner = live job role/model or "you" |
| Due dates | SKIP | Agents work in tokens and phases |
| Attachments | LATER | `rb:` refs in comments first |
| Cover/background | SKIP | Noise |
| WIP limit | NOW | Caps parallel agents |
| Swimlanes | NOW phase; LATER item | Items wait for Planner v2 H6 |
| Search | NOW | `q:` filter token |
| Saved views | LATER | Hash + localStorage already persist |
| Board bulk | LATER | List bulk exists |
| Archive | NOW (collapse Done) | Last 5 + "Show all N" |
| Templates | SKIP | `plan import` is the template |
| Copy link | HAVE | R7.12 |
| Shortcuts | NOW `n` `/` `?` | Cheap |
| Power-ups | SKIP | — |

## 3. Data model (additive; old files parse unchanged)
- Labels: none stored; chips derive from `model`, `phase`, the first `f:`, `blocked` and `needsUser`.
- Owner: the snapshot `owner`, only when set: the running job's `role/model`, or `you`. No plan field.
- Description: the existing `# note` with its existing cap.
- Order: the line order of tasks within a phase is the rank. `task.move` rewrites the order only, with no format change.
- WIP: setting `wip.doing` (int; unset means no limit), in the limits store. The snapshot has `wipDoing` only when set.
- Dates: none; the target is a phase or plan item. Snapshot growth is under 0.3 KB.

## 4. Card and drawer
The card is a fixed grid with the same tracks on every card and no min-height:
1. Id, chips (with text, never colour only), copy ref (the last `--ref-col` track).
2. Title clamped to 2 lines; the full text is in `title`.
3. Tabular tracks, right-aligned: owner, subtasks, tokens (est/spent), comments. Empty cells keep their width.
4. Actions in a fixed position, then More (Move up/down, Move to…, Queue, Stop). A meter shows only when a cap is set.

Column head: label, count, `n/WIP` (amber at the limit, red over), and a collapse control (Done, Backlog).

Drawer adds: Description (inline edit), Owner, Activity (last 5, with undo), Move up/down.

## 5. Interactions
- Drag between columns (exists) and within a column inside the same phase. A drop into another phase is refused with a toast.
- Keys: Alt+Up/Down reorders and Alt+Left/Right moves a column (a rebind; `?` lists it).
- Quick add "+ Add task" at the foot of Todo; Enter keeps focus; phase = filtered phase, else first open; `n` focuses it.
- Inline title edit: Enter on a focused title calls `task.rename`.
- The filters bar is one row: search (`/`), chips, Phase `<select>`, Owner `<select>`, Lanes `<select>` (none|phase).
- Phase lanes are header rows spanning the columns, and the columns stay aligned.
- Phone (<768 px): one snapping column per screen with count tabs; no touch drag (More: Move to…, up/down); quick add allowed.

## 6. Agent interface
Every op writes activity and undo through the commands framework:
- `task.add {title, phase?, status}`: `roadmap task add "<t>" [--phase P]` → `ok T42 todo in P3. next: roadmap task start T42`
- `task.move {id, before|after}`: `roadmap task move T42 --before T40` → `ok T42 before T40 in P3`
- `task.note {id, text}` is for the GUI. The CLI keeps `task set note=`.
- WIP guard: when an agent starts a task with Doing at or over WIP → `refused: WIP 4/4. next: roadmap task stop <id> or ask the person`. A start by the person is allowed and logged.
- `task list --q <text> --owner <x>`. `roadmap status` adds `doing 3/4` to an existing line.

## 7. Breakdown (Haiku; strict files, in order)
Decision: **sequence after Backlog**; **merge `task.add` into Backlog step 2** (`backlog.add` = `task.add status=backlog`).
- **W1 ops** (after Backlog 2): `roadmap/services/commands.py`, `roadmap/core/mdtables.py`, task CLI file, `tests/unit/test_work_v2_ops.py`.
- **W2 snapshot** (after W1, Backlog 3): `roadmap/core/snapshot.py`, status-line code, `tests/unit/test_work_v2_snapshot.py`.
- **W3 board** (after W2, Backlog 4): `web/js/views/board.js`, `web/css/work.css`, `tests/web/test_work_v2_board.py`.
- **W4 shell** (after W3): `web/js/views/work.js`, `list.js`, `tree.js`, `tests/web/test_work_v2_shell.py`.
- **W5 drawer** (∥ W3): `web/js/views/details.js`, `tests/web/test_work_v2_details.py`.
- **W6 docs** (last): `docs/AGENT-INTERFACE.md`, `UI-SPEC.md`, `PRODUCT-SPEC.md`, lead/worker SKILL.md, `CHANGELOG.md`.

W3/W4 also wait for row alignment B and R7.23 (held files).

agy audits: A) rule 0 + a11y (equal card tracks, button + key path per drag, focus, no colour-only flags, 375 px no scroll); B) every new op logs activity + undo, respects caps; `task.move` never crosses phases.

## 8. Risks and questions
Risks: CSS (Backlog 1.2 KB + this exceeds ~4 KB free: W3 deletes old card min-height/meta rules first, net ≤2 KB); Alt-key rebind surprises; reorder races agent writes (store lock); stale owner when a job dies (job staleness).

Questions:
1. WIP: hard-refuse agent starts, or only warn?
2. May agents reorder Todo, or only you?
3. Owner derived only, or also an assignable `o:` field?
