| bullet | source file:line |
|---|---|
| Python standard-library-only project manager serving as a bridge between AI agents and human GUI | docs/HANDOVER.md:13 |
| Background service running via macOS launchd agent `com.roadmap-board.agent` on `127.0.0.1:8780` | docs/HANDOVER.md:8 |
| UI Rule 0: numbers and actions align in fixed grid columns with unconstrained full-width layout | docs/HANDOVER.md:18 |
| Custom lightweight design system using 25 KB CSS tokens and strict CSP with no inline scripts or styles | docs/HANDOVER.md:29 |
| Interactive SVG workflow diagram engine without vendored dependencies displaying tasks, jobs, dependencies, and timeline | docs/HANDOVER.md:30 |
| Planner section binding tasks to features with a maximum cap of 3 feature links per task | docs/facts/FACTS.md:584 |
| Planner feature capacity capped at 60 features per project, accepted exclusively by the user | docs/facts/FACTS.md:585 |
| GUI sections covering Overview, Inbox, Roadmap, Planner, Work (board/list/tree), Issues, Agents, Workflow, Tokens/limits, Rules, Research, Activity, Settings, and ⌘K palette | docs/HANDOVER.md:36 |
| Claude Code hooks for PreToolUse deny, SessionStart, and Stop pickup with rules enforcement | docs/HANDOVER.md:36 |
| Fail-open PreToolUse hook sentinel enforcing stop and limit controls with agent guard preventing limit lifting | docs/HANDOVER.md:31 |
| Session presence tracking via `docs/presence.json` in data directory recording hook ISO timestamp, watch ISO timestamp, and watchPid | docs/R7.1-SPEC.md:14 |
| Hook presence touch throttled to at most once per 30 s to remain within the 300 ms hook budget | docs/R7.1-SPEC.md:15 |
| `roadmap watch` sets presence watch timestamp and watchPid on start, refreshes every 30 s, and clears both on exit | docs/R7.1-SPEC.md:16 |
| Derived snapshot session state classified into "watching" (<60 s), "open" (<10 min), or "none" | docs/R7.1-SPEC.md:17 |
| GUI Run status displays session state ("Queued, a session is picking it up", "Queued, picked up at the session's next stop", or "Queued, waiting for a session" with a Copy command button) | docs/R7.1-SPEC.md:18 |
| Desktop notifications via osascript adapt message when no session is open and maintain rate limits | docs/R7.1-SPEC.md:22 |
| Optional launch (`launchOnStart: true`) runs Terminal with `claude` once per 10 min when presence is none | docs/R7.1-SPEC.md:23 |
| Presence service (`roadmap/services/presence.py`) providing atomic writes and non-raising state queries | docs/R7.1-SPEC.md:30 |
| Launcher service (`roadmap/services/launcher.py`) gating execution with argv-only shell and AppleScript escaping | docs/R7.1-SPEC.md:35 |
| `roadmap serve` CLI runs dashboard server on port 8780 with options to disable usage loop and phone listener | docs/facts/FACTS.md:8 |
| `roadmap service` CLI provides launchd lifecycle actions (install, uninstall, start, stop, restart, status, logs) | docs/facts/FACTS.md:33 |
| `roadmap project` CLI provides registration and maintenance actions (add, list, show, init, remove, check, migrate, new) | docs/facts/FACTS.md:53 |
| `roadmap job` CLI tracks agent jobs and token consumption (start, done, fail, progress, list, prune) | docs/facts/FACTS.md:75 |
| `roadmap task` and `roadmap plan` CLIs manage phases, tasks, bulk set lines, and grammar import/export | docs/facts/FACTS.md:94 |
| `roadmap ask` and `roadmap answer` CLIs allow agents to ask questions with options, defaults, timeouts, and blocking | docs/facts/FACTS.md:164 |
| `roadmap issue` and `roadmap subtask` CLIs manage project issues and checklist subtasks | docs/facts/FACTS.md:131 |
| `roadmap rules` CLI manages project rules in docs/rules.txt and syncs rules into CLAUDE.md | docs/facts/FACTS.md:429 |
| `roadmap usage` and `roadmap limit` CLIs manage account usage points and unified token stop/budget rules | docs/facts/FACTS.md:447 |
| `roadmap phone` CLI manages secure read-only phone tunnels and rotating access tokens | docs/facts/FACTS.md:473 |
| `roadmap doctor` CLI inspects system health and outputs plain-words remediation fixes | docs/facts/FACTS.md:463 |
| `roadmap skills` CLI lists and installs agent skills into `.claude/skills` | docs/facts/FACTS.md:501 |
| Start queue capped at 50 entries (`CAP = 50`) stored in `queue.json` | docs/facts/FACTS.md:580 |
| Open issues capped at 200 (`OPEN_CAP = 200`) and open questions capped at 50 (`OPEN_CAP = 50`) | docs/facts/FACTS.md:599 |
| Activity log stored in `activity.jsonl` keeping the newest 500 operations with reversible undo support | docs/facts/FACTS.md:590 |
| Standard system paths defined for config (`~/.config/roadmap-board/`), state, logs, and project data (`<project>/docs/`) | docs/facts/FACTS.md:762 |
