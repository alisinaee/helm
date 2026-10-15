# Head agent v2: the tool thinks, the model executes (R7.64, design only, 2026-10-15)

Goal (the person): the head does all of it (run, check, commit, update board and asks, comment), any model can be head
(Haiku, Cursor, Gemini), and an Opus head stays cheap. Principle: put the head's judgement in `bin/roadmap`, so the
model reads at most 15 lines, runs the printed commands, and records each one.

## 1. Diagnosis
- The head's state machine lives in prose (SKILL.md 48 lines + RUNBOOK 69 + SPEC 264 + HANDOVER). A weak model cannot
  hold it, so it asks permission each step and idles; a strong model re-reads it every turn and burns tokens.
- The gate (`head brief --gate`, Stop hook) says WHAT is open ("H121 bound 7m: ...") but never the next COMMAND. A
  model with no plan loops on the same block.
- Nothing links events to state: job start does not set the task to doing, a commit naming R7.44 does not mark it,
  an ask is not closed when its tasks are done. The head must remember each step, and it forgets.
- Ask-close has no guard: the tool accepts `status=done` with any note, so ~13 asks were bulk-closed with a generic
  note, and binding to the umbrella R7.31 alone was only refused late (R7.34).
- Job registration depends on luck: an Agent call is tracked only if its description has a task id; cursor-job.sh
  hardcodes R7.31 (head hand-edited docs/jobs.json); agy-queue takes a task id, the others do not.
- Limits are in 4 places that disagree (CLAUDE.md 90/95, SKILL 80/95, RUNBOOK 80/85, autonomy.json weekly 85 +
  fiveHour 90). `usage show` prints STALE but no command refuses a launch on a stale or over-limit reading.
- Worker failure is invisible: OpenCode "Insufficient account funds" sat in logs; no runner marks the job failed with
  a reason, so the head reads logs (long outputs = tokens).
- Worker prompts are hand-written each time, so rules (file list, temp ROADMAP_HOME, no push) drift or get dropped.
- Verification is manual reading of diffs and test output; there is no "verify job J" that runs the right tests for
  the job's files and prints pass/fail in one line.

## 2. Target head loop (any model)
```
0. bin/roadmap head next            # <=15 lines: numbered actions A1..A5, each an exact command, or "idle: reason"
1. For each action in order: run its command exactly. Never edit docs/*.json by hand.
2. Action kind "launch": paste the brief from `bin/roadmap brief <T>` as the worker prompt (Agent: description
   "<T> <title>", model as printed). Runners (cursor/agy/opencode) are launched by the printed shell line.
3. Action kind "verify": run `bin/roadmap verify <J>`; pass -> next action it prints (commit); fail -> `job fail`.
4. Action kind "ask": copy the printed question to the person in one line, then stop the turn.
5. After each action: `bin/roadmap head done <A-id> [--ref commit:<sha>|job:<J>]`.
6. Repeat from 0 until it prints "idle" or "stop". Then reply to the person in <=5 lines and end the turn.
Never ask permission for printed actions; only kind "ask" goes to the person. Never read files the action did not name.
```

## 3. Tool packages (ordered; S/M/L; parallel groups marked)
Group A can run in parallel (disjoint files). B needs A1+A2. C needs B1.

A1 (S) **One limits source + budget guard.** `roadmap/services/budget.py` gains `guard()` reading only
docs/autonomy.json (5h stop, weekly stop, `maxUsageAgeMin` default 90). `job start` refuses past a stop (exit 3,
"stop: weekly 86% >= 85%") and warns on stale usage ("usage 3h old: run usage push"). Files: services/budget.py,
commands/job.py, docs/autonomy.json (fix fiveHour to 80 only if the person confirms). Test: start refused at 86%,
allowed at 84%, stale warning after 91 min.

A2 (M) **Event-driven status.** `job start` with task T -> task T partial (doing) if todo. `git commit` (roadmap git
commit and the PostToolUse Bash hook for git commit) parses `R\d+\.\d+` in the message -> appends `commit:<sha>` to the
task and the job; prints "done candidate: R7.44 (job j701 closed)". Asks fold: when every bound task is done, the ask
becomes done with note "auto: R7.44 c1a2b3c, R7.45 d4e5f6a" (person still reviews). Files: services/jobs.py,
services/gitops.py, services/head.py (fold), hooks.py (commit detector). Test: start->partial; commit msg ->
commit ref on task; ask auto-done note lists the real shas; ask with an unfinished task stays open.

A3 (S) **Ask-close guard.** `head set Hn status=done` requires a note with a real ref (commit sha that exists, job id,
or `answer:` text >= 20 chars that is not a repeat of another close in the last hour); refuses more than 3 closes per
minute ("use head next"); refuses binds to umbrella tasks alone (extend R7.34 rule to `head t`). Files:
commands/head.py, services/head.py. Test: generic note refused; 4th close in a minute refused; real sha accepted.

A4 (S) **Runners take a task id and report failure reasons.** cursor-job.sh: `cursor-job.sh <TASK> "<title>"
<effort> <out> "<prompt>"` (no hardcoded R7.31). New `tools/oc-job.sh` (OpenCode) and agy-queue use `job fail <J>
--reason "<first error line, 80 chars>"`; known patterns (Insufficient account funds, 403, Cannot connect) set the
engine `unavailable` in a small state file for 6 h so `head next` stops proposing it. Files: tools/cursor-job.sh,
tools/oc-job.sh (new), commands/job.py (`--reason`), services/jobs.py. Test: fail with reason stored; engine
marked unavailable; cursor job binds the given task.

A5 (S) **Agent jobs always bound.** hooks.py AgentDetector: no task id in description -> look in the prompt; still
none -> bind to the task of the newest `head next` launch action (state file) and log it; never drop the job. Files:
roadmap/services/hooks.py. Test: description "Opus review" + prompt containing R7.40 -> job on R7.40.

A6 (S) **Compact output contract.** Every head/job/task/git/verify command prints <= 15 lines by default (`--full`
for more); errors are one line plus `next: <command>`. A test walks the CLI and asserts line counts on fixture data.
Files: commands/*.py (trim only), tests/unit/test_cli_compact.py. Test: as stated.

B1 (M) **`roadmap brief <T>`: worker prompt generator.** From tasks.json (title, files, spec ref), rules.txt and the
runbook worker rules it prints the full prompt: task, strict file list, spec pointer, temp ROADMAP_HOME, forbidden
commands, test command for those files, commit message "<T> ..." with Co-Authored-By, report in 5 lines. Tasks with
no file list -> refuses and prints `task set <T> files=...`. Files: commands/brief.py (new), services/briefs.py (new),
tasks schema gains `files` (optional). Test: output contains every rule and the file list; refuse without files.

B2 (M) **`roadmap verify <J>`.** For the job's task files: `git diff --stat` on them, files outside the list (fail),
the matching tests (tests/**/test_<module>*.py plus the task's `tests` field), `make check` when web files changed.
One line out: "pass j701: 3 files, 41 tests; next: roadmap git commit <paths> -m '<T> ...'" or "fail j701: <first
failing test>". Files: commands/verify.py (new), services/verify.py (new). Test: stray file -> fail; green -> commit
line with exact paths.

C1 (L) **`roadmap head next` and `head done`.** The planner (pure function, like `head.gate`) over ledger rows, tasks
(todo, files, deps), running jobs, git dirty/unpushed, usage guard, engine availability. Priority: stop/limit ->
"stop"; finished jobs -> verify; verified -> commit/push; unbound or new asks -> `head t` with a suggested task (dup
heuristic) or create one; done-candidate tasks -> `task done` + ask fold; free tasks whose files do not overlap running
jobs -> launch (model by rule: edits haiku, audits agy, reviews cursor; skip unavailable engines); stale usage ->
kind "ask" with the exact question; nothing -> "idle: <reason>". Each line: `A3 launch R7.45 haiku files=3 ::
<command>`. `head done A3 --ref ..` records it in head.jsonl (action log) so a new head resumes mid-plan. Files:
services/headnext.py (new), commands/head.py (next, done). Test: fixture boards for each branch produce the expected
first action; overlapping files never launched twice; limit -> only "stop".

C2 (S) **Stop gate prints commands.** hooks._stop_gate uses `headnext.plan()[:3]` and emits "continue: A1 <command>;
A2 ..." instead of ask lists; a gate that repeats the same top action 3 times escalates to kind "ask" (no loop).
Files: roadmap/services/hooks.py. Test: block reason contains a runnable command; 3rd repeat -> ask.

C3 (S) **Skill v2.** Replace ~/.claude/skills/head/SKILL.md with section 4 below; RUNBOOK keeps only person rules
the tool cannot hold. Files: the skill, docs/HEAD-RUNBOOK.md. Test: `make check` docs lint; skill <= 30 lines.

## 4. Skill (<= 30 lines) vs tool
Stays in the skill (target text, ~25 lines):
```
You are the head. Permission is given: run every action `head next` prints without asking.
Start: cd ~/Works/roadmap-board; bin/roadmap head claim --model "<you>"; then the loop:
  1. bin/roadmap head next      (read only its output)
  2. run each action's command exactly; launch = Agent with prompt from `bin/roadmap brief <T>`,
     description "<T> <title>", model as printed; runners by the printed shell line
  3. bin/roadmap head done <A-id> --ref <commit|job>
  4. repeat until "idle" or "stop"; then reply in <= 5 lines.
Log every person message first: bin/roadmap head log "<verbatim>" (the hook may already have done it).
Kind "ask" actions: put the printed question to the person, end the turn.
Never: edit docs/*.json or docs/*.jsonl by hand, close asks yourself without a ref, read whole files or logs,
use `git add -A`, push --force, touch port 8780, ~/.claude, keychain, the person's browser tabs.
If a command fails: run the `next:` line it prints; if none, `head next` again; twice the same failure -> ask.
/head save: bin/roadmap head save (writes the checkpoint to HANDOVER section 0), push, reply with its output.
Opus head: no file reads beyond printed paths; workers do all edits; review only on "review" actions.
```
Moves to the tool: what to launch and on which model, file-overlap check, limits and stale usage, job registration
and binding, task status changes, ask binding suggestions and fold-close with shas, verify (tests per file), commit
paths and message, idle-engine detection, worker prompt rules, handover checkpoint (`head save` = M package after C1).

## 5. Token budget per head turn (targets)
| Item | Haiku / Cursor / Gemini head | Opus head |
|---|---|---|
| `head next` output | <= 15 lines (~400 tok) | same |
| per action (command + result) | <= 300 tok in, 1 line out | same |
| worker brief | generated, never echoed (~0 head output) | same |
| verify | 1 line result; diff read only on fail (<= 60 lines) | hooks/security diffs only |
| turn total, 5 actions | <= 6k in, <= 1k out | <= 4k in, <= 600 out |
| reply to person | <= 5 lines | <= 5 lines |
| resume (`/head`) | claim + next <= 2k tok; no HANDOVER read unless `next` prints it | same |
Hard rule in the tool: any output > 15 lines is a bug (A6 test). Opus effort low for the head loop; medium only on a
printed "review" action.
