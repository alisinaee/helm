Read-only review of the git write path. I'll inspect the commit, push, branch, switch, and revert guards and report findings in this chat.

Skill is for `/review-security` diffs. This request is a targeted read of the git write path, so I'll inspect those modules directly.

Write path is in those two modules. Next I’ll check agent detection, public-op gates, and how path and ref checks are actually enforced.

Read-only review of the git write path. Nine findings. `shell=False` list argv holds, and `valid_rel_path` still jails `..`, absolute paths, and a symlink whose target leaves the repo. The holes are identity, policy, and path scope.

### High

1. `roadmap/services/gitops.py:50` (also `:274`, `:315`, `:340`) — **Agent check is `CLAUDECODE` or source `agent` only.** `refuse_if_agent` / `_is_agent` do not look at `CURSOR_`, `AGY_`, `ANTIGRAVITY_`, `CODEX_`, or `CLAUDE_CODE_`. `commands.write` labels the CLI with `source_name()`, which uses that same check. A Cursor, agy, or Codex shell is source `cli`, so it is the person: `git.revert` runs, the protected-branch and `push: off` blocks are skipped, and `git.branch` may create any name, not only `agent/<task>`. `person_context` in `roadmap/services/agentguard.py:84` already treats those environments as not the person. HTTP is tighter: an unproven browser is source `agent`.
   **Fix:** Make `_is_agent` true unless `person_context(current_source())`. Call that for revert (require the person), push policy, and the `agent/` prefix. Add a CLI test with `CURSOR_AGENT=1` and no `CLAUDECODE`.

2. `roadmap/services/gitops.py:110` (also `:122`, `:314`) — **Push policy is the worktree file `docs/git.json`.** A detected agent can write `{"push":"task-done","protected":[]}`. An empty `protected` list passes the check (`all(...)` on an empty list is true) and replaces the default `main` / `master` / `release/*`. The next `git.push` then publishes `main`.
   **Fix:** Keep the mode and the protected list in `ROADMAP_HOME`, writable only from `person_context`. On the agent path, ignore the worktree file and always union `DEFAULT_POLICY["protected"]`. Reject a protected list that drops those names.

3. `roadmap/services/gitops.py:207` (also `:216`, `:227`) — **A directory path commits every file under it.** `_commit_path` accepts any path that is not a file when `git ls-files -- <path>` prints anything. A directory with one tracked file qualifies. Ownership is an exact match on that directory string (`:218`), so another job’s `src/app.py` is not owned when the path is `src`. `git add -- src` then stages every change under `src`, including untracked files.
   **Fix:** Reject directories. For a deletion, require `ls-files -z -- <norm>` to be exactly that one path. Run the same check inside the data lock immediately before `add`.

### Medium

4. `roadmap/services/gitops.py:218` (also `:184`) — **The other-job guard trusts the caller’s `job` id.** `owner != a["job"]` lets anyone who can read `jobs.json` pass the owner’s id and commit that job’s files. Owner keys are stored raw, so a list entry `./a.txt` does not match the normalized commit path `a.txt`. On this Mac, `core.ignorecase` makes `Readme.md` and `readme.md` the same file and the map misses it.
   **Fix:** Normalize owner paths with `valid_rel_path` before compare, and compare case-insensitively when the repo’s `core.ignorecase` is true. Do not let the request body grant the exception; tie it to the job this process actually started.

5. `roadmap/services/gitops.py:322` (also `:315`) — **`after-check` is the boolean `checked` in the request.** The agent sets `"checked": true` and no check result is read. `task-done` has no task-status check at all; any non-protected branch pushes.
   **Fix:** Have `make check` write a stamp (time, HEAD sha) that the push reads. Drop the client boolean. For `task-done`, require that task id to be done in the task store.

6. `roadmap/services/gitops.py:319` (commit `:214`, switch `:388`) — **Protected branches apply only to agent push.** A detected agent can `git.switch` to `main` and `git.commit` on it. `fnmatchcase` is case-sensitive, so a branch `Main` is not `main` (`:129`). On a case-insensitive volume that can be the same ref.
   **Fix:** If the actor is an agent, refuse commit when the current branch matches protected, and refuse switch when the target does. Compare with `casefold` when `core.ignorecase` is set. Treat `release/*` with a matcher that cannot be dodged by `Main`.

7. `roadmap/services/gitops.py:327` — **`git push` does not pin how git pushes.** `remote.<name>.mirror=true` makes this invocation a mirror push: force-update and delete remote refs, including protected ones, instead of the `refs/heads/<branch>:<same>` refspec built here. `core.sshCommand` and an `ext::` / `fd::` remote URL run a program. `shell=False` does not cover that. Aliases that hide `push` or `commit` are ignored by git, so that part holds. Repo hooks on commit and push are what `docs/GIT-SPEC.md` asks for.
   **Fix:** On the push argv, set `-c remote.<name>.mirror=false` and `-c core.sshCommand=ssh`. Refuse a remote URL whose scheme is not `https`, `ssh`, `git`, or `file`. Refuse `core.hooksPath` that resolves outside `<git-dir>/hooks` if you do not want the spec’s hook behavior.

8. `roadmap/services/gitops.py:251` and `roadmap/services/commands.py:487` — **Person-only revert stops at the forward op.** `git.uncommit` and `git.branch.drop` are not public, but `undo` is, and it runs those handlers with no second person check. The origin check is phone-only. A detected agent can undo the person’s revert (`git reset --soft HEAD^`) or force-delete the person’s new branch (`git branch -D`) while the tip sha still matches. Push does not take `lock.locked` (`:304`), and uncommit’s “not pushed” check (`:260`) does, so a push can land between the ancestor check and the soft reset.
   **Fix:** In `undo`, allow an agent to reverse only an activity whose source is `agent`. Require `person_context` to undo `git.revert`. Hold the same data lock across push and across the not-pushed check plus `reset --soft`.

### Low

9. `roadmap/services/git.py:234` (push skips it at `gitops.py:327`; in-progress at `git.py:223`) — **`index.lock` is never deleted; that part holds.** The busy check does not. It joins `rev-parse --git-path index.lock` onto the worktree and uses `exists` (follows symlinks, misses a broken symlink). A linked worktree’s `.git` file makes that path miss the real lock, so the guard fails open. Git’s own `O_EXCL` lock still runs. There is a gap between the check and `git add`. Push never checks. `in_progress` only sees merge and rebase, so a conflicted revert or cherry-pick does not trip commit, switch, or revert. `git add` / `git commit` do not pass `--literal-pathspecs` (`gitops.py:227`); the denylist of `*?[]{}` and a leading `:` is the only pathspec block. `_pushed` (`gitops.py:243`) puts the upstream name from stdout into the next argv.
   **Fix:** Take `--absolute-git-dir`, `realpath` it, and `lexists` only `<git-dir>/index.lock`. Call that at the start of push too. Treat `CHERRY_PICK_HEAD`, `REVERT_HEAD`, and bisect like merge. Pass `--literal-pathspecs` on `add` and `commit`. Use `merge-base --is-ancestor <sha> @{u}` so the upstream name is not a second argv.

