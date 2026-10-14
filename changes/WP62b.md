# WP62b: phase approval gate and research status line

- `roadmap task start <id>...` is refused (exit 4, nothing written) when the task's phase has `approved` explicitly false. Message: `roadmap: phase P1 is not approved. next: ask the person to approve it (GUI Roadmap > Approve, or roadmap phase approve P1)`. Done, hold and phases without the key are unchanged. Helpers: services/tasks.py `unapproved_phases`, `start_refusal`.
- `roadmap status` shows one extra line when docs/research/ exists or a phase is unapproved, e.g. `research 1/1 open, phase P1 not approved` (open notes out of INDEX.md lines; the first unapproved phase, `(+N)` for more). It sits after the run lines; the 8-line / 700-char budget still drops the lowest lines first.
- Tests: tests/unit/test_phase_gate.py (15).
- Not covered: the GUI op path `task.status` in services/commands.py (`_h_task_status`) does not run this check; that file was outside this change.
