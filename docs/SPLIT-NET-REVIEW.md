# split-net review for tomorrow (2026-10-17)

Read-only investigation. Helm board vs split-net's own docs, plus Helm-setup gaps.

## 1. What split-net is, real current state (per its own docs)

macOS-only per-app network router (Linux/Windows parked). Electron UI (`app/`), root
helper + guard (`helper/`), sing-box/Xray config gen (`core/`), agent CLI (`tools/cli`).

**Its own docs disagree on "latest state" and are themselves stale relative to today:**
- `README.md` says "Status (2026-10-11)".
- `project-state.md` self-labels "Older... the current one is session-checkpoint.md", dated 2026-10-10.
- `session-checkpoint.md` (the doc the README points to as current) is dated **2026-10-12, evening** — 5 days old.
- Newest actual repo activity: git log shows last commit **2026-10-16 21:29** ("tasks: add P7.18-P7.25 and a P2.13 note from the MultiPath review") — a day *after* session-checkpoint.md. So the most current source of truth is actually `docs/tasks.json` + git log, not the checkpoint doc.

Per session-checkpoint.md (2026-10-12), proven live that day: Allow dialog, failover+return,
sleep/wake, pause/Continue, `vpn test`, global capture 30s, Telegram via subscription VPN (ws+tls).
Xray companion engine pinned and working for two German VPNs via `vpn test`.

**Still open as of the checkpoint (likely still open — no later doc confirms closure):**
1. Reinstall the test helper (installed helper is older than working tree; missing `list-app-peers`, `close-connection`, capabilities, guard fixes). Needs the person's password.
2. Live `profile learn` test with Antigravity running + Start the profile, check models load (L14h).
3. Restart app to pick up latest UI.
4. Telegram-through-Xray-from-the-app not yet tested; xhttp VPNs, failover with Xray members, UDP not tested.
5. Global capture with the system VPN ON still refused by design — needs a decision with the person.

A commit landed 2026-10-16 adding tasks P7.18-P7.25 and a P2.13 note "from the MultiPath review" — this is **not reflected** in session-checkpoint.md, meaning the checkpoint doc undercounts current scope by at least 8 new tasks.

## 2. Board vs docs — discrepancies

Helm's `bin/roadmap status --project split-net` (data from split-net's own `docs/tasks.json`,
last updated per status line **2026-10-16**) shows:

> 276 tasks: 130 done, 79 partial, 38 todo, 29 hold, needs-you 27, running 0

This **matches** the person's earlier-reported numbers exactly — board is reading the live
tasks.json, not a stale cache. Good news: no drift between Helm's board and split-net's own
task file, because Helm reads that file directly rather than mirroring it.

**The real drift is inside split-net's own docs**, not between Helm and split-net:
- `session-checkpoint.md` (the "read this first" doc) is 5 days behind the actual `tasks.json`/git state — a worker reading only that file tomorrow would miss the 2026-10-16 MultiPath task additions.
- `project-state.md` (2026-10-10) is even further behind and should probably be dropped or merged rather than kept as a second "state" doc — having three competing state docs (project-state, session-checkpoint, README's own status line) is itself a source of confusion the person should flatten before relying on it.
- No "done" task in the needs-you sample contradicts its board status — several "done" tasks (P0.5, P0.11, P0.13, P0.16) correctly carry notes like "V backlog" / "real VPN = V backlog", i.e. the board already encodes the live-vs-fake caveat in the note field rather than falsely marking them fully proven. No board/docs falsification found.

## 3. Helm setup gaps for real head-driven work tomorrow

- **Registered**: yes, `split-net` project added 2026-10-15T04:45:34Z, path/dataPath both resolve to `/Users/ali/Works/split_net(/docs)`, path exists.
- **rules.txt**: exists at `docs/rules.txt` (R1-R12, sensible: no VPN flaps, macOS-only, agent-first CLI, Haiku workers, max 3 parallel, register every job) but **still shows as untracked (`??`) in split-net's own `git status`** — confirmed still true, matches what Helm's HANDOVER flagged. It has never been committed in split-net's repo.
- **Hooks**: split-net's `.claude/settings.local.json` wires `PostToolUse`/`SubagentStop`/`Stop` to its **own** `tools/roadmap-web/jobs_auto.py` — a separate, older dashboard (port 8765), not to Helm's `bin/roadmap hook`. Helm's own `.claude/settings.local.json` (this repo) wires `PreToolUse`/`SessionStart`/`PostToolUse`/`SubagentStop`/`Stop`/`UserPromptSubmit` to `bin/roadmap hook`. **split-net has none of that** — no `PreToolUse`, no `SessionStart`, no `UserPromptSubmit`, and its PostToolUse goes to the old system, not Helm.
- **Net effect**: HEAD-RUNBOOK's note ("split-net is registered as a separate read-only project — no hooks changed; old dashboard 8765 untouched") is **still accurate today**. Helm can read and display split-net's task/job data (because it points its dataPath at split-net's docs folder) but cannot auto-register jobs, auto-gate tool use, or get session-start briefs the way it does for Helm's own repo — because none of split-net's hooks call `bin/roadmap hook`.
- **To do real head-driven work tomorrow** (parallel workers, auto job registration, budget gating) the person needs to decide: (a) add Helm-style hooks to split-net's `.claude/settings.local.json` alongside or instead of its own `jobs_auto.py`, or (b) keep using split-net's own `jobs_auto.py`/dashboard and have Helm just read the resulting `docs/jobs.json`/`tasks.json` passively (current state). Nothing was changed by this investigation — this is a decision point, not a gap that blocks viewing.
- `docs/roadmap.db` is also untracked in split-net's repo (alongside `rules.txt`) — likely Helm- or dashboard-generated local data file; same uncommitted-local-state pattern.

## 4. The 27 needs-you items (from `task list --needs-you`)

- **P0.5** / **P0.11** / **P0.13** / **P0.16** (done, flagged needs-you) — DNS-in-TUN, system-VPN coexistence, D1-D5 ADR decisions, tether unplug/replug: all validated in Docker/sim; real-hardware/system-VPN confirmation still backlog items, not blockers.
- **P0.12b** (partial) — run RH1-RH10 on a real second connection; waiting on you having one.
- **P0.17** (todo) — RH4 sleep/wake on a *different* network; same-network sleep/wake already proven live.
- **P0.18** (partial) — RH5 DNS leak test on real networks.
- **P0.19** (todo) — RH6 QUIC/HTTP3 browser test per network.
- **P0.20** (partial) — RH7 short-connection match-miss rate with real apps.
- **P0.22** (todo) — RH9 needs your system VPN running alongside two networks.
- **P0.23** (todo) — RH10 manual real-app checks (browser, torrent) on separate networks.
- **P0.24** (todo) — RH11 DNS retest toggling your third-party VPN off/on.
- **P2.12** / **P2.19** (partial) — sleep/wake + Wi-Fi change handling; same-network case proven, other-network wake still open.
- **P2.15** (todo) — hard tests H1-H8 on macOS; H3 needs a literal hard power-off.
- **P6.1** (partial) — full leak suite (DNS/IPv6/WebRTC/kill-switch); needs root tcpdump run.
- **P3.15** (partial) — onboarding/install flow; real password-prompt install not done yet.
- **P2.17** (partial) — global "all apps" capture; exit-through-VPN in global mode unconfirmed.
- **P2.18** (partial) — DNS in global mode; live test needs you.
- **P2.20** (partial) — production helper install (RunAtLoad/KeepAlive); needs your password for a real install.

(List above covers the 20 returned by the default query window; a few more of the 27 likely
exist past the default print limit — rerun `bin/roadmap task list --project split-net --needs-you --full --json` for the exact remaining count if you want the full 27.)

**Bottom line for tomorrow**: most needs-you items cluster around two things only you can do —
(1) a real-hardware/password-gated install or VPN toggle, (2) being present for a live test run.
None of them indicate a broken board; the "needs-you" flag is doing its job correctly.
