---
name: helm
description: Use when the user mentions Helm, the roadmap board, `/helm`, or wants to set up or resume project tracking. This is the entry point for everyone.
---

# Helm entry

## Rules
- Never open or edit `docs/tasks.json`, `docs/jobs.json` or `docs/autonomy.json`. The roadmap CLI is the only writer.
- Never run `bin/roadmap init` before the user says yes.

## 1. Check (budget 0.3k tokens)
```
bin/roadmap init --check --json
```
Read-only. If it errors, say so and stop.

## 2. Already set up
If the project is registered and its data files are present:
- Show the status in 3 lines.
- Do not run init again.
- Offer `/head` to resume as project head. Stop.

## 3. Ask first
If not set up, ask with AskUserQuestion: "Set up Helm for this project?" (yes / no). On no, stop.

## 4. Ask how far to go
Ask with AskUserQuestion:
- A) empty board only.
- B) A plus a plan: analyse the project (README, code layout) and add phases and tasks with the roadmap-plan-new skill.
- C) B plus the architecture view (`bin/roadmap system`, docs/system.json).

## 5. Set up (budget 0.5k tokens)
```
bin/roadmap init --no-service
```
Start the service only if the user agrees. Then run the chosen extras.
Never overwrite existing board files. Never copy anyone else's board.

## 6. Finish
Tell the user where to open the dashboard: `bin/roadmap open`.
