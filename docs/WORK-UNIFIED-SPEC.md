# R7.25 Work unified spec: issues on the board, add anything

## 1. Model: (a) unify in the GUI only
Keep `issues.json`, `services/issues.py` and `roadmap issue` as they are. Work shows issues as a card kind.

Not (b), issues as tasks `kind=issue`:
- **Compatibility:** it changes plan format, parsers, ids, refs, archive, blocker logic.
- **Tokens:** guide and skills rewritten; agents re-learn.
- **Risk:** issues have own caps (200 open, 100 closed); as tasks they inflate counts, progress and tokens.

Unchanged: CLI, plan format, `snapshot.issues`, `snapshot.blocked`, ref `rb:<proj>/issue/I1`, blocker rule.

Additive: snapshot `issuesClosed` (newest 5 `{id,title,kind,closed}`, <0.5 KB); `issue.status` made public for drag (undo exists).

## 2. Card kinds
| Kind | Source | Chip | Column |
|---|---|---|---|
| task | tasks | — | any |
| idea | task `backlog` | `idea` | Backlog |
| issue | issues.json | `bug`/`risk`/`question`/`blocker` + `sev1-3` | open→To do, doing→Doing, closed/wontfix→Done |

- **Grid (rule 0):** task tracks. Track 1: `I3`, kind chip, ref. Subtasks cell: linked tasks; tokens cell empty, width kept. Actions: Start, Close, More (Link, Won't fix, Reopen).
- **Blocker badge:** a blocked task shows red `⛔ I3` (opens the issue); the issue shows `blocks T12`.
- **Order:** sev, then id; no reorder. Drop into Hold/Backlog refused (toast).
- **Done:** collapsed, last 5, "Show all".
- **List:** Kind column after id. **Tree:** issues under linked tasks; unlinked in a last "Issues" group.
- **Filter:** Kind `<select>` (All, Tasks, Issues, Blockers, Ideas; hash `k=`). `q:` matches issues.

## 3. One "+ Add"
`+ Add ▾` sits in the Work head. Each column has an inline "+ Add" at its foot whose kind defaults to the column (To do → task, Backlog → idea).

| Kind | Fields | Op | Lands in |
|---|---|---|---|
| Task | title | `task.add` | To do (filtered phase) |
| Issue/bug | title | `issue.new kind=bug sev=2` | To do |
| Blocker | title, task picker | `issue.new kind=blocker` + task | To do, plus a badge on the task |
| Idea | title | `backlog.add` | Backlog |
| Ask the agent | text | `question.ask` | Inbox (toast links there); no card |

Card adds (More or drawer): Subtask `subtask.add`, Comment `comment.add`, Plan item `feature.link`, Blocker for this task.

Flow: title first; Enter saves, keeps focus; Tab switches kind; Esc cancels. Sev, note, phase later in the drawer. Every add toasts Undo (`z`). Enter on a task title: `task.rename` (issues: Q2).

Keys (outside inputs; `g` chords stay): `n` task, `i` issue, `b` idea, `/` search, `?` help.

Phone (<768 px): a "+ Add" sheet (task, issue, idea, ask) with no drag; cards move via More → Move to…. The read-only phone link hides adding.

## 4. Nav, routes, counts
- **Nav:** Issues leaves `routes.js`; Work badge = blocked tasks + open blockers (red); `g u` → Work `k=issues`.
- **Redirects:** `#/p/<id>/issues` → `work?k=issues` (`f=blockers` → `k=blockers`); `/issues/i/I3` → `/work/i/I3`.
- **Drawer:** reuses `issueView` in `details.js`, plus Start, Close, Won't fix and Link task.
- **Overview** line links to filtered Work; **Inbox** unchanged.
- **Deleted:** `issues.js`; `app.js` routes `issue-close` to `work.js`.

## 5. Agent interface
- Commands are unchanged. `issue new` adds the line `next: roadmap issue link I7 <task>`.
- `roadmap status` folds into an existing line: `tasks: 34 left, 12 done, backlog 7, issues 3 (1 blocker)`. The 8-line cap stays.
- The guide gains one line: "issues show on Work".

## 6. Amendments to the WORK-V2 and BACKLOG breakdowns
- **Backlog 1–3:** unchanged. Step 1 is running.
- **W1:** make `issue.status` public in `services/commands.py`; add the `next:` line in `commands/issue.py`; test file `tests/unit/test_work_unified_ops.py`.
- **W2:** `issuesClosed` and the status fold in `snapshot.py`, with tests in `test_work_v2_snapshot.py`.
- **W3:** in `board.js` and `work.css`: issue cards, the blocker badge, the Kind filter and the column add.
  - First, move the `.iss*` rules out of `plan.css` and prune them. W3 owns `plan.css` for that cut only.
- **W4:**
  - `work.js` (menu, keys), `list.js`, `tree.js`, `routes.js`, `router.js`, `keys.js`, `app.js`; delete `issues.js`.
  - Waits for R7.23 (`topbar.js`, badge) and row alignment B.
- **W5:** `details.js`, issue actions.
- **W6:** `UI-SPEC.md` (drop the Issues section, its nav order and its badge), `AGENT-INTERFACE.md`, skills.
- **CSS:** 68.9 of 72 KB used (~3 KB free). Pruning `.iss*` (1.7 KB) frees ~1.2 KB. Adds: Backlog 1.2 + Work v2 2 + unified 0.8 ≈ 4 KB, just inside ~4.2 KB.

agy audits: A) old `/issues` hashes, `g u`, refs land on Work. B) Close and drag-to-Done clear the badge; Undo restores it.

## 7. Risks and questions
Risks: two stores, distinct ids (`T`/`I`); "Show all" needs a fetch; lost nav habit (`g u` helps); held files delay W4; issue `question` vs "Ask the agent" (label "Question (issue)").

Questions:
1. Issues mixed into To do/Doing/Done (proposed), or in their own "Issues" swimlane?
2. Add `issue.rename` and `issue.set sev=` so issues can be edited inline?
3. Should "Ask the agent" also create a board card, or only go to Inbox (proposed)?
