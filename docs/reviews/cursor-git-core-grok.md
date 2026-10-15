Read-only review of `roadmap/services/git.py` and its tests. Findings stay in this chat — no plan or report file.

Skill is for `/review-security` diffs, not this file-level review. Reading both files and their call sites.

The read runner’s current git commands use fixed arguments plus a clamped integer. Two holes still let a registered repo or the server environment run a command, and the cap, redaction, and log parser do not hold the boundary the file claims.

## Findings

**1. High** — `roadmap/services/git.py:110` (`read_status` at `:169`)
`git status` compares the worktree through `run_diff_files`, which calls `refresh_fsmonitor`. If that repo’s config sets `core.fsmonitor` to a command, or points it at `.git/hooks/fsmonitor-watchman`, git executes it as a child of the roadmap process. `GIT_OPTIONAL_LOCKS=0` only skips the optional index lock; it does not clear this. A clone or an agent can write `.git/config`, and the next status poll runs that command. Nothing in the argv disables it.
Fix: on every read, pass `-c core.fsmonitor=` and `-c core.fsmonitorHookVersion=` before the subcommand. Add a temp-repo test whose `core.fsmonitor` would create a marker file and assert the marker is absent after `read_status`.

**2. High** — `roadmap/services/git.py:37` and `:97`
The module says the caller’s `GIT_*` environment is dropped. The filter removes seven names plus the `GIT_CONFIG*` prefix, then copies everything else. These still reach git and can run a program or write a file: `GIT_SSH_COMMAND`, `GIT_SSH`, `GIT_EXTERNAL_DIFF`, `GIT_EXEC_PATH`, `GIT_PROXY_COMMAND`, `GIT_ASKPASS`, `SSH_ASKPASS`, `GIT_TRACE`, `GIT_TRACE_PACKET`, `GIT_CURL_VERBOSE`, `GIT_TRACE2*`. `GIT_NO_LAZY_FETCH` is unset, so a partial clone can fetch during `git log` and then run `credential.helper` from repo or user config (`GIT_TERMINAL_PROMPT=0` only blocks the terminal prompt).
Fix: build the child environment by dropping every `GIT_*` key, then set only `GIT_TERMINAL_PROMPT=0`, `GIT_PAGER=cat`, `PAGER=cat`, `LC_ALL=C`, `GIT_OPTIONAL_LOCKS=0`, `GIT_NO_LAZY_FETCH=1`. On reads, also pass `-c credential.helper=` (empty value clears helpers). Extend `tests/unit/test_git_service.py:199` to assert those exec and trace variables are absent.

**3. Medium** — `roadmap/services/git.py:110` and `:124`; bypass at `:178`
The 2 MB cap is applied only after `subprocess.run(..., capture_output=True)` has already stored all of stdout and stderr. `read_log` never applies it: it calls `_git` and decodes the whole log. `%B` is the full commit message, so one large message (or 100 of them, up to `LOG_MAX`) is loaded with no limit, and `subject` is returned with no length cap. Stderr is also fully decoded before the 400-character cut at `:114`.
Fix: stream stdout and stderr, kill the child at `STDOUT_CAP + 1`, and apply that same path inside `read_log`. Cap `subject` (and author) before they leave the parser. Use `start_new_session=True` and kill the process group on timeout so a helper spawned by git does not survive the 5 s limit (`:112`).

**4. Medium** — `roadmap/services/git.py:178` and `:255`
Log records are split on raw `\x1e` / `\x1f`, and `%B` is the commit message. Those bytes are legal in a message or author. An extra `\x1e` starts a new row with an attacker-chosen sha, subject, `Task:`, and `Job:`. `split(FIELD, 4)` also shifts columns when a field contains `\x1f`, so the trailer search runs on the wrong slice. That forges the task/job link this parser exists to produce.
Fix: let git extract the trailers, for example `%x00`-separated `%H`, `%an`, `%at`, `%s`, `%(trailers:key=Task,valueonly)`, `%(trailers:key=Job,valueonly)`. Drop a record that contains a NUL inside a field. Add a unit test whose body contains `\x1e...\x1fTask: R9.99` and assert it does not become an extra row.

**5. Medium** — `roadmap/services/git.py:33`, `:56`, `:114`
`redact` only rewrites `http://` and `https://` userinfo, and only on stderr. Stdout is returned raw, so a commit subject from `read_log` (`:264`) can carry `https://user:token@host` onto the board and the phone listener. `ssh://user:secret@host/...` and `HTTPS://...` do not match. The pattern stops at the first `@`, so `https://user@name:secret@host` becomes `https://***@name:secret@host`. Query tokens (`access_token=`, `ghp_`, `Bearer`) are left intact. `roadmap/core/secrets.py:30` already uses a case-insensitive any-scheme userinfo pattern plus vendor and bearer rules; this runner does not call it.
Fix: run credential redaction on stderr and on every returned log/status string. Cover any URL scheme, case-insensitive; mask `ssh://` userinfo; do not leave a second userinfo after the first `@`. Add tests for `ssh://git:tok@host/a`, `HTTPS://user:tok@host/a`, and a token in a commit subject.

**6. Medium** — `roadmap/services/git.py:81` and `:105`
`valid_rel_path` accepts `-rf`, `--upload-pack=evil`, and paths containing newlines. `run` / `_git` will execute any argument list in any cwd and do not call `repo_root` or insert `--end-of-options`. Today’s read helpers pass only constants, so nothing in this file is injectable yet. The next caller that does `run(project, ["add", valid_rel_path(...)])` without `--` turns a filename into a git option.
Fix: reject a path that starts with `-` or contains `\n` or `\r`. Call `repo_root` inside `_git` before exec. Keep read entry points on fixed argv; put `--end-of-options` before any ref, sha, or path.

**7. Low** — `roadmap/services/git.py:149` and `:160`
`in_progress` and `check_index_free` trust `rev-parse --git-dir` and `--git-path`. `os.path.join(project, absolute)` drops `project`, and a relative `gitdir:` with `..` leaves the worktree. Both calls only test existence, and neither function calls `repo_root`. `strip()` also deletes interior-adjacent whitespace from the path git printed.
Fix: take `--absolute-git-dir`, `realpath` it, and only join the fixed names `MERGE_HEAD`, `rebase-merge`, `rebase-apply`, and `index.lock` onto that directory. Refuse a path that is not that resolved git dir.

**8. Low** — `roadmap/services/git.py:65`, `:77`, `:86`, `:208`
Rejected refs, shas, and paths are copied into `RoadmapError.message` (first 40–200 characters), including newlines and whatever secret was pasted in. `parse_status` indexes `parts[8]`, `parts[9]`, and `parts[10]` with no length check, and `# branch.ab` is unpacked with `split` / `int` (`:236`). A short or odd porcelain record raises `IndexError` or `ValueError` instead of a `RoadmapError`. `read_log` uses bare `int(limit)` (`:177`), so a non-numeric limit does the same.
Fix: use a fixed usage message with no raw input. Ignore a porcelain record that has too few fields. Catch `ValueError` on `limit` and raise `RoadmapError` with `EXIT_USAGE`.

## Tests

**9. Medium** — `tests/unit/test_git_service.py:199`
The env test sets `GIT_DIR` and `GIT_CONFIG_GLOBAL` and stops. `GIT_SSH_COMMAND` and the other exec variables above would still pass.
Fix: assert the full drop list and that `GIT_NO_LAZY_FETCH` is `1`.

**10. Medium** — `tests/unit/test_git_service.py:210`
The cap test mocks `git.run` only. `read_log` is uncovered, and no test reads a real pipe and checks the child dies at 2 MB.
Fix: one test that `read_log` raises `git_too_big` when stdout exceeds `STDOUT_CAP`, and one streaming test that output past the cap does not stay buffered.

**11. Medium** — `tests/unit/test_git_service.py:109`
`parse_log` fixtures contain no `\x1e` or `\x1f` inside a message, so finding 4 stays green.
Fix: add the forged-record case from finding 4.

**12. Low** — `tests/unit/test_git_service.py:61`, `:41`, `:222`
Redaction asserts `git@github.com:a/b.git` is unchanged and never tries `ssh://` or `HTTPS://`. Path tests never pass `-rf`, `--config`, or `a\nb`. The stderr secret sits in the first 400 bytes, so cutting before redacting still satisfies `assertNotIn("tok")`. There is no `repo_root` test that a symlinked project path is refused (`git.py:136`).
Fix: add those cases; put the token past byte 400 and assert it is gone from the exception message.

## What holds

`shell=False`, `stdin=DEVNULL`, and a list argv are in place. Refs reject a leading `-`, `..`, `//`, and option characters. `valid_rel_path` jails `..` and a symlink that points outside the project (`test_git_service.py:49`). `repo_root` requires an absolute canonical toplevel. The default read path sets `GIT_OPTIONAL_LOCKS=0`. `GIT_DIR`, `GIT_WORK_TREE`, and `GIT_CONFIG*` are removed. Stderr `https://user:token@host` is masked and the raised message is truncated. `.git/index.lock` is reported and not deleted.

