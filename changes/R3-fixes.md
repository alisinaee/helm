# R3 fixes (WP22): review findings and known bugs

Review: `docs/reviews/R3-cmd-limits-cursor-auto.md` (10 findings), plus known bugs a to d. Regression tests:
`tests/unit/test_r3_fixes.py`. Removed expectedFailure marks: `tests/unit/test_limits_gaps.py` (2),
`tests/integration/test_question_flow.py` (1).

## Findings

| # | Finding | Real? | Fix |
|---|---|---|---|
| 1 | /cmd always gui, so the agent guard never applied | real | A dashboard write is `gui` only with browser proof (Origin of this server and Sec-Fetch-Site same-origin). The proof is a thread-local flag for that request (`agentguard.browser_proven`). Any other main-listener write is `agent`. Documented as a speed bump in SECURITY.md "Known limits". |
| 2 | A bad project file dropped every row, global included | real | Global rows always apply. A project whose files cannot be read loses only its own rows (logged). |
| 3 | Weekly dip counted as a full reset; no range check | real | A drop under 10 points is jitter (adds nothing). Reset only on a drop of 10 or more. Non-finite and negative readings refused. Upper bound 1000, not 100: a reading above 100 is real over-allowance and must still count. |
| 4 | Phone undo could reverse another party's change | real | A phone may undo only a change whose own activity line came from the phone. |
| 5 | Two undos of one change could both run the inverse | real (replay) | The check and an `undoing` claim are written under the folder lock before the inverse runs. A failed inverse writes `undoFailed`, which releases the claim. Not fixed: undoing an old change still overwrites a later change to the same object (last write wins; documented). |
| 6 | Ledger trimming dropped days inside the week | real | Days of the current week are never dropped. If the week does not fit, the oldest day's per-project tokens fold into `_other`. |
| 7 | A future `updated` counted as fresh | real | Fresh only within 60 s of skew and 1800 s old. |
| 8 | CLAUDECODE was cleared process-wide | real | The environment is never changed. The thread-local proof replaces it. |
| 9 | tokensK unbounded (overflow after the write) | real | Ceiling 10,000,000, checked before anything is written. |
| 10 | NaN and Infinity accepted in JSON | real | Strict JSON on the cmd and sync bodies. `isfinite` in limit, rule, budget and ledger numbers. |
| a | Malformed row removed, then not_found (file changed) | real | A malformed row is not a limit row: it is left alone and the call returns not_found. |
| b | Removing a warn budget returned a block row | real | The removal returns the stored action, so the undo restores a warning. |
| c | CLI ask from an agent shell logged as `cli` | real | `commands.write` logs `agent` when CLAUDECODE is set. |
| d | `watch` refused while blocked | real | `watch` added to `ALLOWED_WHILE_BLOCKED`. |

## Other changes

- `tests/api/test_cmd_route.py` `post()` sends the browser Origin, because a page's write carries it.
- `tests/unit/test_cmdops.py`: the in-process gui-in-agent-shell test now covers both the proven and unproven cases.
- `tests/integration/test_question_flow.py`: the asking line is `agent` (it was the bug).
- `docs/SECURITY.md`: the checklist citations were re-checked against the code; the three open gaps are closed (serve starts
  the phone listener, `open` is registered, the stderr log handler redacts). New Known limits entries.
- `docs/skill-draft/SKILL.md`: commands written with placeholders or alternatives that the parser rejected are fixed
  (`job start|done|fail`, `task done|start|hold`, `plan import`, `hooks install`, `project init`, `project migrate`).
  `roadmap serve --port <N>` is left as a placeholder.
