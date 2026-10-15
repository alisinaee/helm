VERIFIED 27/27 (3 corrected: 209, 210, 198 validated column; line/label fixes at 158, 309, 644, 675; real bug: glob/magic pathspec bypasses job ownership, see tests/unit/test_git_ops.py ArgvGuardGaps)

| file:line | argv/guard | input source | validated? | note |
|---|---|---|---|---|
| roadmap/services/git.py:257 | argv: git log -n <count> --format=... | limit query/arg | yes | clamped to 1 <= count <= 100 via int(limit) at git.py:253 |
| roadmap/services/gitops.py:209 | argv: git add -- <paths> | paths in git.commit | partly: globs and pathspec magic pass (BUG) | valid_rel_path at gitops.py:198 (no leading -, inside repo); after --; '*' or ':/' stages every file, bypassing the job ownership check at gitops.py:203 |
| roadmap/services/gitops.py:210 | argv: git commit --only -m <text> -- <paths> | message, task, job, paths in git.commit | partly: globs and pathspec magic pass (BUG) | msg/trailers sanitized at gitops.py:165-181; paths after --; same glob gap as 209, '*' commits other jobs' files |
| roadmap/services/gitops.py:229 | argv: git merge-base --is-ancestor <sha> <upstream> | sha in git.uncommit | yes | valid_sha (7-40 hex) at gitops.py:153, 220; upstream from rev-parse at gitops.py:225 |
| roadmap/services/gitops.py:239 | argv: git rev-parse --verify --quiet <sha>^{commit} | sha in git.uncommit | yes | valid_sha (7-40 hex) at gitops.py:153, 220 |
| roadmap/services/gitops.py:260 | argv: git rev-parse --verify --quiet <sha>^{commit} | sha in git.revert | yes | valid_sha (7-40 hex) at gitops.py:153, 253 |
| roadmap/services/gitops.py:263 | argv: git revert --no-edit <full> | sha in git.revert | yes | valid_sha at gitops.py:253; full resolved from verified commit at gitops.py:260 |
| roadmap/services/gitops.py:309 | argv: git push <remote> <ref>:<ref> | remote, branch in git.push | yes | remote regex at gitops.py:272; valid_ref on branch at gitops.py:294 and on remote at gitops.py:307 (rejects leading -); never force (+) |
| roadmap/services/gitops.py:328 | argv: git branch <name> <sha> | name in git.branch | yes | valid_ref at gitops.py:316; agent prefix agent/ enforced at gitops.py:322 |
| roadmap/services/gitops.py:346 | argv: git rev-parse --verify refs/heads/<name> | name in git.branch.drop | yes | valid_ref at gitops.py:336; verifies branch tip matches creation sha at gitops.py:347 |
| roadmap/services/gitops.py:351 | argv: git branch -D <name> | name in git.branch.drop | yes | valid_ref at gitops.py:336; checked not current branch at gitops.py:341 |
| roadmap/services/gitops.py:377 | argv: git switch <name> | name in git.switch | yes | valid_ref at gitops.py:358; _ref_exists at gitops.py:371; clean tree at gitops.py:366 |
| roadmap/http/routes.py:644 | argv: git show -s --format=... <sha> -- | URL route {sha} in git_show | yes | valid_sha (7-40 hex) at routes.py:641; placed before -- delimiter |
| roadmap/http/routes.py:675 | argv: git show --numstat --no-renames <sha> -- <rel> | URL {sha}, query path in git_diff | yes | valid_sha at routes.py:670; valid_rel_path at routes.py:671; placed after -- |
| roadmap/services/gitops.py:158 | guard: commit schema (_check_commit) | a payload (paths, message, task, job) | yes | paths non-empty <= 500 (160); msg <= 4000 (168, 165 is the empty check); task/job regex (170) |
| roadmap/services/gitops.py:198 | guard: commit paths relative and inside repo | a["paths"] | partly: globs and pathspec magic pass (BUG) | valid_rel_path ensures no leading -, no .., canonical path inside repo root; it does not reject '*' or ':/' pathspecs |
| roadmap/services/gitops.py:199 | guard: commit writable tree check (_writable) | repo status (git.read_status) | yes | refuses write if merge/rebase in progress (gitops.py:102) or detached HEAD (gitops.py:105) |
| roadmap/services/gitops.py:204 | guard: commit file ownership check (_owners) | docs/jobs.json active running jobs | yes | refuses path owned by a different running job (owner != a["job"]) |
| roadmap/services/gitops.py:207 | guard: write lock & index.lock check | repo state & docs/ lock | yes | lock.locked(data_dir) flock (gitops.py:207); check_index_free raises git_busy (gitops.py:208) |
| roadmap/services/gitops.py:240 | guard: uncommit HEAD, unpushed & parent check | a["sha"], repo HEAD, upstream tracking | yes | refuses if sha != HEAD (gitops.py:241), already pushed (gitops.py:243), or root commit (gitops.py:245) |
| roadmap/services/gitops.py:257 | guard: revert person-only restriction | commands.current_source() | yes | agentguard.refuse_if_agent forbids agents from invoking git.revert |
| roadmap/services/gitops.py:272 | guard: push remote name & checked bool check | a.get("remote"), a.get("checked") | yes | remote matched against [A-Za-z0-9._-]{1,60} (gitops.py:272); checked must be bool (gitops.py:147) |
| roadmap/services/gitops.py:289 | guard: push in-progress, detached & ref checks | repo status branch & docs/git.json | yes | refuses in-progress (gitops.py:290), detached HEAD (gitops.py:292), or invalid ref (gitops.py:294) |
| roadmap/services/gitops.py:298 | guard: push policy & protected branch check | commands.current_source(), docs/git.json | yes | agent push refused if off (gitops.py:299), branch protected (gitops.py:302), or unchecked (gitops.py:305) |
| roadmap/services/gitops.py:322 | guard: branch agent prefix restriction | commands.current_source(), a["name"] | yes | agents can only create branches starting with agent/ (AGENT_BRANCH) |
| roadmap/services/gitops.py:341 | guard: branch drop current branch & tip check | a["name"], a["sha"], repo ref state | yes | refuses if current branch (gitops.py:342), missing ref (gitops.py:345), or new commits (gitops.py:348) |
| roadmap/services/gitops.py:364 | guard: switch in-progress, clean tree & ref | repo status, docs/ exclusion, a["name"] | yes | refuses if in-progress (gitops.py:365), dirty tree (gitops.py:367), or missing local ref (gitops.py:372) |
