# WP15: agent interface, research-first onboarding, UI kit decision

## 1. UI kit decision: keep our own design system and borrow Tabler's patterns

1. **Payload.** Our CSS is 25 KB, against Tabler's 635 KB of CSS plus 135 KB of JS. The page would get about 25 times heavier and gain nothing it lacks today (dark mode, tokens, a11y and contrast tests already pass).
2. **Token cost per edit.** Our markup is semantic (`.task-row`, `.phase`). Tabler's markup is long chains of utility classes, so each UI change makes an agent read and write about 2 to 3 times more tokens, on every future change.
3. **Rework cost.** Adopting Tabler means rewriting every template and JS render function, plus the CSP and a11y test baselines: about 150 to 250k tokens for no user-visible gain. Gentelella is worse: it needs a Vite/SCSS build step, which breaks the zero-dependency stdlib promise.
4. **CSP.** Our files have no inline code and are allowlisted. Tabler's JS (Bootstrap plugins, data-attribute behaviours) adds review surface we don't need.
5. **Borrow, don't adopt.** Copy only Tabler's *patterns* (card header and body, status badge colours, empty states, progress bar proportions) into our token CSS when a UI work package touches them. No new UI work package now.

## 2. Agent interface spec (no agent ever reads or writes tasks.json)

**General rules (every new command):**
- Plain text output by default; `--json` keeps the `{ok,data|error}` envelope.
- Errors print one line: `roadmap: <what is wrong>. next: <exact command>`. JSON adds an optional `error.next` field. This is backward compatible because it is an extra key.
- Every write takes the lock from `store/lock.locked()`, then writes through `schema.write_data("tasks")`.
- Every write sets `updated` to today's date.
- Every write recomputes the status of each *touched* phase: all done → done, any started → partial, otherwise todo. A phase marked `hold` is left alone.
- A write that would change more than 10 tasks makes a backup first.

**Commands and output budgets:**

| Command | Purpose | Output budget |
|---|---|---|
| `roadmap status [--project ID]` | brief board summary | ≤ 8 lines, ≤ 700 chars |
| `roadmap task show <id>` | one task as one plan line | 1 line |
| `roadmap task list [--phase P] [--status todo,partial] [--needs-you] [--limit N=20]` | partial read, in plan lines | ≤ 20 lines |
| `roadmap task done\|start\|hold <id>... [--tokens K] [--note "…"]` | quick status change | 1 line per id |
| `roadmap task set [-] [--dry-run]` | bulk patch from stdin | 1 summary line + ≤ 5 error lines |
| `roadmap plan import <file\|-> [--dry-run]` | create or update phases and tasks from plan text | same as `task set` |
| `roadmap plan export [--phase P]` | plan text, for a re-plan | 1 line per record |
| `roadmap plan template` | grammar plus example | ≤ 15 lines |
| `roadmap research new <slug> "<title>"` / `list` / `check` | research notes | ≤ 10 lines |
| `roadmap agent-guide` | the rules for agents without a skill | ≤ 40 lines |

### Plan text format (UTF-8, one record per line)

```
line    := phase | task | feature | link | comment | blank
phase   := "P" SP id SP status SP "|" SP name
feature := "F" SP fid SP ("-"|"hold") SP prio SP (phase|"-") SP (parentFid|"-") SP "|" SP title [SP "#" SP acceptance]
link    := "L" SP fid SP taskId (SP taskId)*      ; adds the feature to each task's feats, idempotent
task    := "T" SP id SP status SP tokensK SP model "/" thinking [SP "!"] [SP "c:" check "/" checkK] SP "|" SP title [SP "#" SP note]
comment := "#" text
id      := [A-Za-z0-9]+ ("." [0-9]+)?      ; task id must start with "<phase>."
status  := todo|partial|done|hold|-
model   := haiku|sonnet|opus|-     thinking := low|medium|high|-
tokensK := integer|-               "!" = needsUser true (absent = false on create, unchanged on update)
check   := none|sonnet|opus        "-" = keep the current value (update) / use the default (create)
```

Defaults on create: status todo, check none, checkK 0. Each task belongs to the phase named in its id prefix.

Example (6 lines that create a phase and 5 tasks):

```
P M1 todo | Foundations
T M1.1 todo 20 haiku/low | Scaffold repo, CI and lint
T M1.2 todo 40 sonnet/medium c:sonnet/8 | Data model and storage layer
T M1.3 todo 5 haiku/low ! | Create hosting account and API key # needs your login
T M1.4 todo 80 opus/high c:opus/15 | Sync engine design and spike
T M1.5 todo 10 haiku/low | README quick start
```

Import also accepts a Markdown file. It reads only the first fenced block tagged `roadmap-plan`, so a research note can carry its own plan.

### Bulk update syntax (`roadmap task set`, stdin, one task per line)

```
P2.4 status=done tokensK=35 note="wired; tests green"
P2.5 status=partial
V.3 needsUser=false
```

- Allowed keys are the task fields only. Values are parsed against the same enums as the plan format.
- `note=` with an empty value clears the note.

### Status output example

```
split-net  updated 2026-10-12  236 tasks: 120 done, 9 partial, 80 todo, 27 hold
left 89 (~2.9M tok)  needs-you 6  running 1
P1 Engine 72% | P2 macOS MVP 40% | P3 Full UI 0% | V Validation 10%
next: P2.4 sonnet 40k Rule engine wiring
next: P2.5 haiku 15k Rules file reload
you: V.1 Test on a real VPN; V.3 Approve helper install
run: j12 sonnet P2.4 14m
```

### Idempotency and validation

- Import and set **upsert by id**. Running the same input twice prints `0 changed` and does no write.
- Nothing is deleted. Only `plan import --replace-phase P` may remove the tasks of P that are missing from the input, and it lists them on dry run first.
- Validation is all-or-nothing:
  - every line is validated before any write;
  - on error nothing is written, and the output is the first 5 errors, each as `line N: <problem> (allowed: …)`;
  - the last line is `next: fix the file, then roadmap plan import <file> --dry-run`.
- `--dry-run` prints `would: +P1 +T5 ~T2 =T3 (no write)`, plus up to 10 `~` field diffs (`P2.4 status partial→done`).
- Unknown id in `task set` or `task done`: `roadmap: no task P9.9. next: roadmap task list --phase P9`.

### Copy references (R7.12)

The Copy button on each row and section puts a board ref and a one-line state on the clipboard. The person pastes it into an agent chat:

```
rb:roadmap-board/task/R3.2
task "Planner filters" status=doing feature=F7 orphan=no subs=2/5
```

- Format: `rb:<project>/<kind>/<id>` (kinds: phase, task, sub, feature, issue, question, job, research, section, view). A project ref is `rb:<project>`. Regex: `^rb:[a-z0-9-]+(/[a-z]+/[A-Za-z0-9._-]+)?$`.
- `roadmap ref <ref> [--json]` is read only. Plain output is `key: value` lines, at most 10, ending with `next: <full command>`. `--json` prints the same as one object under `data`.
- Exit codes: 0 found; 2 (usage) a malformed ref or an id the project does not have (`roadmap: unknown ref: ...`); 3 (not found) no registered project with that slug (`next: roadmap project list`).
- Output has no absolute paths. Use the `next:` line for the full record.

### Backward compatibility

- The tasks.json schema stays at v1. No migration, and no changes to the web, API or parsers.
- Writers keep unknown keys and the existing key order. New tasks get every field in the canonical order shown in the skill table.
- Writers use the same `indent=2` formatting, so git diffs stay small.
- jobs.json and the hooks are untouched.

## 3. Research-first onboarding workflow (total budget about 55k tokens)

Notes live in `docs/research/NN-<slug>.md`:
- At most 6 notes, each at most 120 lines and 6 KB. `research check` enforces this.
- `docs/research/INDEX.md` has one line per note (`NN slug — title — 1-line finding`). `research new` maintains it, and `research list` prints it.
- Each note uses the same template: `## Question`, `## Findings` (bullets), `## Decisions`, `## Sources` (URLs only).

| Step | Action | Budget |
|---|---|---|
| 0 | `roadmap agent-guide`; `roadmap project init . && roadmap project add .` | 1k |
| 1 | Ask the user at most 5 questions in one message (goal, users, platforms, deadline, hard constraints). Write `01-brief`. | 3k |
| 2 | Domain and similar products: at most 5 web searches and 3 page fetches. Write `02-landscape` (competitors, the features they have, what to copy or avoid). Use sonnet if web search is available, otherwise haiku. | 20k |
| 3 | Constraints and risks (technical, legal or platform, cost), each with a mitigation that becomes a task or a `!` item. Write `03-risks`. | 8k |
| 4 | Work breakdown: phases → tasks, each 5 to 150k tokens (estimating rule from the skill), model and thinking per task, `!` wherever the user must act, `c:` for risky tasks. Write `04-plan` with a `roadmap-plan` block. | 12k |
| 5 | `roadmap research check`, then `roadmap plan import docs/research/04-plan.md --dry-run`. Fix the reported lines and rerun until clean. Then import without `--dry-run`. | 3k |
| 6 | `roadmap status`. Show the user the output plus the `you:` items and ask for approval. Changes go through `task set`. | 2k |

Re-planning later uses `roadmap plan export --phase P`, an edit to a few lines, then `plan import --dry-run` and the real import. The whole file is never read.

## 4. Skills and agent-guide

**Skill A: `roadmap-update`** (≤ 60 lines; ≤ 3k tokens per workflow)
- *Trigger:* "Use when you finish, start or block a task in a project that has a roadmap dashboard, or the user asks for roadmap status or progress. Never open docs/tasks.json."
- Outline:
  1. Rule: never read or edit tasks.json or jobs.json.
  2. See the board: `roadmap status`.
  3. Find work: `roadmap task list --status todo --limit 10`.
  4. Record a job: `job start "<title>" <model> <task>` … `job done <id> "<note>" --tokens K`.
  5. Change tasks: `task done <id> --tokens K` / `task set` with a 2-line example.
  6. Errors: run the `next:` command printed, nothing else.
  7. Token estimate rule (3 lines).
  8. Budget table: status 0.5k, update 1k, bulk update 2k.

**Skill B: `roadmap-plan-new`** (≤ 90 lines; ≤ 55k tokens total)
- *Trigger:* "Use when the user starts a new project or asks to create or redo a roadmap, plan or task breakdown for a project. Research first, then fill the dashboard."
- Outline:
  1. The 7 steps of section 3, each with its exact commands and budget.
  2. The note template.
  3. The plan grammar (copied from `plan template`) plus the 6-line example.
  4. Model choice: haiku for mechanical work, sonnet for multi-file work, opus for design or security.
  5. `!` rules: accounts, secrets, payments, hardware, approvals.
  6. Stop conditions: a budget is exceeded, or a question needs the user.

**Existing `docs/skill-draft/SKILL.md`:** keep install, service and hooks. Replace section 4 with 6 lines that point to `roadmap-update` and the CLI.

**`roadmap agent-guide`** prints static text from `roadmap/core/guide.py`, at most 40 lines:
- the rules: no JSON edits, the `next:` convention, dry-run first;
- the 8 most-used commands;
- the plan grammar plus 3 example lines;
- the research layout;
- the token estimate rule.

A unit test asserts it is ≤ 40 lines and that every command it names parses.

## 5. Work packages

### WP16: task, plan and status CLI and formats (2 Haiku jobs; about 90k total; check: sonnet, 15k)

**WP16.1** (haiku, 45k): pure format and service layer.
- New `roadmap/core/planfmt.py`:
  - `parse_plan(text) -> (records, errors)`;
  - `format_task(t)`, `format_phase(p)`;
  - `extract_block(md)`, which takes the first fenced block tagged `roadmap-plan`;
  - `parse_set_line(line)`, which handles `key=value` and quoted values.
- New `roadmap/services/tasks.py`:
  - `load(data_dir)`, `query(...)`, `apply(data_dir, records, dry_run, replace_phase=None) -> diff`;
  - `summary(data_dir, jobs) -> lines`;
  - phase status recompute.
  - It uses `store.lock.locked`, `store.schema.read_data/write_data("tasks")`, the backup service and `jobs.resolve_project`.
- `roadmap/errors.py`: add an optional `next` argument to `RoadmapError` (default None).
- New tests: `tests/unit/test_planfmt.py` and `tests/unit/test_tasks_service.py`. They cover the grammar, `-` keep semantics, idempotency (second apply changes 0), all-or-nothing validation, key-order preservation and no schema bump.

**WP16.2** (haiku, 45k): commands.
- New `roadmap/commands/task.py`, `plan.py` and `status.py`, following the `job.py` pattern (`_project_option`, plain text unless `--json`).
- `roadmap/cli.py`: add 3 names to `COMMAND_MODULES`, and make `_fail` print `. next: …` and set `error.next` when present.
- README command table: 8 rows.
- New test: `tests/unit/test_task_cmds.py`. It checks output line budgets and the error `next:` lines.

**Acceptance:**
```
make test
P=$TMPDIR/rb16; roadmap project init $P && roadmap project add $P --name rb16
printf '<the 6-line example>\n' | roadmap plan import - --project rb16 --dry-run   # "would: +P1 +T5", no write
… same without --dry-run; run again → "0 changed"
echo 'M1.1 status=done tokensK=18' | roadmap task set - --project rb16
roadmap status --project rb16 | wc -l        # ≤ 8
roadmap task set - <<<'M9.1 status=done'     # exit 3, prints next:
cd ~/Works/split_net && roadmap status && git diff --stat docs/tasks.json   # no diff from reads
```

**Do NOT touch:** `roadmap/http/`, `web/`, `roadmap/core/parsers.py`, `store/schema.py` versions, `migrations.py`, the jobs.json format, hooks, or split_net's tasks.json (except a manual check).

### WP17: skills, research onboarding and agent-guide (1 Haiku job, 40k; check: sonnet, 8k)

- New `roadmap/commands/research.py`:
  - `new <slug> "<title>"`: next NN, template, adds an INDEX line, refuses beyond 6 notes;
  - `list`;
  - `check`: caps of 120 lines and 6 KB, the required headings, a valid `roadmap-plan` block via `planfmt`.
- New `roadmap/templates/research_note.md`.
- New `roadmap/core/guide.py` and `roadmap/commands/agent_guide.py`, registered as `agent-guide`. Add both modules to `COMMAND_MODULES`.
- New skills: `docs/skill-draft/roadmap-update/SKILL.md` (≤ 60 lines) and `docs/skill-draft/roadmap-plan-new/SKILL.md` (≤ 90 lines), with the outlines from section 4.
- `docs/skill-draft/SKILL.md`: replace section 4 as described in section 4.
- README: add the command rows and a short "New project" subsection (≤ 10 lines).
- Tests: `tests/unit/test_research_cmd.py` and `tests/unit/test_agent_guide.py`. They check that guide output is ≤ 40 lines and that the commands named in the guide and skills parse with `build_parser()`.

**Acceptance:**
```
make test
roadmap agent-guide | wc -l     # ≤ 40
roadmap research new landscape "Similar products" --project rb16
roadmap research check
wc -l docs/skill-draft/*/SKILL.md   # ≤ 60 and ≤ 90
```
Dry run of the skill: a Haiku session given only `roadmap-plan-new` and the prompt "new project: a habit tracker" builds a plan that imports cleanly in ≤ 55k tokens.

**Do NOT touch:**
- the WP16 modules, except to call their public functions;
- `web/` and `http/`;
- the live `~/.claude/skills`: installing the new skills is a manual cutover by the person.

No extra package is needed. The UI decision needs no work now.

### Critical Files for Implementation
- ~/Works/roadmap-board/roadmap/cli.py
- ~/Works/roadmap-board/roadmap/errors.py
- ~/Works/roadmap-board/roadmap/commands/job.py (pattern to copy)
- ~/Works/roadmap-board/roadmap/store/schema.py and ~/Works/roadmap-board/roadmap/store/lock.py
- ~/Works/roadmap-board/docs/skill-draft/SKILL.md