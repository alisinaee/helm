# Architecture

This file describes how roadmap-board is put together, for someone who will change it. For what the tool does
and how to run it, read the [README](../README.md). For the HTTP contract, read [API.md](API.md). For the threat
model, read [SECURITY.md](SECURITY.md).

## Shape of the system

```
 Claude Code (hooks) ──► bin/roadmap hook ──┐
 you (terminal) ───────► bin/roadmap <cmd> ─┤  CLI (argparse, --json, exit codes)
                                            ▼
                         services/  (jobs, hooks, usage, projects, launchd, doctor, loader)
                                            │
                         store/     (paths, atomic writes, locks, config, schema, backups)
                                            │
   browser ──► 127.0.0.1:8780 ──► http/ (routes, security, static) ──► services/loader ──► core/ (pure)
                                                                         │
                                                       project folder: docs/*.json, docs/*.md
```

There are three ways in: the CLI, the Claude Code hooks (which call the CLI's `hook` command), and the HTTP server
that the service runs. All three go through the same services, so a job started from a hook and a job started
from the terminal end up in the same `jobs.json`.

Data lives in two places. Each project keeps its own data in its own repo (`<project>/docs/`). roadmap-board keeps
only a global registry of project paths, plus its settings, usage and logs, in your home folder. Nothing is in a
database.

## Layers

The package is `roadmap/`. The rule is lint-enforced by `tools/lint_py.py`: a module may import only from the
layers below it.

| Layer | Holds | May import |
|---|---|---|
| `core/` | pure functions, no I/O: Markdown tables, parsers, the snapshot, extras, number formats | nothing from the project |
| `store/` | paths, atomic JSON writes, directory locks, the config registry, schema versions and migrations, backups | `core`, `errors`, `log` |
| `services/` | jobs, hooks, usage, projects, hook install, launchd, doctor, the snapshot loader | `core`, `store`, `errors`, `log` |
| `http/` | the HTTP server, the route table, the security rules, the static file allowlist | `core`, `store`, `services`, `errors`, `log` |
| `commands/` | one module per command group; each one registers its subcommands | `core`, `store`, `services`, `http`, `errors`, `log` |
| `cli.py`, `__main__.py` | argparse tree, the `--json` envelope, exit codes, dispatch | `commands`, `errors`, `log` |
| `errors.py`, `log.py` | `RoadmapError` and the exit codes; logging, rotation, redaction | nothing from the project |

Other rules, also lint-enforced:

- **Standard library only.** No third-party imports. The target is Python 3.9 (macOS `/usr/bin/python3`), so no
  `match` statements and no `X | Y` type syntax.
- **`subprocess` only in `services/`.** Commands are argument lists. `shell=True` is refused.
- **No `print` outside `commands/` and `cli.py`.** Services return data or raise `RoadmapError`.
- **Bare `except` only in the hook entry** (`commands/hook.py`), which must never fail a tool call.
- **Every module has a docstring.** Lines are at most 120 columns, LF endings, a final newline.

`cli.py` is a fixed table. A new command group is a new module in `commands/` with a `register(sub, common)`
function, and its name listed in `COMMAND_MODULES`.

## Directory layout

```
bin/roadmap                       shim: follows its own symlinks, sets PYTHONPATH to the clone, runs python3 -m roadmap
roadmap/
  __init__.py                     __version__ (the single source of the version)
  __main__.py, cli.py             entry point, argparse tree, JSON envelope, exit codes
  errors.py                       RoadmapError(code, message, exit) and the exit-code constants
  log.py                          logger setup, RotatingFileHandler for server.log, redaction filter, access line
  commands/                       backup doctor hook hooks job phone project serve service usage version
  core/                           PURE: mdtables.py parsers.py snapshot.py extras.py format.py
  store/                          paths.py atomic.py lock.py config.py schema.py migrations.py backup.py
  services/                       jobs.py hooks.py hooks_install.py projects.py usage.py launchd.py doctor.py loader.py
  http/                           server.py routes.py security.py static.py
  templates/                      tasks.json jobs.json autonomy.json roadmap.config.json plist.tmpl
web/                              index.html, css/{tokens,base,components}.css,
                                  js/{app,api,state,router,dom,format}.js, js/views/{home,topbar,usage,kpi}.js,
                                  dev/tests.html, dev/tests.js, legacy.html (old page, removed in WP8)
tests/
  unit/                           store, core, services, commands and CLI tests (fake security, fake launchctl)
  api/                            a real server on port 0 in a thread, checked against tests/api/schemas/*.json
  web/                            static checks on web/ (imports, CSP-safe markup, tokens, contrast gate)
  fixtures/splitnet/              split-net's data files, used by the golden snapshot test
  fixtures/golden_snapshot.json   the old server's output for those files, with server_time removed
tools/
  check.py                        make check: lint_py, lint_js, then unittest discover
  check_docs.py                   runs the roadmap commands the docs show (see CONTRIBUTING.md)
  lint_py.py, lint_js.py          the lint rules above, and the JavaScript rules
  contrast.py                     WCAG contrast of every text and surface pair in both themes
docs/                             ARCHITECTURE, API, SECURITY, skill-draft/SKILL.md
changes/WPn.md                    one change fragment per work package; merged into CHANGELOG.md at release
```

## Where things are on disk

`store/paths.py` is the only place that builds these paths. Setting `ROADMAP_HOME=<dir>` moves all of them under
`<dir>` (`config/`, `state/`, `logs/`), which is how the tests and `check_docs` keep the real machine untouched.
Every directory roadmap creates is mode 0700. Every file it creates is mode 0600.

| What | Default location | Holds |
|---|---|---|
| Config | `~/.config/roadmap-board/` | `config.json` (the registry, the ports, usage settings); `phone.token` once phone access exists |
| State | `~/Library/Application Support/roadmap-board/` | `usage.json`, `hooks-<project>.json` (active hook jobs), `backups/<project>/<timestamp>/`, `tunnel.pid` |
| Logs | `~/Library/Logs/roadmap-board/` | `server.log` (1 MB × 5, redacted), `hooks.log`, `launchd.out`, `launchd.err` |
| launchd plist | `~/Library/LaunchAgents/com.roadmap-board.agent.plist` | the service definition (mode 0644); `ROADMAP_LAUNCH_AGENTS` overrides the folder |
| Project data | `<project>/docs/` | `tasks.json`, `jobs.json`, `autonomy.json`, `roadmap.config.json`, and any extra Markdown files the config names |
| Project hooks | `<project>/.claude/settings.local.json` | the three roadmap hook entries, merged with the project's own entries |

The global config is `schemaVersion` 1 with `port` (8780), `phonePort` (8766), `usage` (`intervalS` 120,
`mirrorToProjects` true) and `projects` (`id`, `name`, `path`, `dataDir`, `addedAt`). Project settings do not live
there. They live in the project's own `docs/roadmap.config.json`, so they travel with its repo:

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

WP27 additions: the usage ledger is `state/ledger.json` (14 local days, at most 4 KB; a corrupt file is moved to
`ledger.json.corrupt` and started again). Global limit rows are the config key `limits` (a list). Project limit rows
are the budget key `limitRows` (a list, next to the existing `limits` object of budget caps).

`extras` lists optional Markdown files and the parser each one uses (`core/extras.py`: `spikes`, `testing`,
`roadmap`). A project with no extras has `"extras": {}`.

## Data files, schema versions and migrations

Every JSON file roadmap reads or writes has a `schemaVersion` key. A file without one counts as version 1.

| Kind | File | Current | Notes |
|---|---|---|---|
| `config` | global `config.json` | 1 | the registry |
| `usage` | state `usage.json` | 1 | the global plan-usage record |
| `hooks` | state `hooks-<project>.json` | 1 | active hook jobs for one project |
| `tasks` | `docs/tasks.json` | 1 | phases and tasks; written by you or by an agent |
| `jobs` | `docs/jobs.json` | 1 | the job registry, written only through roadmap |
| `autonomy` | `docs/autonomy.json` | 2 | `limit` (your rule) and the mirrored `usage` block |
| `roadmap_config` | `docs/roadmap.config.json` | 1 | project settings and extras |
| `issues` | `docs/issues.json` | 1 | issues; at most 200 open, closed ones beyond the newest 100 move to `issues-archive.jsonl` |
| `questions` | `docs/questions.json` | 1 | agent questions; at most 50 open, answered ones beyond the newest 50 move to `questions-archive.jsonl` |
| `comments` | `docs/comments.json` | 1 | comments per task or issue; at most 20 per target and 150 KB, older ones move to `comments-archive.jsonl` |
| `budget` | `docs/budget.json` | 1 | limits and spend per task and model; a job id is counted once (the last 500 are remembered) |
| `queue` | `docs/queue.json` | 1 | the start queue; at most 50 entries |

`docs/activity.jsonl` is not a schema kind: one JSON object per line, the newest 500 kept. The five new JSON files
are created by their first write, never by `project init`; `migrate` and `backup` cover them.

The rules, implemented in `store/schema.py` and `store/migrations.py`:

- **Reads upgrade in memory and never write.** `MIGRATIONS` is an ordered list per kind, for example
  `"autonomy": [(1, 2, fn)]`. Version 1 to 2 keeps only `limit`; the usage block moves to the global store and is
  mirrored back when mirroring is on.
- **Writes always save the newest version**, through `store/atomic.py`.
- **A file newer than the code is refused.** It gives a `newer_schema` error (exit 5 for a CLI command, an entry in
  `errors[]` for a page). It is never overwritten.
- **`roadmap project migrate <id>`** backs up every data file of the project first, then writes the upgraded
  files. It stops before any write when a file is newer than the code. It writes nothing when nothing changes.
- **Backups** keep the newest 14 per project. They run before `project migrate`, before `hooks install` changes a
  settings file, and on `roadmap backup`.

## Atomic writes and locks

- `store/atomic.write_json`: write a temp file in the same folder, `fsync` it, `os.replace` it over the target,
  `fsync` the folder, and keep the original file mode (new files get 0600). A reader never sees half a file.
- `store/lock.locked(dir)`: `flock` on the directory's file descriptor, waiting up to 10 seconds. A timeout is
  exit 4 (`locked`). The lock is the same mechanism the split-net `jobs.py` used, so old and new writers stay safe
  during a cutover.
- Every writer re-reads the file inside the lock. Job writes, the config, the usage store, the hook state and the
  mirror into `autonomy.json` all follow this order: lock, read, change, write.
- The usage store locks the state folder. The mirror locks each project's data folder.

## Services

- **`jobs.py`**: start, finish (`done` or `failed`, optional `tokensK` and note), list and prune (keeps running jobs
  and the newest 30 finished). IDs are `j1`, `j2`, ... A task argument must exist in `tasks.json`. A finished job
  cannot be finished again. A corrupt or newer `jobs.json` stops the command (exit 5) and is not overwritten.
- **`hooks.py`**: the hook driver, ported from split-net's `jobs_auto.py`. `run_hook` never raises. Detectors are a
  registry: `agent` (an Agent or Task call, closed by `SubagentStop`, or when its output has been quiet for 180 s, or
  after 2 hours), `agy` (an `agy-companion` Bash run that names a result file), `cursor` (a `cursor-review2.sh` run).
  A project picks its detectors with `hookDetectors`. Task ids are found with `taskIdPattern` and must exist in
  `tasks.json`. State is per project in `hooks-<project>.json`.
- **`hooks_install.py`**: merges our three entries into `.claude/settings.local.json`. Entries are recognised by the
  marker `roadmap hook`, so install is idempotent and writes identical bytes on a second run. Other keys and other
  hooks are kept. `--replace-legacy` removes only entries whose command contains `jobs_auto.py`. Uninstall removes
  only our entries. Status reports `installed`, `stale` (points at another copy) or `missing` per event.
- **`usage.py`**: the reading (keychain, one HTTPS request, parse), the global store, the mirror into each project's
  `autonomy.json`, `show` (with `stale` at more than twice the interval), `push` (JSON on stdin), and `run_loop`
  (waits first, then reads; 120 s between reads, 600 s after 3 failures in a row, never less than 30 s). The token
  is held in memory only. Errors carry a plain reason, never the token.
- **`projects.py`**: init (template files only where missing), add, list, show, remove, check (parses each file with
  `core.parsers`, checks schema versions and the settings of `roadmap.config.json`), migrate and backup.
- **`launchd.py`**: renders `templates/plist.tmpl`, writes it, and runs `launchctl bootstrap|bootout|kickstart|print`
  through one injectable runner. It also truncates `launchd.out` and `launchd.err` above 5 MB at serve start, and
  runs `lsof` (read-only) to name a process that holds a port.
- **`doctor.py`**: runs each check and returns rows with `ok|warn|fail`, a detail and a fix. It never reads the
  keychain secret.
- **`ledger.py`** (WP27): the usage ledger. `record_reading` adds the points since the last reading of the weekly
  window (the first reading of a day is compared with yesterday's last one; a reset adds the new value).
  `record_spend` adds a finished job's thousands of tokens to its project for the day. `rate` is points per thousand
  tokens over seven days, with no estimate under 200k tracked; `estimate` is a project's token share of the points.
  `pace_per_hour` is the slope of the last two hours of readings.
- **`limits.py`** (WP27): the limit rows. `check_spec` allows only the valid scope, window and kind combinations.
  `evaluate_rows` reads usage (fresh within 30 minutes), the ledger and the budget, and gives each row a state:
  warn at 80%, block at 100% (action block only), unknown when a value is missing or stale (never blocks). Any failure
  gives an empty list, which is ok, and is logged once a minute. `meters` and `show_lines` serve the snapshot and
  `limit show`. Stores: global config rows, project `limitRows`, and the read-through AUTO (autonomy stop) and BUD
  (project budget) rows.
- **`loader.py`**: reads a registered project's files from `<path>/<dataDir>` and gives the text of each to
  `core.snapshot`. A missing file is not an error; a file that cannot be read becomes an `errors[]` entry.

## Core: the render data, without I/O

`core/` is the part that is easy to test, and it never touches the disk or the network:

- `mdtables.py` reads Markdown tables and sections (used by the extras).
- `parsers.py` parses `tasks.json`, `jobs.json` and `autonomy.json`, and (WP20) the issues, questions, comments, budget,
  queue and activity files. Each returns `(data, errors)` and never raises. The WP20 task, phase and job keys (`subs`,
  `capK`, `approved`, `parent`, `role`) appear in the parsed output only when the file has them.
- `extras.py` parses the configured Markdown files (`spikes`, `testing`, `roadmap`).
- `snapshot.py` turns the file texts into one dict: `summary`, `overall`, `phases`, `tasks`, `jobs`, `spikes`, `rh`,
  `next`, `log`, `errors`, plus `project` and `schemaVersion`. `build_snapshot(files, config, now)` is pure. WP20 adds
  `issues`, `questions`, `comments`, `budget`, `blocked`, `needsYou`, `agents`, `control`, `queue` and `activity`; a
  project without those files gets them empty.
- `format.py` formats tokens, percentages, durations and counts, and the web's `format.js` is tested against the
  same `tests/fixtures/format_cases.json`.

The split-net fixture goes through `build_snapshot` in a golden test, and its output must equal the old server's
`/data.json` (with `server_time` removed). That is what keeps the move from the old server honest.

## HTTP

`http/server.py` binds `127.0.0.1` only, on the port from the config or `--port`. It is a `ThreadingHTTPServer`
with daemon request threads. The pieces, in the order a request passes them:

1. **Host check** (`security.host_allowed`): the `Host` header must be `127.0.0.1:<port>` or `localhost:<port>`,
   otherwise 421. This blocks DNS rebinding.
2. **Route table** (`routes.py`): a regex per path, with the allowed methods. A wrong method is 405 with an `Allow`
   header.
3. **Write guard** for `POST /api/v1/usage/sync`: `Sec-Fetch-Site: same-origin` or an `Origin` on this server, the
   `X-Roadmap-CSRF` token (per process, compared in constant time), `Content-Type: application/json`, and a body of
   at most 4096 bytes. The order is fixed: CSRF and origin, then content type, then size, then the work.
4. **Handler**: reads return JSON from `loader` and `usage`. Reads never write.
5. **Static files** (`static.py`): an allowlist built at start from `web/`. URL paths never become file paths.
6. **Headers on every reply**: the Content-Security-Policy (no inline script or style), `X-Frame-Options: DENY`,
   `nosniff`, `Referrer-Policy: no-referrer`, `Cross-Origin-Resource-Policy: same-origin`.

The snapshot has a strong `ETag` over its content with `server_time` left out, so an unchanged project answers
`304` to `If-None-Match`. The access log writes method, path without the query string, status and milliseconds.

The full route table, the error shape and the examples are in [API.md](API.md).

## Web

The page has no build step. It is native ES modules, with `index.html`, three CSS files and eight JavaScript files.

1. `app.js` starts the router and then the poll loop: the snapshot every 2 seconds, plan usage every 30 seconds, and
   both every 30 seconds while the tab is hidden.
2. `api.js` fetches JSON. It keeps the last body per URL and sends `If-None-Match`, so a `304` reuses it. It sends
   the CSRF token from `<meta name="csrf">` on the one write.
3. `state.js` normalizes the snapshot into a view model and keeps the preferences (theme, minimal or expanded, per
   project) in `localStorage`. A failed storage access falls back to the defaults.
4. `views/*.js` are pure functions from view model to an HTML string. All text goes through `dom.esc`.
5. `dom.patch(sectionId, html)` writes only the sections whose HTML changed, then restores focus and the expanded
   state. `dom.applyMeters(root)` then sets bar widths from `data-pct` through the CSSOM. Inline `style=`
   attributes would break the CSP, so they are not used.
6. Each view runs in its own try/catch. A view that throws shows its section's error and sets `data-render-error`
   on `#app`, and the other sections keep working.

`web/css/tokens.css` is the only file with colour values. `tools/contrast.py` checks every text and surface pair in
both themes. `tests/web/test_assets.py` checks that every file a page refers to exists, that every `var(--x)` is
defined, that no hex colour appears outside the tokens, and that there are no inline scripts or `on*=` attributes.

## The service

`roadmap service install` writes `com.roadmap-board.agent.plist` and loads it with `launchctl bootstrap gui/<uid>`.
The agent runs `python -m roadmap serve` with `PYTHONPATH` and `WorkingDirectory` set to the clone, with
`RunAtLoad`, `KeepAlive`, `ThrottleInterval 10`, `ProcessType Interactive` and `LimitLoadToSessionType Aqua`. The
Aqua session type is what lets the Keychain prompt appear. The Python path is the one that ran the install, so
reinstall after you change Python.

`serve` binds the port (exit 4 with the holder's name if busy), starts the usage loop in a daemon thread (unless
`--no-usage-loop`), and shuts down cleanly on SIGINT or SIGTERM. The log goes to `server.log` through a rotating
handler with a redaction filter that removes `Bearer ...`, `sk-ant-...` and `k=...` values.

## Errors

`RoadmapError(code, message, exit)` is the one error type. The CLI prints its message (plain, in the `--json`
envelope when asked) and exits with `exit`. The HTTP layer maps the code to a status (`not_found` to 404,
`forbidden` to 403, and so on) and falls back to the exit code. An unexpected exception becomes `internal`,
exit 1, with no traceback in the output.

## Change history

Every work package adds one fragment in `changes/WPn.md`. The release package merges the fragments into
`CHANGELOG.md` under a version heading. Parallel workers never edit the changelog together.

## Data files added for the interactive manager

| file | location (project data dir, global state dir or global config dir) | what it holds | size caps (module constants) | written by (module) |
|---|---|---|---|---|
| `issues.json` | project data dir | open, doing, and recent closed/wontfix issues | `OPEN_CAP = 200`, `CLOSED_KEEP = 100`, `TASKS_MAX = 5` | `roadmap.services.issues` |
| `issues-archive.jsonl` | project data dir | archived closed and wontfix issues (beyond the newest `CLOSED_KEEP`) | `CLOSED_KEEP = 100` | `roadmap.services.issues` |
| `questions.json` | project data dir | agent questions asked to user (open and recent answered/defaulted) | `OPEN_CAP = 50`, `ANSWERED_KEEP = 50`, `OPT_MAX = 60` | `roadmap.services.questions` |
| `questions-archive.jsonl` | project data dir | archived answered and defaulted questions (beyond the newest `ANSWERED_KEEP`) | `ANSWERED_KEEP = 50` | `roadmap.services.questions` |
| `comments.json` | project data dir | flat comment thread per target (task or issue id) | `PER_TARGET = 20`, `FILE_MAX_BYTES = 150 * 1024`, `BY_MAX = 40` | `roadmap.services.comments` |
| `comments-archive.jsonl` | project data dir | archived older comments (per-target overflow, or the oldest when the file is over `FILE_MAX_BYTES`) | `PER_TARGET`, `FILE_MAX_BYTES` | `roadmap.services.comments` |
| `queue.json` | project data dir | start queue (`entries`): tasks waiting to be started, and stop requests (`op: "stop"`) | `CAP = 50` | `roadmap.services.queue`, `roadmap.services.commands` |
| `undo.jsonl` | project data dir | inverse of each reversible write, keyed by activity id (for `undo <A>`) | `UNDO_KEEP = 500` | `roadmap.services.commands` |
| `budget.json` | project data dir | token limits, spend per task/model, limitRows, and remembered job ids | `JOBS_KEEP = 500` | `roadmap.services.budget`, `roadmap.services.limits` |
| `activity.jsonl` | project data dir | log of write operations ({id, at, src, op, sum, undo}) | `KEEP = 500` (services/activity.py), `ACTIVITY_SUM_MAX = 60` (core/parsers.py) | `roadmap.services.activity` |
| `ledger.json` | global state dir | measured account points and project tracked tokens across 14 local days and recent readings | `DAYS_KEEP = 14`, `MAX_BYTES = 4096`, `RECENT_MAX = 36` | `roadmap.services.ledger` |
| `control-<project>.json`, `block-<project>` | global state dir | recomputed control state (stop, blocks, warnings); the `block-` file exists only while something blocks | none | `roadmap.services.control` |
| `config.json` | global config dir | global config, including the global limit rows under the "limits" key | none | `roadmap.store.config` (`update_limits`, called by `roadmap.services.limits`) |
