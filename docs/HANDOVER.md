# HANDOVER: everything the person said and decided about roadmap-board (2026-10-14)

Read this first in a new chat (new Claude account is fine: everything is in this repo). Repo: https://github.com/alisinaee/roadmap-board (public) at ~/Works/roadmap-board. Sibling project: split-net (https://github.com/alisinaee/split-net, ~/Works/split_net, per-app VPN routing on macOS): its tools drive this project's job registration. The person's email is not needed.

Pointers: head procedure in docs/HEAD-RUNBOOK.md; next work to 1.0.0 in docs/NEXT-WAVE.md.

## 0. State right now (2026-10-15, written by `/head save` before an account switch)
START HERE in a new chat (any account, same Mac): `cd ~/Works/roadmap-board` and send exactly `/head` (skill ~/.claude/skills/head). Nothing needs re-explaining: read this file, docs/HEAD-RUNBOOK.md, docs/FINISH-PLAN.md, docs/HEAD-SECTION-REQUEST.md.
- **Board:** roadmap-board is its own AUTHORITATIVE project (docs/AUTHORITATIVE stops split-net's sync): 92 tasks (74 done, 4 partial, 14 todo), features F1-F25. Register jobs with `bin/roadmap job start|done` (task id from docs/tasks.json), new work with `bin/roadmap plan import` + `bin/roadmap feature link` (see HEAD-RUNBOOK). split-net is registered as a separate read-only project (no hooks changed; old dashboard 8765 untouched). Both projects have 12 rules in docs/rules.txt (split-net's file is uncommitted in ITS repo).
- **Service:** launchd agent on 127.0.0.1:8780 (`bin/roadmap service restart` loads new code; the static file list is built at startup so NEW web files 404 until restart). The person's browser pane tab 'seed' is shared: workers must open their own tab with tabs_create, never preview_start.
- **Limits the person set (OBEY):** weekly stop 95%; 5-HOUR stop 90% (2026-10-15): do not launch or continue work past it until the person says so. Usage is NOT automatic here (no keychain token): ask the person for the current 5h/weekly %, push with `roadmap usage push` or the Enter usage form. At the time of this save the person said they think the limit is reached, so ASK FIRST for numbers before launching anything.
- **Tests:** last full run 2450 tests, 5 failures, all from the unfinished WIP below. `make check`, `make check-ui` were green at e96b157 (2070 tests, 101 page runs).
- **Last pushed commit:** see `git log -1` (pushed). Finished and committed this session: wake-a-session (R7.1), copy refs (R7.12), workflow map v2 (R7.14), Planner v2 core+services+commands+screen (R7.13 H1-H6, H3b), logging steps 1-4, 2b, 3, 5a (R7.16), usage fix (R7.27), panel toggle (R7.23), rows alignment A/B, aria, Cursor reviews fixes (R3.3-R3.5 + web log/tasks fixes), UX groups A and C, Backlog step 1 (b45ca53: NOT safe alone: counts still include backlog until step 3), Tokens screen B (4b97565).
- **WIP, UNCOMMITTED (4 Haiku workers were stopped mid-edit by the account switch; their edits are in the tree):**
  1. UX group B (R8.5-R8.10 overview/activity/agents/roadmap rows): web/js/views/{overview,next,recent,activity,agents,roadmap,phases}.js, web/css/flow.css, plan.css, tests test_agents/test_plan/test_sections/test_rows/test_ref_polish/test_ux_lists.
  2. UX group D (Cmd-K button, Mark bug button+key, settings choice state; ALSO must make the 375px top bar fit: it scrolls horizontally): web/js/keys.js, palette.js, topbar.js, settings.js, web/icons.svg, tests/web/test_ux_discover.py.
  3. Map fixes from the Cursor grok review (findings 1-5, 11, 14): web/js/graph/{model,layout,render,viewport}.js, web/js/views/workflow.js, tests test_graph_*/test_workflow_*.
  4. Tokens screen package A (limits.js: weekly stop + one share per project; B is committed): web/js/views/limits.js, tests/web/test_limits_simple.py, render_limits_simple.mjs, docs/LIMITS-SIMPLE-SPEC.md. B said A must drop its duplicate sentence and not use the first project's slug in the All view.
  First job of the new head: `git diff --stat`, then one Haiku per group to FINISH (prompts: see the job titles in `bin/roadmap job list | grep failed` + docs/UX-AUDIT.md / docs/reviews/cursor-web-grok.md / docs/LIMITS-SIMPLE-SPEC.md) or revert with the person's OK; then the full suite.
- **Running outside Claude:** Cursor grok-4.7-xhigh logging/security review (job j599) writes docs/reviews/cursor-logging-grok.md when done: read it and file fixes.
- **TOP PRIORITY NEW FEATURE (the person: very important): the HEAD section** (R7.31, F25): docs/HEAD-SECTION-REQUEST.md has the person's words and the brief. First action: Opus, effort HIGH, design docs/HEAD-SPEC.md; then build. It is the persistent ledger of everything the person asks/decides, bound to tasks/issues/reviews with status; it also removes the need to re-explain after an account switch.
- **Queue after that (see docs/FINISH-PLAN.md, specs in docs/):** Backlog steps 2-3 then Work v2 + unified Issues (docs/BACKLOG-SPEC, WORK-V2-SPEC, WORK-UNIFIED-SPEC; person wants Issues folded into Work and Work interactive: + Add anything), Tokens C/D/E + a 5-hour stop control (docs/LIMITS-SIMPLE-SPEC), Git section (docs/GIT-SPEC, 7 steps + Cursor grok gate), logging 5b/6 (docs/LOGGING-SPEC), remaining UX R8.x (docs/UX-AUDIT.md; run the UX routine after every wave), R7.30 workflow map 'Open in new tab' with node details in the side panel, panel mail count vs Inbox badge (R8.22), agy/Cursor audits kept busy (agy jobs go through ~/Works/split_net/tools/agy-queue.py; Cursor via tools/cursor-review2.sh with CURSOR_MODEL=grok-4.7-xhigh), cutover R3.2 (person present), tag 1.0.0.
- **Tool facts learnt:** workers must never amend or reset commits that are pushed (it caused a diverged push once); agy needs the VPN (403 otherwise: rerun); Cursor review runs one at a time; the `rules add` CLI refuses agents (rules.txt was written directly on the person's request).

### Checkpoint 2026-10-15 (/head save, chat near limit)
- Last commit: 61aaf25 (Agents engine + effort). Pushed. Tests: full suite green except WIP web/css noise.
- Running (not stopped): j662 Cursor Head UI review, j671/j673/j674 agy audits, j675 Cursor git review, j679 Haiku reply+assets capture (WIP in roadmap/services/head.py, headops.py, hooks.py, http/routes.py, core/secrets.py and their tests).
- WIP uncommitted: the j679 capture files above; Head review fixes (secrets, forget, spool) are in the same files, commit by path with j679.
- Open for the person: run `bin/roadmap hooks install roadmap-board` (capture is OFF until then; the config flag is on); `bin/roadmap head forget H24` (placeholder entry).
- Rules from this chat: Haiku/agy/Cursor only (Sonnet and Opus off, save-token mode); agy model unpinned (CLI lists gemini-3.8-flash-high etc.); head model must follow chat model (transcript fallback in hooks); Head rows: summary + full text + attachments + AI reply + state + bound task, aligned; HEAD is the only focus now.
- First message for the new chat: `/head`

### Checkpoint 3 (/head save, usage near the limit, 2026-10-15)
- Last commit: cda12c9 (Agents: newest running job on top). Pushed.
- Running, NOT stopped (25 jobs): agy audits (8), Cursor (5: Head bug hunt, sync investigation H48, lazy-load plan H56), Haiku (1), OpenCode free models (11, some hit the free daily cap).
- WIP, uncommitted (71 files): review outputs in docs/reviews/ (agy-*, oc-*, cursor-*), and the in-progress code edits from earlier workers (secrets scrub, head ops guard, planfmt model list, head-text and head ledger data). Commit by path only after verifying.
- Open for the person: asks H35, H36, H47, H48, H49 stay open until outputs are verified (the stop hook blocks on them). H66-H71 are questions and the Argon/browser setup.
- Argon: gemini-4-argon via OpenCode returned "Insufficient account funds" (paid, no credit). Browser route: Claude extension is installed in Arc and listed as connected, but tab creation timed out; not yet tested.
- First message for the new chat: `/head`

### Checkpoint 5 (Opus head, 2026-10-15, context near limit)
- Pushed this session: 2b83d5b secrets (R7.35), 929c826 head list trim/order (R7.32), 8c456ee no umbrella-only
  binds (R7.34), 5e88be1 Agents opencode chip (R7.38), 2e48e57 head counts (R7.32). CSS cap test fixed by moving a
  stray audit file out of web/css (now docs/reviews/head-css-audit.md).
- New tasks R7.32-R7.43 (one per package, see `bin/roadmap task list`). Reviews: docs/reviews/cursor-head-p1.md,
  cursor-head-p2.md (13 real sync findings), head-agents-effort-audit.md, p6-gui.md.
- Also pushed: 311ad45 + 5040843 (R7.40 sync server/client), ef7685b (R7.41 Agents model/effort), 40e223c (R7.43
  head layout). Suite: 3138 OK at ef7685b.
- Running at save: R7.44 Haiku head paging + lazy load (routes.py, services/head.py, head.js, tests test_head_paging*);
  R7.45 Cursor grok sync ROOT CAUSE (writes docs/reviews/cursor-sync-root.md; then file Haiku fixes from it);
  R7.46 Haiku ledger audit (writes docs/reviews/head-unhandled.md; then file one task per NOT HANDLED ask and run
  them). Verify each, full suite, commit by path, push.
- /head skill now carries a "Standing mandate" (no re-tuning needed in a new chat, H106).
- Open asks: H52 and H81 need the person (unclear text); H58 needs OpenCode credit; H73 Chrome access untested;
  H84 waits on R7.41. Rules from this chat are in HEAD-RUNBOOK "Usage limits".
- First message for the new chat: `/head`

### Checkpoint 4 (/head save, 2026-10-15)
- Last commit: 2f5f594 (Cursor jobs record the real engine model; cursor-job wrapper closes its job). Pushed.
- Running: 0. All stale running jobs (24) were closed as failed. Runners fixed: agy queue, OpenCode runner and tools/cursor-job.sh close their job on crash or kill.
- Cursor sync report written (docs/reviews/cursor-sync-grok.md): partial, 3 numbered findings, not yet checked against the code. Its rerun job (j764) recorded as failed although the report exists: cause not yet found.
- Head list cut: root cause diagnosed (docs/reviews/cursor-head-lazyload-fix.md): byte trim in snapshot.py drops newest rows; the Cursor fix job (H79) edits snapshot.py and head.js. Result NOT reviewed yet.
- WIP uncommitted (about 75 files): review outputs (docs/reviews/agy-*, oc-*, cursor-*) and earlier in-progress edits. Commit by path only after verification.
- Open asks (stop hook blocks on them): H35, H36, H47, H48, H49 (bound, unverified). Decide: verify, or close as delivered-pending-verification.
- Argon: gemini-4-argon via OpenCode needs paid credit. Browser route: Claude Chrome extension connects (Browser 1 works); the Gemini app accepted the prompt once and was still planning when the test stopped. Not finished.
- Standing rules from this chat: Haiku, agy (high is max) and Cursor only for work; Sonnet and Opus off; save-token mode; Head is the focus; agents list must show real model and effort.
- First message for the new chat: `/head`

## 1. What the product is (the person's vision, in their words/themes)
A project manager that is the BRIDGE between AI agents and a human GUI: "something like Jira but so small and light, just for AI agents using"; very user friendly AND AI-agent friendly; "next generation project management AI GUI, over the fly". Python stdlib only, runs as a local service, works for ANY project (split-net is only the first), separate project in ~/Works.
Features the person asked for (keep all): planner; progress manager; subtask/task/phase manager; tasks manager; issues section; overall section; project token-usage manager; agent and subagent rules; Claude rules for the project (CLAUDE.md sync); agents can ASK the user questions (inbox, one-click answers); comments on tasks; roadmap visual; agents workflow visual = a REAL interactive diagram map (nodes/edges, done/doing/todo/blocked, handoffs, dependencies, blockers, touch+mouse, pan/zoom) plus timeline; interactive: start a task from the GUI (queue), stop, set limits, answer questions, approve phases; global (all projects) AND per-project daily/weekly usage limits ("just use below 10% of daily or weekly"); sidebar LEFT for sections, panel RIGHT for projects/general; modern Jira/Trello feel; full-width UI (no max-width cap); dark+light; phone/touch; very token-optimized for agents (cheap commands, tiny outputs, Haiku-sized skills); research-first onboarding for NEW projects (agent researches the project's needs, then fills the plan); a Planner section: features -> tasks bound to each feature (traceability, uncovered features, orphan tasks, person accepts features); notifications; ⌘K palette; daily usage limit widget; all numbers and actions ALIGNED.

## 2. Rules from the person (obey)
1. TOKENS ARE VERY LIMITED: short replies; the person wants "focused and spartan" answers (ADHD-friendly: only the answer); no long essays; workers read only what they need.
2. UI RULE 0 (top priority): numbers and actions align in fixed grid columns (right-aligned tabular numbers, actions in one fixed column, titles ellipsize) so it is readable at a glance. Also: do not limit UI width (full size). See docs/UI-CHECKLIST.md (derived from the installed ui-ux-pro-max skill, ~/.claude/skills/ui-ux-pro-max: use only its UX guidelines search, `python3 ~/.claude/skills/ui-ux-pro-max/scripts/search.py "<topic>" --domain ux -n 3` WITHOUT -I).
3. Workers: Haiku 5.5 subagents do the work; the head (Sonnet/Opus) plans and verifies. Opus 5.5 (medium/low effort) is allowed whenever advice/design/review is needed ("feel free"), kept short. Cursor Auto (tools/cursor-review2.sh, needs the person's VPN ON) for independent security/code reviews (read-only, uses Cursor quota). agy staff (Gemini 3.8 Flash, UNLIMITED quota, weak model; needs VPN + a Google login: if 403 'log out and log back in' the person must run `agy` and /login) for small atomic read-only audits, gap lists, fixtures, drafts from a facts file; read docs/AGY-PLAYBOOK.md; ALWAYS verify agy output with a Haiku (about 30-40% of its facts are wrong in doc edits). Never ask agy to run code, do security logic, UI visuals, or multi-file refactors. Run via tools/agy-queue.py (AGY_MAX env, default 3).
4. Parallelism: only file overlap limits it; give every worker a strict file list; workers stage ONLY their own files by explicit path (never `git add -A`, never reset the index); shared files (routes.js, app.js, state.js, cli.py, cmdops.py) need minimal re-read-before-edit hunks.
5. The person wants the head NOT to be idle while tasks exist ("this is the rule: dont be idle as head") BUT the LATEST instructions override: "after running tasks done, don't start new tasks at all" and "stop the tasks": everything is stopped now. Only start work when asked.
6. Always register jobs on the dashboard (hooks do it when the Agent description contains a real task id), close with tokens, update tasks.json notes, sync the board, commit, push. Show the roadmap/state at the end of every job.
7. Worker prompts must always say: never `usage sync`, never read the keychain, no network, NEVER execute `roadmap service|serve|hooks install|usage sync` (parse only), TEMP ROADMAP_HOME for runs, never touch the launchd service / real ~/.config/roadmap-board / split_net / ~/.claude, never touch port 8780 or the person's browser tabs (use own port + own new tab with explicit tabId), spawn no subagents, do not push (the head pushes). One worker once broke this and ran service install/restart: the service was verified healthy.
8. Browser: never drive the person's dashboard tab; open new tabs and close them.
9. Fresh session at ~70% context; keep the checkpoint current. When weekly usage nears the stop, report instead of continuing.
10. split-net project rules (memory, in ~/.claude/projects/-Users-ali-Works-split-net/memory/): never risk the person's VPN (Claude session depends on it: no flaps, no global TUN on the live machine), macOS only, use own core VPN for VPN tests, agent-first CLI, etc. They matter only if you touch split-net.

## 2b. Decisions and wishes added on 2026-10-14/15 (all binding)
- Be the head like before: parallel workers on disjoint files, verify, register, commit, push; never idle; Opus (medium/high) for design advice and think-heavy features; agy (unlimited, verified) and Cursor (auto or grok-4.7-xhigh, NOT API) as much as possible; Haiku edits.
- Issues must be part of Work/board (not a separate section); Work must be interactive (+ Add anything: task, issue, idea->Backlog, question, subtask, comment); a Backlog status/column; Work like Trello (docs/WORK-V2-SPEC.md).
- Tokens section must be SIMPLE: usage now + limit per PROJECT (one number) + one weekly stop; no tiny settings.
- Rules section must show both projects' rules (done: 12 each). Planner = project structure plan tree (done). Workflow map = FigJam-like flow start->now (done) + open in new tab (R7.30).
- A Git section (history, branches, auto commit/push policy, agents work close to git) (docs/GIT-SPEC.md). A Head section (R7.31, top priority). A full UI+core log for debugging what the person tests (R7.16).
- Always care for UI/UX with the ui-ux-pro-max skill after every wave and file tasks from it (UX routine in HEAD-RUNBOOK).
- The side panel must be reopenable (done: top-bar toggle). Drag on the map must not select text (done).

## 3. Decisions already made (do not reopen without asking)
- Own design system (about 64 KB CSS in web/css, tokens, CSP: no inline script/style); NOT Tabler/Gentelella/other kits (payload and edit cost). CSS total cap now 64 KB (tests/web/test_shell.py CSS_TOTAL_MAX).
- Workflow diagram: our own SVG engine, nothing vendored; default order = Dependency; jobs as pills under tasks (docs/WORKFLOW-DIAGRAM-SPEC.md). Planner = own section; tasks may have up to 3 feature links (`feats`); ONLY the person accepts a feature (docs/PLANNER-SPEC.md).
- Interaction model: Start in the GUI = queue request for an agent (no launcher at MVP); Stop/limits are ENFORCED by a fail-open PreToolUse hook + sentinel; phone listener read-only; agents cannot lift limits (agent guard; honest note: a malicious local process can forge headers: docs/SECURITY.md Known limits).
- Port 8780 for the new service; keep 8765 for the old dashboard until the cutover (docs/RELEASE.md).
- Usage limits unify weekly stop + budgets + daily/weekly rows (docs/UI-SPEC.md 2b).

## 4. What exists (built, committed, pushed)
Core (store, parsers, snapshot, API v1, launchd service, doctor, phone tunnel code, logs/redaction), agent CLI (status, task, plan import/export with P/T/F/L records, research, ask/answer/inbox, issue, subtask, comment, budget, limit, rules, stop/resume/override, feature, watch, skills install, project new --research, job progress, agent-guide), hooks (PreToolUse deny, SessionStart, Stop pickup with rules + done lines), usage ledger + limits + control, notifications (osascript), GUI: shell + left nav + right panel + sections Overview, Inbox, Roadmap, Planner, Work (board/list/tree), Issues, Agents, Workflow (timeline/table/map diagram), Tokens+limits editor, Rules, Research, Activity, Settings, ⌘K palette; 22 seeded features; demo fixtures (fixtures/demo/alpha|beta|gamma); security reviews R1 (7), R2 (8), R3 (10 + 4 bugs) fixed; ~170 agy/Cursor/Opus docs in docs/*.md and docs/reviews/.
Specs written by Opus: docs/roadmap-board-architecture.md, AGENT-INTERFACE.md, PRODUCT-SPEC.md, UI-SPEC.md, GAP-ANALYSIS.md (incl. cutover rollout order), WORKFLOW-SPEC.md, WORKFLOW-DIAGRAM-SPEC.md, PLANNER-SPEC.md, BREAKDOWN-WP57.md (task breakdown WP58-WP69 with waves, agy jobs and plan-import text), AGY-PLAYBOOK.md.

## 5. NOT done / open (nothing queued)
- Cutover into split-net (docs/RELEASE.md): register split-net as a project, `hooks install --replace-legacy` (limits on Warn first), swap out the legacy jobs_auto hooks, free port 8765, install skills (`bin/roadmap skills install` or tools/install-skills.py), delete web/legacy.html, tag 1.0.0 (version already 1.0.0 in code; not tagged). Needs the person present.
- Opus final review (WP18). Cursor review of the Planner features backend never finished.
- GUI Start/status in an unapproved phase is not gated (only the CLI is): services/commands.py _h_task_status.
- Snapshot features rows ~14 KB for 60 features (target 8 KB waived). `status` hides the features line when many jobs run.
- Planner/Workflow gap-test lists; docs refresh from docs/facts/FACTS.md (generator tools/gen_facts.py); plain-words strings pass (agy audits in docs/reviews/agy-s*-strings.md); aria fixes from docs/reviews/agy-a4-aria.md; row-alignment audit docs/reviews/agy-a05-rows.md; docs/API.md citations; SECURITY.md citation line numbers.
- Router keeps only `f`/`g` filters (workflow map filters are encoded in `f=`); ui_smoke is flaky under heavy parallel load.
- Replace `/Users/ali` paths in docs with `~` (113 mentions, cosmetic).

## 6. Facts you would otherwise rediscover
- Automatic usage is NOT possible here: the keychain item "Claude Code-credentials" holds only MCP connector tokens (atlassian/linear/slack), NOT the account token (the desktop app does not store its login there). Never print/read values of that item. Option: the person signs in once with the Claude Code CLI (`claude` -> /login) so a claudeAiOauth token appears; otherwise push usage manually.
- Cursor and agy need the VPN on (the person runs it); transient network errors kill workers (ENOTFOUND): resume them with SendMessage; agy 'Eligibility check failed' without 403 = rerun.
- Claude Code settings: hooks for job registration are in ~/Works/split_net/.claude/settings.local.json (project-local, git-ignored globally). Plugin "mods" did NOT work in the desktop app; classic hooks do. statusLine does not run in the desktop app.
- Do not use `sed -i` without '' on macOS; heredoc for hook payload JSON (zsh echo breaks \n).
- The person gets the app on 8780; screenshots: headless Chrome min width ~500 px (use the browser pane for 375).
- GitHub: `gh` is logged in as alisinaee; pushing the repo is fine (the person asked); keep pushing after finished packages unless told otherwise.

## 7. How to resume
1. `cd ~/Works/roadmap-board && git pull && python3 -m unittest discover -s tests -t . -q`.
2. `bin/roadmap service status`; open http://127.0.0.1:8780/ .
3. Ask the person what to do. Suggested order: cutover steps with the person -> Opus final review -> remaining gaps in section 5.
