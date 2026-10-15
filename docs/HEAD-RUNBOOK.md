# Head runbook (how the head works here; read after HANDOVER.md)

The head plans, launches workers in parallel, verifies, registers, commits, pushes. It never idles while tasks exist
(unless the person said stop). Answers stay short.

## Loop
1. Pick every task whose files do not overlap running workers. Launch them all at once (Agent tool, model haiku).
2. Opus (low/medium) only for design or review advice; it writes one docs file, nothing else.
3. agy (unlimited, weak) for the 8 playbook job types (docs/AGY-PLAYBOOK.md); Cursor Auto for independent reviews.
   Both need the person's VPN. Verify every agy result with a Haiku; check `git status` after each agy job.
4. On every worker result: read the diff (hooks, launcher, security code: head reads it), close the job with tokens,
   commit by explicit path, push, show the board, launch the next wave.

## Register jobs (this board is authoritative since 2026-10-15; docs/AUTHORITATIVE stops the split-net sync)
Run from `~/Works/roadmap-board` (hooks do not fire here, so the head registers by hand):
- start: `bin/roadmap job start "<model>: <title>" <haiku|sonnet|opus|cursor|agy> <TASK>` (task id from docs/tasks.json, e.g. R7.16)
- done: `bin/roadmap job done <jid> --tokens <K>` (or `job fail <jid>`); live: `job progress`
- tasks: `bin/roadmap task done|start|hold <TASK>`; new work: `bin/roadmap plan import <file>` (T lines), `bin/roadmap feature link F<n> <TASK>`
- Never use split-net's jobs.py / rb-done.py / sync-rb-board.py for this project again. split-net is registered as its own project.

## agy queue (sandbox off; needs VPN)
`AGY_MAX=2 python3 ~/Works/split_net/tools/agy-queue.py <jobs.json> ~/Works/roadmap-board <results-dir>`
jobs.json = `[{"id","title","task":"R7.19","prompt"}]`; prompt follows the template in AGY-PLAYBOOK.md.

## Cursor Auto review (VPN, one at a time)
`tools/cursor-review2.sh <out.md> "<read-only review prompt>"` in the background, then register a `cursor` job.

## Worker prompt must say
Strict file list; stage only own files by path; temp ROADMAP_HOME; never run `roadmap service|serve|hooks install|usage
sync`; never touch port 8780, ~/.claude, keychain, split_net or the person's browser tabs; no network; no subagents;
do not push; commit with the Co-Authored-By line; report in 5-6 lines.

## Limits
Weekly stop 95% (docs/autonomy.json in split_net). Usage is not automatic: push it by hand (HANDOVER section 0, 6).
