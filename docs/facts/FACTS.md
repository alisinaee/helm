# FACTS: roadmap-board grounding file

Generated 2026-10-14 by tools/gen_facts.py. Do not edit by hand; run `python3 tools/gen_facts.py`.
Every fact here is read from the code or the docs at generation time. Where this file and another doc disagree, the code wins.

## 1. Command help (`bin/roadmap <command> --help`)

### roadmap serve

```text
usage: roadmap serve [-h] [--json] [--port PORT] [--no-usage-loop]
                     [--no-phone]

options:
  -h, --help       show this help message and exit
  --json           print the {ok, data | error} JSON envelope on stdout
  --port PORT      listener port (default: config port, 8780)
  --no-usage-loop  do not refresh plan usage in the background
  --no-phone       do not start the read-only phone listener
```

### roadmap open

```text
usage: roadmap open [-h] [--json] [--port PORT]

options:
  -h, --help   show this help message and exit
  --json       print the {ok, data | error} JSON envelope on stdout
  --port PORT  open this port for this call only (default: config port, 8780)
```

### roadmap service

```text
usage: roadmap service [-h] [--json] ACTION ...

positional arguments:
  ACTION
    install    install the launchd agent
    uninstall  remove the launchd agent
    start      start the service
    stop       stop the service
    restart    restart the service
    status     show whether the service is loaded and answering
    logs       show the service logs

options:
  -h, --help   show this help message and exit
  --json       print the {ok, data | error} JSON envelope on stdout
```

### roadmap project

```text
usage: roadmap project [-h] [--json] ACTION ...

positional arguments:
  ACTION
    add       register a project folder
    list      list registered projects
    show      show one project
    init      write template data files into a project folder
    remove    unregister a project (files are kept)
    check     check that a project's files parse
    migrate   upgrade a project's data files (backs up first)

options:
  -h, --help  show this help message and exit
  --json      print the {ok, data | error} JSON envelope on stdout
```

### roadmap job

```text
usage: roadmap job [-h] [--json] ACTION ...

positional arguments:
  ACTION
    start     start a job
    done      mark a job done
    fail      mark a job failed
    list      list jobs
    prune     remove finished jobs beyond the newest 30

options:
  -h, --help  show this help message and exit
  --json      print the {ok, data | error} JSON envelope on stdout
```

### roadmap task

```text
usage: roadmap task [-h] [--json] ACTION ...

positional arguments:
  ACTION
    show      show one task as one plan line
    list      list tasks as plan lines
    done      mark tasks done
    start     mark tasks started (partial)
    hold      put tasks on hold
    set       bulk patch from stdin, one 'ID key=value ...' line per task

options:
  -h, --help  show this help message and exit
  --json      print the {ok, data | error} JSON envelope on stdout
```

### roadmap plan

```text
usage: roadmap plan [-h] [--json] ACTION ...

positional arguments:
  ACTION
    import    create or update phases and tasks from plan text
    export    print the plan text
    template  print the plan grammar and an example
    view      phases and their open tasks, in plan order (at most 15 lines)
    move      move a task before or after another task

options:
  -h, --help  show this help message and exit
  --json      print the {ok, data | error} JSON envelope on stdout
```

### roadmap issue

```text
usage: roadmap issue [-h] [--json] ACTION ...

positional arguments:
  ACTION
    new       open an issue
    list      list open issues
    show      show one issue on one line
    close     close an issue
    link      link tasks to an issue

options:
  -h, --help  show this help message and exit
  --json      print the {ok, data | error} JSON envelope on stdout
```

### roadmap subtask

```text
usage: roadmap subtask [-h] [--json] ACTION ...

positional arguments:
  ACTION
    add       add a subtask to a task
    done      mark a subtask done

options:
  -h, --help  show this help message and exit
  --json      print the {ok, data | error} JSON envelope on stdout
```

### roadmap ask

```text
usage: roadmap ask [-h] [--json] [--project ID] [--task ID] [--opt A]
                   [--default A] [--block] [--timeout S]
                   [TEXT ...]

positional arguments:
  TEXT          the question, or one of: get Q3 | wait Q3 | list

options:
  -h, --help    show this help message and exit
  --json        print the {ok, data | error} JSON envelope on stdout
  --project ID  project id (default: $ROADMAP_PROJECT, then the registered
                project of this folder)
  --task ID     the task the question is about
  --opt A       an answer option (repeatable)
  --default A   the answer taken on timeout
  --block       the task waits for the answer
  --timeout S   seconds until the default is taken
```

### roadmap answer

```text
usage: roadmap answer [-h] [--json] [--project ID] Q3 value [value ...]

positional arguments:
  Q3            question id
  value         one of the options, or free text when there are none

options:
  -h, --help    show this help message and exit
  --json        print the {ok, data | error} JSON envelope on stdout
  --project ID  project id (default: $ROADMAP_PROJECT, then the registered
                project of this folder)
```

### roadmap comment

```text
usage: roadmap comment [-h] [--json] [--project ID] ID text [text ...]

positional arguments:
  ID            task or issue id, for example P2.4 or I3
  text          comment text, up to 280 characters

options:
  -h, --help    show this help message and exit
  --json        print the {ok, data | error} JSON envelope on stdout
  --project ID  project id (default: $ROADMAP_PROJECT, then the registered
                project of this folder)
```

### roadmap comments

```text
usage: roadmap comments [-h] [--json] [--project ID] [--last N] ID

positional arguments:
  ID            task or issue id

options:
  -h, --help    show this help message and exit
  --json        print the {ok, data | error} JSON envelope on stdout
  --project ID  project id (default: $ROADMAP_PROJECT, then the registered
                project of this folder)
  --last N      how many of the newest comments (default 5)
```

### roadmap feature

```text
usage: roadmap feature [-h] [--json] ACTION ...

positional arguments:
  ACTION
    add       add a feature
    list      one line per feature
    show      one feature and its tasks
    link      link a feature to tasks
    unlink    unlink a feature from tasks
    accept    mark a feature accepted (the person only)
    rm        remove a feature with no tasks

options:
  -h, --help  show this help message and exit
  --json      print the {ok, data | error} JSON envelope on stdout
```

### roadmap inbox

```text
usage: roadmap inbox [-h] [--json] [--project ID]

options:
  -h, --help    show this help message and exit
  --json        print the {ok, data | error} JSON envelope on stdout
  --project ID  project id (default: $ROADMAP_PROJECT, then the registered
                project of this folder)
```

### roadmap budget

```text
usage: roadmap budget [-h] [--json] ACTION ...

positional arguments:
  ACTION
    show      show spend and limits (8 lines)

options:
  -h, --help  show this help message and exit
  --json      print the {ok, data | error} JSON envelope on stdout
```

### roadmap undo

```text
usage: roadmap undo [-h] [--json] [--project ID] A812

positional arguments:
  A812          activity id from the activity log

options:
  -h, --help    show this help message and exit
  --json        print the {ok, data | error} JSON envelope on stdout
  --project ID  project id (default: $ROADMAP_PROJECT, then the registered
                project of this folder)
```

### roadmap research

```text
usage: roadmap research [-h] [--json] ACTION ...

positional arguments:
  ACTION
    new       start a note: next number, template, and its INDEX line
    list      print the research index
    check     check the caps, the headings and any roadmap-plan block

options:
  -h, --help  show this help message and exit
  --json      print the {ok, data | error} JSON envelope on stdout
```

### roadmap agent-guide

```text
usage: roadmap agent-guide [-h] [--json]

options:
  -h, --help  show this help message and exit
  --json      print the {ok, data | error} JSON envelope on stdout
```

### roadmap status

```text
usage: roadmap status [-h] [--json] [--project ID]

options:
  -h, --help    show this help message and exit
  --json        print the {ok, data | error} JSON envelope on stdout
  --project ID  project id (default: $ROADMAP_PROJECT, then the registered
                project of this folder)
```

### roadmap hook

```text
usage: roadmap hook [-h] [--json] [gate]

positional arguments:
  gate        pre: the PreToolUse gate (set by hooks install)

options:
  -h, --help  show this help message and exit
  --json      print the {ok, data | error} JSON envelope on stdout
```

### roadmap hooks

```text
usage: roadmap hooks [-h] [--json] ACTION ...

positional arguments:
  ACTION
    install    merge the hooks into the project settings
    uninstall  remove the roadmap hook entries
    status     show which hooks are installed

options:
  -h, --help   show this help message and exit
  --json       print the {ok, data | error} JSON envelope on stdout
```

### roadmap stop

```text
usage: roadmap stop [-h] [--json] [--task ID] [--project ID]

options:
  -h, --help    show this help message and exit
  --json        print the {ok, data | error} JSON envelope on stdout
  --task ID     stop only this task
  --project ID
```

### roadmap resume

```text
usage: roadmap resume [-h] [--json] [--project ID]

options:
  -h, --help    show this help message and exit
  --json        print the {ok, data | error} JSON envelope on stdout
  --project ID
```

### roadmap override

```text
usage: roadmap override [-h] [--json] --hours N [--project ID]

options:
  -h, --help    show this help message and exit
  --json        print the {ok, data | error} JSON envelope on stdout
  --hours N
  --project ID
```

### roadmap limit

```text
usage: roadmap limit [-h] [--json] ACTION ...

positional arguments:
  ACTION
    set       set a limit row, or stopAtPercent with a bare PCT
    rm        remove a limit row by id, for example L3
    show      show the limit rows and where they stand
    budget    set a budget in thousands of tokens: project | phase P | model M
              | task ID, then K (or clear)

options:
  -h, --help  show this help message and exit
  --json      print the {ok, data | error} JSON envelope on stdout
```

### roadmap phase

```text
usage: roadmap phase [-h] [--json] ACTION ...

positional arguments:
  ACTION
    approve   mark a phase approved

options:
  -h, --help  show this help message and exit
  --json      print the {ok, data | error} JSON envelope on stdout
```

### roadmap rules

```text
usage: roadmap rules [-h] [--json] ACTION ...

positional arguments:
  ACTION
    show      the rules for a task, model and role (at most 12 lines)
    add       add a rule at the end of docs/rules.txt
    rm        remove a rule by id, for example R3
    sync      write the all, lead and claude rules into CLAUDE.md
    check     validate docs/rules.txt against the caps

options:
  -h, --help  show this help message and exit
  --json      print the {ok, data | error} JSON envelope on stdout
```

### roadmap usage

```text
usage: roadmap usage [-h] [--json] ACTION ...

positional arguments:
  ACTION
    show      show the stored usage
    sync      fetch usage now
    push      store usage from JSON on stdin

options:
  -h, --help  show this help message and exit
  --json      print the {ok, data | error} JSON envelope on stdout
```

### roadmap doctor

```text
usage: roadmap doctor [-h] [--json]

options:
  -h, --help  show this help message and exit
  --json      print the {ok, data | error} JSON envelope on stdout
```

### roadmap phone

```text
usage: roadmap phone [-h] [--json] ACTION ...

positional arguments:
  ACTION
    start     rotate the phone token and start the tunnel
    stop      stop the tunnel and delete the token
    link      print the private phone link
    status    show whether the tunnel is running

options:
  -h, --help  show this help message and exit
  --json      print the {ok, data | error} JSON envelope on stdout
```

### roadmap backup

```text
usage: roadmap backup [-h] [--json] [--project PROJECT]

options:
  -h, --help         show this help message and exit
  --json             print the {ok, data | error} JSON envelope on stdout
  --project PROJECT  project id (default: all projects)
```

### roadmap skills

```text
usage: roadmap skills [-h] [--json] ACTION ...

positional arguments:
  ACTION
    list      list the skill templates, sizes and install state
    install   copy the skills into <project>/.claude/skills

options:
  -h, --help  show this help message and exit
  --json      print the {ok, data | error} JSON envelope on stdout
```

### roadmap watch

```text
usage: roadmap watch [-h] [--json] [--project ID] [--max SECONDS]

options:
  -h, --help     show this help message and exit
  --json         print the {ok, data | error} JSON envelope on stdout
  --project ID   project id (default: $ROADMAP_PROJECT, then the registered
                 project of this folder)
  --max SECONDS  give up after this many seconds (default 1800)
```

### roadmap version

```text
usage: roadmap version [-h] [--json]

options:
  -h, --help  show this help message and exit
  --json      print the {ok, data | error} JSON envelope on stdout
```

## 2. HTTP routes (roadmap/http/routes.py)

| method | path (regex) | purpose |
|---|---|---|
| GET | `/api/v1/health` | - |
| GET | `/api/v1/meta` | - |
| GET | `/api/v1/projects` | - |
| GET | `'/api/v1/projects/(?P<pid>' + _PID + ')/snapshot'` | - |
| GET | `'/api/v1/projects/(?P<pid>' + _PID + ')/notes(?:/(?P<name>[^/]*))?'` | GET /api/v1/projects/{pid}/notes: the note list. GET .../notes/{name}: one note as plain text (UTF-8). |
| GET | `/api/v1/usage` | - |
| POST | `/api/v1/usage/sync` | - |
| POST | `/api/v1/cmd` | POST /api/v1/cmd {op, args, project?}: one registry op. Order: CSRF and origin, JSON type, body size (413), |
| GET | `/data\.json` | Deprecated alias: the first registered project's snapshot. Removed in 2.0. |

## 3. /cmd ops (roadmap/services/cmdops.py)

- `budget.set`
- `control.override`
- `control.resume`
- `control.stop`
- `limit.rm`
- `limit.set`
- `phase.approve`
- `rules.add`
- `rules.rm`
- `rules.sync`
- `task.cap`

## 4. Size and cap constants (module level, roadmap/**/*.py)

| name | file:line | value |
|---|---|---|
| `ACC_MAX` | `roadmap/core/features.py:20` | `160` |
| `ACC_MAX` | `roadmap/services/featops.py:18` | `160` |
| `ACTIVITY_SUM_MAX` | `roadmap/core/parsers.py:25` | `60` |
| `AFTER_MAX` | `roadmap/core/planfmt.py:17` | `5` |
| `AFTER_MAX` | `roadmap/core/snapshot.py:26` | `5` |
| `ANSWERED_KEEP` | `roadmap/services/questions.py:14` | `50` |
| `ANSWER_MAX` | `roadmap/commands/watch.py:19` | `60` |
| `BUDGET_MAX` | `roadmap/services/rules.py:23` | `100000` |
| `BY_MAX` | `roadmap/services/comments.py:15` | `40` |
| `CAP` | `roadmap/services/queue.py:8` | `50` |
| `CLOSED_KEEP` | `roadmap/services/issues.py:12` | `100` |
| `COMMENT_MAX` | `roadmap/core/parsers.py:24` | `280` |
| `DAYS_KEEP` | `roadmap/services/ledger.py:30` | `14` |
| `FEATS_MAX` | `roadmap/core/parsers.py:27` | `3` |
| `FEATURES_MAX` | `roadmap/core/planfmt.py:19` | `60` |
| `FEAT_ACC_MAX` | `roadmap/core/planfmt.py:21` | `160` |
| `FEAT_TITLE_MAX` | `roadmap/core/planfmt.py:20` | `80` |
| `ID_MAX` | `roadmap/services/features.py:24` | `99` |
| `JOBS_KEEP` | `roadmap/services/budget.py:14` | `500` |
| `KEEP` | `roadmap/services/activity.py:12` | `500` |
| `KEEP` | `roadmap/store/backup.py:11` | `14` |
| `KEEP_FINISHED` | `roadmap/services/jobs.py:17` | `200` |
| `LAUNCHD_LOG_LIMIT` | `roadmap/services/doctor.py:32` | `5 * 1024 * 1024` |
| `LINE_MAX` | `roadmap/services/control.py:29` | `160` |
| `LINK_MAX` | `roadmap/services/featops.py:20` | `3` |
| `LIST_MAX` | `roadmap/commands/ask.py:18` | `10` |
| `LIST_MAX` | `roadmap/commands/issue.py:8` | `20` |
| `NOTE_MAX` | `roadmap/core/parsers.py:21` | `300` |
| `OPEN_CAP` | `roadmap/services/issues.py:11` | `200` |
| `OPEN_CAP` | `roadmap/services/questions.py:13` | `50` |
| `OPTS_MAX` | `roadmap/core/parsers.py:23` | `5` |
| `OPT_MAX` | `roadmap/services/questions.py:15` | `60` |
| `PERCENT_MAX` | `roadmap/services/cmdops.py:25` | `100` |
| `PHASE_LINE_MAX` | `roadmap/services/tasks.py:23` | `160` |
| `PHONE_FAIL_LIMIT` | `roadmap/http/security.py:29` | `10` |
| `QUERY_LIMIT` | `roadmap/services/tasks.py:20` | `20` |
| `Q_TEXT_MAX` | `roadmap/core/parsers.py:22` | `200` |
| `RECENT_MAX` | `roadmap/core/snapshot.py:21` | `2` |
| `RECENT_MAX` | `roadmap/services/ledger.py:36` | `36` |
| `SHOWN_MAX` | `roadmap/commands/budget.py:11` | `8` |
| `SUBS_MAX` | `roadmap/core/parsers.py:14` | `12` |
| `SUB_TITLE_MAX` | `roadmap/core/parsers.py:15` | `80` |
| `SUMMARY_MAX` | `roadmap/services/notify.py:25` | `60` |
| `TASKS_MAX` | `roadmap/services/issues.py:13` | `5` |
| `TEXT_MAX` | `roadmap/services/notify.py:24` | `120` |
| `TITLE_MAX` | `roadmap/commands/research.py:24` | `80` |
| `TITLE_MAX` | `roadmap/core/features.py:19` | `80` |
| `TITLE_MAX` | `roadmap/core/parsers.py:20` | `120` |
| `TITLE_MAX` | `roadmap/services/featops.py:19` | `80` |
| `TITLE_MAX` | `roadmap/services/jobs.py:21` | `200` |
| `TOKENS_K_MAX` | `roadmap/services/commands.py:32` | `10000000` |
| `UNDO_KEEP` | `roadmap/services/commands.py:27` | `500` |
| `VIEW_MAX` | `roadmap/commands/plan.py:77` | `15` |
| `_KEEP` | `roadmap/core/planfmt.py:28` | `object()` |

## 5. Module tree (first docstring line of each file)

### roadmap/

- `roadmap/__init__.py`: roadmap-board: a live roadmap dashboard and job tracker for Claude Code projects.
- `roadmap/__main__.py`: Entry point for `python3 -m roadmap`.
- `roadmap/cli.py`: Command line entry point: the argparse tree, the --json envelope and the exit codes.
- `roadmap/commands/__init__.py`: Command groups. Each module here registers its own commands with the CLI.
- `roadmap/commands/agent_guide.py`: Command agent-guide: print the short guide for AI agents (roadmap.core.guide, at most 40 lines).
- `roadmap/commands/ask.py`: Questions: ask, ask get, ask wait, ask list, and answer.
- `roadmap/commands/backup.py`: Top-level command backup: copies the data files of one or all projects into the state directory.
- `roadmap/commands/budget.py`: Command budget: show the spend and the limits (budget show [--phase P], at most 8 lines).
- `roadmap/commands/comment.py`: Commands comment and comments: add a comment on a task or issue, and read the newest ones.
- `roadmap/commands/control.py`: Command group control: stop (always allowed), resume and override (refused from an agent shell).
- `roadmap/commands/doctor.py`: Top-level command doctor: runs the install checks and prints ok, warn or fail with a plain-words fix for each
- `roadmap/commands/feature.py`: Command group feature (WP52): the planner's features. add, list, show, link, unlink, accept and rm.
- `roadmap/commands/hook.py`: Top-level command hook: the stdin entry that Claude Code hooks call.
- `roadmap/commands/hooks.py`: Command group hooks: install and inspect the Claude Code hooks of a project.
- `roadmap/commands/inbox.py`: Command inbox: what needs the user or the next agent, in at most 6 lines (queued requests, answers, open questions).
- `roadmap/commands/issue.py`: Command group issue: open, list, show, close and link issues (issues.json). Writes go through the command layer.
- `roadmap/commands/job.py`: Command group job: record Claude jobs and their tokens in the project's jobs.json.
- `roadmap/commands/limits.py`: Command groups limit and phase: the limit rows that stop agents (services/limits.py, services/control.py).
- `roadmap/commands/open.py`: Top-level command open: opens the dashboard at http://127.0.0.1:<port>/ with the macOS open command (WP13).
- `roadmap/commands/phone.py`: Command group phone: start, stop, link and status for the read-only phone listener's tunnel (WP13).
- `roadmap/commands/plan.py`: Command group plan: import plan text into tasks.json, export it for a re-plan, or print the grammar (plan template).
- `roadmap/commands/project.py`: Command group project: register projects and keep their data files healthy.
- `roadmap/commands/research.py`: Command group research (WP17): numbered research notes in <data dir>/research, one INDEX line per note, and checks.
- `roadmap/commands/rules.py`: Command group rules: show, add, rm, sync and check the project rules (services/rules.py).
- `roadmap/commands/serve.py`: Top-level commands serve and open. serve runs the dashboard server on 127.0.0.1 and, unless --no-usage-loop,
- `roadmap/commands/service.py`: Command group service: the launchd lifecycle of the background server (WP11).
- `roadmap/commands/skills.py`: Command group skills: list the Haiku-sized skill templates and install them into <project>/.claude/skills.
- `roadmap/commands/status.py`: Top-level command status: the board summary of one project in at most 8 lines and 700 characters.
- `roadmap/commands/subtask.py`: Command group subtask: add a subtask to a task, and tick or untick one (P2.4/2). Writes go through the command layer.
- `roadmap/commands/task.py`: Command group task: read and change tasks in the project's tasks.json (show, list, done, start, hold, set).
- `roadmap/commands/undo.py`: Command undo: put back a change that reports undo, by its activity id (undo A812).
- `roadmap/commands/usage.py`: Command group usage: the global plan-usage store.
- `roadmap/commands/version.py`: Top-level command version: prints the package version. The one implemented command in WP1.
- `roadmap/commands/watch.py`: Command watch: block until a new Start is queued or a question is answered, then print one line.
- `roadmap/core/__init__.py`: Pure core: markdown tables, data-file parsers, extras, snapshot and number formatting. No I/O.
- `roadmap/core/extras.py`: Registry of the optional roadmap extras: spikes, testing (RH checks) and the roadmap's Next up and Progress log.
- `roadmap/core/features.py`: Planner features (docs/features.json): derive feature rows, coverage and orphan tasks.
- `roadmap/core/format.py`: Number formatting for the dashboard. Mirrors web/js/format.js; both are tested against format_cases.json.
- `roadmap/core/guide.py`: The static text of `roadmap agent-guide`: rules, the most used commands, the plan grammar, research and estimates.
- `roadmap/core/mdtables.py`: Markdown helpers for the roadmap files: table rows, table iteration, level-2 sections and status classification.
- `roadmap/core/parsers.py`: Parsers for tasks.json, jobs.json and autonomy.json.
- `roadmap/core/planfmt.py`: Plan text format for roadmap tasks and phases, and the bulk "set" line format. Pure functions, no I/O.
- `roadmap/core/snapshot.py`: Build the roadmap snapshot: the dict the dashboard renders, from the texts of a project's data files.
- `roadmap/errors.py`: Typed errors shared by the CLI and the HTTP layer, with the CLI exit codes.
- `roadmap/http/__init__.py`: The HTTP layer: the 127.0.0.1 server, the API v1 routes, the static pages and the security checks.
- `roadmap/http/routes.py`: API v1 routes: the path table, the reply helpers and one function per route.
- `roadmap/http/security.py`: Security rules for the HTTP layer as pure functions: Host and Origin checks, the CSRF check, the phone cookie, the
- `roadmap/http/server.py`: The dashboard server: ThreadingHTTPServer bound to 127.0.0.1 only, with the request handler, the access log and
- `roadmap/http/static.py`: Static pages from web/: an allowlist built once at startup. URL paths are only looked up in that map, so they
- `roadmap/log.py`: Logging for the roadmap package: the namespace, the file handler with rotation, the redaction filter and the
- `roadmap/services/__init__.py`: Service layer: jobs and hooks (WP4), usage (WP6), and later launchd, tunnel and loader.
- `roadmap/services/activity.py`: Activity log (activity.jsonl): one line per write, {id, at, src, op, sum, undo}. Keeps the newest 500 lines.
- `roadmap/services/agentguard.py`: Agent guard: ops that loosen control are refused from an agent's shell (any non-empty CLAUDECODE), or when the
- `roadmap/services/budget.py`: Budget (budget.json): limits in thousands of tokens and the spend per task and model.
- `roadmap/services/cmdops.py`: Command ops that wire the control, limit, rules and budget services into the WP21 registry (commands.OPS).
- `roadmap/services/commands.py`: Command layer (WP21): the one write path for CLI calls, and the registry behind POST /api/v1/cmd.
- `roadmap/services/comments.py`: Comments (comments.json): a flat thread per target (a task or an issue id). At most 20 per target; the older ones
- `roadmap/services/control.py`: Control state (WP22): stop, resume, override and the limits that stop the agents of a project.
- `roadmap/services/doctor.py`: The checks behind `roadmap doctor`. Each check returns a row: id, title, status (ok, warn or fail), detail, and fix
- `roadmap/services/featops.py`: Feature ops (WP52): the registry entries for the planner's features, run through commands.run like the other ops.
- `roadmap/services/features.py`: Planner features (WP52): the service behind the feature ops and the feature CLI.
- `roadmap/services/hooks.py`: Hook driver: turns Claude Code hook events into job starts and closes. Ported from split-net's jobs_auto.py.
- `roadmap/services/hooks_install.py`: Install, remove and inspect the roadmap hook entries in a project's .claude/settings.local.json (WP10).
- `roadmap/services/issues.py`: Issues (issues.json): open, close and list. At most 200 open (open or doing); closed or wontfix issues beyond the
- `roadmap/services/jobs.py`: Job registry in each project's data folder (jobs.json): start, finish, list and prune.
- `roadmap/services/launchd.py`: The launchd user agent that runs `roadmap serve`: render and write the plist, the lifecycle through launchctl,
- `roadmap/services/ledger.py`: Usage ledger (WP27): the global ledger.json of measured account points and of each project's tracked tokens.
- `roadmap/services/limits.py`: Limit rows (WP27): the rules that stop agents when a window of usage is used up. Specified in docs/UI-SPEC.md 2b.
- `roadmap/services/loader.py`: Load a registered project's data files into a snapshot, and name the process that holds a TCP port.
- `roadmap/services/notify.py`: Desktop wake-up notifications (GAP-ANALYSIS 2.1): one macOS notification through osascript when a Start is queued,
- `roadmap/services/projects.py`: Project maintenance (WP10): init templates, add, list, show, remove, check, migrate and backup.
- `roadmap/services/questions.py`: Questions (questions.json): ask, answer, expire on timeout, list. At most 50 open. Answered or defaulted questions
- `roadmap/services/queue.py`: Start queue (queue.json): tasks waiting to be started, at most 50 entries, oldest first.
- `roadmap/services/records.py`: Shared file work for the WP20 services: load a keyed JSON document at the current schema, save it atomically,
- `roadmap/services/rules.py`: Project rules (WP22): docs/rules.txt, one rule per line, shown to the lead and to workers, and synced to CLAUDE.md.
- `roadmap/services/tasks.py`: Tasks service (WP16): read, query, bulk upsert of phases and tasks from parsed plan records, and the status summary.
- `roadmap/services/tunnel.py`: The phone tunnel: rotate the phone token, start ssh to localhost.run, read the tunnel URL, keep the pid file,
- `roadmap/services/usage.py`: Account usage for the dashboard: the Anthropic usage reading, the global usage.json store, the mirror into each
- `roadmap/store/__init__.py`: Storage layer: paths, atomic JSON writes, directory locks, config, schema versions, migrations and backups.
- `roadmap/store/atomic.py`: Atomic JSON writes (temp file, fsync, replace, fsync the directory) and strict JSON reads.
- `roadmap/store/backup.py`: Timestamped copies of data files under the state directory. Keeps the newest 14 backups per project.
- `roadmap/store/config.py`: Global config.json: schema v1 with ports, usage settings and the project list. Add, list, get and remove.
- `roadmap/store/jsonl.py`: JSON-lines files (activity.jsonl and the *-archive.jsonl files): append one line, read tolerantly, keep the newest N.
- `roadmap/store/lock.py`: Exclusive directory lock: flock on an fd of the data directory itself, the same mechanism as split_net jobs.py.
- `roadmap/store/migrations.py`: Ordered migration steps per data kind. Reads upgrade in memory only; writers save the newest version.
- `roadmap/store/paths.py`: Locations of the config, state and log directories. Setting ROADMAP_HOME redirects every path under one root.
- `roadmap/store/schema.py`: Schema versions per data file kind, with the read and write rules.

### web/js/views/

- `web/js/views/activity.js`: Activity (WP30): the activity lines, newest first.
- `web/js/views/agents.js`: Agents (WP34): the running jobs as a tree (a lead job with its workers indented under it), the last 10 finished jobs, and a Stop button per row (op task.stop).
- `web/js/views/board.js`: Work, Board view (WP31), and the helpers the List and Tree views share: the project's tasks with their live status (deferred tasks are not shown), the filter...
- `web/js/views/details.js`: Details tab (WP29): the task, issue or question named by the route (#/p/<id>/<section>/i/<item>), or the project card when nothing is selected.
- `web/js/views/extras.js`: Extras: the spike board and the real-hardware board.
- `web/js/views/home.js`: Home (#/): one card per project, then Running now across projects.
- `web/js/views/inbox.js`: Inbox (WP30): the open questions as cards, one button per option (the default is highlighted), a countdown when the question has a timeout, and the task it b...
- `web/js/views/issues.js`: Issues (WP32).
- `web/js/views/kpi.js`: KpiRow: six tiles for the project view.
- `web/js/views/legend.js`: Legend: what the glyphs, chips and token figures mean.
- `web/js/views/limits.js`: Limit rows (WP33): the editor rows, the add presets and their actions.
- `web/js/views/list.js`: Work, List view (WP31): a dense table of the project's tasks with a checkbox, id, title, phase, status, model, est, spent, cap and flags.
- `web/js/views/nav.js`: Left nav (WP28): the section list with badges and the settings link at the foot.
- `web/js/views/needsyou.js`: Needs you: the open tasks whose needsUser flag is set (the same count as the summary's need_user), as task rows.
- `web/js/views/next.js`: Next up: the queued items from the roadmap, as plain text (the markdown bold and code marks are removed).
- `web/js/views/overview.js`: Overview (WP30).
- `web/js/views/palette.js`: Command palette (Cmd+K / Ctrl+K): search snapshot tasks, issues, questions and run commands.
- `web/js/views/panel.js`: Right panel (WP29): one <aside> with two tabs, Projects and Details.
- `web/js/views/phases.js`: Phases: the main column of the project view.
- `web/js/views/planner.js`: Planner (WP53).
- `web/js/views/projects.js`: Projects tab (WP29): "All projects" first, then one row per project.
- `web/js/views/recent.js`: Recent progress: the newest rows of the roadmap log.
- `web/js/views/research.js`: Research (WP34): the project's research notes (read only, from GET /api/v1/projects/{id}/notes) with a plain-text reader, and the onboarding checklist for a...
- `web/js/views/roadmap.js`: Roadmap (WP32).
- `web/js/views/rules.js`: Rules (WP33): the project's rules in tabs by scope group, a delete on each rule, an add form (scope, kind, text with a 160-character counter) and Sync to CLA...
- `web/js/views/running.js`: Running now: the running jobs with live timers, then the last 6 finished jobs with duration and tokens.
- `web/js/views/settings.js`: Settings (WP33): theme, density, what a phone may change, keyboard help and where the data lives.
- `web/js/views/tasks.js`: Task rows and job chips.
- `web/js/views/toast.js`: Toasts (WP28): one aria-live region.
- `web/js/views/tokens.js`: Tokens (WP33): the meters (Today and This week) for the scope, the limits editor, the account card, spend and the override.
- `web/js/views/topbar.js`: Top bar (WP28): the scope crumb (project name, section, view), the control pill with one Stop or Resume button, the Today and Week mini meters, the connectio...
- `web/js/views/tree.js`: Work, Tree view (WP31): phase, then task, then subtask checkboxes.
- `web/js/views/usage.js`: UsageBand: the weekly and five-hour plan meters, reset countdowns, the stale marker and the Sync now button.
- `web/js/views/work.js`: Work section (WP31): the Board, List and Tree views of one project's tasks.
- `web/js/views/workflow.js`: Workflow (WP48, W2): the job spans and task edges of each project's snapshot (the workflow key, WP47), drawn as swimlanes (Timeline), phases as columns of ta...

## 6. Data files and locations (from docs/ARCHITECTURE.md)

### Where things are on disk

| What | Default location | Holds |
| Config | `~/.config/roadmap-board/` | `config.json` (the registry, the ports, usage settings); `phone.token` once phone access exists |
| State | `~/Library/Application Support/roadmap-board/` | `usage.json`, `hooks-<project>.json` (active hook jobs), `backups/<project>/<timestamp>/`, `tunnel.pid` |
| Logs | `~/Library/Logs/roadmap-board/` | `server.log` (1 MB × 5, redacted), `hooks.log`, `launchd.out`, `launchd.err` |
| launchd plist | `~/Library/LaunchAgents/com.roadmap-board.agent.plist` | the service definition (mode 0644); `ROADMAP_LAUNCH_AGENTS` overrides the folder |
| Project data | `<project>/docs/` | `tasks.json`, `jobs.json`, `autonomy.json`, `roadmap.config.json`, and any extra Markdown files the config names |
| Project hooks | `<project>/.claude/settings.local.json` | the three roadmap hook entries, merged with the project's own entries |
### Data files added for the interactive manager

| file | location (project data dir, global state dir or global config dir) | what it holds | size caps (module constants) | written by (module) |
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

## 7. Last 30 commit subjects (newest first)

- WP71: workflow graph model and layout
- docs: workflow diagram spec (Opus WP70)
- WP48: workflow view
- WP52: features service, ops, CLI, snapshot
- docs: task breakdown and agy playbook (Opus WP57)
- WP53: planner view
- R3 fixes: review findings and known bugs
- WP51: plan format F and L records
- WP50: planner core
- WP36b: row alignment rule 0
- docs: planner spec (Opus WP49)
- WP47: workflow data
- WP40: notifications and roadmap watch
- WP42: haiku-sized skills and skills install
- WP43: default port 8780 and doctor port warning
- docs: workflow map spec (Opus WP46)
- WP38: end-to-end integration tests
- WP41: rules and definition of done in pickups
- WP37: release 1.0 prep
- WP36: wide screens and cosmetic fixes
- docs: gap analysis and next improvements (Opus WP39)
- UI: remove the 1280 px width cap, the app uses the full window width
- WP35b: ui smoke for the new shell, visual fixes
- WP35: final responsive and visual pass
- WP34: agents, research, notes route, question undo
- agy output verified: fixtures, changelog, architecture, test gaps
- WP33b: snapshot action and rules fields
- WP31: work board, list, tree
- WP32: roadmap lanes and issues
- WP33: tokens, limits, rules, settings

## 8. UI rules (docs/UI-CHECKLIST.md, numbered rules)

- 0. TOP PRIORITY, row alignment
- 1. Accessibility
- 2. Touch/interaction
- 3. Dragging
- 4. Feedback
- 5. Layout
- 6. Typography/colour
- 7. Icons
- 8. Forms
- 9. Navigation
- 10. Tables/boards
