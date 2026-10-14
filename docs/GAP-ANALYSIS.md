# Gap analysis vs the vision, top improvements, cutover plan (Opus WP39, 2026-10-14)

I read only the parts you named, plus a few greps of `hooks.py`, the config and split-net's hook settings. The main findings are below.

## 1. Gap analysis

| Vision item | State | What a user would still miss |
|---|---|---|
| Bridge between agents and a human GUI | built | One write path through `/cmd`, a cheap CLI and hooks. |
| Planner | built | Lanes, ↑/↓, Approve and `plan import`. Task dependencies (`after:[]`) are LATER, so "what can run in parallel" isn't shown. |
| Progress manager | built | Spend only updates when a job finishes; running jobs show no live tokens. |
| Phase / task / subtask manager | built | No inline edit of a task title or plan line from the GUI; you'd need to check this. |
| Issues | built | Blockers gate `next:`. Nothing else is missing. |
| Overall view | built | No daily digest: "what happened since I last looked" is LATER. |
| Project token-usage manager | partial | Meters, caps and override exist. No cost in $. Estimates are not calibrated per model, so "≈" stays rough. |
| Tasks manager (board) | built | ↑/↓ only, no drag and drop. That is acceptable. |
| Agent / subagent rules, Claude rules | partial | Rules engine, CLAUDE.md sync and `rules show --for` exist. But a lead only gets the rules if it remembers to run `rules show` before spawning a worker. Nothing injects them on its own. |
| "Small Jira just for AI agents" | built | The command set is complete. 35 top-level commands is a lot for a Haiku agent to find its way through. |
| Agents ask the user questions | built | `ask`/`answer`/`ask get` work. **But the person is never alerted.** A blocking question sits in the Inbox until someone opens the GUI. |
| Comments on tasks | built | Flat thread. Fine. |
| Roadmap visual | built | Lanes on a CSS grid. |
| Agents workflow visual | partial | The Agents-live card shows workers indented under their lead. The time-axis timeline with handoffs is LATER. |
| Start / stop from the GUI | partial | Stop is real (PreToolUse deny). Start only queues a request. The Stop hook picks it up only if a session is running and finishes a turn. **If no session is open, pressing Start does nothing you can see.** This is the largest gap people will feel. |
| Set limits / answer questions in the GUI | built | Through PF. |
| Global + per-project day/week limits ("below 10%") | built | Ledger, limits, the 10% preset and a global fan-out. Usage older than 30 minutes is treated as `unknown` and the hook allows work, so the limit is soft when the usage loop stalls. |
| "Next-gen AI PM GUI on the fly" | partial | The shell, panel and live polling exist. No ⌘K palette or search. Activity has no filters. |
| Modern Jira/Trello feel | partial | Board, list, tree and drawer exist. Drag and drop and search are missing, so it feels about 80% of the way there. |
| Optimized for the user's tokens | built | Status ≤8 lines, inbox ≤6, the hook fast path. Not measured end to end: no one has checked the real token cost of a full agent cycle. |
| Good skills for Haiku agents | **partial/missing** | The skills are still drafts in `docs/skill-draft/` (the main `SKILL.md` alone is 12.7K, too big for Haiku). They aren't installed, and no `roadmap skills install` exists. |
| Research-first onboarding for new projects | partial | `research new/check` and the onboarding checklist exist. No single command starts a new project with research → plan → approve. |
| Any project, runs as a service | partial | launchd, `project add` and `doctor` exist. **The default port in code is still 8765** (`roadmap/store/config.py:19`, `commands/serve.py:18`), which is the same as the legacy split-net server. Split-net still runs the legacy `jobs_auto.py` hooks. |

## 2. Top 8 improvements

**1. Wake-up notification for Start and questions.**
- **What:** When a Start is queued, a blocking question is asked, or a limit blocks work, the service sends one desktop notification through `osascript display notification` (rate-limited, can be switched off in config). The text gives the exact action, for example: "Start P2.4 queued, run `claude` in ~/Works/x or type 'go'".
- **Why:** It fixes both "agents ask questions" and "Start from the GUI" for about 1/10 of what the launcher costs.
- **Size:** 15k. **Worker:** Haiku, then a head check.
- **Files:** new `roadmap/services/notify.py`; hook calls in `services/queue.py` and `services/questions.py`.
- **Acceptance:** A queue add calls notify once. A second add within 60 s does not. Setting `notify:false` does nothing. No macOS → no-op, exit 0.

**2. `roadmap watch` (or `next --wait`).**
- **What:** A long-poll command that blocks on `queue.json` and the questions file (mtime poll every 2 s, timeout `--max 1800`). It prints one line: `start P2.4` / `answer Q3 yes` / `timeout`.
- **Why:** An idle lead session can sit in `roadmap watch`, so GUI Start reaches it at almost no token cost. This is the cheap launcher.
- **Size:** 12k. **Worker:** Haiku.
- **Files:** new `roadmap/commands/watch.py`, plus registering it in `cli.py`.
- **Acceptance:** In a temp home, with `watch` running in the background, a `/cmd` task.start makes it print `start P1.1` and exit 0 in under 3 s.

**3. Make the SessionStart and Stop pickups bring the rules with them.**
- **What:** When `_stop_pickup` surfaces a queued task, also attach the output of `rules show --for <task> --role lead` (≤12 lines) and the task's definition of done.
- **Why:** Rules then get applied without the lead having to remember to fetch them (vision item: agent rules).
- **Size:** 8k. **Worker:** head or Sonnet, because this is hook code (WP22 risk area).
- **Files:** `roadmap/services/hooks.py` only.
- **Acceptance:** The Stop-hook fixture reason contains `R` rule lines. It still finishes in under 300 ms. The pickup cap of 3 per session still holds.

**4. Ship Haiku-sized skills.**
- **What:** Cut `docs/skill-draft/*` down to two skills of 2–3K each (`roadmap-worker`: about 10 commands; `roadmap-lead`: plan, rules, spawn), and add `roadmap skills install [--project]`, which copies them into `.claude/skills`.
- **Why:** This is the "good skills for Haiku" item, and the part agents actually read.
- **Size:** 20k. **Worker:** head writes the text, Haiku writes the install command.
- **Files:** `roadmap/templates/skills/`, new `commands/skills.py`.
- **Acceptance:** `wc -c` is under 3200 per skill. `tools/check_docs.py` passes on every command the skills mention. A cold Haiku session finishes "mark P1.1 done with 20k" in at most 2 tool calls.

**5. Port and config cutover safety.**
- **What:** Change the default port to 8780. `doctor` warns when 8765 is held by a non-roadmap process. Add `roadmap open --port`.
- **Why:** Avoids the port clash at cutover (see Risk 2).
- **Size:** 5k. **Worker:** Haiku.
- **Files:** `store/config.py`, `commands/serve.py`, `services/doctor.py`, docs that mention the port.
- **Acceptance:** A fresh config gives 8780. `doctor` with a dummy listener on 8765 gives `warn`.

**6. `roadmap project new --research`.**
- **What:** One command that runs init, creates research note 1 from a template, makes the plan template and leaves phase 1 unapproved. The Overview checklist then points to "approve phase 1".
- **Why:** Research-first onboarding becomes one step.
- **Size:** 10k. **Worker:** Haiku.
- **Files:** `commands/project.py` (new subcommand only), `templates/`.
- **Acceptance:** In a temp home, `status` shows "research 1/1 open, phase P1 not approved", and a worker's `task start` is refused with a hint.

**7. Live job tokens plus the stale-usage warning.**
- **What:** `job progress --tokens K` (optional, cheap). The Agents card shows a "usage stale" pill when the reading is older than 30 minutes, so the soft-allow is visible.
- **Why:** Makes progress and limits feel honest.
- **Size:** 15k. **Worker:** Haiku for the backend; agy or Cursor reviews the UI.
- **Files:** `services/jobs.py`, `web/js/views/agents.js`, `views/topbar.js`.
- **Acceptance:** A stale fixture shows the pill. `job progress` updates the snapshot, and spend is not counted twice when `job done` runs.

**8. ⌘K palette (jump to a task or issue, run Start/Stop/Answer).**
- **What:** Search the in-memory snapshot on the client and dispatch the existing `/cmd` ops.
- **Why:** This is what makes it feel like modern Jira or Linear "on the fly", and it also gives you client-side search.
- **Size:** 25k. **Worker:** Cursor writes it, head reviews.
- **Files:** new `web/js/views/palette.js` and the `keys.js` hook-up.
- **Acceptance:** ⌘K then "P2.4" then Enter opens the drawer. `>stop` stops the project. No console or CSP errors. Light, dark and 375 px all checked.

**Total:** about 110k. Items 1–6 (70k) are the "feels finished" core.

**Parallel-safe pairs (no shared files):** (1 ‖ 2), (4 ‖ 5), (6 ‖ 7), then 3 alone (it is in the hooks file), then 8.

## 3. Cutover risks for split-net

**Risk 1: the hooks swap halts or double-counts sessions.**
Split-net's `.claude/settings.local.json` has three `jobs_auto.py hook` entries. If the old and new hooks both run, every job is counted twice. If the new PreToolUse hook fails closed, every session stops.

**Risk 2: port 8765.**
The legacy split-net server and roadmap's default both use 8765. If both run, one fails to bind, or the browser and `open` hit the wrong server. Phone and bookmark URLs also break.

**Risk 3: data compatibility.**
The migration (autonomy v1 to v2), new files and `schemaVersion` refusal can leave the legacy `tools/roadmap-web` scripts unable to read files the new code changed. They can also turn a stale or `unknown` usage reading into a false block or false allow on day one.

**Safe rollout order**

1. **Back up and dry-run.**
   - Run `roadmap backup` and `git stash` of `.claude/`.
   - Copy split-net's data into a temp `ROADMAP_HOME` and run `project add`, `doctor` and `status` there.
   - Compare the snapshot with the legacy page. The fixture tests say they match exactly; confirm it on live data.
   - **Rollback:** delete the temp home.
2. **Service on 8780, read-only alongside the old one.**
   - Run the new service on 8780 with the legacy server still on 8765. Register split-net with no hooks installed.
   - **Rollback:** `roadmap service uninstall`.
3. **Check the migration files are byte-identical before any writes.**
   - Confirm acceptance item 6 (old project files byte-identical afterwards) on a copy of the real data.
   - **Rollback:** restore the timestamped backup.
4. **Hooks swap with enforcement off.**
   - Run `hooks install --replace-legacy` with the limits set to Warn, not Stop. Run 1–2 days, watching `doctor` and the job counts against the legacy log.
   - **Rollback:** `hooks uninstall` and restore the backed-up `settings.local.json`. Install already writes this backup.
5. **Turn on enforcement.**
   - Switch to Stop and test it by hand with `roadmap stop` and then `resume`.
   - **Rollback:** switch back to Warn. You can do this in one GUI click with undo.
6. **Retire the legacy server, keep 8780.**
   - Stop the legacy server, keeping `tools/roadmap-web` for one release. Do not move roadmap onto 8765.
   - **Rollback:** restart the legacy server. Its data is untouched if step 3 held.

## 4. Cut or defer

- **Defer the launcher (90k).** Items 1 and 2 cover about 80% of what it would do.
- **Defer:** the swimlane timeline, task dependencies, drag and drop, the limits history chart, cost in $, digest, decisions log, the cross-project board, the 5-hour window, per-model calibration, activity filters and inline rule edit.
- **Cut:**
  - phone writes (keep phone read-only);
  - markdown rendering of notes;
  - Tabler and chart libraries (already cut);
  - any per-hour or per-date limits.
- **Shrink:**
  - Hide rarely used commands (`phone`, `backup`, `undo` by id, `plan template`) from the agent guide so a Haiku agent sees about 12 commands.
  - Delete `legacy.html` once step 6 is stable.

### Critical files for implementation
- /Users/ali/Works/roadmap-board/roadmap/services/hooks.py
- /Users/ali/Works/roadmap-board/roadmap/services/queue.py
- /Users/ali/Works/roadmap-board/roadmap/store/config.py
- /Users/ali/Works/roadmap-board/docs/skill-draft/SKILL.md
- /Users/ali/Works/split_net/.claude/settings.local.json