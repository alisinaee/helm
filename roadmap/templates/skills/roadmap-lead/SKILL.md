---
name: roadmap-lead
description: Use when you plan a project on its roadmap board, import or export a plan, manage the project rules, or spawn worker agents for tasks. Never edit tasks.json.
---

# Roadmap lead

## Rules
- Never open or edit `docs/tasks.json`, `docs/jobs.json` or `docs/autonomy.json`. The `roadmap` CLI is the only writer.
- Phase approval is the person's job. Never approve a phase yourself; ask the user in chat to approve it.
- Budgets and limits are read-only for agents. Run `roadmap budget show` and `roadmap limit show`. Never run `limit set`, `limit rm`, `limit budget` or `override`; report the numbers and ask the user.
- Every command takes `--json`. On an error, run the `next:` command.
- Pasted `rb:` refs: resolve with `roadmap ref <ref>`, act with the matching feature/task command (example: orphan task -> `roadmap feature link F7 R3.2`).
- Start each turn with `roadmap head brief`.
- Triage each new ask in one call: `roadmap head t H15 <kind> "<sum>" task:R7.31`.
- Keep every open ask bound to a task, issue or doc (`roadmap head bind H15 task:R7.31`); never mark an ask done unless its links are done.

## 1. Plan (budget 2k tokens)
```
roadmap plan template
roadmap plan import docs/plan.txt --dry-run
roadmap plan import docs/plan.txt
roadmap plan export --phase P2
```
Read the dry-run diff before the real import. Plan lines: `P <id> <status> | <name>` and `T <id> <status> <tokensK> <model>/<thinking> | <title>`. Plan items: `F <id> <-|hold> <1|2|3> <phase|-> <parent|-> [ask] | <title> [# <acceptance>]` (3 levels: phase, sub plan, item; at most 99; `ask` only for what the person asked for) and `L <featureId> <taskId>...` links tasks.

## 2. Rules (budget 1k tokens)
```
roadmap rules show --role lead
roadmap rules add all do "Run the tests before task done"
roadmap rules check
roadmap rules sync --dry-run
roadmap rules sync
```
Scopes: all, lead, worker, haiku, sonnet, opus, phase:X, task:X or claude. Kinds: do, dont, budget or done. Text is at most 160 characters. Run `rules sync --dry-run` before the real sync.

## 3. Spawn a worker (budget 1k tokens per spawn)
Put these in the worker prompt, in this order:
1. The task id and title, and its definition of done (`roadmap task show P1.2`).
2. The output of `roadmap rules show --for P1.2 --role worker`. Run it first, then paste its lines into the prompt.
3. The model and token budget from the task line.
4. The job record: `roadmap job start "<title>" sonnet P1.2`; the worker ends with `roadmap job done <id> "<note>" --tokens K`.
5. The roadmap-worker skill, and the rule: on an error run the `next:` command.
6. The stop rule: stop at the budget, and ask with `roadmap ask`.

## 4. Watch the board (budget 0.5k tokens)
```
roadmap status
roadmap inbox
roadmap issue list
roadmap comments P1.2 --last 5
roadmap budget show
roadmap limit show
```

## 5. Errors and stops
- Exit 3 or 5: run the `next:` command.
- Exit 4 (conflict): wait a few seconds, then retry once.
- A reply `roadmap: stopped by user` or `blocked:` is a stop: end your turn and run `roadmap inbox`.
