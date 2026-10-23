# Planner section (Opus WP49, 2026-10-14). Decisions: own section; tasks have feats (<=3); only the person accepts

**WP49: Planner advice for roadmap-board (read-only)**

## 1. Advice

1. Make **Planner its own left-nav section**, placed between Roadmap and Work. Leave Roadmap and Work exactly as they are.
2. Each section answers one question. Roadmap is "when and how much" (phases by time and effort). Work is "what is happening today". Planner is "what are we building, and is every piece covered?"
3. Putting features into Roadmap would mix two axes in one view: phases describe time, features describe value. One task (for example R6.6) can serve two features while sitting in a single phase.
4. Planner is the only place to see uncovered features, orphan tasks and the person's acceptance. Those checks are the whole point of the request.
5. The cost is small: one file, one optional task field, one view of about 12 KB and one CSS file of 3 KB or less. Work's drawer gets a feature chip later, as a link only.

## 2. Data model (additive only)

**Storage: a new file, `docs/features.json`.** Don't put features inside tasks.json phases. A separate file keeps tasks.json at schemaVersion 1, gets its own kind in `schema.py`, and is covered by backups and migrate.

```
{"features":[{"id":"F3","title":"≤80","acc":"≤160","prio":1-3,
  "parent":"F2"|null, "phase":"R6"|null, "hold":false, "accepted":"2026-10-14"|null}]}
```

- **Ids:** `F1`–`F99`, with at most 99 features. A sub-plan is a feature with a `parent`. The tree has 3 levels (phase, sub plan, item): a parent may itself have one parent, never two. `ask` marks an item the person asked for.
- **Tasks:** gain an optional `feats:[≤3 ids]`, and the first id is the primary one. Use a list rather than a single `feat`. Shared tasks are a real pattern here (R5.3 builds questions, comments and issues in one go), and with a single field you would get false "uncovered" flags. Global totals still count each task once. Only the per-feature figures count a shared task in each of its features.

**Derived in a new pure module, `roadmap/core/features.py`.** The snapshot gets one new key:

`features:{rows:[{id,title,acc,prio,parent,phase,hold,accepted,tasks[],done,total,estK,spentK,blocked,running,state}], uncovered:[ids], orphans:[task ids], counts:{total,done,doing,todo,uncovered}}`

Feature state is computed in this order (first match wins):
- `hold` if the hold flag is set;
- `uncovered` if it has 0 tasks;
- `done` if every task is done;
- `doing` if any task is done or partial, or a job is running on it;
- `todo` otherwise.

`accepted` is stored separately and is only set by the person. A parent's figures roll up its children.

**Plan text: two new record types.**

```
F F3 - 2 R6 F2 | Roadmap visual # lanes, timeline, approve; usable at 1440 and 375
L F3 R6.6 R2.1                      ; appends feats on those tasks (≤3 each)
```

- Field order is `F id status(-|hold) prio phase|- parent|- [ask] | title # acc`.
- `plan export` emits the F lines, then the P and T lines. Each T line gets an optional ` f:F3,F7` token before the `|`.
- Haiku agents normally only need L lines, which cost about 10 tokens each.

**CLI:**
- `roadmap feature add "title" --acc ".." [--prio 2 --phase R6 --parent F2]`
- `feature list` gives one line per feature: `F3 doing 4/5 380K/410K blk0 Roadmap visual`
- `feature show F3` lists the feature's tasks.
- `feature link F3 R6.6 [R2.1..]` and `feature unlink F3 R6.6`
- `feature accept F3`, which is refused from the phone listener's agent path; only the GUI or a person sets it.
- `status` gains one line: `features: 22 (9 done, 6 doing, 4 todo, 3 uncovered; 2 orphan tasks)`.

## 3. The Planner screen

**At 1440 px:**

```
Planner  [Status: All▾] [Phase: All▾] [□ Unaccepted only]                    [+ Feature]
┌ ! 2 uncovered: F11b Start wakes a session · F21 Palette        [Link tasks] ┐
└ ! 3 orphan tasks: R6.13 R4.4 R6.11                             [Assign…]    ┘
 ▸ ID   Feature / acceptance                 Phase Pri ▕██████░░▏ Tasks  Est K Spent K Blk  State   Acc  ⋯
 ▾ F2   Planner                                R6   1  ▕█░░░░░░░▏   1/6    290      45   0  doing    ☐   ⋯
        "Features ↔ tasks traceability, uncovered/orphan callouts"
     ↳  R6.23 Planner design (Opus)   done  opus     50K  → Work
     ↳  R7.1  features backend        todo  haiku    70K  → Work
 ▸ F10  Token usage + limits           R6   1  ▕████████▏   3/3    330     318   0  done     ☑   ⋯
 ▾ F13  Agents workflow map            R6   2  ▕██░░░░░░▏   1/3    240      50   1  doing    ☐   ⋯
   ▸ F13.a (sub-plan rows indented 16px, same columns)
```

**Fixed columns (UI rule 0):**
- Grid template: `24px 52px 1fr 52px 36px 120px 64px 72px 72px 40px 76px 40px 32px`.
- All numbers are right-aligned with `font-variant-numeric: tabular-nums`.
- The state chip, the Acc checkbox and the ⋯ menu always sit in the last three columns.
- The acceptance line is 1 line of muted text under the title, cut with an ellipsis.
- Expanded task sub-rows show id, title, status chip, model, est K, and a "→ Work" link that opens `#work?task=R7.1` in the drawer.
- The bar is a plain `<div>` with an inline width, coloured green when done, amber when blocked, and grey otherwise.

**At 375 px (cards):**

```
F2 Planner                 [doing]
▕██░░░░░░░░▏ 1/6 · 290K est · ☐ acc
"Features ↔ tasks traceability…"
▸ 6 tasks                       ⋯
```

On phone, callouts become two collapsible chips at the top, filters move into a sheet, and "+ Feature" becomes a floating button.

**Actions and ops** (all through POST `/api/v1/cmd`, all registered with `public=True`):

| Op | What it does |
|---|---|
| `feature.add` | Create a feature |
| `feature.set` | Change title, acc, prio, phase, parent or hold |
| `feature.link` | `{task, feats[]}`: link a task, from the ⋯ menu or the orphan "Assign…" picker |
| `feature.unlink` | Remove a link |
| `feature.accept` | `{id, on}`: the Acc checkbox; asks for confirmation if the feature isn't done |
| `feature.rm` | Remove a feature (only when it has 0 tasks) |

All of these go into undo.jsonl and log to activity.

**Empty state:** "No features yet. Features say what you're building; tasks say how. [+ Feature] or `roadmap plan import` with F/L lines." If any tasks exist, it also shows "N tasks are orphans."

**CSS:** a new `web/css/planner.css` of 3 KB or less, reusing the existing chip, bar and grid tokens. That takes the total from 52.7 KB to about 55.7 KB, under the 64 KB cap.

## 4. Seed for roadmap-board (`plan import`)

Status is derived, and Acc is set by the person. "Not fully built" is the honest gap.

| F | Feature: acceptance | Tasks | Not fully built? |
|---|---|---|---|
| F1 | Agent↔GUI bridge: one write path (/cmd), CLI and hooks | R1.3 R1.4 R1.5 R5.3 R5.5 | – |
| F2 | Planner: features↔tasks, uncovered/orphans, acceptance | R6.23 R6.13 (+new) | **yes** |
| F3 | Roadmap visual: lanes, timeline, approve | R6.6 R2.1 | – |
| F4 | Progress manager/Overview: meters, blockers, live tokens | R6.4 R6.18 | **yes** (live job tokens) |
| F5 | Phase/task/subtask manager: create/edit/move in GUI+CLI | R5.2 R4.2 | partial (no inline title edit) |
| F6 | Light Jira/Trello: board, list, tree, drag | R5.1 R5.6 R6.5 | partial (no search) |
| F7 | Issues: bug/risk/blocker gating `next` | R5.2 R5.3 R6.6 | – |
| F8 | Agents ask the person; Inbox + notifications | R5.3 R6.4 R6.14 | – |
| F9 | Comments on tasks: flat thread, caps | R5.2 R5.3 | – |
| F10 | Token usage + day/week limits, global/project, "under 10%" | R1.6 R6.1 R6.7 | partial (soft when usage is stale) |
| F11 | Interactive control: start/stop/answers from GUI | R5.4 R6.12 | **yes**: Start doesn't wake a session (uncovered sub-plan F11b) |
| F12 | Agent/subagent + Claude rules auto-applied | R5.4 R6.15 | – |
| F13 | Agents workflow map + timeline | R6.20 R6.21 R6.22 | **yes** |
| F14 | Token-lean agent interface: status ≤8 lines | R4.1 R4.2 | **yes**: full-cycle cost never measured (uncovered) |
| F15 | Haiku skills ≤3.2 KB + `skills install` | R4.3 R6.16 R2.3 | – |
| F16 | Research-first onboarding in one command | R4.1 R4.3 R6.18 | **yes** |
| F17 | Any project, runs as a service; split-net cutover | R1.1 R1.2 R1.8 R1.9 R6.17 R3.2 | **yes** (cutover, legacy hooks) |
| F18 | App shell: left nav, right panel, full width | R1.7 R6.2 R6.3 R6.10 | – |
| F19 | At-a-glance alignment, dark/light, a11y | R2.2 R6.9 (+row-alignment task) | **yes** (row-alignment in flight, not in tasks.json) |
| F20 | Phone access: phone listener, responsive | R3.1 R6.8 | – |
| F21 | ⌘K palette and search | R6.19 | **yes** |
| F22 | Security + release 1.0 | R3.1 R3.2 R6.11 R4.4 | **yes** |

Import text, in the format shown in section 2: `F F1 - 1 R1 - | Agent↔GUI bridge # one write path…` and so on, then `L F1 R1.3 R1.4 R1.5 R5.3 R5.5`. Add the tasks for F11b and F14 as new `R7.x` T lines, so they show as covered but todo.

## 5. Packages (Haiku workers, about 235k total)

**Ownership.** Two files are owned by other running workers:
- `snapshot.py` and `commands.py` belong to the workflow-data worker. Ops register through cmdops' `_register` in a new `featops.py`, with no edit to commands.py.
- `web/**` belongs to the row-alignment worker. New web files are fine; shared web files wait until it finishes.

| # | Package | Files | Acceptance | Size | When |
|---|---|---|---|---|---|
| B1 | Core | new `roadmap/core/features.py`, `roadmap/store/schema.py` (+features kind), `roadmap/core/parsers.py` (task `feats`) | Pure `derive()` gives states, rollup, uncovered and orphans; caps enforced; unit tests | 50k | Now. Touch parsers.py only after the workflow worker's `after` change lands; check `git log` first. |
| B2 | Plan format | `roadmap/core/planfmt.py`, `roadmap/services/tasks.py` | F/L records parse and export round-trip; `--dry-run` shows `+F3 ~R6.6` | 35k | Parallel with B1 |
| B3 | Service, ops, CLI | new `roadmap/services/features.py`, new `roadmap/services/featops.py` (imported by one line in `cmdops.py`), new `roadmap/commands/feature.py`, `roadmap/cli.py`, `roadmap/commands/status.py` | 6 ops with locks and undo; `feature accept` refused for agents on the phone path; status line ≤1 | 50k | After B1 |
| B4 | Snapshot hook | `roadmap/core/snapshot.py` (+1 key) | `features` is in the snapshot and adds ≤6 KB for 60 features (superseded: see PLANNER-V2-SPEC section 6) | 10k | After the workflow-data worker merges |
| V1 | View | new `web/js/views/planner.js`, new `web/css/planner.css` (≤3 KB) | Layout as in section 3; ui_smoke passes at 1440 and 375; numbers tabular | 60k | Parallel with B3, against a fixture |
| V2 | Wire-up | `web/js/routes.js`, `web/index.html`, icon, Work drawer feature chip | Nav entry, deep link to Work | 15k | After row-alignment finishes and after B4 |
| S1 | Seed + docs | import section 4 into the project; `docs/AGENT-INTERFACE.md` grammar; skill gets 3 lines | `status` shows the features line | 15k | Last |

Order: B1 ∥ B2, then B3 ∥ V1, then B4, then V2, then S1. Have Sonnet check B3 and V2.

## 6. Three decisions for the person

1. **Planner as its own section, or folded into Roadmap and Work?** I recommend its own section. Roadmap and Work stay untouched.
2. **Can a task belong to more than one feature?** I recommend `feats` with up to 3 per task, the first being primary. A single feature per task would wrongly show Issues, Comments and Questions as uncovered.
3. **Who marks a feature as accepted?** I recommend only the person, from the GUI or as a human at the CLI. Agents can make a feature "done" but never "accepted", and Planner highlights done-but-unaccepted features as the person's review queue.

### Critical files for implementation
- ~/Works/roadmap-board/roadmap/core/planfmt.py
- ~/Works/roadmap-board/roadmap/services/cmdops.py (`_register`, line 311)
- ~/Works/roadmap-board/roadmap/core/snapshot.py
- ~/Works/roadmap-board/web/js/routes.js
- ~/Works/roadmap-board/docs/tasks.json