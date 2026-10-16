# Project Dashboard Map & Evaluation

| Section | File(s) | Purpose in 1 line | State | Overlaps With | Advice |
|---|---|---|---|---|---|
| Overview | web/js/views/overview.js:1-4 | Cockpit displaying limit banners, KPI tiles, inbox preview, running agents, and recent events | works (overview.js:1-19, HANDOVER.md:12) | Inbox, Activity, Agents, Roadmap | Keep as primary landing cockpit |
| Inbox | web/js/views/inbox.js:1-7 | Central queue for human decisions on agent questions, Head asks, rule proposals, and blockers | works (inbox.js:1-7, HANDOVER.md:52) | Overview (preview), Head (asks), Work (blockers) | Keep as core human-in-the-loop bridge |
| Head | web/js/views/head.js:1-12 | Persistent audit ledger of all user prompts, AI replies, asks, and linked task decisions | half (head.js:1-12, HANDOVER.md:27-30) | Inbox (asks), Work items, Activity | Keep; finalize lazy-loading and hook capture |
| Roadmap | web/js/views/roadmap.js:1-10 | Phase milestone lanes with task ordering, token spend progress, and phase approval gates | works (roadmap.js:1-10, HANDOVER.md:53) | Work (tasks/phases), Workflow (timeline) | Keep for macro-level milestone progress |
| Planner | web/js/views/planner.js:1-8 | Feature tree hierarchy (F#) mapping high-level specs to tasks with acceptance criteria | works (planner.js:1-8, HANDOVER.md:13) | Work (tasks/tree/items, WORK-MODEL.md:3-6) | Merge into Work items (W#) and retire section |
| Work | web/js/views/work.js:1-5 | Day-to-day Kanban board, list, and tree managing active tasks, issues, and live job status | half (work.js:1-5, WORK-MODEL.md:5-7,61) | Planner (features), Roadmap (tasks), Issues (defects) | Keep; absorb Planner features and Issues |
| Issues | web/js/views/issues.js:1-5 | Standalone issue tracking view for bugs, risks, and blockers linked to tasks | broken (routes.js:28-30 redirects to Work; dead code) | Work (work.js:10-11, kind:issue) | Delete file (already folded into Work per R7.97) |
| Agents | web/js/views/agents.js:1-7 | Live worker tree of active jobs, models/efforts, tokens, and paged execution history | works (agents.js:1-7, HANDOVER.md:26,62) | Overview (running card), Workflow (swimlanes) | Keep for agent observability and process control |
| Workflow | web/js/views/workflow.js:1-8 | Visual diagram map (SVG graph), timeline swimlanes, and job table showing execution flows | works (workflow.js:1-8, HANDOVER.md:42) | Agents (jobs), Roadmap (phase timeline) | Keep as visual workflow debugger |
| Tokens | web/js/views/tokens.js:1-6 | Token spend telemetry, weekly/5h quota meters, limits configuration, and 1-hour overrides | half (tokens.js:1-6, HANDOVER.md:18) | Topbar (usage band), Overview (limit banner) | Keep; commit package A limits consolidation |
| Rules | web/js/views/rules.js:1-4 | Agent guardrail editor scoped by model/role with one-click sync to CLAUDE.md | works (rules.js:1-4, HANDOVER.md:52) | Inbox (rule proposals) | Keep for prompt instruction management |
| Git | web/js/views/git.js:1-9 | Safe repo browser for staged changes, commit history linked to tasks, and branches | half (git.js:1-9, WORK-MODEL.md:68) | Activity (audit log), Work (commit bindings) | Keep; finalize 7-step spec without mutating cmds |
| Activity | web/js/views/activity.js:1-4 | Unified chronological event log across GUI, CLI, and agents with single-click undo | works (activity.js:1-4, HANDOVER.md:13) | Overview (recent activity), Git (commit history) | Keep for reversibility and auditability |
| Settings | web/js/views/settings.js:1-4 | Theme selection, UI density, single-key shortcuts toggle, and runtime debug log viewer | half (settings.js:1-4, HANDOVER.md:16) | Topbar (theme controls) | Keep; finish uncommitted choice state |
| Research | UNKNOWN (no file in web/js/views/) | UNKNOWN in GUI; CLI stores up to 6 exploratory notes in docs/research/ | broken (README.md:40 claims nav rail; routes.js omits it) | Head ledger, docs/research/ notes | Delete GUI nav mentions; clean orphaned CLI/tests |

## What the Project Is For
1. Local lightweight project management bridge connecting human supervision to Claude Code and AI agent swarms (README.md:3, HANDOVER.md:129).
2. Runs as a local daemon on macOS at 127.0.0.1:8780 with zero third-party dependencies using Python 3.9+ stdlib (README.md:6-8).
3. Reads and writes project state via validated, atomic, undoable operations on local files (README.md:4,359).
4. Provides a human browser GUI with fixed tabular alignment, dark/light themes, and mobile-friendly layouts (README.md:38, HANDOVER.md:130,134).
5. Provides a token-optimized CLI where commands return compact text or --json to keep agent context cheap (README.md:7,360).
6. Enforces hard safety limits on token spend via 5h/weekly quotas, PreToolUse guard hooks, and stop sentinels (README.md:5,142, HANDOVER.md:11).
7. Keeps a human-in-the-loop decision queue (Inbox) for single-click answers, unblocking, and phase approval (README.md:202-209,381).
8. Tracks live agent execution with real-time job trees, model effort, and runtime statuses across parallel workers (README.md:181-184, HANDOVER.md:135).
9. Synchronizes project-scoped constraints and prompt rules directly into CLAUDE.md (README.md:227, HANDOVER.md:130).
10. Maintains a persistent ledger (Head) of human requests and decisions that survives chat restarts and context limits (HANDOVER.md:21, WORK-MODEL.md:32).

## Where It Got Lost
1. Abstraction mixing: blurred human deliverables and low-level agent packages in tasks.json (WORK-MODEL.md:3-6).
2. Entity triplication: ran Planner features (F#), Work tasks (R#), and Work items (W#) simultaneously (PLANNER-SPEC.md:1-24, WORK-MODEL.md:8-16).
3. Phantom GUI sections: advertised a Research section in README.md:40 that was never registered in routes.js:5-21 or built.
4. Zombie code accumulation: deprecated Issues into Work (routes.js:28-30) but left orphaned issues.js and tests (test_plan.py:240-266).
5. Broken usage sync: keychain item lacked account OAuth token, forcing manual push workarounds (README.md:44-46, HANDOVER.md:11,174).
6. Custom engine over-engineering: hand-rolled a 1643-line SVG graph/swimlane engine (workflow.js:1-60) while Work model stalled (WORK-MODEL.md:91-102).
7. Sudden pivot to Head: redirected effort to a 1264-line prompt/chat ledger (head.js:1-12, HANDOVER.md:21) before 1.0 cutover was complete.
8. Sub-agent coordination bloat: spawned dozens of parallel Haiku, Cursor grok, agy, and Opus workers generating review churn (HANDOVER.md:13-23,35).
9. Recurring token exhaustion: progress repeatedly stalled due to hitting weekly (85-95%) and 5h (80-90%) Claude quotas (HANDOVER.md:11,41,50,60,78).
10. Premature multi-project scope: built cross-project aggregations (home.js, tokens.js:34) before split-net cutover finished (HANDOVER.md:165).

## Planner vs Work Overlap & Merge Plan
- **Overlap**: Planner (planner.js:1-8) tracks feature tree (F#) with acceptance criteria and tasks; Work (work.js:1-5, tree.js:1-5) tracks tasks and filters by feat: (work.js:47-97). WORK-MODEL.md:8-16 introduces Work items (W#), making Planner redundant.
- **Merge Plan**:
  1. *Model*: Migrate features.json into work_items (W#) in docs/work.json; feature title/acc become Work item title/outcome (WORK-MODEL.md:12,44-53).
  2. *Hierarchy*: Move Planner's tree (planner.js:48-113) into Work Tree tab (tree.js:1-58) as Work item -> Agent tasks -> Subtasks.
  3. *Acceptance*: Move Planner's Accept button (planner.js:218-220) to Work Review column and drawer (WORK-MODEL.md:22,100).
  4. *Binding*: Replace task feats:[F#] with work_id:W# (WORK-MODEL.md:14,46).
  5. *Retirement*: Delete web/js/views/planner.js, remove Planner from web/js/routes.js:12 and web/js/views/nav.js:94.

## Research Section Usage (To Delete)
- **Nav & Docs**: Remove "Research" from nav rail in README.md:40, onboarding in README.md:96-99, and CLI table in README.md:212-214.
- **Web Files**: Delete kind === "research" handler in web/js/ref.js:70-72; confirm no web/js/views/research.js exists.
- **Web Routes**: None exist (never registered in web/js/routes.js or web/js/router.js).
- **Backend Files**: Delete roadmap/commands/research.py; remove "research" from roadmap/cli.py:31; clean research from roadmap/core/guide.py:1,26,39-43, roadmap/core/refs.py:6,14,29,162-168,205,224-225, roadmap/commands/ref.py:14,41,51-55, roadmap/commands/project.py:7,52,55,146,153,158-162,188-193, and roadmap/commands/status.py:11,80-89.
- **Tests**: Delete tests/unit/test_research_cmd.py; remove tests in tests/unit/test_cmd_ref.py:104-113, tests/unit/test_phase_gate.py:136-147, and tests/unit/test_project_new.py:23-45.
