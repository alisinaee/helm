# R7.13 Planner v2: the plan tree (spec, 2026-10-14)

Goal: Planner is the project STRUCTURE and PLAN: phases with sub plans, what the person asked, and the tasks that fulfil each item, built by an agent in one import.

## 1. What is wrong now
It is a flat feature audit table with token columns. It has no outline, no "you asked" marker and no in-place tree building.

## 2. Data model (additive)
A plan item is a feature (`docs/features.json`); everything existing stays.

| Change | Rule |
|---|---|
| Depth | Parent chain ≤2, so 3 levels (phase > sub plan > item). A cycle or a 4th level is an error. |
| Order | File order is the plan order. New op `feature.move {id, dir}` swaps siblings. |
| `ask: true` | Optional: "the person asked for this". Omitted when false. |
| Outline | Derived in the view, never stored: `P0`, `P0.0`, `P0.0.1`, 0-based like the person's P0. Refs keep F ids. |
| Rollup, `gaps` | A parent covers its descendants' tasks; `gaps` counts the uncovered ones. |
| Caps | 60 items raised to 99 (section 8), title 80, acc 160, 3 `feats` per task. |

**Plan text.** An F line takes an optional `ask` token before `|`. A parent may be defined earlier in the same import. T lines already accept `f:`. One import builds everything (about 15 tokens per line):

```roadmap-plan
F F1 - 1 R0 - | Research # brief, landscape, risks notes
F F4 - 1 R1 - | Requirements # every ask has acceptance
F F5 - 1 R1 F4 ask | Offline sync # offline edits merge on reconnect
F F6 - 2 R1 F4 ask | Export to PDF # one click, A4
F F7 - 1 R2 - | Core engine
F F8 - 1 R2 F7 | Storage layer
F F9 - 1 R2 F8 | Schema and migrations
P R2 todo | Core engine
T R2.1 todo 40 sonnet/medium f:F9 | Schema and migrations
T R2.2 todo 30 haiku/low f:F8,F5 | Sync queue
```

## 3. GUI
Every row and the header use one grid (rule 0): `24px 56px 40px 1fr 48px 120px 64px 40px 76px 40px 32px 1.5rem`. Columns: toggle, outline, F id, title (+acc), phase, bar, done/total, gaps, state, Acc, ⋯, copy.

```
Plan [State▾] [□ Asked only] [□ Waiting for your OK]           [+ Plan phase]
! gaps: P1.1 Export to PDF (F6) · ! 3 orphan tasks · 2 waiting for your OK
▾ P0    F1  Research          R0 ▕████░░▏ 1/1     done        ⋯ ⧉
▾ P1    F4  Requirements      R1 ▕█░░░░░▏ 0/1  1  doing       ⋯ ⧉
  ▸ P1.0 F5 ● Offline sync    R1 ▕░░░░░░▏ 0/1     todo   ☐    ⋯ ⧉
       "offline edits merge on reconnect"
```

- Indent goes inside the title cell only (`.lvl1` and `.lvl2`), so the columns never move.
- `●` is an SVG marker with the label "you asked". An ask item keeps its acceptance line until it is accepted.
- Acc: only the person ticks it (it confirms first when the item is not done). Done but not accepted appears in "waiting for your OK".
- Signals: the state chip reads `gap` (text and colour), the gaps column counts on parents, and the orphan callout keeps "Assign…".
- Clicking the title or the count opens Work filtered to the subtree (`f=feat:F4`). The toggle opens children. A leaf opens its task rows.
- The ⋯ menu has Add sub plan, Rename, Edit acceptance, Ask on/off, Link tasks, Move up/down, Hold, and Remove (only with no tasks and no children). Add/Rename edit inline (Enter saves, Esc cancels, Undo toast). 
- Phone: cards with a 12px indent per level; ⋯ and copy at 44px; callouts become chips. Full width, dark and light.

## 4. Agent workflow
- "Create the roadmap in the Planner": the agent runs `agent-guide`, onboarding steps 1-3 (or reads the brief), writes `04-plan.md` (F lines, then P/T lines with `f:`), runs `plan import --dry-run`, the import, then `feature tree`. `plan template --tree` prints the section 2 example.
- `feature tree` prints ≤25 lines, like `P1.0 F5 ask todo 0/1 Offline sync`.
- Agents set `ask` only from the person's words. They may finish an item, but only the person accepts it (refused on the phone agent path).

## 5. Migration
- Keep the callouts, Acc, the ⋯ ops, the task rows and Assign. Empty state: "No plan yet. Ask your agent to create the roadmap."
- Remove the Est K, Spent K and Pri columns (prio stays in the menu) and the Phase filter.
- The 23 current features become top-level items. Regrouping them is one import, after the person approves.

## 6. Budgets
- CSS: planner.css goes from 3.2 to ≤5.5 KB, so the total stays ≤67.5 of 72 KB.
- Snapshot rows add `ask` and `gaps` only when set and carry `acc` until accepted. They drop `estK`, `spentK` and `prio` (`feature show` keeps them). Target ≤8 KB for 60 items (not reached; 99 items measure about 18 KB typical, bounds in the test), asserted in `tests/unit/test_snapshot_features_size.py`.

## 7. Packages (Haiku; each worker stages only its own files)
| # | Files | Accept | When |
|---|---|---|---|
| H1 | roadmap/core/features.py, new tests/unit/test_features_tree.py | depth, cycles, rollup, ask, gaps, slim rows | first |
| H2 | roadmap/core/planfmt.py, new tests/unit/test_planfmt_tree.py | ask round trip, forward parent, depth error with line | ∥ H1 |
| H3 | roadmap/services/features.py, roadmap/services/featops.py, roadmap/core/snapshot.py, tests/unit/test_snapshot_features_size.py | move op, ask on add/set, depth check, ≤8 KB | after H1 |
| H4 | roadmap/commands/feature.py, roadmap/commands/plan.py, new tests/unit/test_cmd_feature_tree.py | `feature tree`, `--ask`, `template --tree` | after H2, H3 |
| H5 | web/js/views/planner.js, web/css/planner.css, tests/web/test_planner*.py | section 3 at 375 and 1440 | after H3 |
| H6 | web/js/views/work.js, web/js/routes.js | `f=feat:` subtree filter | ∥ H5 |
| H7 | docs/AGENT-INTERFACE.md, roadmap/templates/skills/roadmap-lead/SKILL.md, docs/PRODUCT-SPEC.md, docs/PLANNER-SPEC.md | the grammar matches PLAN_ALLOWED | last |

Tests: unit + `make check` each package; `make check-ui` after H5, H6.

agy audits (read-only, the head verifies):
- A1 (after H2): grammar and derive gaps.
- A2 (after H5): rows against the grid, the copy column, aria, no hover-only actions.
- A3 (after H7): the docs, the template and PLAN_ALLOWED agree.

## 8. Decisions (head, 2026-10-23)
1. Labels follow order; a move renumbers them. F ids stay fixed.
2. The cap is raised to 99 items.
3. The 26 features were regrouped into five groups: P0 Board and planning (F27), P1 Agents and the head (F28), P2 Usage and limits (F29), P3 App shell and UI (F30), P4 Platform and release (F31).
4. The Est/Spent/Pri columns are dropped from the Planner screen (Work and Tokens show them).
5. Agents may mark `ask` items from the person's messages.
- Risk: old code drops `ask` on rewrite; land H1+H3 before using it.
