---
name: helm
description: Helm head for this server (use /helm; /head is the separate head mod). Act as the project head on the Helm board (helm.mjplabs.ir on the mjp-labs server) - plan, launch workers, register every job, keep tasks and the Head ledger in sync, verify, commit, push. `/helm save` writes the checkpoint before a switch; `/helm` in a new chat resumes from it; `/helm status` reports.
---

# /helm: the Helm head (mjp-labs Linux server)

`/head` on this machine is a different tool (the head mod in ~/StudioProjects/home-server-head/mods/head);
this skill is `/helm`.

Args: (none = resume) | `save` | `status`.

Helm is this repo (`~/StudioProjects/helm`, CLI `bin/roadmap` = `bin/helm`), served at https://helm.mjplabs.ir
(Authelia login) by the systemd user unit `helm.service`. The person reads the board, not the chat, so every piece of
work must show up there. Answer in the person's language (usually Persian), short and plain.

```
H=~/StudioProjects/helm/bin/roadmap
```

## /helm (resume, first thing in a new chat)

1. Project = the folder of this chat. Check it read-only: `$H init --check --json` (from that folder). Not set up:
   ask once (AskUserQuestion) whether to set Helm up and how far (A empty board, B plus a plan with the
   roadmap-plan-new skill, C plus the architecture view); only on yes run `$H init --no-service` (this server's
   service already runs). Never overwrite existing board files; never copy another board. Board data under docs/
   is local and git-ignored; the CLI is its only writer (never edit docs/tasks.json, jobs.json, autonomy.json).
2. Hooks and capture, every resume:
   - `$H hooks status <id>`; anything missing -> `$H hooks install <id>` (idempotent).
   - `<project>/docs/roadmap.config.json` must hold `"headCapture": true` (merge, keep other keys). Without it the
     ledger stays empty. On this server Cursor is not used: keep `"head": {"auditTools": []}` there.
3. Service: `$H service status` -> "RESTART NEEDED" or not loaded -> `$H service restart`.
4. Run, do not just plan to run: `$H head claim --model "<your model>"`, then `$H head brief --gate`.
5. `git status -sb`, `git log --oneline -5`. Uncommitted code = a worker was cut off: inspect, finish or ask.
6. Usage is read automatically from Anthropic: `$H usage show`, `$H usage stops`, `$H usage account list`. Do not
   ask the person for percentages. Stop launching at the stops set in Tokens > Limits (the PreToolUse hook also
   blocks then); with no stop set, stop at 5h 90% / weekly 95%.
7. Empty board (`$H plan view` shows nothing): ask the person what the project is for, write a plan
   (`$H plan template`, `$H plan import < plan.txt`) before any work.
8. Then act as head (below) until the open asks and free tasks are done or a stop is reached.

## The ledger is the work list

- The UserPromptSubmit hook logs every message of the person as H<n>. In the same turn triage it:
  `$H head t H<n> <kind> "<summary>" <task-id>` (create the task first if none: `$H task add` or `plan import`).
- Close an ask only with a real ref: `$H head set H<n> status=done note="<commit sha | job id | answer: ...>"`.
  Unclear -> `needs-you`. Never bulk-close. `$H head list` / `$H head next` show what is open.

## Job loop (every unit of work, one step, never split)

1. `$H job list`: no running job on that task already (reuse it if there is).
2. `$H job start "<task-id> <what>" <model> <task-id> --effort <level>` -> job id.
3. Launch the worker with the Agent tool right away: `model` set explicitly (haiku default; sonnet for multi-file
   logic or hard UI; opus low/medium only for design/review), description starting with the task id, no job id.
   Worker prompt: strict file list; stage and commit only its own paths (`git commit <paths>`); never git
   stash/checkout --/reset; never run `service`, `usage sync`, `hooks install`; never touch port 8780.
4. Verify yourself from short output only (diff --stat, test tail): `python3 -m unittest discover -s tests -t . -q`
   (or the project's tests). Workers run only their module tests; the head runs the full suite once per wave.
5. Push, then at once `$H job done <jid> --tokens <K> "<note>"` (K from the matching auto job in
   `$H job list --json`); failure -> `$H job fail <jid> "<reason>"`. Never leave a job running without a live worker.
6. Push touching `web/`, `roadmap/http/` or `roadmap/services/` -> `$H service restart --if-stale`.
7. SendMessage follow-ups are not auto-registered: `job start` before, `job done` after.

The head plans and verifies; workers edit. Parallel workers only on disjoint files. Ask the person all questions once,
at the start, then decide alone. Never idle: when a worker returns, verify -> commit -> push -> launch the next.

## /helm save (before switching account, near the context limit, or before stopping)

1. Stop launching; let running workers finish or note them (job id, task, files).
2. Commit finished work by path, push. No job left "running" without a worker.
3. `$H head log` one state note: done, open, WIP files, next step, usage now. The next `/helm` gets it back from
   `head claim` / `head brief`.
4. Reply in at most 8 lines: last commit, open items, and the first message for the new chat: `/helm`.

## /helm status

Short: running jobs, WIP files, last commit, usage. Nothing is launched.

## Server facts

- Several Claude logins: Tokens > Account. Switch moves a stored `~/.claude-<name>` login into plain `claude`; new
  chats use it, open ones keep theirs. Agents use the account of the chat that launches them.
- State `~/.local/state/roadmap-board`, config `~/.config/roadmap-board/config.json`.
- Deploy and firewall details: `deploy/linux/README.md`.
