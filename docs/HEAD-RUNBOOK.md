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
Strict file list; stage only own files by path; NEVER git stash/checkout -- /reset/pop (shared tree holds live board data and other WIP); temp ROADMAP_HOME; never run `roadmap service|serve|hooks install|usage
sync`; never touch port 8780, ~/.claude, keychain, split_net or the person's browser tabs; no network; no subagents;
do not push; commit with the Co-Authored-By line; report in 5-6 lines.

## Limits
No usage stop (H164, 2026-10-16: "rule: no limit"; see Usage limit override below). Usage is not automatic: push it by hand (HANDOVER section 0, 6).

## UX routine (after every wave; the person asked for it)
1. `make check-ui` (own headless Chrome) for fresh screenshots in build/ui-smoke; look at 1440 and 375, dark and light, for every section.
2. Run the ui-ux-pro-max UX queries (`python3 ~/.claude/skills/ui-ux-pro-max/scripts/search.py "<topic>" --domain ux -n 5`, no -I) for what changed.
3. Opus (medium) or Cursor with the screenshots writes findings; agy only for text-only view audits (aria, strings, rows) verified by Haiku.
4. File each finding as a task (`plan import` T lines, phase R8 'UX'), link to a feature, then run them as Haiku packages. See docs/UX-AUDIT.md.

## Usage limits the person set (obey)
- Usage source (2026-10-15): `roadmap usage sync` cannot work here: the keychain entry "Claude Code-credentials"
  holds only mcpOAuth (no claudeAiOauth) because the person signs in through the desktop app. The head reads the
  live numbers with the `get_usage` tool every turn and pipes them into `roadmap usage push`
  ({"rateLimits":[{"kind":"five_hour"|"seven_day","percentUsed":N,"resetsAt":ISO}]}).
- MODEL RULE (H151, 2026-10-15, general): Work items are human-level (Jira/Trello cards, plain words, outcome).
  Agent tasks are machine packages (files, model, done-check, jobs). One Work item binds many agent tasks; agent
  tasks never show as Work cards; Head asks bind to Work items. Design: docs/WORK-MODEL.md (R7.101).
- Usage stops lifted (H164, 2026-10-16): no weekly or 5-hour stop. Earlier values (H99 80% 5h, H160 98% weekly) are superseded. RP13 (80% and 95%) is superseded by this rule.
- Models (H99, H101): head runs on Opus. Haiku 5.5 for edits; Opus or Sonnet 5.5 low/medium only for critical review,
  hard issues and planning advice; Cursor (auto or grok-4.7) and agy without limit. Run as many parallel subagents as
  files allow, watch them, never idle.
- Permissions (H94, H98): full permission: act, commit and push verified work without asking.
- OpenCode (2026-10-15): the account has no credit ("Insufficient account funds"; the free big-pickle model fails with
  "Cannot connect to API"). Do not launch OpenCode jobs until the person tops it up; use Haiku instead.
- Ledger honesty: never bulk-close asks with a generic note. Close each ask with the real result (commit, job, answer);
  an agent cannot set `open` (person only): use `needs-you` for anything unclear or unverified.
- Agent tool jobs register only when the description carries a real task id (e.g. "R7.40 ..."). cursor-job.sh
  hardcodes R7.31: rebind the job's task in docs/jobs.json after it starts.
- Usage is not automatic here: ask the person for the current numbers (or read the Enter usage form), push them (`roadmap usage push`), and estimate burn from worker tokens between readings. Before every launch wave check the last reading; when unsure, ask.

## Priority order (person, 2026-10-15)
1. HEAD section (R7.31, docs/HEAD-SPEC.md H1-H12): highest priority; launch its next free step before anything else. Git/Work/Tokens/UX yield to it, but still run in parallel on disjoint files while workers are free.

## Head ledger (claim, brief, triage, review loop)
Run this loop every turn. The ledger (`roadmap head`) holds the person's asks, so nothing depends on memory.
1. **Claim (new chat or account):** `roadmap head claim --model "<model>" --acct <letter>`; it prints the carried-over asks. Then `roadmap head brief` (at most 15 lines).
2. **Triage:** for each `new` entry, `roadmap head t H<n> <kind> "<sum>" <refs..>` in one call. Use `roadmap head triage` for the list; `split` a message with two asks, `merge` a duplicate.
3. **Bind:** every open ask gets a link (task, issue, doc, commit, job). An ask with no link after 15 min is red in the GUI and in the gate; bind it or ask the person.
4. **Work:** launch the workers for the bound tasks, register the jobs, and tick the asks when their links move (`doing`, then `done` by the fold). The head may set `done` (`roadmap head set H<n> status=done note=".."`).
5. **Review:** the person confirms each done entry with `roadmap head review`, or reopens it with `roadmap head review H<n> reopen`. Only the person accepts (`head accept`). Ask the person when a review is unclear.
6. **Save:** before a switch, list the rules and decisions accepted since the last save for HANDOVER section 2b; do not duplicate the ledger in HANDOVER.

## Head AI duty (person, 2026-10-15)
Every ask, rule, decision or instruction the person gives goes into the Head ledger the same turn (hook or `head log`), is triaged and BOUND to real tasks (`head t ... --bind task:ID`; create the task when none exists), and stays current as jobs run (HEAD-SPEC section 12). The person must always be able to see what is running for each ask and which task serves it.

## Usage limit override (person, 2026-10-16)
"rule: no limit" (H164): the person lifted the Claude usage stops (85% weekly, 80% 5h, and the H160 98% weekly stop). Launch Claude Haiku work without waiting for resets; still check get_usage each wave and report readings. Stop only on a session-limit error.

## Cursor OFF (H193, 2026-10-16): near 99% limit, launch no Cursor jobs; ignore "cursor idle" hints.

## Planner-only head (person, 2026-10-16, H182; overrides older model rules)
Head plans and verifies only (no edits, no big reads). Models: Haiku 5.5 default worker; Sonnet 5.5 low/med for
wide logic/hard UI; Opus 5.5 low/med advice only; agy (unlimited) for every read-only job, verified by Haiku.
Budget this run: stop Claude workers at weekly 10% (start reading 2%). Decisions H182: merge Planner into Work;
delete Research section; archive all old board tasks and start a fresh plan; Git section uses vendored MIT libs
(no build step). Full rules: ~/.claude/skills/head/SKILL.md "Planner-only rules".
