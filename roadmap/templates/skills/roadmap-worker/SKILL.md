---
name: roadmap-worker
description: Use when you work on a task in a project that has a roadmap board. Covers reading the board, starting and finishing a task, asking the user, logging issues and reading rules. Never edit tasks.json.
---

# Roadmap worker

## Rules
- Never open or edit `docs/tasks.json`, `docs/jobs.json` or other roadmap data files. The `roadmap` CLI is the only writer.
- Every command takes `--json`. Pass `--project ID` only when the folder is not registered.
- On an error, run the command on the `next:` line, and nothing else.
- Tokens are thousands: `--tokens 20` means 20K.

## 1. Read the board (budget 1k tokens)
```
roadmap status
roadmap inbox
roadmap task list --status todo --limit 10
roadmap task show P1.2
```
Read `inbox` before you start: it holds answers to your questions.

## 2. Start a task (budget 1k tokens)
```
roadmap task start P1.2
```
If the command is refused, run its `next:` line. Do not work on the task until it starts.

## 3. Finish a task (budget 1k tokens)
```
roadmap task done P1.2 --tokens 20 --note "parser merged"
roadmap subtask done P1.2/2
```
Use the real token figure when you know it. Otherwise estimate: one small file 10 to 30K, a few files 30 to 80K.

## 4. Block or ask (budget 1k tokens)
```
roadmap task hold P1.2 --note "waits for the API key"
roadmap ask "Use SQLite or Postgres?" --opt SQLite --opt Postgres --task P1.2
roadmap ask "Deploy now?" --opt yes --opt no --block
roadmap ask get Q3
```
Use `--block` only when you cannot continue without the answer.

## 5. Log an issue or a comment (budget 1k tokens)
```
roadmap issue new "Login fails on Safari" --kind bug --sev 2 --task P1.2
roadmap comment P1.2 "checked: the fix is in parser.py"
```
Kinds: bug, risk, question or blocker. Severity 1 is the most severe.

## 6. Read the rules (budget 0.5k tokens)
```
roadmap rules show --for P1.2 --role worker
```
Follow its lines (at most 12) before you edit anything.

## 7. Errors and stops
- Exit 3 (not found) or 5 (invalid data): run the `next:` command.
- Exit 4 (conflict): wait a few seconds, then retry once.
- A reply `roadmap: stopped by user` or `blocked:` is a stop: end your turn and run `roadmap inbox`.

## 8. Report
After each task change, tell the user the new counts from `roadmap status` in one line.
