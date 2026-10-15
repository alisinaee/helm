# Planner clean-up (R7.106)

Done with the CLI only (feature/task commands, so ops, activity and undo apply). No task deleted, no docs/*.json edited by hand, nothing committed.

## Before / after

| | Before | After |
|---|---|---|
| Features | 25 | 26 (F26 added) |
| Features done / doing / todo | 10 / 13 / 1 | 9 / 16 / 1 |
| Uncovered features | 1 (F24 Git) | 0 |
| Orphan tasks (no feature) | 84 | 0 |
| Empty features | 0 | 0 |
| Features removed | - | 0 (none unrelated or empty) |

## Changes

Task states (from git history, CLI `task done` / `task start` with a note):
- `task done R7.21` (WAVE-PLAN committed 02b8a1b), `R7.55` (agy audits in 6ceab3c), `R7.76` (keychain message, 90ae7df).
- `task start` (partial) `R7.22` backlog steps 1-3, `R7.24` work v2 ops, `R7.29` git section, `R7.73` head autopilot, `R7.82` v3 waves W0-W3 and S1.

New feature:
- `feature add "Core reliability v3: store, supervisor, sync"` = F26 (one body of today's work, as in the brief).

Links (`feature link`), by feature:
- F1 Agent to GUI bridge: R7.38, R7.39, R7.41, R7.60, R7.95 (agents screen, models, history).
- F2 Planner: R6.24-R6.30 (planner B1-B4, V1, V2, S1), R7.106 (this task).
- F6 Light Jira/Trello board: R7.78, R7.97, R7.101, R7.104, R7.105 (Work board and Work item model).
- F8 Agent questions and Inbox: R7.81, R7.90.
- F10 Token usage and limits: R7.63, R7.76, R7.77, R7.100 (usage source, stale state, keychain).
- F12 Rules applied to agents: R7.103 (rules pipeline, partial).
- F13 Agents workflow map: R6.31, R6.32 (diagram engine), R7.62, R7.74.
- F19 Alignment, dark/light and accessibility: R7.42, R7.47, R7.54, R7.56, R7.59, R7.65.
- F22 Security and release 1.0: R7.35 (secrets), R7.48, R7.53 (Cursor review fixes), R7.55, R7.79 (architecture doc), R7.98 (suite green).
- F24 Git sync and history: R7.29, R7.75.
- F25 Head section: R7.32, R7.34, R7.36, R7.37, R7.43, R7.44, R7.46, R7.49, R7.64, R7.66-R7.73, R7.80, R7.81, R7.89.
- F26 Core reliability v3: R7.33, R7.40, R7.45, R7.50-R7.52, R7.57, R7.58, R7.61 (sync), R7.82-R7.88, R7.91-R7.94, R7.96, R7.99, R7.102 (store, supervisor).

Removals: none. Every feature is linked to tasks and all relate to roadmap-board.

## For the person

Accept (done, not accepted; agents cannot accept):
- F1 Agent to GUI bridge, F3 Roadmap visual, F8 Agent questions and Inbox, F9 Task comments, F11 Start and stop from the GUI, F14 Token-lean agent interface, F15 Haiku skills and install, F18 App shell, F20 Phone access.

Unsure:
- F12 is now doing (R7.103 rules pipeline is partial), it was done before.
- F17 "Any project as a service; split-net cutover" mixes the generic service with the split-net cutover. Kept. Decide if the cutover stays here.
- R7.101, R7.104, R7.105 (Work item model) went to F6 instead of a new feature. Say if you want their own feature.
- R7.35 (secrets) sits under F22 (security), not F25 (head), although the WORK-MODEL map put it under head.
- Done calls from commit evidence: R7.21, R7.55, R7.76. Re-check if they are wrong.
- Left as is: R6.18 (todo, maybe partly done in 4acc30a), R7.59, R7.26, R7.30, R7.13 (todo), R3.6, R3.7, R7.5, R7.12, R7.25, R7.31, R7.16, R7.103, R7.105, R7.106 (partial).
