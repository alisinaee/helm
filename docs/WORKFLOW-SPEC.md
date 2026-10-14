# Workflow map section (Opus WP46, 2026-10-14)

**Why it's missing (4 lines)**
1. We chose to cut it. In WP26, `docs/UI-SPEC.md` §2 says "the swimlane timeline moves to LATER to fund the limits work", and §5 LATER lists "agents swimlane timeline and handoff arrows" and "task dependencies".
2. The data couldn't support it either. jobs.json keeps only 30 finished jobs (`KEEP_FINISHED = 30`). Tasks have no time stamps for status changes and no `after`. Activity lines are `{id, at, src, op, sum≤60}` with no task or job id.
3. Putting limits first was right, because they were the bigger risk and the 800k budget was fixed.
4. How we did it was wrong. The cut went in as "Default with no decision needed" (§6), but you had asked for this feature, so it should have been one of your decisions. Below is the cheap way to bring it back.

---

## 1. The visual: the Workflow section

**Navigation:** a new `SECTIONS` entry `{id:"workflow", label:"Workflow", module:"./views/workflow.js"}` placed after Agents, with routes `#/p/<id>/workflow` and `#/all/workflow`.

**Primary layout: a swimlane timeline.** A segmented control switches between **Timeline | Map | Table**, and the choice is saved in the URL (`?v=map`).

**Lanes**
- Per project: one lane per role. The head (Opus) comes first, then worker lanes grouped by model (sonnet, haiku, agy, other), at most 6. Then a "Queue" lane and a "Blocked" lane.
- Global view: one lane per project (at most 8). Same bars, coloured by status.

**Bars**
- One bar per job, from `started` to `ended`. A running job's bar ends at now and has a pulsing edge.
- Colour by status using existing tokens only: done = `--success`, doing = `--accent`, blocked = `--danger` (hatched), queued = `--unknown` (dashed, placed after the now-line).
- Label: task id plus title, cut short to fit the bar.

**Task nodes**
- A diamond at the time a task moved to done, doing or blocked. This uses the new `at` field (see section 2).

**Edges (SVG paths with an arrowhead marker)**
- Handoff: parent job → child job, drawn from the parent bar's position at the child's start time to the child bar's start. Solid line.
- Dependency: `after` task → task. Dotted line, drawn in Map view only, to avoid spaghetti.
- Blocker: issue (`kind=blocker`, `open`) → blocked task. Red line drawn into the Blocked lane.

**Map view (secondary)**
- Columns are phases (in order). Each column holds task cards with a status dot and a "running job" chip.
- Edges show `after` dependencies and blockers.
- Layout is deterministic: column = phase, row = array order. There is no force layout.

**Range control:** 2 h | Today | Week | All, with ticks to match. The now-line is a vertical `--accent` rule.

**Hover and focus**
- Each bar has an SVG `<title>`, which gives a native tooltip with no script.
- Focus or hover also fills a fixed detail strip under the chart. Its columns are: Status | Job | Task | Model/role | Start | Duration→ | Tokens K→ | [Action].
- Click opens the existing right panel on its Details tab.

**Fixed columns (rule 0)**
- The lane label column is fixed on the left.
- A fixed right gutter shows each lane's job count and tokens K, right-aligned with tabular numbers.
- In Table view the action button always sits in the last column.

**Legend:** a single row (status swatches plus the 3 edge styles), reusing the existing `legend.js` pattern.

**Empty state:** "No jobs recorded yet. Agents record work with `roadmap job start`." plus a link to the Agents section.

**Mobile (under 768 px):** Table view is the default. Timeline scrolls sideways with sticky lane labels. Map stacks the phases vertically.

**Accessibility**
- Each bar is a `<g tabindex="0" role="button">` with an `aria-label` such as "Job J41 haiku worker, task P2.3, done, 14:02–14:20, 38k tokens".
- Left and right arrows move within a lane, up and down move between lanes, and Enter opens Details.
- The Table view shows the same data and is a real `<table>`.
- No inline `style=` or `on*=`: geometry goes in SVG attributes (x, y, width), which the CSP test allows, and colour goes in classes.

## 2. The data

**What exists today**
- jobs: `id, title, model, task, parent, role, status, started, ended, tokensK, note` (`start_job(..., parent, role)` already exists).
- issues: `tasks[], kind, status`.
- Also: questions (with `block`), queue (≤50), and the snapshot keys `jobs, queue, issues, phases, tasks, activity(15)`.

**What is missing**
- Job history beyond 30.
- Task status time stamps.
- `after`.
- Any id on activity lines (we don't need it: `at` covers status history more cheaply).

**Smallest additive backend change (tasks.json stays at schemaVersion 1)**
1. jobs.py: raise `KEEP_FINISHED` from 30 to 200 (about 40 KB on disk).
2. A task gains `at:{doing,done,blocked}` (ISO times, newest only). The task status op stamps it. Missing keys are fine.
3. A task gains `after:[≤5 ids]`, validated: the ids must exist, there can be no cycle, and no self-reference. CLI: `task set P2.4 --after P2.2,P2.3`.
4. The snapshot gains `workflow: {spans:[[id,task,model,role,parent,startEpoch,endEpoch|null,status,tokensK]...≤200], edges:{after:[[from,to]], block:[[issue,task]]}}`. It is built in `build_snapshot`, the arrays are compact (about 16 KB or less), and the server drops anything older than 7 days.

**Handoffs at almost no cost for Haiku agents**
- `job start` reads `ROADMAP_PARENT_JOB` from the environment when `--parent` is not given.
- If `role=worker` is set and exactly one head job is running, it becomes the parent automatically.
- The head exports `ROADMAP_PARENT_JOB=J12` once, so workers type nothing extra.
- Auto-recording from hooks comes later (hooks.py is currently being edited by someone else).

## 3. Interactions (no drag)

- Click a job bar → Details shows Stop (the existing stop command) when the job is running, and Open task otherwise.
- Click a task node or card → Details shows Start (an existing start request) when the task is todo and its phase is approved. It shows Approve phase if the phase is not approved.
- Click a blocker edge or the issue chip → opens the issue.
- In Table view the action column has the same Stop or Start button, one per row.

## 4. Packages (about 255k tokens in total)

**Ownership right now**
- WP36 owns `web/**`.
- The working tree also has uncommitted edits in `roadmap/cli.py` and `roadmap/services/hooks.py`. W1 must not touch hooks.py, and should add its one line to cli.py only after the owner of those edits commits.
- `web/css` already totals 52,585 bytes against `CSS_TOTAL_MAX` 52,224. It is over budget by 361 bytes now, probably because of WP36 work in progress, so WP36 has to close that gap itself.

**WP-W1: backend snapshot plus dependencies (Haiku, about 75k, Python only, can start now alongside WP36)**
- Files:
  - `roadmap/services/jobs.py`: `KEEP_FINISHED`, and the environment/auto parent in `_clean_parent`.
  - The task status op in `roadmap/services/commands.py`: the `at` stamp and `after` with validation.
  - The `schema.py` task fields.
  - `roadmap/core/snapshot.py`: the `workflow` key plus the 7-day and 200-span caps.
  - One `--after` flag in `roadmap/cli.py`.
  - A new `tests/test_workflow_data.py`.
- Acceptance:
  1. Old tasks.json loads and is byte-identical after a read.
  2. `task set --after` rejects cycles and unknown ids with the usage exit code.
  3. A status change stamps `at.<status>`.
  4. The snapshot's `workflow` key has 200 spans or fewer and is 20 KB or less with 250 jobs as a fixture.
  5. `job start` with `ROADMAP_PARENT_JOB` set records the parent.
  6. The full test suite is green.

**WP-W0: CSS trim (Haiku, about 25k, after WP36 merges, before W2)**
- Removes dead selectors from `components.css` (20.9 KB, the largest file): grep each selector against `web/js` and keep a list of what was removed.
- Merges duplicate status and colour rules into the token classes.
- Goal: free at least 2.5 KB, then put whatever was freed into `map.css`. This is not enough alone (see decision 3).

**WP-W2: the view (Haiku, about 115k, after WP36 and W1)**
- Files:
  - `web/js/views/workflow.js`, written as pure functions: `layout(snap, range, now) → model`, `timelineSvg(model)`, `mapSvg(model)`, `tableHtml(model)`, `bind(el)`.
  - `web/css/map.css` (4.5 KB or less).
  - `routes.js` (the section entry), `state.js` (`VIEW_SECTIONS`), the `index.html` stylesheet link, the `i-workflow` icon (staying within the 5 KB icons cap), and the global route that fetches each project's snapshot (8 or fewer).
- Acceptance:
  1. A new `tests/web/test_workflow.py` passes, checking: no inline style or handlers, the CSS budget test, pure-function snapshots for empty, running and blocked fixtures, every bar having an `aria-label`, and the table row count matching the bar count.
  2. Clicking a bar opens Details with Stop.
  3. At 375 px wide the default view is Table.

**WP-W3: review (Sonnet, about 40k)**
- Reviews the diff, runs a browser check at desktop and mobile widths, and confirms the CSP and budget tests pass.

**Order:** W1 runs in parallel with WP36. Then W0, then W2, then W3.

**CSS plan:** `map.css` 4.5 KB or less, made entirely of classes on existing tokens. That needs about 4.9 KB of headroom (4.5 KB plus the current 361-byte overage). W0 frees about 2.5 KB, so the rest needs decision 3.

## 5. Your three decisions

1. **What should the lanes be: role/model or phases?** I recommend role/model, which is the agents view you asked for. Phases are already shown in Map view and on the Roadmap.
2. **Should we add task dependencies (`after`) now?** I recommend yes. The change is small, it is validated, and it is the only way to get real dependency arrows.
3. **CSS budget: raise the cap to 56 KB, or trim more?** I recommend: W0 trims what it can, and we raise `CSS_TOTAL_MAX` to 56 KB to cover the remainder, with a hard limit of 4.5 KB on `map.css`. The alternative is to drop the Roadmap's token-proportional Timeline styles in `plan.css`, because Workflow covers the same need.

### Critical files for implementation
- `/Users/ali/Works/roadmap-board/roadmap/core/snapshot.py`
- `/Users/ali/Works/roadmap-board/roadmap/services/jobs.py`
- `/Users/ali/Works/roadmap-board/roadmap/services/commands.py`
- `/Users/ali/Works/roadmap-board/web/js/routes.js` (plus the new `web/js/views/workflow.js` and `web/css/map.css`)
- `/Users/ali/Works/roadmap-board/tests/web/test_shell.py` (`CSS_TOTAL_MAX`)