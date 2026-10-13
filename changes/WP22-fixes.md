# WP22: R2 review fixes (Cursor Auto)

Source: `docs/reviews/R2-wp22-cursor-auto.md`. One regression test per finding in
`tests/unit/test_hook_enforce_r2.py`. Checklist rows R2-1 to R2-8 are in `docs/SECURITY.md`.

- R2-1 `services/hooks.py` `_project_quiet`: the gate resolves the project from the payload cwd only (`{}` in place of
  the environment). Real.
- R2-2 `services/hooks.py` `_refresh_limits`: a limit block is recomputed inside the remaining 300 ms before a deny. A
  failed or late recompute fails open and removes the sentinel. `control.set_budget_limit` and `set_weekly_limit` write
  the limit and recompute the control state under one data-folder lock (`budget.set_limit_locked`). Real. The usage sync
  already calls `recompute_all` (`usage._control_after_write`), so that part of the finding was not a gap. Limit row
  writes (`set_limit_row`, `remove_limit_row`) still recompute after their own write, not under one lock: they take
  their locks inside `limits.py`.
- R2-3 `bin/roadmap`: the state folder is stripped, `~`-expanded and checked for absolute, normalised form. A relative
  or unnormalised root goes to Python. Real.
- R2-4 `services/hooks.py` `ALLOWED_WHILE_BLOCKED`: while blocked, a roadmap Bash command runs only as `inbox`, `status`,
  `ask` or `rules show`. `agentguard.is_agent` treats any non-empty `CLAUDECODE` as an agent. `commands/hooks.py` `_uninstall`
  refuses from an agent. Real.
- R2-5 `services/rules.py`: the interior between the markers must be the generated intro or `- R…` lines. The write
  re-reads CLAUDE.md under the data-folder lock and refuses if the bytes changed. Real.
- R2-6 `services/control.py` `set_budget_limit`: the current limit is read under the data-folder lock. Real.
- R2-7 `services/hooks.py` `_stop_pickup`: any truthy `stop_hook_active` stops the pickup. The cap of three also counts
  per task set (`pickup` in the control state, keyed by a hash of the queued task ids), so it survives a new session id
  or a deleted pickup file. Real.
- R2-8 `services/hooks.py` `_summary`: job titles keep a 60-character summary with secret-looking tokens replaced. Logs
  carry only ids and detector names. `control.pending_lines` gives question and task ids, no text or answers. Real.

## Behaviour changes to know about
- A Stop pickup for the same queued task set stops after three blocks in total, whatever the session.
- A limit block is re-read at each denied call. A usage reading older than the WP27 freshness window is unknown, so
  a stale block lifts; the tests that expected a deny on a two-hour-old reading now supply a fresh one.
- `roadmap hooks uninstall` from an agent shell is refused (exit 4).

## Files outside the R2 list
- `roadmap/services/budget.py`: `set_limit_locked` (the caller holds the folder lock). Needed so the limit write and
  the control recompute share one lock (R2-2 and R2-6). `set_limit` behaves as before.
- `tests/unit/test_wp27_limits.py`: the CLI hook test pins the clock (the hook recomputes on the real clock now), and
  the override-expiry test supplies a fresh usage reading at expiry.
- `tests/unit/test_hooks_install.py`: the uninstall tests clear `CLAUDECODE` for their run (an agent shell refuses
  uninstall now).
