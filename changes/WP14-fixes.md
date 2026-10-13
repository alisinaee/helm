# WP14: fixes for the R1 security review

All seven findings in `docs/reviews/R1-cursor-auto.md` were checked against the code and are real. Each has a
regression test. The checklist rows are in `docs/SECURITY.md` (R1-1 to R1-7).

1. Symlinks (high): `.claude`, `settings.local.json` and backup sources that are symlinks are refused. The settings real
   path must stay inside the project's `.claude`. Reads use O_NOFOLLOW. A new file is 0600, and an existing regular file
   keeps its mode (lstat, never the link target's mode).
2. Tunnel host (high): only `*.localhost.run` and `*.lhr.life` are accepted. ssh runs with `StrictHostKeyChecking=yes`
   and `UserKnownHostsFile` in the state folder. The Host allowlist accepts `phoneHost` only when it passes the same check.
   First use of the host key is a manual step, documented in `docs/SECURITY.md`.
3. Pids (medium): a pid is signalled only when `ps` still shows our ssh. A `ps` failure exits non-zero, keeps
   `tunnel.pid` and signals nothing.
4. Settings race (medium): the file is re-read just before the replace. If the bytes changed, the merge runs again
   (3 attempts, then exit 4).
5. Uninstall (medium): a bootout failure other than not-loaded (3, 113) is an error, and the plist is kept.
6. Hook budget (medium): each lock wait is at most 1 s (`lock.timeout_scope`). The state lock is released before the
   project lock is awaited. A busy lock returns silently with exit 0.
7. Static map (low): each file is served from its realpath. A symlink whose real file is outside `web/` is dropped.

Extra item from the coordinator: the cursor detector takes the output file from the last `cursor-review2.sh` invocation,
and its title comes from the quoted prompt (70 characters). The agy title stops at a shell operator (`&&`, `||`, `;`,
`|`, `&`).
