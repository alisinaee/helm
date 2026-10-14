# Task breakdown, agy playbook, waves, plan text (Opus WP57, 2026-10-14)

NOTE: R3 fixes are already committed (3a62e57), so WP58.1 is just a verify-and-bookkeeping step. Features service WP52 and Planner WP53, Workflow WP48 are in flight.

# WP57 plan: agy playbook, task breakdown, parallel waves and import text

The R3 fixes are still uncommitted, and they touch `cmdops.py`, `commands.py`, `limits.py`, `routes.js` and `index.html`. The head commits them first (WP58.1); every wave depends on that. The unfinished Planner, Workflow and palette files exist in the repo but have no commits yet. The snapshot does not have a `features` key yet. The `plan import` command only accepts the models haiku, sonnet and opus. Until WP58.3 adds cursor and agy, agy tasks are written as `haiku/low` with the tag `#agy` in the note.

## 1. docs/AGY-PLAYBOOK.md (content)

```
# agy playbook (Gemini 3.8 Flash, unlimited quota, weak model)
## Good at
- Reading many files and filling in a table: audits, lists, diffs between docs and code
- Writing new files from an exact example of the shape
- Prose drafts, but only when every fact comes from a facts file we give it
## Bad at
- Facts it has to work out itself: meanings, caps, folders, counts. About 30-40% are wrong.
- Anything that needs running code: tests, CLI, browser
- Edits across several files, and logic that must stay consistent between them
## Give it (8 job types)
1. Audit table (docs vs code, aria, CSP, strings, colours) -> new file under docs/reviews/agy-*.md
2. Test-gap list for one module -> table: function, missing case, expected result
3. Fixture JSON from a shape reference -> new files only
4. Doc section draft from docs/facts/FACTS.md -> one section of one doc
5. Command list vs docs diff (README, RELEASE, skills)
6. CHANGELOG bullets from the change notes plus FACTS.md
7. Docstring/comment pass on one module (comments only)
8. Plain-words rewrite of UI strings -> a proposals table, not edits
## Never give it
Running code; refactors across files; hooks, agentguard, security or limits logic; UI visuals or CSS;
anything that needs the git history; any file another worker owns.
## Prompt template (always this order)
GOAL: <one sentence>
READ ONLY THESE FILES: <list, at most 8>
FACTS FILE: docs/facts/FACTS.md (the only source for commands, caps, paths)
WRITE ONLY: <one path>  (audits: write a new results file; never edit other files)
OUTPUT FORMAT: <exact table columns, or the exact shape example>
SIZE CAP: <= N rows / <= N lines
RULES: Do not run commands. Do not guess: write UNKNOWN. Cite file:line for every claim.
ACCEPTANCE: <one checkable line, e.g. "every row cites a real file:line">
Reply DONE plus the line ranges you wrote.
## Slicing (1-8 min)
At most 8 files read and 1 file written per job; split view folders a-k / l-r / s-z.
Edits: at most 1 file and 60 changed lines. If a job times out, halve it and rerun.
## Verify (by job type)
Audits and gap lists: Haiku (5-10k tokens) greps 3 random rows; tests written from gap lists must fail before the fix.
Fixtures: Haiku (5k tokens) runs a loader test or json.tool.
Doc edits: Haiku (10-15k tokens) checks every command against check_docs.py and greps 3 claims against FACTS.md.
Comment passes: head checks that `git diff -U0` changes only comment or docstring lines, then runs make check.
Rewrite tables: the head picks which rows to keep (2k tokens); a Haiku applies them.
## Failures
'Eligibility check failed' or a network error: rerun automatically, at most 2 times (60 s wait).
403 login: stop the queue and ask the person to run `agy` and /login (the VPN must be on).
A timeout: halve the job. A wrong answer twice: give the job to Haiku.
Any change outside WRITE ONLY: `git checkout -- <path>`, then reject the job.
## Concurrency
Read-only and new-file jobs: 3 at once (AGY_MAX=3). Try 4 after a clean batch of 10.
Jobs that edit existing files: 1 at a time, or each in its own git worktree (cwd = worktree),
because the companion's change report cannot tell which of several parallel jobs made a change.
## Queue 20+ jobs
python3 tools/agy-queue.py jobs.json ~/Works/roadmap-board <results> [--after JOBID]
Use one jobs.json per wave. Ids look like a01... and the results go to <results>/<id>.md.
The head reads only the DONE lines and the verifier's verdict.
```

## 2. Task breakdown (each parent is one phase, each subtask one task)

- **WP58: agy setup and R3 closure (start here)**
  - **58.1** Head: diff the uncommitted R3 files against `R3-cmd-limits-cursor-auto.md`, run `make check`, commit. 15k.
  - **58.2** Haiku: update `tools/agy-queue.py` (split_net):
    - read AGY_MAX from the environment (default 3);
    - retry twice on Eligibility or network errors;
    - stop on 403;
    - add an `--only` option;
    - append a status line to `<results>/queue.log`.
    - 12k. Parallel with 58.3, 58.4 and 58.5.
  - **58.3** Haiku: `planfmt.py` MODELS gets cursor and agy, plus a test. 6k. Depends on 58.1.
  - **58.4** Haiku: build `docs/facts/FACTS.md` (no edits to existing files):
    - `roadmap <cmd> --help` for every command;
    - the routes table;
    - the `/cmd` ops list;
    - the caps constants (grep `_MAX`);
    - the module tree;
    - a list of the last 30 commits.
    - 15k. Depends on 58.1.
  - **58.5** Head: write `docs/AGY-PLAYBOOK.md` from section 1. 3k.
  - **58.6** agy a04: R3 check table (finding, fixed?, test name, file:line). 5 min. Haiku verifies.
  - **58.7** Haiku: regression tests for the findings 58.6 shows as unfixed. Writes only `tests/unit/test_r3_left.py`. 20k. Depends on 58.6.
- **WP59: Planner finish (WP52-56)**
  - **59.1** Haiku: finish WP52. Files: `services/features.py`, `featops.py`, `commands/feature.py`, `cli.py`, `status.py`, plus tests. Acceptance as B3. 45k. Depends on 58.1.
  - **59.2** Haiku: `plan export` writes F and L lines (WP51 gap). Files: `planfmt.py`, `services/tasks.py`. 15k. Depends on 58.3.
  - **59.3** agy a11: planner fixture `fixtures/demo/planner.json` (shape from PLANNER-SPEC section 2). 4 min.
  - **59.4** Haiku: finish WP53. Files: `planner.js`, `planner.css`, `tests/web/test_planner.py`. 30k. Depends on 59.3.
  - **59.5** Haiku: WP54 snapshot `features` key (`snapshot.py`; at most 6 KB with 60 features). 10k. Depends on 59.1.
  - **59.6** agy: test-gap list for features core, service and planfmt. 5 min. Depends on 59.1 and 59.2.
  - **59.7** Haiku: tests from 59.6 (`tests/unit/test_features_gaps.py`). 20k.
  - **59.8** Haiku: WP56 seed (import section 4, `AGENT-INTERFACE.md` grammar, 3 skill lines). 15k. Depends on 61.2.
  - **59.9** Cursor: review B3 plus V2. Depends on 61.2.
- **WP60: Workflow (WP48)**
  - **60.1** agy a10: fixtures `fixtures/demo/workflow-{empty,running,blocked}.json`. 4 min.
  - **60.2** Haiku: finish W2. Files: `workflow.js`, `map.css`, `tests/web/test_workflow.py`. 60k. Depends on 60.1.
  - **60.3** Cursor: W3 review (diff, CSP and budget tests). Depends on 61.1.
  - **60.4** Head: browser check at 1440 and 375, dark and light (6 screenshots). 10k.
- **WP61: Shell wire-up (owns `routes.js`, `state.js`, `index.html`, `icons.svg`, `details.js`; serial)**
  - **61.1** Haiku: workflow route, nav entry and icon. 12k. Depends on 60.2.
  - **61.2** Haiku: planner route plus the Work drawer feature chip. 15k. Depends on 61.1, 59.4 and 59.5.
  - **61.3** agy a06: audit of `palette.js` (are the ops in the cmdops list? combobox and listbox aria). 4 min.
  - **61.4** Haiku: palette hook-up in `keys.js` and `app.js`, plus a test. Acceptance as GAP item 8. 15k. Depends on 61.3. Parallel with 61.1.
- **WP62: WP44**
  - **62.1** Haiku: `project new --research` (`commands/project.py`, `templates/`). 10k.
  - **62.2** Haiku: `job progress --tokens` (`services/jobs.py`, `commands/job.py`; no double count). 12k.
  - **62.3** Haiku: stale-usage pill in `agents.js` and `topbar.js`, plus a test. 12k. Depends on 62.2.
- **WP63: Alignment and a11y**
  - **63.1** agy a05: row-alignment audit against UI-CHECKLIST rule 0. 6 min.
  - **63.2** Haiku: fix the 63.1 rows. Owns view files except `topbar.js`, `agents.js`, `planner.js` and `workflow.js`. 30k. Depends on 63.1 and 61.2.
  - **63.3** agy: add `aria-expanded` and `aria-controls` to `limits.js:170` and `nav.js:77` (edit job: 1 at a time). 3 min.
  - **63.4** Haiku: the same fix in `topbar.js:22`, plus `tests/web/test_aria_toggles.py` for all 3. 10k. Depends on 62.3 and 63.3.
  - **63.5** agy: aria re-audit of planner, workflow and palette. 5 min. Depends on 61.4.
  - **63.6** Haiku: fix the 63.5 rows plus `ui_smoke` at all widths. 20k.
- **WP64: Plain-words pass**
  - **64.1–64.3** agy a07, a08, a09: string tables for view files a-k, l-r and s-z. 6 min each.
  - **64.4** Head: pick the rows to keep. 3k.
  - **64.5** Haiku: apply the picked rows and update test strings. 20k. Depends on 64.4 and 63.6.
- **WP65: Test gaps**
  - **65.1–65.4** agy a01, a02, a03, a12: gap lists for `hooks.py`, `control.py`, `commands.py` plus `cmdops.py`, and `notify.py`, `watch.py` plus `skills.py`. 5 min each.
  - **65.5–65.8** Haiku: tests from each list. New files only: `test_hooks_gaps.py`, `test_control_gaps.py`, `test_commands_gaps.py`, `test_notify_watch_gaps.py`. 15–20k each. Real bugs go to issues for head triage.
- **WP66: Demo data**
  - **66.1** agy: add `features.json` plus `after`/`at` stamps to `fixtures/demo/{alpha,beta,gamma}` (new files only). 5 min.
  - **66.2** Haiku: loader test over the demo fixtures. 8k.
- **WP67: Docs refresh (after WP59–62; all edits use FACTS.md)**
  - **67.1** Haiku: regenerate FACTS.md. 8k.
  - **67.2** agy: README sections (Planner, Workflow, palette, watch/notify, skills). 6 min.
  - **67.3** agy: `docs/API.md` against the routes and ops. 5 min.
  - **67.4** agy: `docs/ARCHITECTURE.md` module section. 5 min.
  - **67.5** agy: SECURITY.md citations for feature accept, notify and watch. 5 min. Cursor also verifies this one.
  - **67.6** agy: CHANGELOG bullets. 4 min.
  - **67.7** agy: docstring pass on `features.py`, `featops.py`, `notify.py` and `watch.py` (comments only). 6 min.
  - **67.8** Haiku: verify 67.2–67.7 and fix wrong facts. 25k.
- **WP68: Cutover prep**
  - **68.1** Haiku: dry run on a copy of split-net data in a temp ROADMAP_HOME (`project add`, `doctor`, `status`, snapshot compared with the old dashboard). 25k.
  - **68.2** Haiku: on the same copy, check the files stay byte-identical after migration. 10k.
  - **68.3** agy: `RELEASE.md` against the real commands (check against FACTS.md). 4 min.
  - **68.4** Cursor: final security review of everything changed since R3 (replaces WP18). Depends on 67.8.
  - **68.5** Head plus the person: RELEASE sections 1–5 (register, hooks `--replace-legacy` in Warn mode, service, skills). Needs the person.
- **WP69: After cutover**
  - **69.1** Haiku: day-1 check (`doctor`; job counts against the old dashboard's log; no double counting). 10k.
  - **69.2** Head plus the person: Stop enforcement, then `roadmap stop` and `resume`.
  - **69.3** Haiku: retire the 8765 server and delete `legacy.html` (RELEASE section 6, its own commit). 10k.
  - **69.4** agy: audit for leftover mentions of 8765 or `legacy`. 3 min.
  - **69.5** Haiku: tag 1.0.0 after the person agrees (no push). 3k.

## 3. Waves (at most 4 agy, 6 Haiku and 1 Cursor; each file has one owner)

- **Wave 0:** the head runs 58.1 alone (it unblocks everything else).
- **Wave 1:**
  - agy: a01, a02, a03, a04 (read-only, writing to `docs/reviews/agy-*`).
  - Haiku:
    - 58.2: `agy-queue.py`
    - 58.3: `planfmt.py`
    - 58.4: `docs/facts`
    - 59.1: `services/features*`, `cli.py`, `status.py`
    - 62.1: `project.py`
    - 62.2: `jobs.py`, `job.py`
  - Cursor: idle.
  - 59.2 waits for 58.3 because both edit `planfmt.py`.
- **Wave 2:**
  - agy: a10, a11, a05, a06.
  - Haiku:
    - 59.2: `planfmt.py`, `tasks.py`
    - 60.2: workflow files
    - 61.4: `keys.js`, `app.js`
    - 58.7: new test file
    - 65.5 and 65.6: new test files
- **Wave 3:**
  - agy: a07, a08, a09, plus 63.3 (the only edit job running).
  - Haiku:
    - 59.4: planner files
    - 59.5: `snapshot.py`
    - 61.1: shell files
    - 62.3: `agents.js`, `topbar.js`
    - 65.7 and 65.8: new test files
  - Cursor: 60.3.
- **Wave 4:**
  - agy: a12, 59.6, 63.5, 66.1.
  - Haiku: 61.2, 59.7, 63.4, 66.2, 68.1, 68.2.
  - Cursor: 59.9.
- **Wave 5:**
  - Haiku: 63.2 and 63.6, then 64.5.
  - Then Haiku 59.8, followed by WP67 (6 agy jobs in two batches of 3, then Haiku 67.8).
  - Cursor: 68.4.
- **Wave 6:** 68.5 with the person, then WP69.

### First 12 agy jobs: `jobs.json`

`P` stands for the shared prompt skeleton, filled in per job:

```
GOAL: {g}
READ ONLY THESE FILES: {f}
FACTS FILE: docs/facts/FACTS.md if present
WRITE ONLY: docs/reviews/agy-{id}.md
OUTPUT FORMAT: {o}
SIZE CAP: {c}
RULES: Do not run commands. Do not edit other files. Write UNKNOWN instead of guessing. Cite file:line.
ACCEPTANCE: {a}
Reply DONE + line ranges.
```

```json
[
{"id":"a01","title":"hooks test gaps","task":"WP65.1","prompt":"P g=List untested branches of roadmap/services/hooks.py f=roadmap/services/hooks.py, tests/unit/test_hooks*.py, tests/unit/test_hook_*.py o=|function|branch file:line|missing case|expected| c=<=25 rows a=every branch cites a real line"},
{"id":"a02","title":"control test gaps","task":"WP65.2","prompt":"P g=Untested branches of control f=roadmap/services/control.py, roadmap/commands/control.py, tests/unit/test_control*.py o=same table c=<=20 a=same"},
{"id":"a03","title":"commands/cmdops gaps","task":"WP65.3","prompt":"P g=Untested ops and error paths f=roadmap/services/commands.py, cmdops.py, tests/unit/test_cmdops.py, tests/unit/test_commands_service.py, tests/api/test_cmd_route.py o=same c=<=25 a=same"},
{"id":"a04","title":"R3 fix check","task":"WP58.6","prompt":"P g=For each finding in docs/reviews/R3-cmd-limits-cursor-auto.md say fixed or not f=that review, roadmap/services/limits.py, ledger.py, cmdops.py, roadmap/http/security.py, tests/unit/test_limits_gaps.py, tests/unit/test_cmdops.py o=|finding|fixed Y/N/UNKNOWN|code file:line|test name| c=1 row per finding a=every Y cites a test"},
{"id":"a05","title":"row alignment audit","task":"WP63.1","prompt":"P g=Find rows where numbers or actions are not in fixed grid columns (rule 0) f=docs/UI-CHECKLIST.md, web/js/views/{list,board,tree,tokens,limits,agents,tasks,phases}.js, web/css/components.css o=|file:line|row|problem|class to use| c=<=30 a=each row cites a line"},
{"id":"a06","title":"palette audit","task":"WP61.3","prompt":"P g=Check that palette.js only dispatches /cmd ops that exist and has combobox/listbox aria f=web/js/views/palette.js, roadmap/services/cmdops.py, web/js/keys.js o=|file:line|issue|fix| c=<=15 a=every op name grep-able in cmdops.py"},
{"id":"a07","title":"strings a-k","task":"WP64.1","prompt":"P g=List user-visible strings that use jargon, with plain-word rewrites f=web/js/views/[a-k]*.js o=|file:line|now|plain|why| c=<=40 a=the now column is quoted exactly"},
{"id":"a08","title":"strings l-r","task":"WP64.2","prompt":"same as a07, f=web/js/views/[l-r]*.js"},
{"id":"a09","title":"strings s-z","task":"WP64.3","prompt":"same as a07, f=web/js/views/[s-z]*.js"},
{"id":"a10","title":"workflow fixtures","task":"WP60.1","prompt":"P (WRITE ONLY fixtures/demo/workflow-{empty,running,blocked}.json) g=Create 3 snapshot fixtures for the workflow key f=roadmap/core/snapshot.py lines 100-140, docs/WORKFLOW-SPEC.md section 2 o=valid JSON with exactly the shape of _workflow_view c=<=200 spans each a=json parses, keys match"},
{"id":"a11","title":"planner fixture","task":"WP59.3","prompt":"P (WRITE ONLY fixtures/demo/planner.json) g=Create a features snapshot fixture: 8 features, every state, 2 uncovered, 1 orphan f=roadmap/core/features.py, docs/PLANNER-SPEC.md section 2 o=JSON matching derive() output c=<=8 KB a=json parses"},
{"id":"a12","title":"notify/watch/skills gaps","task":"WP65.4","prompt":"P g=Untested branches f=roadmap/services/notify.py, roadmap/commands/watch.py, roadmap/commands/skills.py, tests/unit/ (only files whose names contain notify, watch or skills) o=a01 table c=<=20 a=same"}
]
```

## 4. `plan import` text

```
P WP58 todo | agy setup and R3 closure
T WP58.1 todo 15 opus/medium | Commit verified R3 fixes # head
T WP58.2 todo 12 haiku/low | agy-queue AGY_MAX, retry, 403 stop
T WP58.3 todo 6 haiku/low a:WP58.1 | plan import accepts cursor and agy models
T WP58.4 todo 15 haiku/low a:WP58.1 | docs/facts/FACTS.md
T WP58.5 todo 3 opus/low | Write AGY-PLAYBOOK.md # head
T WP58.6 todo 1 haiku/low a:WP58.1 | R3 fix check table #agy a04
T WP58.7 todo 20 haiku/low a:WP58.6 | R3 leftover regression tests
P WP59 todo | Planner finish
T WP59.1 todo 45 haiku/low a:WP58.1 | Features service, ops, CLI (WP52)
T WP59.2 todo 15 haiku/low a:WP58.3 | plan export F/L lines
T WP59.3 todo 1 haiku/low | Planner fixture #agy a11
T WP59.4 todo 30 haiku/low a:WP59.3 | Planner view finish (WP53)
T WP59.5 todo 10 haiku/low a:WP59.1 | Snapshot features key (WP54)
T WP59.6 todo 1 haiku/low a:WP59.1,WP59.2 | Features test-gap list #agy
T WP59.7 todo 20 haiku/low a:WP59.6 | Features gap tests
T WP59.8 todo 15 haiku/low a:WP61.2 | Seed 22 features (WP56)
T WP59.9 todo 1 haiku/low a:WP61.2 | Cursor review B3+V2 #cursor
P WP60 todo | Workflow view (WP48)
T WP60.1 todo 1 haiku/low | Workflow fixtures #agy a10
T WP60.2 todo 60 haiku/low a:WP60.1 | workflow.js, map.css, tests
T WP60.3 todo 1 haiku/low a:WP61.1 | Cursor review W3 #cursor
T WP60.4 todo 10 opus/low a:WP60.3 | Browser check 1440/375 # head
P WP61 todo | Shell wire-up
T WP61.1 todo 12 haiku/low a:WP60.2 | Workflow route, nav, icon
T WP61.2 todo 15 haiku/low a:WP61.1,WP59.4,WP59.5 | Planner route + drawer chip
T WP61.3 todo 1 haiku/low | Palette audit #agy a06
T WP61.4 todo 15 haiku/low a:WP61.3 | Palette hook-up keys.js/app.js
P WP62 todo | WP44
T WP62.1 todo 10 haiku/low | project new --research
T WP62.2 todo 12 haiku/low | job progress --tokens
T WP62.3 todo 12 haiku/low a:WP62.2 | Stale-usage pill
P WP63 todo | Alignment and a11y
T WP63.1 todo 1 haiku/low | Row alignment audit #agy a05
T WP63.2 todo 30 haiku/low a:WP63.1,WP61.2 | Row alignment fixes
T WP63.3 todo 1 haiku/low | aria-expanded limits.js, nav.js #agy edit
T WP63.4 todo 10 haiku/low a:WP62.3,WP63.3 | topbar aria + toggle tests
T WP63.5 todo 1 haiku/low a:WP61.4 | aria re-audit new views #agy
T WP63.6 todo 20 haiku/low a:WP63.5 | aria fixes + ui_smoke
P WP64 todo | Plain-words pass
T WP64.1 todo 1 haiku/low | Strings a-k #agy a07
T WP64.2 todo 1 haiku/low | Strings l-r #agy a08
T WP64.3 todo 1 haiku/low | Strings s-z #agy a09
T WP64.4 todo 3 opus/low a:WP64.1,WP64.2,WP64.3 | Pick rewrites # head
T WP64.5 todo 20 haiku/low a:WP64.4,WP63.6 | Apply rewrites
P WP65 todo | Test gaps
T WP65.1 todo 1 haiku/low | hooks gaps #agy a01
T WP65.2 todo 1 haiku/low | control gaps #agy a02
T WP65.3 todo 1 haiku/low | commands gaps #agy a03
T WP65.4 todo 1 haiku/low | notify/watch/skills gaps #agy a12
T WP65.5 todo 20 haiku/low a:WP65.1 | hooks gap tests
T WP65.6 todo 15 haiku/low a:WP65.2 | control gap tests
T WP65.7 todo 20 haiku/low a:WP65.3 | commands gap tests
T WP65.8 todo 15 haiku/low a:WP65.4 | notify/watch gap tests
P WP66 todo | Demo data
T WP66.1 todo 1 haiku/low a:WP59.5 | Demo features + stamps #agy
T WP66.2 todo 8 haiku/low a:WP66.1 | Demo loader test
P WP67 todo | Docs refresh
T WP67.1 todo 8 haiku/low a:WP61.2,WP62.3 | Regenerate FACTS.md
T WP67.2 todo 1 haiku/low a:WP67.1 | README sections #agy
T WP67.3 todo 1 haiku/low a:WP67.1 | API.md #agy
T WP67.4 todo 1 haiku/low a:WP67.1 | ARCHITECTURE.md #agy
T WP67.5 todo 1 haiku/low a:WP67.1 | SECURITY.md citations #agy
T WP67.6 todo 1 haiku/low a:WP67.1 | CHANGELOG bullets #agy
T WP67.7 todo 1 haiku/low a:WP67.1 | Docstring pass #agy
T WP67.8 todo 25 haiku/low a:WP67.2,WP67.3,WP67.4,WP67.5,WP67.6 | Verify docs
P WP68 todo | Cutover prep
T WP68.1 todo 25 haiku/low a:WP61.2 | Dry run on data copy
T WP68.2 todo 10 haiku/low a:WP68.1 | Byte-identical migration check
T WP68.3 todo 1 haiku/low a:WP67.1 | RELEASE.md vs CLI #agy
T WP68.4 todo 1 haiku/low a:WP67.8 | Cursor final security review #cursor
T WP68.5 todo 20 opus/medium ! a:WP68.2,WP68.4 | Cutover steps 1-5 # needs the person
P WP69 todo | After cutover
T WP69.1 todo 10 haiku/low a:WP68.5 | Day-1 checks
T WP69.2 todo 5 opus/low ! a:WP69.1 | Enforcement Stop test # needs the person
T WP69.3 todo 10 haiku/low a:WP69.2 | Retire 8765, delete legacy.html
T WP69.4 todo 1 haiku/low a:WP69.3 | Leftover 8765 audit #agy
T WP69.5 todo 3 haiku/low ! a:WP69.4 | Tag 1.0.0 # person agrees
```

Two things to check before importing:
- **Dependency limit:** a task can list at most 5 tasks in `a:`. WP67.8 lists exactly 5, so it still waits for WP67.6, but not for WP67.7. If needed, add WP67.7 to WP67.8's list after import with `task set --after`.
- **Sizes:** the agy rows show `1` in the token column as a placeholder, because agy costs no Anthropic tokens. If `plan import` rejects them, run `--dry-run` first to see.

### Critical Files for Implementation
- ~/Works/split_net/tools/agy-queue.py
- ~/Works/roadmap-board/roadmap/core/planfmt.py
- ~/Works/roadmap-board/docs/PLANNER-SPEC.md
- ~/Works/roadmap-board/docs/WORKFLOW-SPEC.md
- ~/Works/roadmap-board/docs/RELEASE.md