# WP19 v3: The bridge, an interactive GUI for people and a cheap CLI for agents

**Approach.** The GUI and the CLI are two front-ends to one command layer. Every write, from either side, is a small validated op that lands in the same small files and adds one line to an activity log. Agents never read JSON. tasks.json stays at schemaVersion 1; everything new is an added key or a new file.

## 0. Tabler: use only the parts you need?

1. A stdlib script could cut chosen selectors out of the 635 KB `tabler.css` without a build step.
2. The cut-out rules still depend on hundreds of `--tblr-*`/`--bs-*` variables and on Bootstrap's reboot, so the result would be fragile and break on every release.
3. It is not worth it. Port the ideas by hand into our own CSS, about 6 KB.
4. Borrow 5 patterns: empty state, stacked progress bar, steps/timeline, status dot plus badge, and a key–value grid.
5. Also take about 15 MIT-licensed Tabler icons as one inline SVG sprite (about 8 KB). Nothing else from Tabler.

## 1. Product (9 sections on 6 screens)

The screens are Overview, Roadmap, Work, Issues, Tokens and Rules.

- **Overall (Overview).**
  - The person sees:
    - a "Stopped / Running" banner with one button to stop or resume;
    - the Inbox: agent questions as one-click option buttons, and needs-you tasks;
    - live meters for project budget and weekly usage against `stopAtPercent`;
    - an Agents-live card;
    - open blockers and an activity feed (the last 15 log lines).
  - Agents use `roadmap status` (≤8 lines) and `roadmap inbox` (≤6 lines).
- **Planner (Roadmap).**
  - The person sees phases as lanes and tasks as cards, drawn with plain CSS grid.
  - Each lane shows its progress bar, estimated vs spent tokens, and the budget.
  - The person can move tasks with ↑/↓ buttons (or `Alt+↑/↓`) and approve a phase with one button.
  - Agents plan through research notes and `plan import/export`. They read `plan view` (≤15 lines) and work only on approved phases.
- **Progress manager.**
  - Progress shows on the Overview and Roadmap screens and as jobs in each task's drawer.
  - Agents record it with `task done|start` and `job done --tokens K`.
- **Phase / task / subtask manager (Work, Tree view).**
  - A tree of phase → task → subtask checkboxes.
  - Clicking a task opens a drawer with:
    - the task's plan line and status;
    - Start and Stop buttons and its per-task cap;
    - subtasks and comments;
    - linked issues, questions and jobs;
    - the rules that apply, including its definition of done.
  - Agents use `task list/show/set` and `subtask add/done`.
- **Tasks manager (Work, Board view).**
  - Columns Todo, Doing, Hold and Done, each card with one-click Start, Done and Hold.
  - Filters: needs-you, model, phase, blocked.
- **Issues.**
  - A list with a New-issue form, one-click close, and links to tasks.
  - An open blocker marks its task Blocked, and `next:` skips it.
  - Agents run `issue new` instead of stalling.
- **Token-usage manager (Tokens).**
  - Editable limits: project, phase, model and per-task caps, plus the weekly `stopAtPercent`.
  - Live meters: amber at 80% means warn; red at 100% means work is blocked.
  - An Override button allows 1–4 hours of work past the limit and is logged.
  - The top 5 tasks by spend and estimate vs actual.
- **Agent and subagent rules / Claude rules for the project (Rules).**
  - `docs/rules.txt` holds one rule per line, for example `R3 haiku budget 60 | Stop at 60k on one task`.
  - Scopes:
    - `all`
    - `lead`
    - `worker`
    - `haiku|sonnet|opus`
    - `phase:X`
    - `task:X` (per-task override)
    - `claude`
  - Kinds: `do`, `dont`, `budget N`, and `done` (the definition of done).
  - In the GUI the person can add or delete a rule and press "Sync to CLAUDE.md".
  - Sync writes only between the `<!-- roadmap:rules -->` markers and makes a backup first.
  - Before spawning a worker, the lead runs `rules show --for P2.4 --model haiku --role worker` (≤12 lines) and pastes it into the worker's prompt.
  - Caps: at most 60 rules, 160 characters each, 8 KB for the file.
- **Questions and comments.**
  - Questions:
    - The agent runs `ask`, with options, a default, a blocking flag and a timeout.
    - The question appears in the Inbox, and the person answers with one click.
    - The agent reads the answer with `ask get Q3`, a single line.
    - When a blocking question times out, the agent takes the default and the log says so.
  - Comments: a flat thread per task or issue, added from the CLI or the drawer.
- **Agents workflow.**
  - The Agents-live card shows one row per running job: model, role, task, elapsed time and tokens.
  - Workers are indented under their parent job, which shows handoffs, and blocked jobs carry a badge.
  - Below that, the last 10 jobs.
  - A full time-axis timeline is LATER.

## 2. Command model (the single write path)

`services/commands.py` holds a registry: `op → (argument schema, handler, inverse, who may run it)`.
- The CLI subcommands and `POST /api/v1/cmd {op, args}` both call `run(op, args, source)`.
- `source` is one of `gui`, `cli`, `agent` or `phone`.
- Each call runs in this order: lock → validate → write → recompute the control state → add a line to `docs/activity.jsonl`.
- The activity line has the form `{id:"A812", at, src, op, sum≤60 chars, undo}`. The log keeps the last 500 lines.
- The reply is `{ok, data, activity:"A812", undo:true|false}`. The GUI updates optimistically and shows an Undo toast for 5 seconds, which sends `undo {id}`.

**Ops at MVP.** Every reversible op stores its inverse for Undo.
- `task.status`
- `task.start` (queue)
- `task.stop`
- `task.cap`
- `subtask.toggle`
- `plan.move`
- `phase.approve`
- `question.answer`
- `comment.add`
- `issue.new`
- `issue.close`
- `budget.set`
- `limit.set` (sets `stopAtPercent`)
- `control.stop`
- `control.resume`
- `control.override`
- `rules.add`
- `rules.rm`
- `rules.sync` (no undo; it makes a backup instead)
- `undo`

**Agent guard.** Ops that loosen control are refused when the environment has `CLAUDECODE=1` (an agent's shell) or when `source` is `agent`. The refusal points the agent at `roadmap ask`. These ops are:
- `control.resume`
- `control.override`
- `budget.set` (raising a budget)
- `limit.set`
- `rules.*`
- `phase.approve`

## 3. Start, stop and limits

**Start.**
- **MVP: a queue.**
  - `task.start` adds `{id:"R5", task, op:"start", status:"queued", by, at}` to `docs/queue.json`. Other values for `op` are `stop` and `note`; other values for `status` are `taken`, `done` and `cancelled`.
  - The agent picks it up with `roadmap inbox` (≤6 lines: queued requests plus newly answered questions).
  - `roadmap task start P2.4` marks the matching request as taken.
  - A **SessionStart** hook adds ≤3 inbox lines to the agent's context.
  - A **Stop** hook surfaces a queued request with `decision:block` and a 1-line reason, so the agent goes on to the queued work. It fires once per request and at most 3 times per session; turn it off with `pickupOnStop:false`.
- **LATER: a launcher (opt-in).**
  - The GUI would run a configured command such as `claude -p "<prompt built from the task and rules show>"`.
  - The command is an argv list, never a shell string.
  - It would be enabled only in the config file, never through `/cmd`.
  - Limits: localhost port only, a confirm dialog where the person types the task id, one run at a time, the per-task cap passed in, the job registered as a worker, never over the phone port.
  - The risks are why it waits:
    - a browser click becomes code execution;
    - unattended permission modes;
    - runaway spend;
    - orphan processes;
    - questions about credentials and auth.

**Stop.**
- **Control state.** Every write recomputes the state of each project into `<state>/control-<project>.json`: `{stop, stopTasks[], block:{reason, scope}, overrideUntil}`.
- **Sentinel file.** A sentinel `<state>/block-<project>` exists only while something is blocked.
- **PreToolUse hook.**
  - It is newly installed, with matcher `Edit|Write|MultiEdit|NotebookEdit|Bash|Agent|Task|WebFetch|WebSearch`.
  - The shell shim first checks whether the sentinel exists. If not, it exits 0 without starting Python, so the normal case costs about 1 ms and 0 tokens.
  - When the sentinel exists, Python reads the control file and answers `permissionDecision:"deny"` with one line, for example: `roadmap: stopped by user at 14:02 (A812). Run roadmap inbox, then end your turn.`
  - Bash commands that start with `roadmap ` are always allowed, so the agent can still read its inbox and ask questions.
  - Read, Grep and Glob are never blocked.
- **Fail open.** If the file is missing or unparsable, a project is unknown, an exception is raised, or the hook runs longer than 300 ms, it exits 0 silently. Normal sessions keep working whether or not the roadmap service is running.
- **Scope.**
  - A project stop, an over-limit project budget and the weekly limit are enforced on every session in the project.
  - A task stop and per-task or phase caps are enforced only when the hook can map the session or subagent to a job for that task. Otherwise they become a queued `stop` request.

**Limits.**
- Budgets live in `budget.json`. Per-task caps live in the task's `capK` field or in `budget N` rules.
- The weekly limit uses the existing `autonomy.json` `stopAtPercent`, now enforced through the usage collector's recompute.
- Sequence: warn at 80%, block at 100%. The Override button adds `overrideUntil`.

## 3b. Data (all additive)

**Existing files gain keys:**
- **tasks.json:** a task gains `subs:[{t≤80, d}]` (at most 12, one level), `capK` and `approved` on the phase. Order is the array order, so `plan.move` needs no new field.
- **budget.json:**
  - Shape: `{limits:{project, phases{}, models{}}, spent:{"P2.4":{"sonnet":35}}}`.
  - It is fed by `job done --tokens`, exactly once per job.
- **jobs.json:** a job gains `parent` and `role`.

**New files:**
- **issues.json:**
  - Fields: `id`, `title≤120`, `kind` (bug|risk|question|blocker), `sev` 1–3, `status` (open|doing|closed|wontfix), `tasks[≤5]`, `by`, `created`, `closed`, `note≤300`.
  - At most 200 open; closed ones beyond 100 are archived.
- **questions.json:**
  - Fields: `id`, `task`, `text≤200`, `opts[≤5]`, `def`, `block`, `timeoutS`, `status` (open|answered|defaulted), `answer`, `asked`, `answered`.
  - At most 50 open.
- **comments.json:**
  - Fields: `on`, `by`, `at`, `t≤280`.
  - At most 20 per target, 150 KB for the file.
- **queue.json:** at most 50 entries. **activity.jsonl:** at most 500 lines. **rules.txt.**

Every JSON file gets its own kind in `schema.py` and is covered by backups and migrate.

## 4. CLI additions (same conventions as before)

- **Issues:** `issue new|list|show|close|link`.
- **Subtasks:** `subtask add P2.4 "<t>"`, `subtask done P2.4/2`.
- **Questions:**
  - `ask "<q>" [--task ID] [--opt A]... [--default A] [--block] [--timeout S]` prints one line, `Q3 open`.
  - `ask get Q3`.
  - `ask wait Q3` waits silently and prints one line. Its timeout is at most 1800 seconds; this is the only command allowed to wait.
  - `answer Q3 <opt>`.
- **Comments:** `comment <ID> "<t>"`, `comments <ID> [--last 5]`.
- **Inbox:** `inbox` (≤6 lines).
- **Control:** `stop [--task ID]`, `resume`, `override --hours N`.
- **Limits:** `budget set project|phase P|model M|task ID <K>`, `budget show` (≤8 lines), `limit set <pct>`.
- **Plan:** `plan view` (≤15 lines), `plan move P2.4 --before P2.2`, `phase approve P2`.
- **Rules:** `rules show|add|rm|sync|check`.
- **Undo:** `undo A812`.

`status` gains the lines `ask:`, `queue:`, `issues:`, `budget:` and `stopped:`. `hooks install` adds PreToolUse and SessionStart.

## 5. Security changes

- **Write routes.** Only `POST /api/v1/cmd` (the op allowlist plus a schema per op) and the existing `POST /api/v1/usage/sync`.
- **Guard.** Same as today: same-origin or Origin check, `X-Roadmap-CSRF` token, JSON body ≤4 KB, the lock. Plus at most 10 ops per second per process.
- **Phone port and tunnel.**
  - Read-only by default.
  - With `phoneWrites:true`, only `question.answer`, `comment.add`, `task.status`, `control.stop` and `undo` are allowed. Stopping is always safe; resuming or raising limits is not allowed there.
- **Agent shells.** Ops that loosen control are refused from agent shells (see section 2).
- **Launcher.** It does not exist at MVP. When it comes later, it needs a config-file opt-in, a localhost-only port, a typed confirmation, and runs one at a time.
- **Logged.** Every write logs time, source, op, a short summary of at most 60 characters with no free text, and the result. Hook denials are logged once per minute.

## 6. Packages (Haiku workers, with Sonnet checks on WP22 and WP23)

**Prerequisite:** WP16 is merged and frozen.

### MVP: 700k total, with no slack

**WP20 Data and snapshot (160k). Wave 1.**
- Files:
  - `store/schema.py` and `core/parsers.py`;
  - services for issues, questions, comments, budget, queue and activity;
  - subtasks, `capK` and `approved`;
  - the snapshot gains inbox, agents, meters and control;
  - templates, backup, `docs/API.md` and `docs/ARCHITECTURE.md`, tests.
- Accept: `python3 -m unittest -q`. An old project gives the old snapshot plus empty keys.

**WP21 Command layer and CLI (150k). Wave 2.**
- Files:
  - `services/commands.py` (registry, undo, activity, agent guard);
  - the CLI modules for every command in section 4;
  - `job.py` (`--tokens` feeds the budget, plus `--parent` and `--role`);
  - status lines, tests.
- Accept:
  - `ask … --block`, then `answer Q1 no`, then `ask get Q1` prints `Q1 answered no`.
  - `CLAUDECODE=1 roadmap resume` is refused.
  - `undo` reverses a `task.status` change.

**WP22 Control, hooks and rules (120k, Sonnet check required). Wave 2, in parallel with WP21.**
- Files:
  - a control recompute module plus the sentinel file;
  - `services/hooks.py`: PreToolUse, SessionStart, and Stop pickup;
  - the shim's fast path and `hooks_install.py` EVENTS;
  - `services/rules.py` and `commands/rules.py`.
- Accept:
  - Feeding a stopped project's PreToolUse JSON to `roadmap hook` gives `deny`.
  - With the sentinel absent, the hook exits in under 20 ms.
  - Corrupt control or a service that is down gives exit 0 with no output.
  - Running `rules sync` twice gives `+0`.

**WP23 The `/cmd` route and security (50k, Sonnet check required). Wave 2.**
- Files: `http/routes.py`, `http/security.py`, handlers, `docs/SECURITY.md`, tests.
- Tests cover: no CSRF token, wrong origin, more than 4 KB, an unknown op, the phone allowlist.
- Accept: those tests pass and a valid op returns 200.

**WP24 Web shell, Overview and Work (120k). Wave 3.**
- Covers: router, nav, the Inbox one-click answers, the stop banner, meters, Agents-live, the activity feed, Tree, Board, the drawer with every action, the undo toast, the keyboard map, empty states.
- Accept: the fixture project works with no console errors; CSS ≤40 KB.

**WP25 Web Roadmap, Issues, Tokens and Rules (100k). Wave 3.**
- Covers: phase lanes with ↑/↓ and Approve, the Issues form, editable budgets and limit with Override, rules add/delete and Sync.
- Accept: every op round-trips and shows in `roadmap status`.

### LATER (the overflow, said plainly)
- **Launcher (opt-in):** ~90k.
- **Agents time-axis timeline with handoff arrows:** ~60k.
- **Task dependencies (`after:[]`):** ~50k.
- **Inline editing of rules:** MVP has add and delete only.
- **Drag-and-drop:** MVP has ↑/↓ buttons only.
- **Daily digest:** `roadmap digest`.
- **Decisions log:** `roadmap decide`.
- **Cost in $:** per-model prices in the config.
- **Client-side search.**

### CUT
- Users, assignees and permissions.
- Nested comment replies, attachments, mentions.
- Sprints, calendar dates, Gantt charts.
- Custom fields, a workflow editor, email or notifications.
- Nested subtasks, issue-to-issue links.
- Chart libraries and any Tabler CSS or JS.
- Launching agents from the phone.

## 7. Risks and 5 decisions

**Risks**
- **A broken PreToolUse hook could halt every session.** Mitigated by failing open, the sentinel fast path, a 300 ms cutoff, and tests that feed corrupt input.
- **The Stop-hook pickup could loop.** Capped at once per request and 3 per session, with a switch to turn it off.
- **Agents lifting their own limits.** Prevented by the `CLAUDECODE` guard.
- **Spend counted twice.** Handled by recording once per job.
- **`/cmd` is a big target.** Mitigated by the allowlist, the schema per op, the CSRF token and the phone allowlist.
- **No slack in the MVP budget.** If WP24 or WP25 runs over, rules and issues editing fall back to "Copy command" buttons.

**Decisions you need to make**
1. **Launcher:** queue only at MVP (recommended), or build the launcher now (+90k, which pushes WP25 to LATER)?
2. **Enforcement:** should the PreToolUse hook actually deny tool calls (recommended), or only warn in `status`?
3. **Stop-hook pickup:** should a queued Start make the running agent continue automatically (recommended, capped), or only show at session start?
4. **Phone:** read-only (recommended), or allow the small write allowlist?
5. **Agent guard:** should agents be locked out of resume, override, raising limits and editing rules (recommended), or trusted with them?

### Critical Files for Implementation
- /Users/ali/Works/roadmap-board/roadmap/services/hooks.py
- /Users/ali/Works/roadmap-board/roadmap/services/hooks_install.py
- /Users/ali/Works/roadmap-board/roadmap/store/schema.py
- /Users/ali/Works/roadmap-board/roadmap/services/jobs.py
- /Users/ali/Works/roadmap-board/docs/AGENT-INTERFACE.md