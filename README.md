# roadmap-board

roadmap-board is a live dashboard and job tracker for projects that you build with Claude Code.
It reads each project's `docs/tasks.json`, shows the phases and the tasks left, and lists the jobs Claude is running now.
It also shows your plan usage and your token limits, with rules that agents follow.
The page is served on your Mac only, at `http://127.0.0.1:8780/`, and nothing leaves the machine except the usage check and the phone tunnel, which you start yourself.
You use it as a GUI, and AI agents use the same data through the `roadmap` command, where every command takes `--json`.
It is Python 3.9 or newer with the standard library only: nothing to pip install, no build step.

## Install

You need a Mac, Python 3.9 or newer (`python3 --version`), and Git.

```sh
git clone <this repo> ~/Works/roadmap-board
cd ~/Works/roadmap-board
make check                               # lint and unit tests; it must pass before you use it
bin/roadmap service install              # the background agent that serves the page on 127.0.0.1:8780
mkdir -p ~/.local/bin
ln -s "$PWD/bin/roadmap" ~/.local/bin/roadmap
```

Put `~/.local/bin` on your `PATH` if it is not there yet (add `export PATH="$HOME/.local/bin:$PATH"` to
`~/.zshrc`). Then check the install with `roadmap version` and `roadmap doctor`. `roadmap doctor` lists each check
as `ok`, `warn` or `fail`, with the fix for each problem, and it is safe to run at any time.
Keep the clone where it is: the launchd agent and the hooks in your projects point at this folder.

## Quick start

Run `roadmap init` in your project folder (registers it, installs the hooks, starts the service; safe to repeat), then start Claude Code and run `/head`. `--no-service` skips the service.

## First run

1. Register your project. A project is any folder with a `docs/` folder inside it:
   `roadmap project init <project-path>` and `roadmap project add <project-path> --name "My App"`.
2. Install the hooks, so Claude Code records jobs for you: `roadmap hooks install my-app`.
3. Open the dashboard: `roadmap open`, or go to `http://127.0.0.1:8780/` yourself.

The details, and a job recorded by hand, are in [Quick start with a project](#quick-start-with-a-project).

## The dashboard

The GUI has these sections, in the navigation rail: **Overview**, **Inbox**, **Roadmap**, **Work**, **Issues**,
**Agents**, **Tokens**, **Rules**, **Research**, **Activity** and **Settings**.

## Honest notes

- **Usage.** The usage collector reads the Claude Code sign-in from the keychain, which needs a Claude Code CLI login
  on this Mac for the account token. macOS asks once, and you should choose Always Allow. Without that login, enter
  the numbers yourself with `roadmap usage push` (see [Plan usage](#plan-usage)).
- **Phone access.** `roadmap phone start` needs one step from you first: the tunnel host key must be added to
  `known_hosts` by hand (see [Phone access](#phone-access)).
- **Hooks.** `roadmap hooks install` edits the project's `.claude/settings.local.json`, makes a backup first, and
  changes nothing when run again.

## Quick start with a project

A project is any folder with a `docs/` folder inside it. `project init` writes the template data files into
`docs/` and keeps any file that already exists. `project add` registers the folder under an id.

```sh
roadmap project init <project-path>
roadmap project add <project-path> --name "My App"
roadmap project check my-app
```

`<project-path>` is the folder of your project, for example `~/Works/my-app`. The id `my-app` comes from the
name. The check reads every data file and prints its schema version.

Next, install the hooks, so Claude Code records jobs for you:

```sh
roadmap hooks install my-app
```

This merges three hook entries into `<project>/.claude/settings.local.json`. A backup of the old file is made
first, and running the command again changes nothing. See [Hooks](#hooks).

Record a job by hand. The task id must exist in the project's `tasks.json`:

```sh
roadmap job start "Write the README" haiku P1.1
roadmap job done j1 "README drafted" --tokens 12
roadmap job list
```

`job start` prints the job id (`j1` in a fresh project). Use the id it printed in `job done`.
`--tokens` is in thousands of tokens.

Then start the background service and open the page:

```sh
roadmap service install
```

Open `http://127.0.0.1:8780/` in a browser tab. The page refreshes itself every 2 seconds.

### New project

For a new project, an agent follows the draft skill `docs/skill-draft/roadmap-plan-new/SKILL.md`. It reads
`roadmap agent-guide`, asks a few questions, and writes up to 6 research notes in `docs/research/`. Then it imports
the plan. Check the notes with `roadmap research check`, and the plan with `roadmap plan import` and `--dry-run`
first. To install the packaged skills, run `roadmap skills install`, which copies them into `<project>/.claude/skills`.

## Plan usage

The usage band on the page shows your weekly and five-hour plan usage, the time until each limit resets, and
when the reading was taken. It comes from the account that is signed in to Claude Code on this Mac.

**What `roadmap usage sync` does, step by step:**

1. It runs `security find-generic-password -s "Claude Code-credentials" -w`. That is the keychain item where
   Claude Code keeps its sign-in. The `security` tool is run with an argument list; no shell is involved.
2. **macOS asks once.** The first time, the Keychain shows a prompt that asks whether `security` may use this
   item. Choose **Always Allow** if you want the background service to keep the usage fresh. If you choose
   Deny, the sync fails with "keychain access denied", and nothing else changes. You can run the sync again
   later and answer the prompt then.
3. The access token from that item is kept in memory for one request. It is never printed, logged, or written
   to a file.
4. It sends one HTTPS `GET` to `api.anthropic.com` (`/api/oauth/usage`) with the token. Redirects are refused.
   No other host is contacted. This endpoint and its beta header are not a documented public API, so they can
   change. If they do, the usage reading fails with a plain reason and the last good numbers stay.
5. It keeps the five-hour and weekly percentages, their reset times, the time of the reading and the source.
   The record goes to `~/Library/Application Support/roadmap-board/usage.json`. It is then copied into the
   `usage` block of each registered project's `docs/autonomy.json`, so the work-limit rules your agents follow
   can read it there.

The background service runs step 1 to 5 every 120 seconds. After 3 failures in a row it waits 600 seconds.
A reading older than 240 seconds (twice the interval) is marked stale on the page and by `usage show`.

`roadmap doctor` checks that the keychain item exists. It does not read the secret.

To enter the numbers yourself, for example from the usage panel of the Claude app, pipe JSON into
`roadmap usage push`. The windows that you leave out keep their values:

```sh
echo '{"rateLimits":[{"kind":"seven_day","percentUsed":61,"resetsAt":"2026-10-16T07:59:00+00:00"},{"kind":"five_hour","percentUsed":13,"resetsAt":"2026-10-13T18:00:00+00:00"}]}' | roadmap usage push
```

## Hooks

`roadmap hooks install <project>` adds three entries to the project's `.claude/settings.local.json`:

| Event | Matcher | What roadmap does |
|---|---|---|
| `PreToolUse` | `Edit\|Write\|MultiEdit\|NotebookEdit\|Bash\|Agent\|Task\|WebFetch\|WebSearch` | denies the call while the project is stopped or blocked (`roadmap stop`, a limit); fails open |
| `SessionStart` | none | adds at most 3 inbox lines to the agent's context |
| `PostToolUse` | `Agent\|Task\|Bash` | starts a job when an agent, a task or a known background command starts |
| `SubagentStop` | none | closes the job of that agent |
| `Stop` | none | closes jobs whose work has finished (an agent with no output change for 3 minutes, a result file that has appeared) |

Each entry runs the absolute path of `bin/roadmap` with the word `hook`. The desktop app gives hooks a minimal
`PATH`, so the absolute path is needed. The hook never fails a tool call and prints nothing.

The job title comes from the agent's description, and the task id comes from the description or prompt. Put
the task id in the description, for example `P1.3 parser review`. Tokens are not known to hooks, so add them
with `roadmap job done <id> "<note>" --tokens <K>`.

`roadmap hooks status <project>` shows which events are installed, and `roadmap hooks uninstall <project>`
removes only roadmap's entries.

## Commands

Every command accepts `--json` and then prints `{"ok": true, "data": ...}` or
`{"ok": false, "error": {"code", "message"}}`. Exit codes are listed under [Exit codes](#exit-codes).

| Command | What it does |
|---|---|
| `roadmap version` | print the version |
| `roadmap doctor` | check the install and print a fix for each problem |
| `roadmap backup [--project ID]` | copy the data files of one or all projects into the state folder (keeps the newest 14) |
| `roadmap service install` | write the launchd agent and load it; the server starts at login |
| `roadmap service uninstall` | unload the agent and delete its plist (logs and config stay) |
| `roadmap service start\|stop\|restart` | control the loaded agent |
| `roadmap service status` | show whether the agent is loaded and answering |
| `roadmap service logs [-f]` | show the last 100 lines of `server.log`; `-f` follows it |
| `roadmap serve [--port N] [--no-usage-loop] [--no-phone]` | run the server in this terminal (Ctrl+C stops it); the service runs the same thing |
| `roadmap project init <path>` | write the template data files into `<path>/docs`, keeping existing ones |
| `roadmap project add <path> [--name N] [--data-dir D]` | register a project folder (the data folder must exist) |
| `roadmap project list` | list registered projects |
| `roadmap project show <id>` | show one project and where its files are |
| `roadmap project check [<id>]` | parse each data file and print its schema version (exit 5 if one is bad) |
| `roadmap project migrate <id>` | upgrade the data files to the current schema (backs up first) |
| `roadmap project remove <id>` | unregister a project; its files are kept |
| `roadmap job start "<title>" <model> [<task>] [--parent ID --role lead\|worker] [--project ID]` | record a running job, print its id |
| `roadmap job done\|fail <id> ["<note>"] [--tokens K]` | finish a job; `--tokens` adds to the budget once per job id |
| `roadmap job list [--project ID]` | list the jobs of a project |
| `roadmap job prune [--project ID]` | remove finished jobs beyond the newest 200 (running jobs are kept) |
| `roadmap status [--project ID]` | brief board summary: at most 8 lines, including running jobs |
| `roadmap task show <id>` | print one task as one plan line |
| `roadmap task list [--phase P] [--status todo,partial] [--needs-you] [--limit N]` | list tasks as plan lines (default 20) |
| `roadmap task done\|start\|hold <id>... [--tokens K] [--note "..."]` | change the status of one or more tasks |
| `roadmap task set [-] [--dry-run]` | bulk patch from stdin, one `ID key=value ...` line per task |
| `roadmap plan import <file\|-> [--dry-run] [--replace-phase P]` | create or update phases and tasks from plan text |
| `roadmap plan export [--phase P]` | print the plan text for a re-plan |
| `roadmap plan template` | print the plan grammar and an example |
| `roadmap plan view` | phases and their open tasks in plan order (at most 15 lines) |
| `roadmap plan move <id> --before\|--after <id>` | move a task within its phase (undoable) |
| `roadmap issue new "<title>" [--kind bug\|risk\|question\|blocker] [--sev 1-3] [--task ID]... [--note "..."]` | open an issue, print `I3 open` |
| `roadmap issue list [--all]` | list open issues (closed ones with `--all`), at most 20 lines |
| `roadmap issue show <I3>` | one issue on one line |
| `roadmap issue close <I3>` | close an issue (undoable) |
| `roadmap issue link <I3> <task>...` | link tasks to an issue (at most 5 per issue) |
| `roadmap subtask add <P2.4> "<text>"` | add a subtask (at most 12 per task) |
| `roadmap subtask done <P2.4/2>` | tick a subtask; ticking a done one is a no-op |
| `roadmap ask "<question>" [--task ID] [--opt A]... [--default A] [--block] [--timeout S]` | ask the user, print `Q3 open` |
| `roadmap ask get <Q3>` | print one line: `Q3 open` or `Q3 answered no` |
| `roadmap ask wait <Q3> [--timeout S]` | wait (checks every 5 s, at most 1800 s) and print one line |
| `roadmap ask list` | list open questions (at most 10 lines) |
| `roadmap answer <Q3> <option\|text>` | answer an open question |
| `roadmap comment <ID> "<text>"` | add a comment on a task or issue |
| `roadmap comments <ID> [--last 5]` | show the newest comments on a task or issue |
| `roadmap inbox` | queued requests, questions answered in the last 24 h, open questions (at most 6 lines) |
| `roadmap budget show [--phase P]` | spend by model and phase, and the limits (at most 8 lines) |
| `roadmap undo <A812>` | reverse one change by its activity id (once) |
| `roadmap research new <slug> "<title>"` | start research note NN (next number, template, INDEX line; at most 6 notes) |
| `roadmap research list` | print the research index |
| `roadmap research check` | check the caps (120 lines, 6 KB), the headings and any roadmap-plan block |
| `roadmap agent-guide` | print the short guide for AI agents (at most 40 lines) |
| `roadmap hooks install\|uninstall\|status <id>` | manage the Claude Code hook entries of a project |
| `roadmap hook` | the hook entry point; Claude Code runs it, you do not |
| `roadmap stop [--task ID]` | stop the project, or one task: the next gated tool call is denied |
| `roadmap resume [--project ID]` | clear the stop and the stopped tasks (refused from an agent shell) |
| `roadmap override --hours N` | let work run past a budget or weekly block for 1 to 4 hours (refused from an agent shell) |
| `roadmap limit set <pct>` | stop agents at this weekly usage percent, 1 to 100 (refused from an agent shell) |
| `roadmap limit budget project\|phase P\|model M\|task ID <K>` | set a budget in thousands of tokens; `clear` removes it; raising it is refused from an agent |
| `roadmap phase approve <P>` | mark a phase approved (refused from an agent shell) |
| `roadmap rules show [--for ID] [--model M] [--role lead\|worker]` | the rules for a worker or lead, at most 12 lines |
| `roadmap rules add <scope> <kind> "<text>" [--budget N]` | add a rule to `docs/rules.txt` (refused from an agent shell) |
| `roadmap rules rm R3` | remove a rule (refused from an agent shell) |
| `roadmap rules sync [--dry-run]` | write the all, lead and claude rules into `CLAUDE.md` between the markers, with a backup |
| `roadmap rules check` | validate `docs/rules.txt` against the caps (60 rules, 160 characters, 8 KB) |
| `roadmap usage show` | print the stored plan usage and whether it is stale |
| `roadmap usage sync` | read the plan usage now (keychain, then the Anthropic endpoint) |
| `roadmap usage push` | store plan usage from JSON on stdin |
| `roadmap feature add\|list\|show\|link\|unlink\|accept\|rm` | manage features (a feature groups tasks; only the person accepts one) |
| `roadmap watch [--project ID] [--max SECONDS]` | block until a new Start is queued or a question is answered, then print one line (default 1800 s) |
| `roadmap skills list\|install` | list the packaged skill templates, or copy them into `<project>/.claude/skills` |
| `roadmap open [--port PORT]` | open the dashboard in the browser |
| `roadmap phone start\|stop\|link\|status` | the read-only phone listener and its tunnel (see [Phone access](#phone-access)) |

`--project ID` is optional. Without it, roadmap uses `$ROADMAP_PROJECT`, and then the registered project whose
folder contains the current directory.

## Phone access

`roadmap phone start` makes a new random token (file mode 0600), starts a read-only listener on `127.0.0.1:8766`,
and opens an ssh tunnel to `localhost.run` for a public address. `roadmap phone link` prints the private link,
`roadmap phone status` shows whether the tunnel runs, and `roadmap phone stop` closes it and deletes the token.

Before the first `phone start`, add the tunnel host key once, by hand: run `ssh-keyscan localhost.run`, check the
key yourself, and append its lines to the `known_hosts` file in roadmap-board's state folder. roadmap never fetches
the key itself, and `phone start` exits 6 until the key is there. See [docs/SECURITY.md](docs/SECURITY.md).

## Troubleshooting

Run `roadmap doctor` first. Each row below is a message it can print, with the fix it gives.

| Check | Message (short) | Fix |
|---|---|---|
| Python | "is too old (3.9 or newer is needed)" | install Python 3.9 or newer, then run the check again |
| Repo path | "the roadmap package is not at ..." | run the command from the clone you installed |
| `bin/roadmap` shim | "is missing or not executable" | re-create the link from the clone's `bin/roadmap` |
| roadmap on PATH | "the roadmap command is not on PATH" (warn) | add `~/.local/bin` to `PATH` |
| Global config | the message names the file it cannot read | fix or move that file. roadmap never overwrites a file it cannot read |
| launchd plist | "not installed yet" (warn) | `roadmap service install` |
| launchd plist | "does not lint: ..." (fail) | `roadmap service install` again, which writes the plist again |
| Service loaded | "launchd does not have the job loaded" (warn) | `roadmap service start`, or `roadmap service install` if it is not installed |
| Health endpoint | "the service is loaded but no answer" (fail) | `roadmap service restart`; if it still fails, `roadmap service logs` |
| Port 8780 | "used by X (pid N), not by roadmap" (fail) | stop that process, or change `"port"` in the config and run `roadmap service restart` |
| File and folder modes | "is 0644" and similar (fail) | run the `chmod` command the message prints |
| Claude Code keychain item | "not found" (warn) | sign in to Claude Code on this Mac, then `roadmap usage sync` |
| Claude Code keychain item | "access denied or the keychain is locked" (warn) | when the prompt appears, choose Always Allow, then `roadmap usage sync` |
| Plan usage | "last read failed: ..." (warn) | `roadmap usage sync`; the message says why the read failed |
| Plan usage | "stale (last good reading N min ago)" (warn) | `roadmap usage sync`, or check the service with `roadmap service status` |
| Project files | "<file>: <reason>" (fail) | `roadmap project check <id>` lists every file; fix the one it names |
| Project files | "missing ..." (warn) | `roadmap project init <path>` |
| Project hooks | "hooks are not installed" (warn) | `roadmap hooks install <id>` |
| Project hooks | "hooks point to another copy of roadmap" (warn) | `roadmap hooks install <id>` from this clone |
| Log sizes | "over 5 MB" (warn) | `roadmap service restart`; the service trims its launchd logs at start |

If a job or a task is refused, the message names the id. `job start` with an unknown task id exits 3 and
says `task 'X' is not in tasks.json`. Add the task to the file, or leave the task argument out.

If the page shows a banner for a file, the file is the problem, not the server. Run `roadmap project check <id>`
and fix the file it names. A file written by a newer roadmap-board is never overwritten: update roadmap-board
first.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | ok |
| 1 | error (including an internal error) |
| 2 | usage: unknown command or bad arguments |
| 3 | not found (project, job, task or file) |
| 4 | conflict (port busy, already registered, job already finished, lock held) |
| 5 | invalid data file (bad JSON, or a file written by a newer roadmap-board) |
| 6 | external failure (keychain, network, launchctl) |
| 10 | `roadmap doctor` found a failed check |

## Migrating a project from tools/roadmap-web

Older projects carry a copy of the dashboard in `tools/roadmap-web/`. The copy is replaced by this command, and
the data files stay where they are.

1. Install roadmap-board as above, and run `make check`.
2. Keep `docs/tasks.json`, `docs/jobs.json` and `docs/autonomy.json` as they are. `project init` keeps them.
3. Turn `docs/roadmap.config.json` into the new format, if the project has one. The old keys map like this:

   | Old key | New key |
   |---|---|
   | `title` | `title` (same) |
   | `files.spikes` | `extras.spikes` (a file name) |
   | `files.testing` with `testing_section` | `extras.testing` = `{"file": ..., "section": ...}` |
   | `files.roadmap` with `next_heading` and `log_heading` | `extras.roadmap` = `{"file": ..., "next": ..., "log": ...}` |

   A project with none of these needs only `"schemaVersion": 1`. Keep `taskIdPattern` and `hookDetectors` if you
   changed them.
4. Register the project as in the quick start (`roadmap project init` and `roadmap project add`), then replace
   its hooks:

   ```sh
   roadmap hooks install my-app --replace-legacy
   roadmap project check my-app
   ```

   `--replace-legacy` removes only the old `jobs_auto.py` entries. It leaves every other hook alone.
5. Restart the service, then check the page: `roadmap service restart` and `roadmap doctor`.
6. When the page shows the project and the hooks work, delete `tools/roadmap-web/` from the project yourself,
   and remove the old hook lines by hand if `--replace-legacy` did not find them.

Nothing in roadmap-board deletes the old copy for you.

## Uninstall

```sh
roadmap service uninstall
roadmap hooks uninstall my-app
roadmap project remove my-app
rm ~/.local/bin/roadmap
```

`service uninstall` removes the launchd plist and unloads the agent. `hooks uninstall` removes only roadmap's
entries from the project's settings. `project remove` unregisters the folder and keeps its files.
Your project's `docs/` files are never deleted by roadmap-board.

To remove roadmap's own state, delete these folders by hand. Nothing else on your Mac is touched:

- `~/.config/roadmap-board/` (the registry and the phone token, once phone access exists)
- `~/Library/Application Support/roadmap-board/` (usage, hook state, backups)
- `~/Library/Logs/roadmap-board/` (logs)

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for `make check`, the layering rule, change fragments and the definition of
done. The design is in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). The HTTP contract is in
[docs/API.md](docs/API.md), and the threat model is in [docs/SECURITY.md](docs/SECURITY.md).

## Interactive project manager (agents and GUI)

An interactive management bridge combining a browser GUI for humans with a fast, cheap CLI for AI agents.
Both interfaces share a unified command layer where every write executes as a validated, undoable operation.
Agents receive compact text outputs without parsing JSON, minimizing token spend and latency.
Enforces oversight through live budget meters, weekly usage limits, task rules, and tool-use guard hooks.

| Command | Description |
|---|---|
| `roadmap ask [TEXT] [--task ID] [--opt A] [--default A] [--block] [--timeout S]` | Ask the user a question (`get`, `wait`, `list` for status) and optionally block or timeout. |
| `roadmap answer Q3 value` | Answer an open question with an option value or free text. |
| `roadmap inbox` | Show queued requests, recently answered questions, and open questions. |
| `roadmap issue new\|list\|show\|close\|link` | Open, list, display, close, or link issues to tasks. |
| `roadmap subtask add\|done` | Add a subtask to a task or mark an existing subtask done. |
| `roadmap comment ID text` | Add a comment of up to 280 characters to a task or issue. |
| `roadmap comments [--last N] ID` | Show the newest comments on a task or issue. |
| `roadmap budget show` | Show token spend and limits across models and phases. |
| `roadmap limit set\|rm\|show\|budget` | Set or remove limit rows, adjust weekly stop percentage, or configure token budgets. |
| `roadmap rules show\|add\|rm\|sync\|check` | View scoped rules for a task/model/role, manage rules, sync to CLAUDE.md, or validate caps. |
| `roadmap stop [--task ID]` | Stop the project or stop a specific task, blocking further agent tool calls. |
| `roadmap resume` | Clear the project stop state and all stopped tasks. |
| `roadmap override --hours N` | Temporarily allow work past a budget or weekly block for 1 to 4 hours. |

### GUI capabilities

- **Overview & Inbox:** One-click stop/resume, live budget and usage meters, active agents card, and single-click answers to agent questions.
- **Roadmap & Work:** Phase lanes with progress bars and spend, task reordering, phase approvals, and Kanban board or tree task management.
- **Task drawer:** Inspect status, manage subtasks and comments, view linked issues, and check applicable rules.
- **Issues:** Open new issues, link them to tasks, and close resolved issues with one click.
- **Tokens & Rules:** Adjust spend caps and weekly stop limits, trigger temporary overrides, and edit rules with one-click sync to `CLAUDE.md`.
