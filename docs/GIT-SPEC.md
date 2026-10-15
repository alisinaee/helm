# R7.29 Git section and agent git (spec)

Goal: the person sees and controls every agent change. Git is the truth; roadmap reads it and runs a few safe, logged writes.

## 1. Scope and reads
- One repo per registered project = its project path. No repo: empty state "Not a git repo" + hint `git init` (we never run it). Submodules: listed as one row, not entered.
- **Status**: branch, upstream, ahead/behind, detached flag, in-progress merge/rebase (read-only banner + hint "finish in a terminal"), conflicts list. Files (staged / changed / untracked) grouped by owner: running or recent job (its file list from jobs.json) > task > "unattributed".
- **History**: `git log` rows: short sha, author, rel. time, subject, files count, linked task/job. Link = trailer `Task: R7.12` / `Job: j123` in the message, else the job registry (`jobs[].commits`).
- **Commit detail**: files with +/-; diff viewer read-only, per file 200 KB / 2,000 lines cap, binary and >1 MB files skipped ("binary, 3 MB"), whole response 1 MB cap.
- **Branches**: current, local list with ahead/behind vs upstream, last commit time. **Tags**: list only. Stash, blame: skipped in v1.
- **Timeline**: one row per job with its commits and files ("what did this agent change").
- New refs (R7.12): kinds `commit` (`rb:p/commit/1a2b3c4`, 7-40 hex) and `branch` (`rb:p/branch/agent.R7.12`, `/` written as `.`). `roadmap ref` resolves both.

## 2. Writes and who may do them
Every write is a commands.py op (`git.commit`, `git.push`, `git.branch`, `git.switch`, `git.revert`): validated, one activity line, `core.write` log event, undo where sensible.

| op | agent | person | undo |
|---|---|---|---|
| commit (explicit paths only) | yes, own paths + trailer | GUI "Commit selected" | soft reset, only if unpushed and still HEAD |
| push | only if project policy allows | yes | none (never force) |
| branch create | yes (`agent/<task>`) | yes | delete if no new commits and not current |
| switch | yes, clean tree only | yes, clean tree only | switch back |
| revert (new commit) | no | yes | soft reset if unpushed |
| tag, PR via `gh` | later | later | - |

Never offered: discard, reset --hard, clean, checkout of paths, amend of pushed commits, merge, rebase, force push (say so in the GUI help line). Push policy per project in docs/git.json: `off` (default) | `after-check` (after green `make check`) | `task-done`. Protected branches list (default `main`, `master`, `release/*`): agents never push there without the person. Person-only ops use `agentguard.refuse_if_agent`.

## 3. Safety model (roadmap/services/git.py)
- `subprocess.run([git, ...], shell=False)`, git path resolved once; cwd = registered project path after `realpath`, must equal the stored path (symlink escape refused).
- Env scrubbed: `GIT_TERMINAL_PROMPT=0`, `GIT_PAGER=cat`, `PAGER=cat`, `GIT_OPTIONAL_LOCKS=0` for reads, `LC_ALL=C`, no `GIT_DIR`/`GIT_WORK_TREE`/`GIT_CONFIG*` from the caller. Hooks: reads trigger none; commit runs the repo's own hooks (they are its checks), and status shows `core.hooksPath` when set outside `.git/hooks` so a surprise is visible.
- No `-c` or option from user input: every arg built by us; refs checked with `git check-ref-format` rules + `^[A-Za-z0-9._/-]{1,100}$`, no leading `-`; paths relative, inside repo, no `..`, always after `--`.
- Timeouts 5 s reads, 30 s commit, 60 s push; stdout cap 2 MB; stderr cut to 400 chars.
- Secrets: remote URLs redacted (`https://***@host/...`); credential helpers never invoked for reads; push output redacted; diffs of files matching `.env*`, `*.pem`, `*key*`, `id_*` shown as "hidden (secret pattern)".
- Index lock: if `.git/index.lock` exists, writes answer "busy, retry" (no deletion). One service lock per repo for our own writes.
- Phone listener: status, branches, log only; no diffs, no writes. Write routes: existing `_write_guard` (CSRF, Origin, JSON) via `POST /api/v1/cmd`.
- Log events: `core.write` op `git.*` (paths count, sha, never content); new `core.git` (cmd verb, ms, exit code) DEBUG only.

## 4. Agent interface (token-cheap)
- `roadmap git status` (<= 8 lines: branch, ahead/behind, counts, top 5 files with owner).
- `roadmap git log [--task R7.12] [--job j12] [-n 10]` (one line each).
- `roadmap git commit <paths...> -m "msg" [--task T] [--job J]`: adds trailers, stages exactly those paths, refuses a path owned by another running job, refuses an empty path list, never `-A`.
- `roadmap git push` (policy checked, prints the reason when refused), `roadmap git branch [new <name>|switch <name>]`, `roadmap git show <sha> [--stat]`.
- `job done` auto-links: commits since the job's start whose trailer names the job, else HEAD commits by the head that touch the job's files.
- Skills: worker "`roadmap git commit <own paths> -m ... --task T`; never push." lead "`roadmap git status` before each wave; `roadmap git push`."

## 5. GUI
- Left nav item "Git" (branch icon). Tabs: Changes, History, Branches, Timeline. Rule 0 grid: sha | subject (ellipsis) | task | author | time | files (right, tabular) | actions (fixed column: copy-ref, open).
- Filters: task, author, branch. Changes tab: "Uncommitted by job" panel with checkboxes, "Commit selected" (message field, task picker).
- Push button with policy banner ("Auto-push: off. Protected: main."). Overview chip "ahead 3 / dirty 7". Empty, no-repo, detached, conflict states. Phone: read-only, no diffs.
- Data NOT in the shared snapshot: `GET /api/v1/projects/{pid}/git/{status|log|branches|show/{sha}|diff/{sha}?path=}`, cached 3 s TTL (status) / 30 s (log), invalidated after our own writes. Overview chip reads the status route lazily.
- CSS: new web/css/git.css <= 2 KB, reusing work.css row grids and the diff colours from tokens. Budget: 69.1 of 72 KB used; free room by stripping comments in components.css (about 1.7 KB) and flow.css (0.4 KB).

## 6. Breakdown (Haiku, in order, no file overlap)
1. Core: roadmap/services/git.py (runner, validation, parsers, redaction, caps), tests/unit/test_git_service.py (temp repos).
2. Read routes: roadmap/http/routes.py hunk, roadmap/core/refs.py hunk (commit/branch), tests/unit/test_git_routes.py.
3. Write ops + guards: roadmap/services/gitops.py, roadmap/services/commands.py OPS hunk, docs/git.json schema, tests/unit/test_git_ops.py.
4. **Gate: Cursor grok-4.7-xhigh security review of 1-3** (argv, paths, env, redaction, guard).
5. Commands: roadmap/commands/git.py, roadmap/cli.py COMMAND_MODULES hunk, job done link in roadmap/commands/job.py, tests/unit/test_git_cmd.py.
6. GUI: web/js/views/git.js, web/css/git.css, nav.js + routes.js hunks, comment strip in components.css, tests/web/test_git_view.py.
7. Docs/skills: docs/SECURITY.md section, skills lines, docs/UI-SPEC.md row.
8. agy audits: (a) spec vs code gap list; (b) every git argv built from input, listed. Both verified by a Haiku.

## 7. Risks
Destructive ops (none offered); secrets in diffs (patterns miss unusual names); huge repos (caps, timeouts, over 5,000 untracked files: `-uno` with a note); workers holding index.lock (busy reply); detached HEAD (banner, commit refused); submodules (row only); line endings/filemode noise (shown as git reports).

## 8. Questions for the person
1. Auto-push default: off, after green check, or on task done?
2. Protected branches: `main`, `master`, `release/*` enough?
3. Agents on `agent/<task>` branches, or all on the current branch?
4. Who commits: workers with `roadmap git commit`, or only the head (as today)?
