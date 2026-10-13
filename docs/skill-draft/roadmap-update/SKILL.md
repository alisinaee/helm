---
name: roadmap-update
description: Use when you finish, start or block a task in a project that has a roadmap dashboard, or the user asks for roadmap status or progress. Never open docs/tasks.json.
---

# Roadmap update

## 1. Rules
- Never read or edit `docs/tasks.json` or `docs/jobs.json`. The `roadmap` CLI is the only writer.
- On an error, run the command printed on the `next:` line, and nothing else.
- Every command takes `--json`. Dry-run first where `--dry-run` exists.
- `--project ID` is optional. Without it, roadmap uses the project registered for this folder.

## 2. See the board (0.5k tokens)
```
roadmap status
```
At most 8 lines: phases, tasks left, running jobs.

## 3. Find work (0.5k tokens)
```
roadmap task list --status todo,partial --limit 10
roadmap task show P1.2
roadmap inbox
roadmap ask "<question>" --opt A --opt B --default A
```
Read the answer later with `roadmap ask get Q3`. `roadmap inbox` lists queued starts and answers (at most 6 lines).

## 4. Record a job (1k tokens)
```
roadmap job start "Write the parser" sonnet P1.2
roadmap job done j3 "parser done" --tokens 18
roadmap job fail j3 "reason in a few words"
```
`job start` prints the job id. Use it in `job done` or `job fail`. Put the job's real tokens in `--tokens` (thousands).
Before you spawn a worker, run `roadmap rules show --for P1.2 --model sonnet --role worker` and paste its lines in.

## 5. Change tasks (1k tokens; bulk 2k)
```
roadmap task done P1.2 --tokens 20 --note "parser merged"
roadmap task start P1.3
roadmap task hold P1.4 --note "Deferred: waits for the API key"
```
Bulk: one `ID key=value ...` line per task, on stdin:
```
P1.2 status=done tokensK=20
P1.3 status=partial
```
Run `roadmap task set --dry-run` first, read the diff, then run `roadmap task set` without the flag.

## 6. Errors
Exit 3: run the `next:` command. Exit 4 (locked): wait, then retry. Exit 5: fix the named lines.
A tool call answered `roadmap: stopped by user` or `blocked:` is a stop: end your turn and run `roadmap inbox`.

## 7. Token estimate
- Small one-file change: 10 to 30K. A few files: 30 to 80K. Large or new feature: 80 to 150K.
- Round to 5. A check review is 10 to 25% of the work. Use the real figure when you know it.

## 8. Budget
Status 0.5k, one job or task change 1k, bulk update 2k. Then tell the user the new counts from `roadmap status`.
