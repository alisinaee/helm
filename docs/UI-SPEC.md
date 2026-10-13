# WP26: Dashboard app shell plus usage limits (full combined plan)

New in this version: section 2b (usage limits), and changes to sections 3 to 6. I checked how the backend does limits today:
- `services/control.py` reads `stopAtPercent` from each project's `autonomy.json` and the weekly percent from the global usage store.
- `services/budget.py` has `set_limit` and `record_job_spend`.
- `services/usage.py` only reports 5-hour and weekly account percent.

## 1. App shell (unchanged)

**Right panel decision:** one right panel with two tabs, **Projects** and **Details**.
- Selecting a task, issue or question switches the panel to Details; `Esc` goes back to Projects.
- In the 1024 px layout the panel becomes a 360 px overlay. On phones it becomes a sheet.

**1440 px** (nav 232, main fluid, panel 320, all docked):
```
┌────────────┬──────────────────────────────────────────┬──────────────┐
│ ◧ roadmap  │ rb-site ▾ › Work › Board  ●Running [Stop]│[Projects|Det]│
│ ⌂ Overview │ day ▓░ 4/10%  week ▓▓▓░ 62%  ● live  ☾ ? │ All projects │
│ ✉ Inbox  3 │──────────────────────────────────────────│ ● rb-site    │
│ ◫ Roadmap  │ [Board|List|Tree]  needs-you model▾ ph▾  │  ▓▓▓░ ✉2 !1▶1│
│ ▦ Work   1!│ ┌Todo 8──┐┌Doing 2─┐┌Hold 1─┐┌Done 14┐   │ ○ split-net  │
│ ⚠ Issues 1 │ │card    ││card    ││card   ││card   │   │  ▓▓░░        │
│ ⇄ Agents ▶2│ └────────┘└────────┘└───────┘└───────┘   │              │
│ ◔ Tokens ● │                                          │              │
│ ☰ Rules ✎ Research ↻ Activity ⚙ Settings « collapse   │              │
└────────────┴──────────────────────────────────────────┴──────────────┘
```
**1024 px:** the nav becomes a 56 px icon rail with dot badges. The panel is hidden until you press `]` or click the project name.

**375 px:** top bar shows the project name ▾ (opens the Projects sheet), the Run/Stop pill and ⋯. A bottom nav holds ⌂, ✉, ▦, ⚠ and More. Details is a full-height `<dialog>` sheet.

**Left nav:**
- Order: Overview, Inbox, Roadmap, Work, Issues, Agents, Tokens, Rules, Research, Activity. Settings sits at the bottom.
- Icons come from a same-origin `icons.svg` sprite (≤5 KB).
- Badges: Inbox (questions plus needs-you), Work (blocked, red), Issues (blockers, red), Agents (running, green), Tokens (amber or red dot).
- **Changed:** the Tokens dot now reflects the worst limit across global and project rows.

**Top bar:** scope crumb, control pill (Stop/Resume), connection dot, theme, `?`.
- **Changed:** it now shows two mini meters, today and this week, against the tightest applicable limit.

**Projects tab:** "All projects" first, then one row per project with a mini meter and the ✉ ! ▶ badges.
- **Changed:** a 🔒 mark shows when a limit is blocking that project.

**Details tab:** unchanged. It shows a task, issue or question, or the project info card when nothing is selected.

**Keyboard map:** unchanged (g-chords, `1`/`2`/`3`, `j`/`k`, `Enter`, `Esc`, `s` `x` `d` `h` `c`, `Alt+↑/↓`, `n`, `a` then 1–4, `[` `]`, `z`, `Shift+X`, `?`). Added: `g t` then `l` focuses the limits editor.

## 2. Sections

Unchanged except Tokens.
- **Overview:** banner, Inbox, meters, agents live, blockers, activity.
- **Inbox:** one-click answers.
- **Roadmap:** lanes with drag, ↑/↓ and Approve, plus a token-proportional Timeline view.
- **Work:**
  - Board: native drag to change status on desktop, with buttons as fallback.
  - List: dense table with filters, grouping, and a bulk bar for status and start/stop (bulk cap is now LATER).
  - Tree.
- **Issues, Rules, Activity, Settings:** unchanged.
- **Agents:** live tree with handoff chips and the last 10 jobs. **Changed:** the swimlane timeline moves to LATER to fund the limits work.
- **Research:** notes reader plus the onboarding checklist.

The ops, empty states and phone behaviour are as in the first version.

**Tokens (redesigned).** Scope follows the right panel: "All projects" means global, a project means that project.
1. **Meters row.**
   - Two meters, Today and This week, for the selected scope. Each shows used, the limit, and the 80% warn tick.
   - The weekly meter has a "today started here" tick.
   - Each meter has a pace line, either "At this pace: limit reached about 16:40" or "Won't reach today".
   - A grey "unknown" state appears when usage data is stale.
2. **Limits editor.** One row per limit.
   - Window: Day, Week or Total. Unit: "% of weekly" or "tokens".
   - A ± stepper plus a 0–100 slider (tokens use a number field).
   - Action: Warn or Stop.
   - Live preview: "≈ 1.4M tokens at your current rate" or "≈ 9% of weekly".
   - Delete button. "+ Add limit" offers three presets:
     - "Stay under 10% a day";
     - "Weekly 60%";
     - "Daily for all projects", which only appears in global scope.
3. **Account card:** 5-hour and weekly account percent with reset times (reuses `usage.js`), and the per-project account ceiling (`stopAtPercent`).
4. **Spend:** in project scope, phase, model and task caps plus the top 5 tasks by spend. In global scope, a per-project table with today's tokens, this week's tokens and estimated % share.
5. **Override:** 1–4 hours.
6. **Accuracy note:** one line, linked to a short explainer (see 2b).

Ops: `limit.set`, `limit.rm`, `budget.set`, `task.cap`, `control.override`.
- Empty state: "No limits. Agents may use your whole weekly allowance." with the presets.
- Phone: meters stack and each limit row becomes a sheet editor.

## 2b. Usage limits: model, measurement, enforcement

**One concept: a limit row.**
```
{id:"L3", scope:"global"|"project", window:"day"|"week"|"total",
 kind:"pct"|"tok"|"acct", value:N, action:"block"|"warn", setBy, setOn}
```
- `pct` means percentage points of the account's weekly allowance used by this scope within the window. "10% a day" means this scope may use 10 weekly points per local day.
- The account has no daily window, so the weekly allowance is the unit. The UI shows "a fair day is about 14.3%" (1/7) as a hint.
- `tok` means thousands of tokens, measured exactly from `job done --tokens`.
- `acct` means a ceiling on the whole-account weekly meter. It is the existing concept.

**Where limits live.** No existing file breaks; old files read as before.
- Global rows go in the global config under a new `limits: []` key (`store.config`).
- Project rows go in `budget.json` under a new `limits: []` key.
- Existing data is read through as rows, not migrated:
  - `autonomy.json` `limit.stopAtPercent` is shown as the read-only project row `{window:"week", kind:"acct", value:stopAtPercent, action:"block", src:"autonomy"}`.
  - Writing the `acct` kind writes `autonomy.json` exactly as `limit set <pct>` does today.
  - The existing project budget in `budget.json` is shown as `{window:"total", kind:"tok", src:"budget"}` and is edited through `budget.set`.
  - Phase, model and task caps stay where they are.

**Measurement: the usage ledger.** A new global file, `ledger.json`, of 4 KB or less, holding 14 days.
- `days[YYYY-MM-DD] = {pts, lastW, firstAt, lastAt, tok:{<project>:K}}`.
- **On each usage reading** (one call added in `services/usage.py`):
  - if `w ≥ lastW`, add `w - lastW` to `pts`;
  - otherwise the weekly window has reset, so add `w`.
  - Then set `lastW = w`.
  - The first reading after local midnight carries the previous `lastW` forward, so the day baseline is "the last reading before midnight".
- **Daily used (global, measured)** = `pts(today)`. **Weekly used** = the account weekly percent itself.
- **On each job done** (one call added in `budget.record_job_spend`): `tok[project] += K` for the day of `job done`.
- **Project share estimate:** `rate = Σpts / Σtok` over the trailing 7 days (points per 1k tokens).
  - `est_pts(project, window) = tok(project, window) × rate`.
  - When tracked tokens are under 200k, there is no estimate, and only `tok` and `acct` limits enforce for that project.
- **Global `pct` limits** use the measured account points. That is honest and conservative because it counts all Claude use on the account.
- **Pace:** the slope of `pts` over the last 2 hours gives the projected time to the limit.

**Caveats the UI shows in plain words:**
1. Usage outside these projects (chats, other machines) is counted in global limits and makes project estimates high. That errs on the safe side.
2. Tokens are counted when a job ends, so a long running job shows up late.
3. When the reader is off, those hours are added at the next reading, but they land in that day.
4. Project % figures are estimates (shown with "≈"). Token figures are exact for reported jobs.

**Enforcement.**
- `services/control.py` recompute gains one call, `limits.evaluate(project) → worst {state ok|warn|block|unknown, row, used, limit}`, which checks all applicable rows, global and project.
- States:
  - Warn at 80% or more: an amber status line, a SessionStart note, and an Overview banner. Nothing is denied.
  - Block at 100% or more, but only when the row's action is `block`. Rows with action `warn` never block.
- **Global block fan-out:** recompute loops over the registry and writes every project's sentinel. The hook fast path stays a single sentinel read and is unchanged.
- **Recompute triggers:** a usage reading, job done, `limit.set`/`limit.rm`, and a day rollover (date compared at each recompute).
- **Override:** the existing `control.override` per project bypasses both project and global blocks for 1–4 hours, and is logged.
- **Fail-open:**
  - When usage is stale (over 30 minutes) or the ledger is missing or corrupt, `pct` and `acct` rows evaluate to `unknown` and never block. `tok` rows still enforce.
  - Any exception in `evaluate` means `ok`, and the error is logged once per minute.

**CLI and ops.**
- `limit set --scope global|project --window day|week|total --pct N | --tokens K [--warn]` prints `L3 set`.
- `limit rm L3`.
- `limit show` prints at most 8 lines, for example `day 4.1/10% ok · week 62/60% BLOCK (global L1) · est rb-site ≈2.3% today`.
- The old `limit set <pct>` still works as an alias for `--kind acct --window week`.
- `status` gains the line `limits: day 4/10 week 62/60 BLOCK`.
- Ops:
  - `limit.set` gets extended args `{scope, window, kind, value, action}`; undo restores the previous row.
  - `limit.rm` is new; undo re-adds the row.
  - Both are under the agent guard. Agents use `roadmap ask` instead.

**MVP:** day and week windows, the pct/tok/acct kinds, the warn/block actions, the ledger, a 7-day calibration rate, pace, and the global and per-project scopes.

**LATER:** a 5-hour window, per-model rate calibration, live tokens from running jobs, notifications, and a history chart (14 day bars).

## 3. Components and CSS budget

**Reuse:** unchanged (buttons, chips, badges, meters, banners, empty and skeleton states, KPI tiles, the usage band, segmented control, task, run, log and phase rows, and the `dom.js` helpers).

**New CSS files:**

| File | Size | Change |
|---|---|---|
| `shell.css` | 6 KB | unchanged |
| `panel.css` | 4.5 KB | unchanged |
| `work.css` | 6 KB | unchanged |
| `plan.css` | 3.5 KB | unchanged |
| `admin.css` | 3.5 KB | was 2.5 KB; adds `.lim-row` `.step` `.range` `.mtick` (day tick) `.pace` `.est` |
| `flow.css` | 1.5 KB | was 2.5 KB; no timeline |

- The total stays at +25 KB, so all CSS is ≤51 KB.
- **New tokens:** `--w-nav`, `--w-rail`, `--w-side`, `--h-top`, `--h-bnav`, `--shadow-1`, `--shadow-2`, `--scrim`, `--sel`, `--drop`, `--z-over`, `--z-toast`, `--t-fast`, plus `--unknown` (grey for the stale-meter state).

## 4. Routing and state (unchanged, plus one change)

- Routes: `#/all/<section>` for global scope and `#/p/<id>/<section>[/<view>][/i/<item>]`, with filters in `?f=…&g=…`. Old links redirect.
- `routes.js` holds the section registry and loads sections with dynamic `import()`; a missing module shows "Coming soon".
- UI state persists under `rb.ui.v2`.
- `cmd.js` does optimistic apply, then on failure reverts and shows an error toast; the Undo toast lasts 5 s and `z` triggers it.
- Stale and offline states as before; while offline, writes are disabled.
- **Change:** the snapshot gains `meters.limits[]` = `{id, scope, window, kind, used, limit, state, est:boolean, paceAt, src}`. The top bar and Tokens read only this; the client does no maths.

## 5. Revised packages (800k total)

At most 2 packages run at once, with disjoint files. Every package's acceptance includes "no console errors, no CSP violations, light and dark both checked, 375 px checked".

**WP-L Ledger, limits service, CLI and ops (110k, backend, Sonnet check). Wave 1, parallel with PA.**
- Files:
  - new `roadmap/services/ledger.py` and `roadmap/services/limits.py`;
  - small edits to `services/usage.py` (record the reading), `services/budget.py` (add spend), `services/control.py` (evaluate and global fan-out), `services/cmdops.py` (`limit.set` extended, `limit.rm`), `commands/limits.py` and `core/snapshot.py` (`meters.limits`);
  - `docs/API.md`;
  - tests.
- Accept:
  1. `python3 -m unittest -q` passes.
  2. Fake readings of 40 then 43 on one day give `roadmap limit show` → `day 3.0`. A reset reading of 43 then 1 adds 1.
  3. `limit set --scope global --window day --pct 2` marks every registered project blocked, and a PreToolUse fixture gives `deny`.
  4. After `override --hours 1`, the hook allows.
  5. With usage older than 30 minutes, the state is `unknown` and the hook allows.
  6. An old project with only `autonomy.json` shows `week acct 100% (autonomy)`, and its files are byte-identical afterwards.
  7. `CLAUDECODE=1 roadmap limit set …` is refused.
  8. `undo` restores the previous row.

**PA Shell, router, command layer (110k). Wave 1.**
- Files: as before (`index.html`, `tokens.css`, `shell.css`, `icons.svg`, `router.js`, `routes.js`, `app.js`, `state.js`, `cmd.js`, `keys.js`, `views/nav.js`, `views/topbar.js`, `views/toast.js`).
- Acceptance as before, plus: the top-bar day/week meters render from `meters.limits`, and show grey when it is missing.

**PB Right panel (110k). Wave 2, parallel with PC.**
- Files: as before (`views/panel.js`, `views/projects.js`, `views/details.js`, `panel.css`), plus the 🔒 blocked mark on project rows.
- Accept: as before.

**PC Overview, Inbox, Activity (90k). Wave 2.**
- Files: as before (`views/overview.js`, `views/inbox.js`, `views/activity.js`, the `.qc` part of `flow.css`). Activity source filters move to LATER.
- Accept: as before, plus a limit-warn banner appears at 80%.

**PD Work: Board, List, Tree (120k). Wave 3, parallel with PE.**
- Files: as before (`views/work.js`, `views/board.js`, `views/list.js`, `views/tree.js`, `work.css`). Bulk is status and start/stop only.
- Accept: as before.

**PE Roadmap and Issues (90k). Wave 3.**
- Files: as before (`views/roadmap.js`, `views/issues.js`, `plan.css`).
- Accept: as before.

**PF Tokens and limits UI, Rules, Settings (110k). Wave 4, parallel with PG. Depends on WP-L.**
- Files: `views/tokens.js`, `views/limits.js`, `views/rules.js`, `views/settings.js`, `admin.css`.
- Accept:
  - Add the "Stay under 10% a day" preset in global scope; `roadmap limit show` lists it.
  - The Tokens meters show the day tick and a pace line, and the "≈" marks appear on project estimates.
  - Changing Stop to Warn clears the block within one poll.
  - Undo works.
  - Rules acceptance as before.

**PG Agents live and Research (60k). Wave 4.**
- Files: `views/agents.js`, `views/research.js`, the rest of `flow.css`, the notes GET route in `http/routes.py` and its test.
- Accept:
  - Worker rows are indented under their lead.
  - The onboarding checklist shows on a new project.
  - Lighthouse accessibility score of at least 95.
  - `wc -c web/css/*.css` totals ≤51 KB.

**Total:** 110 + 110 + 110 + 90 + 120 + 90 + 110 + 60 = 800k.

**Waves:** (WP-L ‖ PA), then (PB ‖ PC), then (PD ‖ PE), then (PF ‖ PG).

**LATER:** agents swimlane timeline and handoff arrows, the 5-hour limit window, per-model calibration, live running-job tokens, the limits history chart, bulk cap, activity filters, ⌘K palette and search, cross-project board, inline rule edit, task dependencies, launcher, digest, decisions log, cost in $, drag and drop on touch, markdown notes.

**CUT:** as before, plus deleting `legacy.html` after PG, and any per-calendar-date or per-hour limits beyond day and week.

## 6. Decisions for you

1. **One right panel with Projects and Details tabs?** I recommend yes.
2. **Native drag and drop now (desktop, with buttons kept)?** I recommend yes.
3. **What does "% of daily" mean?** I recommend: percentage points of your weekly allowance used today, so "10% a day" means 10 weekly points. The UI shows the "fair day ≈ 14%" hint.
   - The alternative is a percentage of a fair day (weekly/7). It is more intuitive, but it is a made-up window.
4. **Should global percent limits count all Claude use on the account (measured, safe) or only these projects' tracked share (estimated)?** I recommend measured all-use for global limits and estimated share for per-project limits, both labelled clearly in the UI.

(Default with no decision needed: the agents timeline moves to LATER to fund the limits work.)

### Critical Files for Implementation
- /Users/ali/Works/roadmap-board/roadmap/services/control.py
- /Users/ali/Works/roadmap-board/roadmap/services/usage.py
- /Users/ali/Works/roadmap-board/roadmap/services/budget.py
- /Users/ali/Works/roadmap-board/roadmap/commands/limits.py
- /Users/ali/Works/roadmap-board/web/js/app.js