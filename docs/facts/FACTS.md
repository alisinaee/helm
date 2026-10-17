# FACTS: roadmap-board grounding file

Generated 2026-10-17 by tools/gen_facts.py. Do not edit by hand; run `python3 tools/gen_facts.py`.
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

### roadmap tick

```text
usage: roadmap tick [-h] [--json] [--project ID]

options:
  -h, --help    show this help message and exit
  --json        print the {ok, data | error} JSON envelope on stdout
  --project ID  project id (default: $ROADMAP_PROJECT, then the registered
                project of this folder)
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
    new       start a project: init, plan with phase P1 not approved, optional
              research note 1

options:
  -h, --help  show this help message and exit
  --json      print the {ok, data | error} JSON envelope on stdout
```

### roadmap init

```text
usage: roadmap init [-h] [--json] [--name NAME] [--no-service] [path]

positional arguments:
  path          project folder (default: the current folder)

options:
  -h, --help    show this help message and exit
  --json        print the {ok, data | error} JSON envelope on stdout
  --name NAME   display name (default: the folder name)
  --no-service  do not install or start the launchd service
```

### roadmap job

```text
usage: roadmap job [-h] [--json] ACTION ...

positional arguments:
  ACTION
    start     start a job
    done      mark a job done
    fail      mark a job failed
    progress  record the live tokens of a running job (optional)
    list      list jobs
    prune     remove finished jobs beyond the newest 30

options:
  -h, --help  show this help message and exit
  --json      print the {ok, data | error} JSON envelope on stdout
```

### roadmap tokens

```text
usage: roadmap tokens [-h] [--json] ACTION ...

positional arguments:
  ACTION
    backfill  fill tokens of past jobs from subagent transcripts

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
    backlog   move a task to the backlog (the person only)
    promote   move a backlog task to todo (the person only)
    add       add a todo task (quick add)
    move      reorder a task within its phase
    set       bulk patch from stdin, one 'ID key=value ...' line per task

options:
  -h, --help  show this help message and exit
  --json      print the {ok, data | error} JSON envelope on stdout
```

### roadmap backlog

```text
usage: roadmap backlog [-h] [--json] ACTION ...

positional arguments:
  ACTION
    add       add a backlog task

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
usage: roadmap ask [-h] [--json] [--project ID] [--task ID] [--option A]
                   [--default A] [--block] [--timeout S]
                   [TEXT ...]

positional arguments:
  TEXT                 the question, or one of: get Q3 | wait Q3 | list

options:
  -h, --help           show this help message and exit
  --json               print the {ok, data | error} JSON envelope on stdout
  --project ID         project id (default: $ROADMAP_PROJECT, then the
                       registered project of this folder)
  --task ID            the task the question is about
  --option A, --opt A  an answer option: "Label" or "Label: description"; add
                       " (recommended)" to the label to mark it. 2 to 6
                       options, or none; free text is always allowed
                       (repeatable)
  --default A          the answer taken on timeout
  --block              the task waits for the answer
  --timeout S          seconds until the default is taken
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
    tree      the plan outline: one line per item (at most 60 lines)
    set       change a feature's ask flag
    move      move a feature up or down, or under a parent
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

### roadmap head

```text
usage: roadmap head [-h] [--json] ACTION ...

positional arguments:
  ACTION
    log       log one message verbatim (redacted), with its kind and summary
    t         triage one entry in one call: head t H15 <kind> "<sum>" [REF..]
              [--status S]
    list      one line per entry: id, kind, status, age, links, summary
    show      one entry: summary, verbatim, links with their states, history
              (at most 14 lines)
    set       change fields: head set H15 status=declined note=".." (a done
              close needs a commit sha, job id or answer: note)
    bind      add links to an entry
    unbind    remove links from an entry
    split     split one entry into two: head split H15 "<sum a>" "<sum b>"
    merge     merge a duplicate into another entry: head merge H16 --into H9
    convert   create a task, issue or backlog item from an entry and bind it
    claim     start a head session: writes a claim record and prints the
              carried-over open asks
    brief     the resume digest, at most 15 lines
    pause     pause the autopilot gate (writes the head-pause file)
    resume    resume the autopilot gate (removes the head-pause file)
    triage    untriaged entries with suggestions
    next      the head ops that can run now, one runnable command per line
    review    the person's review: no id lists the done entries, H15 confirm
              or H15 reopen decides
    accept    mark an entry accepted (the person only)
    forget    blank the
... (truncated)
```

### roadmap work

```text
usage: roadmap work [-h] [--json] ACTION ...

positional arguments:
  ACTION
    list      one line per Work item: id, status, prio, n/m done, title
    show      one Work item: outcome and its agent tasks (at most 15 lines)
    add       add a Work item: work add "<title>" [--outcome ..] [--kind
              task|issue] [--prio P0-P3]
    set       change a Work item: work set W12 [--title ..] [--outcome ..]
              [--prio P0-P3]
    link      bind an agent task to a Work item: work link R7.86 W12
    accept    accept a Work item into Done (the person only)
    reopen    reopen a Review or Done Work item (the person only)

options:
  -h, --help  show this help message and exit
  --json      print the {ok, data | error} JSON envelope on stdout
```

### roadmap ref

```text
usage: roadmap ref [-h] [--json] ref

positional arguments:
  ref         the ref the Copy button gives, for example rb:roadmap-
              board/task/R3.2

options:
  -h, --help  show this help message and exit
  --json      print the {ok, data | error} JSON envelope on stdout
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
    show       the rules for a task, model and role (at most 12 lines)
    add        add a rule at the end of docs/rules.txt
    rm         remove a rule by id, for example R3
    sync       write the all, lead and claude rules into CLAUDE.md
    check      validate docs/rules.txt against the caps
    propose    propose a rule (agents may); the person accepts
    proposals  the open rule proposals (at most 15 lines)
    accept     accept a proposal into docs/rules.txt (person only)
    reject     reject a proposal (person only)

options:
  -h, --help   show this help message and exit
  --json       print the {ok, data | error} JSON envelope on stdout
```

### roadmap usage

```text
usage: roadmap usage [-h] [--json] ACTION ...

positional arguments:
  ACTION
    show        show the stored usage
    sync        fetch usage now
    push        store usage from JSON on stdin
    statusline  Claude Code status line: store its rate_limits, then print a
                status line
    account     which Claude login the usage sync reads

options:
  -h, --help    show this help message and exit
  --json        print the {ok, data | error} JSON envelope on stdout
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

### roadmap logs

```text
usage: roadmap logs [-h] [--json] [--since 10m|2h|1d] [--src {core,hook,ui}]
                    [--ev NAME] [--ref rb:...] [--session last|SID]
                    [--level {DEBUG,INFO,WARN,ERROR}] [--limit N]
                    [--on | --off]
                    [{summary,marks,status}]

positional arguments:
  {summary,marks,status}
                        summary | marks | status (default: the last WARN and
                        ERROR events)

options:
  -h, --help            show this help message and exit
  --json                print the {ok, data | error} JSON envelope on stdout
  --since 10m|2h|1d     only events newer than this
  --src {core,hook,ui}  ui, core or hook
  --ev NAME             one event name, for example ui.error
  --ref rb:...          one project/kind/id reference
  --session last|SID    one session id, or the newest one
  --level {DEBUG,INFO,WARN,ERROR}
                        the lowest level shown (default WARN)
  --limit N             newest N events (cap 100)
  --on                  status: turn the debug log on
  --off                 status: turn the debug log off
```

### roadmap git

```text
usage: roadmap git [-h] [--json] ACTION ...

positional arguments:
  ACTION
    status    branch, counts and top changed files
    log       the newest commits
    branches  local branches
    branch    create or switch a branch (no argument: list them)
    show      one commit: header and file list
    commit    commit exactly the named paths (never everything)
    push      push the current branch (policy in docs/git.json; never forced)

options:
  -h, --help  show this help message and exit
  --json      print the {ok, data | error} JSON envelope on stdout
```

### roadmap system

```text
usage: roadmap system [-h] [--json] ACTION ...

positional arguments:
  ACTION
    show      show the components, layers and edges
    check     validate docs/system.json (exit 1 when invalid)

options:
  -h, --help  show this help message and exit
  --json      print the {ok, data | error} JSON envelope on stdout
```

## 2. HTTP routes (roadmap/http/routes.py)

| method | path (regex) | purpose |
|---|---|---|
| GET | `/api/v1/health` | - |
| GET | `/api/v1/meta` | - |
| GET | `/api/v1/projects` | The project list. Each row is built from the same cached snapshot the project's own route ser... |
| GET | `'/api/v1/projects/(?P<pid>' + _PID + ')/snapshot'` | - |
| GET | `'/api/v1/projects/(?P<pid>' + _PID + ')/head'` | GET /api/v1/projects/{pid}/head: the rows (f=open drops done and declined; the newest n) with... |
| GET | `'/api/v1/projects/(?P<pid>' + _PID + ')/panel'` | GET /api/v1/projects/{pid}/panel (R11.2): the person's newest board actions with their head s... |
| GET | `'/api/v1/projects/(?P<pid>' + _PID + ')/jobs'` | GET /api/v1/projects/{pid}/jobs?offset=0&limit=10: one page of the finished jobs, newest firs... |
| GET | `'/api/v1/projects/(?P<pid>' + _PID + ')/history'` | GET /api/v1/projects/{pid}/history?kind=&actor=&from=&to=&q=&before=&limit=: the project's hi... |
| GET | `/api/v1/history` | GET /api/v1/history?...&project=: every project's history merged, each event with project and... |
| GET | `'/api/v1/projects/(?P<pid>' + _PID + ')/git/status'` | GET .../git/status: branch, upstream, ahead/behind, detached, in-progress, and the changed fi... |
| GET | `'/api/v1/projects/(?P<pid>' + _PID + ')/git/log'` | GET .../git/log?n=10: the newest commits (n from 1 to 100) with their task and job links. |
| GET | `'/api/v1/projects/(?P<pid>' + _PID + ')/git/branches'` | GET .../git/branches: the local branches, the current one flagged, with ahead/behind and last... |
| GET | `'/api/v1/projects/(?P<pid>' + _PID + ')/git/show/(?P<sha>[^/]*)'` | GET .../git/show/{sha}: one commit (its links) and its files with +/- counts. Same-origin pag... |
| GET | `'/api/v1/projects/(?P<pid>' + _PID + ')/git/diff/(?P<sha>[^/]*)'` | GET .../git/diff/{sha}?path=: one file's patch for that commit. Secret names are hidden; bina... |
| GET | `'/api/v1/projects/(?P<pid>' + _PID + ')/git/diff'` | GET .../git/diff?path=: one changed file's diff in the worktree (an untracked file as all add... |
| GET | `'/api/v1/projects/(?P<pid>' + _PID + ')/system'` | GET /api/v1/projects/{pid}/system: the System map of one registered project. Components (with... |
| GET | `/api/v1/tokens/history` | GET /api/v1/tokens/history[?project=pid]: daily token sums by model, totals, per-task sums, t... |
| GET | `/api/v1/usage` | - |
| POST | `/api/v1/usage/sync` | - |
| GET | `/api/v1/usage/accounts` | GET /api/v1/usage/accounts: the Tokens page Account tab's rows, emails masked. Read only. |
| POST | `/api/v1/usage/accounts/(?P<id>[^/]+)/(?P<action>[a-z]+)` | POST /api/v1/usage/accounts/{id}/{action}: connect, disconnect, switch, check or login one ac... |
| POST | `/api/v1/cmd` | POST /api/v1/cmd {op, args, project?}: one registry op. Order: CSRF and origin, JSON type, bo... |
| POST | `/api/v1/log` | POST /api/v1/log {sid, events: [...]} (R7.16): a batch of browser debug events, at most 50. O... |
| GET | `/api/v1/log/status` | GET /api/v1/log/status: whether the debug log is on, its size in bytes and its file count. No... |
| GET | `/api/v1/log/report` | GET /api/v1/log/report?n=30: the plain-text debug report for the GUI's Copy button (R7.16 ste... |
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
| `ACC_MAX` | `roadmap/core/features.py:26` | `160` |
| `ACC_MAX` | `roadmap/services/featops.py:22` | `160` |
| `ACTIVITY_SUM_MAX` | `roadmap/core/parsers.py:27` | `60` |
| `AFTER_MAX` | `roadmap/core/planfmt.py:17` | `5` |
| `AFTER_MAX` | `roadmap/core/snapshot.py:34` | `5` |
| `AGENTS_MAP_MAX` | `roadmap/services/hooks.py:47` | `200` |
| `ANSWERED_KEEP` | `roadmap/services/questions.py:14` | `50` |
| `ANSWER_MAX` | `roadmap/commands/watch.py:21` | `60` |
| `ASK_OF_MAX` | `roadmap/core/refs.py:18` | `5` |
| `ASSETS_MAX` | `roadmap/services/head.py:29` | `20` |
| `BIND_MAX` | `roadmap/core/head.py:25` | `2` |
| `BUDGET_MAX` | `roadmap/services/rules.py:24` | `100000` |
| `BY_MAX` | `roadmap/services/comments.py:15` | `40` |
| `CACHE_MAX` | `roadmap/services/system.py:38` | `16` |
| `CACHE_MAX` | `roadmap/services/system_arch.py:40` | `8` |
| `CACHE_MAX` | `roadmap/services/system_v2.py:22` | `16` |
| `CACHE_MAX` | `roadmap/services/systemheat.py:26` | `16` |
| `CAP` | `roadmap/services/queue.py:10` | `50` |
| `CAP` | `roadmap/services/system_tasks.py:14` | `40` |
| `CLOSED_KEEP` | `roadmap/services/issues.py:12` | `100` |
| `COMMENT_MAX` | `roadmap/core/parsers.py:26` | `280` |
| `DAYS_KEEP` | `roadmap/services/ledger.py:30` | `14` |
| `DEFAULT_LIMIT` | `roadmap/commands/logs.py:20` | `20` |
| `FEATS_MAX` | `roadmap/core/parsers.py:29` | `3` |
| `FEATURES_MAX` | `roadmap/core/planfmt.py:19` | `60` |
| `FEAT_ACC_MAX` | `roadmap/core/planfmt.py:21` | `160` |
| `FEAT_TITLE_MAX` | `roadmap/core/planfmt.py:20` | `80` |
| `FREE_MAX` | `roadmap/services/headpanel.py:24` | `100` |
| `GATE_LIMIT` | `roadmap/services/head.py:751` | `5` |
| `GIT_MAX` | `roadmap/services/history.py:31` | `400` |
| `HEAD_BYTES_MAX` | `roadmap/core/snapshot.py:45` | `8192` |
| `HEAD_DONE_MAX` | `roadmap/core/snapshot.py:37` | `5` |
| `HEAD_HISTORY_MAX` | `roadmap/http/routes.py:554` | `20` |
| `HEAD_LINKED_MAX` | `roadmap/core/snapshot.py:41` | `6` |
| `HEAD_LINKS_MAX` | `roadmap/core/snapshot.py:40` | `3` |
| `HEAD_NOTE_MAX` | `roadmap/core/snapshot.py:39` | `200` |
| `HEAD_OPEN_MAX` | `roadmap/core/snapshot.py:36` | `40` |
| `HEAD_PREV_MAX` | `roadmap/core/snapshot.py:44` | `3` |
| `HEAD_SUM_MAX` | `roadmap/core/snapshot.py:38` | `60` |
| `HEAD_TITLE_MAX` | `roadmap/core/snapshot.py:42` | `60` |
| `HIST_MAX` | `roadmap/services/history.py:36` | `240` |
| `ID_MAX` | `roadmap/services/features.py:25` | `99` |
| `ISSUES_CLOSED_MAX` | `roadmap/core/snapshot.py:32` | `5` |
| `JOBS_KEEP` | `roadmap/services/budget.py:18` | `500` |
| `JOB_IDS_MAX` | `roadmap/services/commands.py:692` | `200` |
| `KEEP` | `roadmap/services/activity.py:12` | `500` |
| `KEEP` | `roadmap/services/headpanel.py:22` | `300` |
| `KEEP` | `roadmap/store/backup.py:11` | `14` |
| `KEEP_FINISHED` | `roadmap/services/jobs.py:18` | `200` |
| `LABEL_MAX` | `roadmap/services/usage_accounts.py:53` | `40` |
| `LAUNCHD_LOG_LIMIT` | `roadmap/services/doctor.py:32` | `5 * 1024 * 1024` |
| `LIMIT_CAP` | `roadmap/commands/logs.py:21` | `100` |
| `LINE_MAX` | `roadmap/core/refs.py:16` | `10` |
| `LINE_MAX` | `roadmap/services/control.py:29` | `160` |
| `LINK_MAX` | `roadmap/services/featops.py:24` | `3` |
| `LIST_MAX` | `roadmap/commands/ask.py:18` | `10` |
| `LIST_MAX` | `roadmap/commands/issue.py:9` | `20` |
| `LOG_BATCH_MAX` | `roadmap/http/security.py:217` | `50` |
| `LOG_MAX` | `roadmap/services/git.py:34` | `100` |
| `MARKS_MAX` | `roadmap/commands/logs.py:22` | `10` |
| `MESSAGE_MAX` | `roadmap/services/gitops.py:34` | `4000` |
| `NOTE_MAX` | `roadmap/core/parsers.py:22` | `300` |
| `NOTE_MAX` | `roadmap/services/head.py:32` | `160` |
| `OPEN_CAP` | `roadmap/services/issues.py:11` | `200` |
| `OPEN_CAP` | `roadmap/services/questions.py:13` | `50` |
| `OPTS_LIMIT` | `roadmap/services/questions.py:18` | `6` |
| `OPTS_MAX` | `roadmap/core/parsers.py:24` | `6` |
| `OPT_MAX` | `roadmap/services/questions.py:15` | `60` |
| `OPT_TEXT_MAX` | `roadmap/core/parsers.py:25` | `260` |
| `OPT_TEXT_MAX` | `roadmap/services/questions.py:16` | `260` |
| `OUTCOME_MAX` | `roadmap/services/work.py:29` | `240` |
| `PATHS_MAX` | `roadmap/services/gitops.py:33` | `500` |
| `PERCENT_MAX` | `roadmap/services/cmdops.py:28` | `100` |
| `PHASE_LINE_MAX` | `roadmap/services/tasks.py:25` | `160` |
| `PHONE_FAIL_LIMIT` | `roadmap/http/security.py:29` | `10` |
| `PROTECTED_MAX` | `roadmap/services/gitops.py:32` | `50` |
| `QUERY_LIMIT` | `roadmap/services/tasks.py:22` | `20` |
| `Q_MAX` | `roadmap/services/history.py:34` | `200` |
| `Q_TEXT_MAX` | `roadmap/core/parsers.py:23` | `200` |
| `REASON_MAX` | `roadmap/services/jobs.py:24` | `80` |
| `RECENT_MAX` | `roadmap/core/snapshot.py:26` | `2` |
| `RECENT_MAX` | `roadmap/services/ledger.py:36` | `36` |
| `REPORT_MSG_CAP` | `roadmap/log.py:554` | `160` |
| `SAMPLES_KEEP` | `roadmap/services/tokenshare.py:18` | `2000` |
| `SHOWN_MAX` | `roadmap/commands/budget.py:11` | `8` |
| `SHOW_MAX` | `roadmap/commands/head.py:35` | `14` |
| `STDERR_KEEP` | `roadmap/services/git.py:26` | `64 * 1024` |
| `STDOUT_CAP` | `roadmap/services/git.py:24` | `2 * 1024 * 1024` |
| `SUBS_MAX` | `roadmap/core/parsers.py:15` | `12` |
| `SUB_TITLE_MAX` | `roadmap/core/parsers.py:16` | `80` |
| `SUMMARY_MAX` | `roadmap/services/history.py:33` | `240` |
| `SUMMARY_MAX` | `roadmap/services/notify.py:25` | `60` |
| `SUM_MAX` | `roadmap/core/head.py:54` | `100` |
| `SUM_MAX` | `roadmap/services/head.py:31` | `head.SUM_MAX` |
| `SUM_MAX` | `roadmap/services/headpanel.py:23` | `160` |
| `TASKS_MAX` | `roadmap/services/issues.py:13` | `5` |
| `TEXT_MAX` | `roadmap/services/head.py:28` | `8000` |
| `TEXT_MAX` | `roadmap/services/history.py:32` | `4000` |
| `TEXT_MAX` | `roadmap/services/notify.py:24` | `120` |
| `TEXT_SHOW_MAX` | `roadmap/commands/head.py:36` | `200` |
| `TITLE_MAX` | `roadmap/commands/research.py:24` | `80` |
| `TITLE_MAX` | `roadmap/core/features.py:25` | `80` |
| `TITLE_MAX` | `roadmap/core/parsers.py:21` | `120` |
| `TITLE_MAX` | `roadmap/services/featops.py:23` | `80` |
| `TITLE_MAX` | `roadmap/services/jobs.py:23` | `200` |
| `TITLE_MAX` | `roadmap/services/work.py:28` | `60` |
| `TITLE_MAX` | `roadmap/store/work_db.py:15` | `60` |
| `TOKENS_K_MAX` | `roadmap/services/commands.py:38` | `10000000` |
| `TREE_MAX` | `roadmap/commands/feature.py:14` | `60` |
| `UNDO_KEEP` | `roadmap/services/commands.py:33` | `500` |
| `USAGE_ISO_MAX` | `roadmap/services/cmdops.py:283` | `40` |
| `VIEW_MAX` | `roadmap/commands/plan.py:78` | `15` |
| `_KEEP` | `roadmap/core/planfmt.py:30` | `object()` |

## 5. Module tree (first docstring line of each file)

### roadmap/

- `roadmap/__init__.py`: Helm: a live roadmap dashboard and job tracker for Claude Code projects.
- `roadmap/__main__.py`: Entry point for `python3 -m roadmap`.
- `roadmap/cli.py`: Command line entry point: the argparse tree, the --json envelope and the exit codes.
- `roadmap/commands/__init__.py`: Command groups. Each module here registers its own commands with the CLI.
- `roadmap/commands/agent_guide.py`: Command agent-guide: print the short guide for AI agents (roadmap.core.guide, at most 40 lines).
- `roadmap/commands/ask.py`: Questions: ask, ask get, ask wait, ask list, and answer.
- `roadmap/commands/backlog.py`: Command group backlog: add an idea to the backlog (status backlog: known, not committed, not...
- `roadmap/commands/backup.py`: Top-level command backup: copies the data files of one or all projects into the state directory.
- `roadmap/commands/budget.py`: Command budget: show the spend and the limits (budget show [--phase P], at most 8 lines).
- `roadmap/commands/comment.py`: Commands comment and comments: add a comment on a task or issue, and read the newest ones.
- `roadmap/commands/control.py`: Command group control: stop (always allowed), resume and override (refused from an agent shell).
- `roadmap/commands/doctor.py`: Top-level command doctor: runs the install checks and prints ok, warn or fail with a plain-wo...
- `roadmap/commands/feature.py`: Command group feature (WP52): the planner's features. add, list, tree, show, set, move, link,...
- `roadmap/commands/git.py`: Command group git: status, log, branches, branch, show, commit and push for the project folde...
- `roadmap/commands/head.py`: Command group head (HEAD-SPEC section 4): the ledger of the person's asks. log, t (triage in...
- `roadmap/commands/hook.py`: Top-level command hook: the stdin entry that Claude Code hooks call.
- `roadmap/commands/hooks.py`: Command group hooks: install and inspect the Claude Code hooks of a project.
- `roadmap/commands/inbox.py`: Command inbox: what needs the user or the next agent, in at most 6 lines
- `roadmap/commands/init.py`: Command init: set a project up in one idempotent step (register, empty board, hooks, service).
- `roadmap/commands/issue.py`: Command group issue: open, list, show, close and link issues (issues.json). Writes go through...
- `roadmap/commands/job.py`: Command group job: record Claude jobs and their tokens in the project's jobs.json.
- `roadmap/commands/limits.py`: Command groups limit and phase: the limit rows that stop agents (services/limits.py, services...
- `roadmap/commands/logs.py`: Command logs: the debug event log (R7.16), read through roadmap.log.
- `roadmap/commands/open.py`: Top-level command open: opens the dashboard at http://127.0.0.1:<port>/ with the macOS open c...
- `roadmap/commands/phone.py`: Command group phone: start, stop, link and status for the read-only phone listener's tunnel (...
- `roadmap/commands/plan.py`: Command group plan: import plan text into tasks.json, export it for a re-plan, or print the g...
- `roadmap/commands/project.py`: Command group project: register projects and keep their data files healthy.
- `roadmap/commands/ref.py`: Command ref: resolve a board ref (rb:<project>/<kind>/<id>, from the Copy button) to one shor...
- `roadmap/commands/research.py`: Command group research (WP17): numbered research notes in <data dir>/research, one INDEX line...
- `roadmap/commands/rules.py`: Command group rules: show, add, rm, sync and check the project rules (services/rules.py), and...
- `roadmap/commands/serve.py`: Top-level commands serve and open. serve runs the dashboard server on 127.0.0.1 and, unless -...
- `roadmap/commands/service.py`: Command group service: the launchd lifecycle of the background server (WP11).
- `roadmap/commands/skills.py`: Command group skills: list the Haiku-sized skill templates and install them into <project>/.c...
- `roadmap/commands/status.py`: Top-level command status: the board summary of one project in at most 8 lines and 700 charact...
- `roadmap/commands/subtask.py`: Command group subtask: add a subtask to a task, and tick or untick one (P2.4/2).
- `roadmap/commands/system.py`: Command group system: the architecture map from docs/system.json (A8, SYSTEM-DESIGN-SECTION.md).
- `roadmap/commands/task.py`: Command group task: read and change tasks in the project's tasks.json (show, list, done, star...
- `roadmap/commands/tick.py`: Top-level command tick: one supervisor pass over the project store (reap, leases, retry, fold...
- `roadmap/commands/tokens.py`: Command group tokens: measured per-job tokens from Claude Code subagent transcripts (R10.32).
- `roadmap/commands/undo.py`: Command undo: put back a change that reports undo, by its activity id (undo A812).
- `roadmap/commands/usage.py`: Command group usage: the global plan-usage store.
- `roadmap/commands/usage_accounts.py`: `helm usage account ...` (R11.8, docs/USAGE-ACCOUNTS.md): list, check, connect, disconnect, s...
- `roadmap/commands/version.py`: Top-level command version: prints the package version. The one implemented command in WP1.
- `roadmap/commands/watch.py`: Command watch: block until a new Start is queued, a question is answered or the person acts o...
- `roadmap/commands/work.py`: Work items from the CLI: work list, show, add, set, link, accept, reopen (docs/WORK-MODEL.md...
- `roadmap/core/__init__.py`: Pure core: markdown tables, data-file parsers, extras, snapshot and number formatting. No I/O.
- `roadmap/core/extras.py`: Registry of the optional roadmap extras: spikes, testing (RH checks) and the roadmap's Next u...
- `roadmap/core/features.py`: Planner features (docs/features.json): derive feature rows, coverage and orphan tasks.
- `roadmap/core/format.py`: Number formatting for the dashboard. Mirrors web/js/format.js; both are tested against format...
- `roadmap/core/guide.py`: The static text of `roadmap agent-guide`: rules, the most used commands, the plan grammar, re...
- `roadmap/core/head.py`: Head section core (HEAD-SPEC section 2, 6): the pure fold of head.jsonl and the stdlib heuris...
- `roadmap/core/mdtables.py`: Markdown helpers for the roadmap files: table rows, table iteration, level-2 sections and sta...
- `roadmap/core/parsers.py`: Parsers for tasks.json, jobs.json and autonomy.json.
- `roadmap/core/planfmt.py`: Plan text format for roadmap tasks and phases, and the bulk "set" line format. Pure functions...
- `roadmap/core/refs.py`: Board references (R7.12): the rb:<project>/<kind>/<id> strings the Copy button puts on the cl...
- `roadmap/core/secrets.py`: Secret scrubbing (HEAD-SPEC section 7): masks credentials, personal data and long opaque runs...
- `roadmap/core/snapshot.py`: Build the roadmap snapshot: the dict the dashboard renders, from the texts of a project's dat...
- `roadmap/core/workstatus.py`: Status roll-up for Work items (docs/WORK-MODEL.md section 2). Pure: no I/O, stdlib only.
- `roadmap/errors.py`: Typed errors shared by the CLI and the HTTP layer, with the CLI exit codes.
- `roadmap/http/__init__.py`: The HTTP layer: the 127.0.0.1 server, the API v1 routes, the static pages and the security ch...
- `roadmap/http/routes.py`: API v1 routes: the path table, the reply helpers and one function per route.
- `roadmap/http/security.py`: Security rules for the HTTP layer as pure functions: Host and Origin checks, the CSRF check,...
- `roadmap/http/server.py`: The dashboard server: ThreadingHTTPServer bound to 127.0.0.1 only, with the request handler,...
- `roadmap/http/static.py`: Static pages from web/: an allowlist built once at startup. URL paths are only looked up in t...
- `roadmap/log.py`: Logging for the roadmap package: the namespace, the file handler with rotation, the redaction...
- `roadmap/services/__init__.py`: Service layer: jobs and hooks (WP4), usage (WP6), and later launchd, tunnel and loader.
- `roadmap/services/activity.py`: Activity log (activity.jsonl): one line per write, {id, at, src, op, sum, undo}. Keeps the ne...
- `roadmap/services/agentguard.py`: Agent guard: ops that loosen control are refused from an agent's shell (any non-empty CLAUDEC...
- `roadmap/services/budget.py`: Budget (budget.json): limits in thousands of tokens and the spend per task and model.
- `roadmap/services/cmdops.py`: Command ops that wire the control, limit, rules and budget services into the WP21 registry (c...
- `roadmap/services/commands.py`: Command layer (WP21): the one write path for CLI calls, and the registry behind POST /api/v1/...
- `roadmap/services/comments.py`: Comments (comments.json): a flat thread per target (a task or an issue id). At most 20 per ta...
- `roadmap/services/control.py`: Control state (WP22): stop, resume, override and the limits that stop the agents of a project.
- `roadmap/services/doctor.py`: The checks behind `roadmap doctor`. Each check returns a row: id, title, status (ok, warn or...
- `roadmap/services/featops.py`: Feature ops (WP52): the registry entries for the planner's features, run through commands.run...
- `roadmap/services/features.py`: Planner features (WP52): the service behind the feature ops and the feature CLI.
- `roadmap/services/git.py`: Git core (GIT-SPEC step 1): a safe read runner for one registered project, input validation,...
- `roadmap/services/gitops.py`: Git write ops (GIT-SPEC step 3): git.commit, git.push, git.branch, git.switch and git.revert,...
- `roadmap/services/head.py`: Head store service (HEAD-SPEC sections 2, 3, 7): appends entries, updates and session records...
- `roadmap/services/headimport.py`: HEAD-SPEC H11: seed the head ledger from a markdown doc. Numbered items and bullets under the...
- `roadmap/services/headops.py`: Head ops (HEAD-SPEC sections 4 and 10): the registry entries behind `roadmap head ...`, run t...
- `roadmap/services/headpanel.py`: Panel to head (R11.2): every write the person makes on the board reaches the head agent.
- `roadmap/services/history.py`: Project history (R11.4, docs/ACTIVITY-V2.md): one read-only feed of everything that happened...
- `roadmap/services/hooks.py`: Hook driver: turns Claude Code hook events into job starts and closes. Ported from split-net'...
- `roadmap/services/hooks_install.py`: Install, remove and inspect the roadmap hook entries in a project's .claude/settings.local.js...
- `roadmap/services/issues.py`: Issues (issues.json): open, close and list. At most 200 open (open or doing); closed or wontf...
- `roadmap/services/jobs.py`: Job registry in each project's data folder (jobs.json): start, finish, list and prune.
- `roadmap/services/jobtokens.py`: Measured tokens per job (R10.32): read a Claude Code subagent transcript and store the sums o...
- `roadmap/services/launchd.py`: The launchd user agent that runs `roadmap serve`: render and write the plist, the lifecycle t...
- `roadmap/services/launcher.py`: Opt-in launcher (R7.1 T4): opens Terminal with `claude` in the project folder when nobody is...
- `roadmap/services/leases.py`: File leases in the SQLite store (docs/roadmap.db, table leases): one row per leased file.
- `roadmap/services/ledger.py`: Usage ledger (WP27): the global ledger.json of measured account points and of each project's...
- `roadmap/services/limits.py`: Limit rows (WP27): the rules that stop agents when a window of usage is used up. Specified in...
- `roadmap/services/loader.py`: Load a registered project's data files into a snapshot, and name the process that holds a TCP...
- `roadmap/services/notify.py`: Desktop wake-up notifications (GAP-ANALYSIS 2.1): one macOS notification through osascript wh...
- `roadmap/services/presence.py`: Session presence (R7.1 T1): tells the board whether a Claude session is listening for a project.
- `roadmap/services/projects.py`: Project maintenance (WP10): init templates, add, list, show, remove, check, migrate and backup.
- `roadmap/services/questions.py`: Questions (questions.json): ask, answer, expire on timeout, list. At most 50 open. Answered o...
- `roadmap/services/queue.py`: Start queue (queue.json): tasks waiting to be started, at most 50 entries, oldest first.
- `roadmap/services/records.py`: Shared file work for the WP20 services: load a keyed JSON document at the current schema, sav...
- `roadmap/services/rules.py`: Project rules (WP22): docs/rules.txt, one rule per line, shown to the lead and to workers, an...
- `roadmap/services/supervisor.py`: Supervisor: one tick() pass over the project store (docs/roadmap.db). Idempotent and safe to...
- `roadmap/services/system.py`: System map A1: load and validate the optional docs/system.json, or build an automatic baselin...
- `roadmap/services/system_arch.py`: System views (R10.33): the engineering views of one project, derived from its code (docs/SYST...
- `roadmap/services/system_behave.py`: R11.103 System v2: the class, deployment, use case and activity diagrams, derived from the co...
- `roadmap/services/system_data.py`: System v2 data diagrams: ER / EER entities and state machines derived from the tracked files...
- `roadmap/services/system_tasks.py`: System v2: which board (agent) tasks and Work items belong to which component (docs/SYSTEM-V2...
- `roadmap/services/system_v2.py`: System v2 backend (docs/SYSTEM-V2-SPEC.md sections 2 and 3): extends the arch dict system_arc...
- `roadmap/services/systemheat.py`: System map A2: heat per component, from the last 30 days of git history, the running jobs, th...
- `roadmap/services/tasks.py`: Tasks service (WP16): read, query, bulk upsert of phases and tasks from parsed plan records,...
- `roadmap/services/tokenhist.py`: Token history for the Tokens page (R11.6): daily sums by model, totals, per-task sums and the...
- `roadmap/services/tokenshare.py`: Share of the weekly limit per job (R10.35): an estimate, not a measurement.
- `roadmap/services/tunnel.py`: The phone tunnel: rotate the phone token, start ssh to localhost.run, read the tunnel URL, ke...
- `roadmap/services/usage.py`: Account usage for the dashboard: the Anthropic usage reading, the global usage.json store, th...
- `roadmap/services/usage_accounts.py`: Usage accounts (R11.8, docs/USAGE-ACCOUNTS.md): which Claude login Helm's usage sync reads, w...
- `roadmap/services/usage_sources.py`: Where account usage comes from when nobody pastes it (R10.29). services/usage.py runs the cha...
- `roadmap/services/work.py`: Work items (the human card) and the link from agent tasks to them (docs/WORK-MODEL.md section...
- `roadmap/store/__init__.py`: Storage layer: paths, atomic JSON writes, directory locks, config, schema versions, migration...
- `roadmap/store/atomic.py`: Atomic JSON writes (temp file, fsync, replace, fsync the directory) and strict JSON reads.
- `roadmap/store/backup.py`: Timestamped copies of data files under the state directory. Keeps the newest 14 backups per p...
- `roadmap/store/config.py`: Global config.json: schema v1 with ports, usage settings and the project list. Add, list, get...
- `roadmap/store/db.py`: SQLite store (stdlib sqlite3): one file per project (docs/roadmap.db), WAL, one short write t...
- `roadmap/store/events.py`: Append-only event log in the SQLite store. One shared integer rev across all event kinds.
- `roadmap/store/export.py`: Deterministic JSON export of the SQLite store into the file shapes the repo tracks (tasks.jso...
- `roadmap/store/head_db.py`: Head ledger on the SQLite store (opt-in backend; JSON head.jsonl stays the default).
- `roadmap/store/jobs_db.py`: Job registry in the SQLite store (roadmap/store/db.py, docs/roadmap.db), used when the switch in
- `roadmap/store/jsonl.py`: JSON-lines files (activity.jsonl and the *-archive.jsonl files): append one line, read tolera...
- `roadmap/store/lock.py`: Exclusive directory lock: flock on an fd of the data directory itself, the same mechanism as...
- `roadmap/store/migrate.py`: Import an existing project's JSON files (tasks.json, jobs.json, head.jsonl) into the SQLite s...
- `roadmap/store/migrations.py`: Ordered migration steps per data kind. Reads upgrade in memory only; writers save the newest...
- `roadmap/store/paths.py`: Locations of the config, state and log directories. Setting ROADMAP_HOME redirects every path...
- `roadmap/store/schema.py`: Schema versions per data file kind, with the read and write rules.
- `roadmap/store/tasks_db.py`: JSON data files mirrored in the sqlite store (used only when the sqlite switch is on; JSON st...
- `roadmap/store/work_db.py`: Work items (the human card) and their agent tasks (the machine packages) in the SQLite store...

### web/js/views/

- `web/js/views/activity.js`: Activity (R11.4, docs/ACTIVITY-V2.md): the full project history.
- `web/js/views/activity_data.js`: Activity data (R11.4, docs/ACTIVITY-V2.md): the per-scope state of the history feed, the read...
- `web/js/views/activity_timeline.js`: Activity timeline (R11.117): the horizontal strip at the top of the Activity page.
- `web/js/views/activity_view.js`: Activity markup (R11.4): the filter bar, the time scrubber, the day-grouped rows and the deta...
- `web/js/views/agents.js`: Agents (WP34): the running jobs as a tree (a lead job with its workers indented under it), an...
- `web/js/views/board.js`: Work, Board view (WP31), and the helpers the List and Tree views share: the project's tasks w...
- `web/js/views/details.js`: Details tab (WP29): the task, issue or question named by the route (#/p/<id>/<section>/i/<ite...
- `web/js/views/extras.js`: Extras: the spike board and the real-hardware board.
- `web/js/views/git.js`: Git (R7.29 W1.c, docs/GIT-SPEC.md section 5): the project's repo as the person reads it.
- `web/js/views/head.js`: Head screen (R7.31 H8, docs/HEAD-SPEC.md sections 5 and 10).
- `web/js/views/headseen.js`: Seen by head (R11.2, docs/PANEL-TO-HEAD.md): the person's newest board actions and whether th...
- `web/js/views/home.js`: Home (#/): one card per project, then Running now across projects.
- `web/js/views/inbox.js`: Inbox (WP30, R7.111): one list of everything that needs you (open questions, Head asks, rule...
- `web/js/views/kpi.js`: KpiRow: six tiles for the project view.
- `web/js/views/legend.js`: Legend: what the glyphs, chips and token figures mean.
- `web/js/views/limits.js`: Limits, simple (R7.28 A, docs/LIMITS-SIMPLE-SPEC.md).
- `web/js/views/list.js`: Work, List view (WP31): a dense table of the project's tasks with a checkbox, id, title, phas...
- `web/js/views/nav.js`: Left nav (WP28): the section list with badges and the settings link at the foot.
- `web/js/views/needsyou.js`: Needs you: the open tasks whose needsUser flag is set (the same count as the summary's need_u...
- `web/js/views/next.js`: Next up: the queued items from the roadmap, as plain text (the markdown bold and code marks a...
- `web/js/views/overview.js`: Overview (WP30).
- `web/js/views/palette.js`: Command palette (WP61b).
- `web/js/views/panel.js`: Right panel (WP29): one <aside> with two tabs, Projects and Details.
- `web/js/views/phases.js`: Phases: the main column of the project view.
- `web/js/views/planner.js`: Planner (R7.109): the plan on the Head screen's layout and classes (.hd-* in head.css).
- `web/js/views/projects.js`: Projects tab (WP29): "All projects" first, then one row per project.
- `web/js/views/recent.js`: Recent progress: the newest rows of the roadmap log.
- `web/js/views/roadmap.js`: Roadmap (WP32, R7.110).
- `web/js/views/roadmap_map.js`: Roadmap Map (R11.5, docs/ROADMAP-MAP.md): the plan as a metro line of phases with a column of...
- `web/js/views/rules.js`: Rules (WP33): the project's rules in tabs by scope group, a delete on each rule, an add form...
- `web/js/views/running.js`: Running now: the running jobs with live timers, then the last 6 finished jobs with duration a...
- `web/js/views/settings.js`: Settings (WP33): theme, density, what a phone may change, keyboard help, where the data lives...
- `web/js/views/system-menu.js`: System context menu (R11.105): header (name, kind, progress), action items, optional inline t...
- `web/js/views/system-panel.js`: System views side panel (R10.33): the facts of the selected node, as a string.
- `web/js/views/system.js`: System (R10.33, docs/SYSTEM-VIEWS-SPEC.md): the selected project drawn the way engineers draw...
- `web/js/views/tasks.js`: Task rows and job chips.
- `web/js/views/toast.js`: Toasts (WP28): one aria-live region.
- `web/js/views/tokens.js`: Tokens (R7.28 B): one plain page, the same for All projects and a project.
- `web/js/views/tokens_by.js`: Tokens by task and by model (R10.32 step 5): two read-only tables summed from the jobs that c...
- `web/js/views/tokens_charts.js`: Small inline-SVG chart helpers for the Tokens page (R11.6).
- `web/js/views/tokens_history.js`: Token history for the Tokens page (R11.6): the Overview tab (general tokens used, remaining e...
- `web/js/views/topbar.js`: Top bar (WP28, R7.28 W1.d): the scope crumb (project name, section, view), the control pill w...
- `web/js/views/tree.js`: Work, Tree view (WP31): phase, then task, then subtask checkboxes.
- `web/js/views/usage.js`: UsageBand: the weekly and five-hour plan meters, reset countdowns, the stale marker, the Sync...
- `web/js/views/wf_table.js`: The Workflow Table (R7.114, B-0 and B-4): one row per task that had activity in the range, no...
- `web/js/views/work.js`: Work section (WP31): the Board, List and Tree views of one project's tasks.
- `web/js/views/workflow.js`: Workflow (WP48, W2): the job spans and task edges of each project's snapshot (the workflow ke...

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

- Board state: R11.114-R11.118 done
- R11.118: Git worktree diff preview (read-only route + diff pane)
- R11.117: timeline spans the whole range via server bins (tl)
- R11.115: spacing control for Workflow map and Roadmap map
- R11.117: Activity horizontal timeline with selected-item point
- R11.116: Git section redesign (chips header, tabs, status pills, docked commit panel)
- R11.115: System diagram spacing control (Spacing - / +, [ ], per-view)
- R11.114: System diagram actions inside the diagram box; band toggle no longer covers label
- Board state: ledger H238/H239
- Runbook: H239 no agy/Cursor/split-net while VPN is off
- R11.109: update timeline source tests to the new pan/zoom code
- Board state: R11.112, R11.113, R10.28 done
- R11.113: route class module edges around boxes, label in the gap
- R11.112: class diagram import/extends edges from the backend
- R11.112: fitShelf packs module boxes to the canvas aspect
- R11.112: Classes diagram grouped by module, collapsed by default, aggregated edges
- Board state: jobs, ledger, tasks; runbook 5h stop 50% (H235)
- R11.111: seed docs/system.json overrides + spec section 6
- R11.110: System v2 integration (new diagram kinds, expand/drill, breadcrumb, context menu)
- R11.8: Account tab one aligned grid (subgrid, content-sized actions)
- R11.104: p7 lint and r765 fixes (rewrap, setHtml, line numbers)
- R11.8: usage accounts routes for the Tokens Account tab
- R11.109: Workflow timeline pan/zoom/Now (buttons, wheel, pinch, keys)
- R11.2 panel-to-head channel; R11.6/R11.8 Tokens history charts and Account tab
- R11.5: Roadmap map view (layout, render, tests)
- R11.104: lint/a11y fixes (toolbar aria-controls, sysdiagrams wrap, system labels, resize css)
- R11.4: Activity redesign (full history, filters, time) + history API service
- R11.104: System v2 UI core (fill-space layout, true fit, zoom readout, native full screen, switcher, toolbar actions)
- R11.102: skip test fixtures in er/states
- R11.108: syslayout collapseGroups, subgraph, anchorShift, toggles

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
