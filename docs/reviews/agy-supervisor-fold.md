| file:line | claim | true? | evidence |
|---|---|---|---|
| docs/reviews/opus-supervisor-review.md:6 | Fold never fires for a task with a failed-then-retried job after retry succeeds | False | roadmap/services/supervisor.py:221-222 excludes earlier failed attempts (`seq < last_done`) from blocking; task marked done at supervisor.py:225 |
| roadmap/services/supervisor.py:160-161 | Lines 160-161 contain fold logic checking `any(s != "done")` | False | roadmap/services/supervisor.py:160-161 is `_escalate()`; `_fold_tasks()` is at supervisor.py:205-227 without `any(s != "done")` |
| roadmap/services/supervisor.py:197-198 | Retried failed jobs keep status 'failed' | True | roadmap/services/supervisor.py:197-198 sets `job["retried_by"] = new_id` and saves without changing status from `'failed'` |
| roadmap/services/supervisor.py:221-222 | Any non-done job permanently blocks fold | False | roadmap/services/supervisor.py:221-222 excludes failed jobs where `seq < last_done` and statuses in DONE_EXCLUDED (supervisor.py:37) |
| roadmap/services/supervisor.py:37 | Fold blocks on cancelled jobs unless fixed | False | roadmap/services/supervisor.py:37 defines `DONE_EXCLUDED = ("done", "cancelled")`, excluded from blocking at supervisor.py:221 |
