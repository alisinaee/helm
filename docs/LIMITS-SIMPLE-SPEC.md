# R7.28 Limits, simple (spec)

Person: "no limit for each tiny section". Wish: one weekly stop (95%), optional share per project, usage at a glance.

## 1. Remove from the GUI

- Limits editor: every row's Window select, Unit select, ± steppers, range slider, number field, Warn/Stop select, live preview, Delete, row sheet editor (phone).
- "+ Add limit" and the presets ("Stay under 10% a day", "Weekly 60%", "Daily for all projects").
- Spend: "Token limit (thousands)" field and "Save cap" (project total), phase, model and task cap editors (`spend-cap`, `task.cap`).
- Global vs project scope switching of the whole page.
- Today/This week meters per scope with 80% tick, "today started here" tick, pace line (keep pace only in the Overview banner).
- "Total" window and the `tok` unit (GUI only).
- Override panel on Tokens (moves to the banner, section 4).

## 2. New screen (one page, same for any project)

1. **Usage now** (grid row, numbers right-aligned): This week `NN %` · Last 5 h `NN %` · `updated 14:20 (manual|head|sync)` · link **Enter usage** (the R7.27 form). Stale over 30 min: grey value + "outdated".
2. **Weekly stop** (one card): toggle **On/Off** + "Stop agents at `[95] %` of my weekly usage" (number 50–100, default 95). Applies to all projects.
3. **Share per project** (optional, collapsed when all are "no limit"): one row per registered project, fixed columns:
   `project | may use up to [__] % of [daily|weekly] | used ≈ NN % | state`.
   Empty number = "no limit" (default). One number and one dropdown per project, nothing else.
4. **Sentence** under both: "At the limit, agents stop starting jobs. You can override for 1 hour from the banner."
5. **Spend (read-only)**: grid per project: today K, this week K, total K, right-aligned. No caps, no inputs.
6. **Advanced**: none. Phase/model/task caps and warn-only rows remain CLI-only.

## 3. Backend (unchanged files, no new op)

- `limits.json`/global config `limits[]`, `budget.json` (`limits`, `spent`, `jobs`), `autonomy.json` stay valid; nothing migrated.
- Weekly stop: today `acct` is project-only (`check_spec`). Map the global stop to `limit.set {scope:global, window:week, kind:pct, value:N, action:block}` (global pct week = account weekly %, per 2b). Off = `limit.rm` of that row. Per-project `autonomy.json stopAtPercent` keeps working; GUI shows only the global value and a note if a project has its own lower stop ("alpha stops at 80%").
- Share: `limit.set {scope:project, window:day|week, kind:pct, value:N, action:block}`; "no limit" = `limit.rm`. The GUI edits only the first such row per project; other rows (tok, warn, extra) are kept, shown as "+ N CLI rules" text.
- Per-task, phase, model, project-total caps stay as CLI/agent features (`roadmap limit budget …`, `task.cap`) and keep enforcing.
- Known gap: project % needs ≥200k tracked tokens before it enforces; show "≈ not enough data" in the state column.
- No new op needed.

## 4. Enforcement visibility

- Overview banner (exists, `overview.js`): "Limit reached: weekly stop 95% (now 96%). Agents stopped." + **Override for 1 hour** (exists). Add the same banner at the top of the Tokens screen.
- Projects panel "Blocked by limit" and nav dot "limit reached" stay.
- Topbar: replace "Today no limit / Week no limit" with "Week 41 % · stop 95 %".

## 5. Agent side

Unchanged: `roadmap limit show`, `status` line, SessionStart note, sentinel fast path, skill text.

## 6. Breakdown (Haiku, low; after R7.27 lands, it edits usage.js/tokens.js)

Order: A → B → C, D in parallel with C; then E.

- **A** `web/js/views/limits.js`: rewrite to `weeklyStopHtml`, `shareRowsHtml`, handlers (`limit.set`/`limit.rm` only). Delete editor, presets, sheet, task.cap/budget.set handlers. Tests: `tests/web/test_limits_view.py` (or existing limits test only).
- **B** `web/js/views/tokens.js`: new section order (usage now, banner, weekly stop, share, sentence, read-only spend). Remove meters, spend caps, override panel, accuracy explainer (keep one line). Reuse `usage.js` untouched.
- **C** `web/css/components.css`: delete `lim-range`, `lim-num`, steppers, sheet, preset rules; add ≤25 lines grid for share/spend rows. Net CSS must be negative (target ≥ −60 lines). `make check-ui`.
- **D** `web/js/views/topbar.js`: the "Week NN % · stop NN %" text only.
- **E** docs only: `docs/UI-SPEC.md` Tokens section → point to this file; `docs/PRODUCT-SPEC.md` line "Editable limits: project, phase, model and per-task caps" → "weekly stop + optional share per project in GUI; caps CLI-only".

Rules: workers stage own files by path, temp ROADMAP_HOME, no service/serve/usage sync, no port 8780. Rebuild `build/ui-smoke` tokens shots (1440x900 dark, 500x900) for review.

**agy audit (1, read-only):** list every `<button>`, `<select>`, `<input>` and `data-action` in `tokens.js` and `limits.js` before and after; mark each kept/removed against section 1; flag any `task.cap`/`budget.set` call left in web/js. Head verifies.

## 7. Questions for the person

1. With manual usage entry, readings go "stale" after 30 min and limits then never block (fail-open). Keep a manual reading valid until you enter a new one (or 6 h)?
2. Share per project: stop only (as spec), or also a soft warning at 80% of the share?
