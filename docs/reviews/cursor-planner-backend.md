Read-only review of Planner features backend — no plans/reports. Pulling the listed files and PLANNER-SPEC now.

Reviewing the four modules and `feature.*` ops directly (no plan tools, no workers).

Ops live in `featops.py` (not `commands.py`). Reading that plus agent guard and plan import paths.

Checking the tasks.apply write-order bug and one more accept-path edge case.

Note: `feature.*` ops live in [`roadmap/services/featops.py`](roadmap/services/featops.py) (registered into `commands.OPS`), not defined in `commands.py`.

### Findings

1. **high** | `roadmap/services/agentguard.py:40-48` + `featops.py:149-154` | Agent accept guard is only `source==agent` or non-empty `CLAUDECODE`. Cursor/agy/other shells without that env run as `cli` via `commands.write` → `feature.accept` succeeds. | Treat accept like person-only: require proven GUI or interactive TTY/person flag; extend `is_agent` for this project’s agent markers; refuse bare `cli` for `feature.accept` unless explicitly allowlisted.

2. **high** | `roadmap/services/tasks.py:187-191` | `schema.write_data(tasks)` runs before `feature_store.apply_records`. If the latter raises (e.g. `core.validate` on an already over-cap or corrupt `features.json`), tasks/L/`f:` links are committed and features are not. | Write features first (or one atomic commit / rollback tasks on features failure). Align plan-path validation with `apply_records` before any write.

3. **high** | `roadmap/services/featops.py:179-188` + `features.py:189-201` | `feature.restore` writes the full feature dict including `accepted` with no `_refuse_accept`. Agent can `feature.rm` then patch `undo.jsonl` args (or rely on a restored accepted record) and `undo` to stamp acceptance. | On restore: strip `accepted` when `agentguard.is_agent`, or refuse restore of accepted features from agent/phone; validate `accepted` with `check_date`.

4. **medium** | `roadmap/services/tasks.py:390-392` | Plan import enforces `FEATURES_MAX` only when `added` is non-empty; updates still proceed on a >60 file, then often blow up in `apply_records` (feeds finding 2). | Always refuse when `len(features) > FEATURES_MAX`, including updates.

5. **medium** | `roadmap/services/tasks.py:476-478` + `planfmt.py:193-205` | T-line `f:F1` **replaces** the whole `feats` list. Partial plan import drops other feature links. | Merge/append like L lines, or require full feats on every `f:`; keep `f:-` as retain-only.

6. **medium** | `roadmap/core/planfmt.py:197-205` | `_parse_feats` allows duplicates (`f:F1,F1,F1`); fills the 3-cap with one id. `tasks.load` does not dedupe (unlike `parsers.parse_feats`). | Dedupe in `_parse_feats` / `_apply_link`; reject duplicates.

7. **medium** | `roadmap/core/planfmt.py:229-231` + `396-407` | Title/acc split on first ` # `. Title containing ` # ` export→import corrupts title/acc. | Forbid ` # ` in title/acc at set/parse, or use an escaping rule.

8. **medium** | `roadmap/core/features.py:95-98` | `hold` rows count in `counts.total` but not in done/doing/todo/uncovered → status line arithmetic lies. | Add `counts.hold`, or exclude hold from `total`.

9. **medium** | `roadmap/services/features.py:189-201` | `restore` skips phase-exists check that `apply_records` does; can restore `phase` missing from `tasks.json`. | Reuse `_phase_ids` check (and parent rules) before append.

10. **low** | `roadmap/core/features.py:181-183` | `accepted` accepted as any non-empty string; no `YYYY-MM-DD` check (ops path uses `check_date`, load/restore/hand-edit do not). | Validate with same `DATE_RE` / `check_date` in `_field_errors`.

11. **low** | `roadmap/core/features.py:181` | `phase` is any non-empty string; no `PHASE_ID_RE` (planfmt/ops are stricter). | Require `PHASE_ID_RE` in `_field_errors`.

12. **low** | `roadmap/core/planfmt.py:193-196` | No plan token clears feats (`f:-` = keep). Export/edit/import cannot unlink; only `feature.unlink`. | Add clear syntax (e.g. empty `f:` or `f:clear`) wired to `_update_task` pop.

13. **low** | `roadmap/services/featops.py:164-165` + `_h_accept` | Undo of accept calls `feature.accept` → `_refuse_accept`, so an agent shell cannot undo a person’s accept/clear (stuck undo). | Run inverse accept with person context, or skip agent refuse for undo inverses while still blocking public accept.

14. **low** | `roadmap/services/features.py:206-218` | `link` checks feature ids then `tasks.apply` without holding the dir lock across both; TOCTOU rm of feature → confusing error (not a write of bad data). | Hold `lock.locked` for check+apply, or only trust apply’s validation.

15. **info** | `featops.py:149-154` + `http/security.py:175` | Intended path is sound: HTTP unproven → `agent`; phone not in `PHONE_OPS` + refuse; `apply_records` / plan F lines preserve `accepted` and do not set it. Gaps are CLI env detection, restore/undo, and plan write ordering above.

**Caps / cycles:** F1–F99, 60 features, ≤3 feats/task, one parent level — enforced on the happy path (`_check`, `_apply_features`, `add`). Parent self-cycle and 2-level parents refused. No multi-level cycle beyond that model.

