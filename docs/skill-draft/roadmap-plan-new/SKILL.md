---
name: roadmap-plan-new
description: Use when the user starts a new project or asks to create or redo a roadmap, plan or task breakdown for a project. Research first, then fill the dashboard.
---

# New project plan (research first)

Budget: about 55k tokens in total. Stop and report when a step goes over its budget.
Never edit `docs/tasks.json` by hand. Only the CLI writes it.

## 1. Steps
| Step | Action (exact commands) | Budget |
|---|---|---|
| 0 | `roadmap agent-guide`, then `roadmap project init <path>` and `roadmap project add <path> --name "<name>"` | 1k |
| 1 | Ask at most 5 questions in one message: goal, users, platforms, deadline, hard constraints. Write `01-brief`. | 3k |
| 2 | Domain and similar products: at most 5 web searches and 3 page fetches. Write `02-landscape`: competitors, features, what to copy or avoid. | 20k |
| 3 | Constraints and risks (technical, legal or platform, cost), each with a mitigation that becomes a task or a `!` item. Write `03-risks`. | 8k |
| 4 | Work breakdown: phases, then tasks of 5 to 150K each, with model, thinking, `!` and `c:`. Write `04-plan` with a roadmap-plan block. | 12k |
| 5 | `roadmap research check`, then `roadmap plan import docs/research/04-plan.md --dry-run`. Fix the lines it names and rerun until clean. Then the same command without `--dry-run`. | 3k |
| 6 | `roadmap status`. Show the output and the `you:` items, and ask the user to approve. | 2k |

Run `roadmap research new <slug> "<title>"` to start each note: it writes the template and the INDEX line.

## 2. Note template
Each note has `# Research NN: <title>`, then `## Question`, `## Findings` (bullets, each with its source),
`## Decisions` and `## Sources` (URLs only). A note is at most 120 lines and 6 KB, and there are at most 6 notes.
`roadmap research check` enforces this.

## 3. Plan grammar
Run `roadmap plan template` when unsure. The two record types:
```
P <id> <status> | <name>
T <id> <status> <tokensK> <model>/<thinking> [!] [c:<check>/<checkK>] | <title> [# <note>]
```
status is todo, partial, done, hold or `-`. model is haiku, sonnet, opus or `-`. thinking is low, medium, high or `-`.
A task id is `<phase>.<n>`. Example block for `04-plan.md`:
```roadmap-plan
P P1 todo | Foundations
T P1.1 todo 20 haiku/low | Scaffold repo and lint
T P1.2 todo 40 sonnet/medium c:sonnet/8 | Data model and storage layer
T P1.3 todo 5 haiku/low ! | Create the hosting account # needs your login
P P2 todo | Core features
T P2.1 todo 80 opus/high c:opus/15 | Sync engine design
```

## 4. Model choice
- haiku with low thinking: mechanical work, docs, tests for finished code.
- sonnet with medium thinking: multi-file work with a clear design.
- opus with high thinking: design, security, hard debugging. Add `c:sonnet/<K>` or `c:opus/<K>` to risky tasks.
- Estimate each task in K tokens (5 to 150). Small one-file change 10 to 30, a few files 30 to 80, large 80 to 150.

## 5. The `!` rule
Mark a task `!` when the user must act: accounts, secrets or API keys, payments, hardware, approvals, or a decision
only they can make. Never write a secret into the plan or a note.

## 6. Re-planning later
Do not read the whole plan. Run `roadmap plan export --phase P1`, change the few lines that differ, then
`roadmap plan import docs/research/04-plan.md --dry-run` and the same command without `--dry-run`.

## 7. Stop and ask when
- a step is over its budget: stop and report the step and its cost;
- a missing answer would change the plan: ask the one question and wait;
- a check or a dry run still fails after two fixes: stop and show the lines it names.

## 8. Done when
`roadmap status` shows the board, and the user has approved the `you:` items.
