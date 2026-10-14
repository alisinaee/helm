# agy playbook (Gemini 3.8 Flash, unlimited quota, weak model)
## Good at
- Reading many files and filling in a table: audits, lists, diffs between docs and code
- Writing new files from an exact example of the shape
- Prose drafts, but only when every fact comes from a facts file we give it
## Bad at
- Facts it has to work out itself: meanings, caps, folders, counts. About 30-40% are wrong.
- Anything that needs running code: tests, CLI, browser
- Edits across several files, and logic that must stay consistent between them
## Give it (8 job types)
1. Audit table (docs vs code, aria, CSP, strings, colours) -> new file under docs/reviews/agy-*.md
2. Test-gap list for one module -> table: function, missing case, expected result
3. Fixture JSON from a shape reference -> new files only
4. Doc section draft from docs/facts/FACTS.md -> one section of one doc
5. Command list vs docs diff (README, RELEASE, skills)
6. CHANGELOG bullets from the change notes plus FACTS.md
7. Docstring/comment pass on one module (comments only)
8. Plain-words rewrite of UI strings -> a proposals table, not edits
## Never give it
Running code; refactors across files; hooks, agentguard, security or limits logic; UI visuals or CSS;
anything that needs the git history; any file another worker owns.
## Prompt template (always this order)
GOAL: <one sentence>
READ ONLY THESE FILES: <list, at most 8>
FACTS FILE: docs/facts/FACTS.md (the only source for commands, caps, paths)
WRITE ONLY: <one path>  (audits: write a new results file; never edit other files)
OUTPUT FORMAT: <exact table columns, or the exact shape example>
SIZE CAP: <= N rows / <= N lines
RULES: Do not run commands. Do not guess: write UNKNOWN. Cite file:line for every claim.
ACCEPTANCE: <one checkable line, e.g. "every row cites a real file:line">
Reply DONE plus the line ranges you wrote.
## Slicing (1-8 min)
At most 8 files read and 1 file written per job; split view folders a-k / l-r / s-z.
Edits: at most 1 file and 60 changed lines. If a job times out, halve it and rerun.
## Verify (by job type)
Audits and gap lists: Haiku (5-10k tokens) greps 3 random rows; tests written from gap lists must fail before the fix.
Fixtures: Haiku (5k tokens) runs a loader test or json.tool.
Doc edits: Haiku (10-15k tokens) checks every command against check_docs.py and greps 3 claims against FACTS.md.
Comment passes: head checks that `git diff -U0` changes only comment or docstring lines, then runs make check.
Rewrite tables: the head picks which rows to keep (2k tokens); a Haiku applies them.
## Failures
'Eligibility check failed' or a network error: rerun automatically, at most 2 times (60 s wait).
403 login: stop the queue and ask the person to run `agy` and /login (the VPN must be on).
A timeout: halve the job. A wrong answer twice: give the job to Haiku.
Any change outside WRITE ONLY: `git checkout -- <path>`, then reject the job.
## Concurrency
Read-only and new-file jobs: 3 at once (AGY_MAX=3). Try 4 after a clean batch of 10.
Jobs that edit existing files: 1 at a time, or each in its own git worktree (cwd = worktree),
because the companion's change report cannot tell which of several parallel jobs made a change.
## Queue 20+ jobs
python3 tools/agy-queue.py jobs.json ~/Works/roadmap-board <results> [--after JOBID]
Use one jobs.json per wave. Ids look like a01... and the results go to <results>/<id>.md.
The head reads only the DONE lines and the verifier's verdict.
