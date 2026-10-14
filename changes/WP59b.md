# WP59b: planfmt models and export F/L

- `roadmap/core/planfmt.py`: `MODELS` now also takes `cursor`, `agy` and `head`, the same words as `services/jobs.py`. The T line and set line errors list them.
- `roadmap/services/tasks.py`: new `export_lines(data_dir, phase=None)`. It emits the F lines first (features.json order), then each P line with its T lines, then orphan tasks. A T line carries ` f:F3,F7` through `planfmt.format_task`. With `phase`, the F lines are that phase's features plus the ones its tasks link to and their parents. A project without features gives the same lines as before.
- Tests: `tests/unit/test_planfmt_models.py` (5) and `tests/unit/test_plan_export_features.py` (9). They cover the model words, export order, the f: token, the export then import round trip (`0 changed`, no write), the phase filter and the unknown-phase error.
- Not in this change: `roadmap/commands/plan.py` `_export` still builds its own loop and does not call `export_lines`. Switching it is a one-line change in that file. Two assertions in `tests/unit/test_planfmt.py` still expect the old three-word model list.
