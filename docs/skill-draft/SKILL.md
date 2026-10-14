---
name: roadmap-dashboard
description: Install and run a live roadmap dashboard for a project. Use when the user asks for a roadmap or progress dashboard, a task board, a phase/progress view, a work-limit / account-usage panel, or a live view of running Claude jobs for a project (phases with expandable sub-tasks, token estimates and measured job tokens, thinking level, model, a "Running now" card, collapsible sections). Covers installing it into the project, starting it on localhost, recording jobs (by hand or by hooks), keeping usage in sync, and editing the task file.
---

<!-- DRAFT for ~/.claude/skills/roadmap-dashboard/SKILL.md. Written inside the roadmap-board repo; copy it over the
     live skill after WP14 (the cutover). Not installed by this repo. -->

# Roadmap dashboard

roadmap-board is a Python command, `roadmap`, that serves a live dashboard on `http://127.0.0.1:8765/`. It reads
each project's `docs/` folder: `tasks.json` (phases and tasks), `jobs.json` (the job registry), `autonomy.json`
(the work limit and the plan usage), and an optional `roadmap.config.json`. It shows phases with their tasks, the
jobs that are running now, the tokens used, and the plan usage. It needs only Python 3.9 or newer.

The dashboard is read-only. Only the `roadmap` commands change the job registry, the usage record and the hook
entries, and only the project's own `docs/` files and `.claude/settings.local.json` are written.

## 1. Install and check

The tool lives in its own clone, not in the project. Look for it first:

```bash
command -v roadmap && roadmap version
```

If `roadmap` is missing, the person installs it once: clone the repo, run `make check`, and link `bin/roadmap` into a
folder on `PATH` (the README in the repo has the exact steps). Do not copy any script into the project.

Then check the install and the service:

```bash
roadmap doctor
```

`doctor` prints `ok`, `warn` or `fail` for each check with a fix. Read the fixes out to the person; do not guess.
Exit code 10 means a check failed.

## 2. Register a project and run it

Once per project, from any folder:

```bash
roadmap project init <project-path>
roadmap project add <project-path> --name "<Display name>"
roadmap hooks install <project-id>
roadmap project check <project-id>
```

- `project init` writes the template files into `<project>/docs/` and keeps any file that exists. Never overwrite a
  real `docs/tasks.json` with a template. Replace the example phases and tasks with the project's real plan
  (the `roadmap-plan-new` skill).
- `project add` gives the project an id (lowercase, from the name unless `--name` is set) and registers its folder.
  Run it once; a second run says the folder is already registered.
- `hooks install` is idempotent. Run it again only after the roadmap clone has moved, or the hooks show "stale".

The service runs the server in the background (`roadmap service install`, once per Mac). Without it, run the server
in a terminal with `roadmap serve`, which stops with Ctrl+C.

Open `http://127.0.0.1:8765/` in a NEW browser tab. Never drive a tab the person already has open. If the port is
busy, `roadmap serve --port <N>` picks another, and tell the person.

Safety: the server binds `127.0.0.1` only. It has one write route, and it is only for the usage sync.

## 3. Job registry

Record each worker (a subagent, a delegated run, or a long step) when it starts and when it ends:

```bash
roadmap job start "<short title>" <haiku|sonnet|opus|cursor|agy|head> [<taskId>] --project <project-id>
roadmap job done <jobId> "<short result note>" --tokens <K> --project <project-id>
roadmap job fail <jobId> "<what went wrong>" --project <project-id>
roadmap job list --project <project-id>
roadmap job prune --project <project-id>
```

- `job start` prints the job id (`j7`). Keep it and pass it to `done` or `fail`.
- `--tokens K` is thousands of tokens the job used. Take the number from the worker's completion report. A job
  without a count shows "–".
- Pass the task id (for example `P1.2`) so the job shows under that task. The task must exist in `tasks.json`, or
  the command exits 3. The phase prefix (`P1`) gives the phase a "running" chip.
- A finished job cannot be finished again. The command refuses (exit 4) and changes nothing.
- `--project` can be left out inside the project folder, or set with `$ROADMAP_PROJECT`.
- `job prune` keeps running jobs and the newest 30 finished ones.
- A corrupt or newer `jobs.json` stops the command with exit 5. Fix or restore the file first. Never delete it to
  make the command work.

## 3b. Automatic registration with hooks (recommended)

Nothing records jobs by itself unless the hooks are installed, so a forgotten `job start` leaves the dashboard
empty. `roadmap hooks install <project-id>` adds three Claude Code hook entries to
`<project>/.claude/settings.local.json`:

- `PostToolUse` with the matcher `Agent|Task|Bash` starts a job for an Agent or Task call (title from its
  `description`, model from `model`), and for an agy or Cursor background command.
- `SubagentStop` closes the Agent job.
- `Stop` closes jobs whose output has been quiet for 3 minutes, and jobs whose result file has appeared.

The entries run the absolute path of the roadmap shim, because the desktop app gives hooks a minimal `PATH`.

- The task id is found by scanning the Agent's description and prompt for an id that exists in `tasks.json`. So
  write the id in the description, for example `P1.3 parser review`. No id means no job.
- Hooks do not know token counts. Add them with `roadmap job done <id> "<note>" --tokens <K>` when the worker reports
  them.
- Use classic settings hooks, not a plugin "mod": in the desktop Code tab, plugin hooks never ran, and classic hooks
  did.
- Test a hook by hand with a heredoc, not `echo` (`echo` escapes `\n` and breaks the JSON):

  ```bash
  roadmap hook <<'EOF'
  {"hook_event_name": "Stop", "cwd": "<project-path>"}
  EOF
  ```

  It must exit 0 and print nothing.
- `roadmap hooks status <project-id>` shows which events are installed, stale or missing.
  `roadmap hooks uninstall <project-id>` removes only roadmap's entries.

## 3c. Work limit and plan usage (docs/autonomy.json)

`docs/autonomy.json` (schema 2) has two parts:

```json
{"schemaVersion": 2,
 "limit": {"kind": "weekly", "stopAtPercent": 65, "setBy": "the person", "setOn": "2026-10-13", "note": "..."},
 "usage": {"weeklyPercent": 61, "fiveHourPercent": 13, "weeklyResetsAt": "ISO", "fiveHourResetsAt": "ISO",
           "updated": "ISO", "source": "..."}}
```

- `limit` is the person's rule for how far Claude may work alone. Change `stopAtPercent` only when the person says so,
  and tell them the new value. `roadmap project migrate <id>` keeps it.
- `usage` is written by roadmap, not by hand. It is a copy of the global `usage.json`, written into each project
  whenever usage is synced or pushed.

Plan usage comes from one of two places:

- `roadmap usage show` prints the stored reading and whether it is stale (older than twice the interval).
- `roadmap usage push` stores numbers the person gives you, for example from the usage panel of the Claude app.
  Pipe JSON in. Windows you leave out keep their values:

  ```bash
  echo '{"rateLimits":[{"kind":"seven_day","percentUsed":61,"resetsAt":"2026-10-16T07:59:00+00:00"},{"kind":"five_hour","percentUsed":13,"resetsAt":"2026-10-13T18:00:00+00:00"}]}' | roadmap usage push
  ```

- `roadmap usage sync` reads the number from the keychain and the Anthropic usage endpoint. The first time, macOS
  shows a Keychain prompt, and only the person at the Mac can answer it. Run it only when the person asks for it, and
  say so before you run it. If it fails, report the plain reason it prints.

Stop working when `weeklyPercent` reaches `stopAtPercent`. A stale or missing reading is not a reason to keep going:
say so and ask the person.

## 4. Changing tasks (use the CLI, not JSON)
Never edit `docs/tasks.json` or `docs/jobs.json` by hand. Record work with `roadmap job start "<title>" <model> <task-id>`, `roadmap job done <id> "<note>"` or
`roadmap job fail <id> "<reason>"`, and
`roadmap task done <id>`, `roadmap task start <id>` or `roadmap task hold <id>`, and bulk changes with `roadmap task set --dry-run`. Plan new work with
`roadmap plan import <file> --dry-run`. The `roadmap-update` skill (day-to-day) and `roadmap-plan-new` skill
(new projects) give the steps and the budgets.

## 5. Project settings (docs/roadmap.config.json)

Settings that belong to one project live in its own `docs/roadmap.config.json`, so they travel with its repo.
The keys:

```json
{
  "schemaVersion": 1,
  "title": "split-net",
  "taskIdPattern": "^[A-Z]+[0-9]+(\\.[0-9]+)?$",
  "hookDetectors": ["agent", "agy", "cursor"],
  "extras": {
    "spikes": "10-spike-results.md",
    "testing": {"file": "07-testing.md", "section": "7.9"},
    "roadmap": {"file": "05-roadmap.md", "next": "Next up", "log": "Progress log"}
  }
}
```

- `title`: the page heading. Defaults to the project folder name.
- `taskIdPattern`: the regex for task ids that hooks look for. Keep the default unless the project uses other ids.
- `hookDetectors`: which detectors hooks run (`agent`, `agy`, `cursor`).
- `extras`: optional Markdown files and the section they read. Only enable an extra the project really has:
  - `spikes` (a file name): a table whose header starts with `Spike` and has `Status`, rows `S1`, `S2`, ...
  - `testing` (`file` and `section`): a table with rows `RH1`, `RH2`, ... under the `section` heading; the last column
    is the status.
  - `roadmap` (`file`, `next`, `log`): `## <next>` holds a numbered list; `## <log>` holds a table whose first column
    is a `YYYY-MM-DD` date.

A missing or broken extra file is listed under `errors` and as a banner. The rest of the page still shows.

Older projects used a `files` / `testing_section` / `next_heading` / `log_heading` layout in this file. It was never
read by the server. Convert it to `extras` as shown in the README's migration section.

## 6. Pitfalls learned from real bugs

- **Never declare a JavaScript variable with the name of a helper.** A `var pct = ...` inside a render function shadows
  the `pct()` helper, and the rest of the render silently stops: sections stay empty and no error is shown. The web
  code uses `const` and `let`, and the lint rejects `var`. Name locals differently anyway.
- **Check the console and every section after a page change.** Load the page, read the console for `TypeError` or
  `ReferenceError`, and confirm every section has content. A screenshot of the top of the page is not enough.
  `data-render-error` on `#app` names a view that threw.
- **One big number per tile.** Never put a value and its total in one number ("2.6M / 11.5M"). The total goes in the
  sub-line. Narrow cards overflow otherwise.
- **Check three widths.** 375, 768 and 1280 px, with no horizontal scroll, in light and dark.
- **The web page has no inline style or script.** The Content Security Policy blocks them. Put styles in the CSS files
  and the state in data attributes.
- **Plugin mods did not run hooks in the desktop app. Classic hooks did.** Install hooks with `roadmap hooks install <project-id>`.
- **Hooks never fail a tool call**, so a hook problem shows up as a missing job, not an error. Check
  `roadmap hooks status <project-id>` and the hook log in `~/Library/Logs/roadmap-board/hooks.log`.

## 7. Migrating a project from the old tools/roadmap-web copy

Older projects have a copy of the dashboard in `tools/roadmap-web/` (`server.py`, `jobs.py`, `jobs_auto.py`,
`usage_collector.py`) and a `install.py` step. The new tool replaces all of it. The data files stay where they are.

1. Confirm `roadmap version` works. If not, the clone is not installed (section 1).
2. Keep `docs/tasks.json`, `docs/jobs.json` and `docs/autonomy.json` as they are. `roadmap project init <path>` keeps them.
3. Convert `docs/roadmap.config.json` to the `extras` layout (section 5), if the project has one.
4. Register and check:

   ```bash
   roadmap project init <project-path>
   roadmap project add <project-path> --name "<Display name>"
   roadmap hooks install <project-id> --replace-legacy
   roadmap project check <project-id>
   ```

   `--replace-legacy` removes only the old `jobs_auto.py` hook entries. Other hooks in the file are kept.
5. Restart the service with `roadmap service restart` (or `roadmap serve` in a terminal), and check the page.
6. Once the page shows the project and the hooks record jobs, the person may delete `tools/roadmap-web/` and any old
   hook lines by hand. Do not delete them for the person without asking.

## Files

- `docs/skill-draft/SKILL.md` (this file) is the draft. It replaces the old `~/.claude/skills/roadmap-dashboard/SKILL.md`
  at cutover (WP14).
- The old `scripts/install.py`, `scripts/server.py`, `scripts/jobs.py` and `scripts/jobs_auto.py` are retired. Nothing
  copies them into projects any more.
- `templates/` (the starter `tasks.json`, `jobs.json`, `autonomy.json` and `roadmap.config.json`) now live in the
  roadmap clone, under `roadmap/templates/`. `roadmap project init <path>` writes them.
