# 5. Roadmap

Rule R0 applies: blockers are skipped, workarounds are used. Dates are not fixed. Phases are
ordered by dependency and risk. Detailed tasks are in [06-dev-plan.md](06-dev-plan.md).

```text
P0 Spikes ──▶ P1 Engine ──▶ P2 macOS MVP ──▶ P3 Full UI ──▶ P4 Linux ──▶ P5 Windows
                                          │                                          │
                                          └────────── P6 Hardening ◀────────────────┘
                                                          │
                                                   P7 Advanced ──▶ P8 Signed mode (optional)
```

| Phase | Status | Goal | Result you can see | Exit gate |
|---|---|---|---|---|
| P0 Spikes | ✅ closed 2026-10-08 (user-hands items moved to the validation backlog). Counts in tasks.json for this phase field: 20 done, 4 partial, 0 todo, 3 hold. P0 also holds P2.31, P2.32, P3.44, P3.45, A1, A2, A5 and the agent CLI tasks P7.13 to P7.15 (filed under P0, not P7) | Prove every unverified claim, pick core and helper language | Spike report per item, decisions D1–D5 closed | All spikes S1–S13 have a result |
| P1 Engine | 🟡 6 done, 4 partial, 0 todo (tasks.json): core parsers, generator, launcher, engine tests and the end-to-end test through a local VLESS server (P1.10) done; CLI profile commands and the connection test partial (fakes); Keychain (P1.7, P1.9) partial (fakes); core binary bundle (P1.1) partial | Standalone engine: core sidecar, profiles, local proxy, no privileges | Import a profile, start it, test it with curl through a local SOCKS port | Each protocol passes on mac, Linux, Windows |
| P2 macOS MVP | 🟡 21 done, 21 partial, 7 todo (tasks.json, recomputed 2026-10-13). Live: scoped Telegram (10.23), two scoped lanes on Wi-Fi + iPhone tether with VPN over a chosen connection (10.24), core crash recovery (10.27), 250 s lane hold after the P2.33 fix (10.28). Not live: global capture (consent and the two human dialogs are fakes only), failover timing (10.26), sleep/wake, real helper install, upgrade and rollback (P2.20, P2.21) | Per-app rules on macOS with a root helper and TUN | App A on Wi-Fi, B on tether, C on VPN, live per-app stats | Hard tests H1–H8 pass on macOS |
| P3 Full UI | 🟡 13 done, 24 partial, 4 todo (tasks.json, recomputed 2026-10-13). Screens built on the kit (profiles, networks, activity, connections, log, tray). One on-screen check on 2026-10-11 (dark, empty, helper-error states) found 3 problems, now fixed; onboarding, Settings, Activity, Connections, Log and the light theme are still not seen on screen | Real product feel | App list, rule editor, profiles import, usage charts, history | UI tests pass, usability pass |
| P4 Linux | ⏸ deferred (R13, macOS first) | Linux backend (netns, cgroup, eBPF) | Same rules on Linux, better isolation | Hard tests pass on 2 distros |
| P5 Windows | ⏸ deferred (R13, macOS first) | Windows backend (WinDivert, WFP, ETW) | Same rules on Windows | Hard tests pass on Win 10 and 11 |
| P6 Hardening | 🟡 started: tasks.json (phase field P6, recomputed 2026-10-13): 10 done, 17 partial, 5 todo (P6.8 done with redacted report and issue template; P6.1 leak suite, P6.3 upgrade and downgrade built with fakes, P6.5, P6.6, P6.7 partial; P6.10 partial, security review: Sonnet done, Opus sign-off pending; P6.2, P6.4, P6.9, P6.11 todo; the phase also holds S, L and C ids); security fixes S1 to S8, S10, S11 done, S9 peer credentials not built | Leaks, crashes, updates, installers, security fixes S1-S9 | Kill switch, recovery, auto-update, uninstaller, diagnostics | Full hard-test suite green on all OSes |
| P7 Advanced | 🟡 started (fakes): tasks.json (phase field P7, recomputed 2026-10-13): 4 done (P7.11, P7.12, P7.16, P7.17), 4 partial (P7.3 limits and quotas, P7.7 CLI, P7.8 notifications, P7.10 auto-switch), 6 todo (P7.1, P7.2, P7.4, P7.5, P7.6, P7.9). The agent guide (P7.14) is done; the agent CLI (P7.13) and the read-only control API (P7.15, built with fakes, tasks.json says partial) are filed under P0, so they are not in these P7 counts. External VPN detection and the activity monitor are done as P2 tasks | Hybrid spread, limits, quotas, schedules, system-VPN-for-one-app | Power features | Each feature has tests |
| P8 Signed mode | ⏸ parked (blocker B1) | Network Extension on macOS (blocker B1 lifted) | Exact attribution, hard block | Only after buying the Apple account |

## Live view

`tools/roadmap-web/` (`python3 tools/roadmap-web/server.py`, http://127.0.0.1:8765, or `make roadmap-web`): a local page that re-reads `docs/tasks.json` and these docs on every request and polls every 2 s, with a live dot and an updated clock. Open it in the Claude Code browser pane. The earlier Claude Code mod pane was removed on 2026-10-08 (it went stale when hot reload was not active).

## Progress log

| Date | Done |
|---|---|
| 2026-10-12 (late) | **Isolation proven live** (10.49): the profile's VPN is really used by its app and other apps keep their own IP, per VPN (sweep of 27 saved VPNs; routes and DNS unchanged every run). Hard self-test 'Profile isolation' added to the app Debug panel (button in the bottom bar next to Restore network). Sidebar fixed: one scroll area, compact, collapsible Advanced, layout probe log. Plain-words message when All apps is refused because a VPN app is connected (L18 part 1). Open: L17 C/D, L18 part 2 (Happ as the profile's VPN), L14, L11-L15 |
| 2026-10-12 | **Global (All apps) capture proven live on Wi-Fi** (10.48): root cause of the dropped connection and Antigravity's models not loading was that the baseline-bound direct fallback had no route (ENETUNREACH) once the TUN /1 routes existed; the helper now adds a guard-recorded interface-scoped default during global capture. Also proven live: Xray companion engine (xhttp, mKCP, TCP header and more) through the helper, the global probe (30 s held, HTTPS ok, routes and DNS unchanged). Open: global with the system VPN on (refused by design), apps with no known IP range (L14), L11-L15 |
| 2026-10-11 | Live: failover on iPhone unplug and return to the preferred connection proven, 59 of 59 requests OK; the lane continues on Wi-Fi with no pause (10.40 fixed, 10.41) |
| 2026-10-11 | Live: `vpn test` through the stored VPN over Wi-Fi: exit IP is the VPN server's, 1 KB used; three bugs found and fixed on the way (10.39) |
| 2026-10-11 | Live: a lane survives a 44 s sleep after the wake-grace fix; a 12 s sleep is still open (10.36, 10.37) |
| 2026-10-11 | Live: Allow dialog from the root helper works; the 60 s give-up through the helper is refused with nothing started; global capture refused with 2 default routes, as designed (10.33, 10.38). Global capture itself not proven |
| 2026-10-11 | Afternoon: "All other apps" lane in the editor (P3.19): macOS Allow dialog flow, 10-minute window, countdown, Keep running. Fakes only (10.32) |
| 2026-10-11 | Afternoon: menu bar title with live speed and a speed line per running profile. Built, not seen on the Mac (10.32) |
| 2026-10-11 | Afternoon: ask on first connect ("Telegram is using the network. Add it to a profile?") wired end to end. Fakes only (P7.8, 10.32) |
| 2026-10-11 | Afternoon: signed update check (ed25519, https only, never installs by itself). Real key not set, not run live (10.32) |
| 2026-10-11 | Afternoon: per-app stats history, 35-day retention, lifetime totals. Tests only (10.32) |
| 2026-10-11 | Afternoon: performance bench in core; overlap check fixed, O(n^2) to a faster check: 11 s down to 2.4 s at 8 lanes x 1000 apps (10.32) |
| 2026-10-11 | Afternoon: app icon pipeline, checksums script and release checklist in packaging (W8). Built, not run on a release build (10.32) |
| 2026-10-11 | Afternoon: plain-language user guide (docs/27) and refreshed install guide (docs/15). Written, not yet checked on the Mac (10.32) |
| 2026-10-11 | Afternoon: dashboard shows a whole-project progress row |
| 2026-10-11 | Afternoon: helper reinstalled on the Mac (test install). First live check of the Allow dialog: a global consent challenge was issued in 6 seconds, not yet known whether a person clicked Allow or the dialog did not appear. NOT PROVEN either way (10.32, docs/26 section 12) |
| 2026-10-11 | Cursor Auto reviews, read-only, pinned CLI: C1 guard and consent 6 of 6 real, C2 install 4 of 6 real, C3 agent CLI 5 of 6 real; every real finding fixed with fake-only tests (docs/research/18 to 20, C1 to C3) |
| 2026-10-11 | Human confirmation for global capture: the helper shows a native macOS dialog as the console user (only Allow counts, 3 per 10 min), the app shows an Electron confirm dialog. Fakes only, neither seen live (S10, S11) |
| 2026-10-11 | Read-only local control API in the running app: loopback, token, GET only, off by default, Settings switch under Advanced. Fakes only, not run on a real app (P7.15) |
| 2026-10-11 | `splitnet report` writes a redacted bug report file; GitHub bug report template added (P6.8, partial) |
| 2026-10-11 | Upgrade and downgrade guard: refuses an older helper unless `--allow-downgrade`, `--rollback` swaps back, state files carry `schemaVersion` with migrations, a newer state file is refused. Fakes only (P6.3 still todo in tasks.json) |
| 2026-10-11 | `probe-vpn` (20 KB cap) behind `splitnet vpn test`; refuses unless one running lane covers the helper's own node. Fakes only, not run through a real VPN (P1.6) |
| 2026-10-11 | On-screen check (dark, empty, helper-error states) found 3 problems: a triple helper banner, a stale Running state, wrapping speed text. All fixed; the banner fix confirmed on screen (P3.44) |
| 2026-10-11 | Live roadmap on the phone: token-protected server option, SSH tunnel script, launcher page template. Built, not proven |
| 2026-10-10 | Helper peer credentials (S9): design note only, not built, because Node has no `LOCAL_PEERCRED`; the socket is 0600 plus a token |
| 2026-10-10 | Install and upgrade: the app checks that the new helper answers with its own version before saying it is done. Fakes only, not proven with a real password prompt (P2.21) |
| 2026-10-10 | Night branch merged (global consent challenge wired in app and CLI, pinned sing-box in the bundle installer). Cloud session, fakes only: upgrade-safe install script with rollback (P2.20, P2.21), `probe-vpn` helper command for `vpn test` (20 KB cap), Silent mode switch in Settings, one error banner and next-step buttons in Activity, Connections and Log, extra tests for S6 and S8, design note for S9 (10.30). Nothing here is proven live |
| 2026-10-09 | **Live: two scoped lanes (Wi-Fi + iPhone tether), VPN over the iPhone**; routes and DNS identical after stop (10.24) |
| 2026-10-09 | Hard-test scripts (`tools/hard-tests`, Wi-Fi only): RH5 lookups ok, leak not proven; RH7 7 % apparent miss, rerun needed (10.25) |
| 2026-10-09 | RH3 first attempts: the failover group picks the fastest link, not the first, so the unplug did not test failover; new task P7.11 (10.26) |
| 2026-10-09 | **RH8 passed**: `kill -9` of the core with two lanes, routes and DNS restored, zero data used (10.27) |
| 2026-10-09 | W7: external VPN detection (P2.23), activity monitor (P2.24), per-app speed, helper `list-external-vpns` and `get-activity` |
| 2026-10-09 | P2 helper: apply-lanes with bind_interface and urltest failover (P2.28), network-change and wake handling (P2.19, live proof pending). IPv6, process-tree grouping and reconnect still todo (P2.13, P2.25, P2.26) |
| 2026-10-09 | App: Activity (P3.39), Connections (P3.5), per-profile Log (P3.41), tray (P3.9), settings; Keychain code written, P1.9 still todo. Built with tests, not yet seen on screen |
| 2026-10-09 | CLI `profile-set` command (tests); CLI start, stop and save still missing (P3.34) |
| 2026-10-09 | Preferred-first failover wired (P7.11, partial); live proof pending |
| 2026-10-09 | Roadmap dashboard skill created at `~/.claude/skills/roadmap-dashboard`; tasks reclassified so `needsUser` is set only where the user must act (commit c354b41) |
| 2026-10-09 | W5 code done: layered screens on the kit (UI-B), helper `apply-lanes` (guard armed first, consent + 10 min cap for global), app Start uses it; core 282, helper 549, app 455, cli 52 tests, all fakes. Not proven live at that point: real TUN, VPN over a chosen connection (proven later, 10.24), global capture |
| 2026-10-05 | Research (3 reports), docs folder, GitHub repo, standalone decision (A6) |
| 2026-10-05 | Fake network lab built (`spikes/lab/`): S5 recovery, S6 short connections (light), S7 UDP passed; S4 DNS partial (needs retest with the other VPN off, RH11) |
| 2026-10-08 | **FIRST LIVE RUN**: real helper installed on the Mac, Telegram routed through the user's profile (scoped), per-app stats flowing; BSD chown bug found and fixed (docs/10, 10.23) |
| 2026-10-08 | CLI (doctor, profile add, telegram on/off, status), real root-owned helper installer with safety checks, Telegram ranges + detection, daemon settings (helper 274 + cli 52 tests, all fakes). Ready for the first live run: the Telegram test (needs the user) |
| 2026-10-08 | UI migrated to the 13-command protocol and the core Rule shape (app 61 tests, helper 203, core 185; tsc clean in all three) |
| 2026-10-08 | Helper backend (fakes), 13-command protocol, typecheck clean, per-connection limiter, Electron scaffold (app/, tsc+build+37 tests) |
| 2026-10-08 | P2 code pieces done by 4 Haiku workers (core 178 + helper 137 tests, unit only; no live network). Worker doubts listed in docs/10, 10.21 |
| 2026-10-08 | P1 core pieces done by Haiku workers: parsers (52 tests), config generator (37, incl. sing-box check), launcher (11, restart in ~1.2 s). Rule R14 (safe workers) after a stray rm -rf probe |
| 2026-10-08 | **P0 closed.** S4, S7, S10, RH3, RH8 done in Docker; user-hands items in the validation backlog (phase V); M1 reached |
| 2026-10-08 | Rule R13: macOS only for now. Linux and Windows deferred (P4, P5, S9, OS-specific items in other phases); code keeps TODO(linux)/TODO(windows) comments for the later port |
| 2026-10-08 | Old mod pane removed (installed copy and `tools/roadmap-pane/`); live web dashboard `tools/roadmap-web/` is the roadmap view (2 s polling) |
| 2026-10-08 | Roadmap pane v0.5: shows work vs check models and tokens per task and in the summary |
| 2026-10-08 | Model policy tightened (R12): Haiku does the work, Sonnet only short checks (50 tasks, ~686k), Opus only 2 tasks (D1-D5 decisions, security review, ~30k); tasks.json updated |
| 2026-10-08 | Roadmap pane v0.4: progress bars rebuilt from Box fills (glyph bars rendered badly), done tasks show no estimate chips |
| 2026-10-08 | Roadmap pane v0.3: card UI, progress bar and percent on every phase |
| 2026-10-08 | Roadmap pane v0.2: expandable phases, sub-tasks, token estimates, thinking and model per task (docs/tasks.json, 102 tasks) |
| 2026-10-07 | Live roadmap pane mod created (`tools/roadmap-pane/`, `/roadmap`), auto-refresh every 3 s from the docs |
| 2026-10-06 | VPN-safety rule added (R11): no flaps or global capture on the live machine; RH3/RH8 re-run on hold |
| 2026-10-06 | Repo folders created; D1–D5 proposed defaults (sing-box sidecar, Go helper, MIT, Electron+React+TS, SQLite). RH3/RH8 first attempt invalid, to re-run |
| 2026-10-06 | RH2: two real networks add up (+38% together); spread mode itself still to test |
| 2026-10-06 | RH1 passed: per-app interface choice on two real networks (en0, en7), exact process matching, packet-capture proof |
| 2026-10-06 | S8 passed (Linux netns + WireGuard sandbox fail-closed, cgroup block). User now has two real networks (en0, en7) |
| 2026-10-05 | S3 passed: unsigned root helper, no repeat prompts, watchdog works; blocker B4 lifted |
| 2026-10-05 | S11 OpenVPN, S12 licenses, S13 process lookup researched; D1 leans sing-box sidecar (GPL, ship source) |
| 2026-10-05 | Scoped lab mode (no global capture) after the hung-test incident; S2 stats exact, S6 1000/1000, S7 UDP 2000/2000 |
| 2026-10-05 | Spike S1 passed: per-app interface choice on macOS, unsigned (sing-box TUN, gvisor stack) |

## Next up

Full list of requirements and the waves to reach them: [14-requirements.md](14-requirements.md).

1. **Now (2026-10-12):** isolation tests C (group of apps) and D (global), L18 part 2 (Happ as the profile's VPN, needs the user's ready), L14 (Antigravity address ranges), L12 and L13 (runner races, guard double-checks), L15 and L11 (in progress)
2. **Finish live proof (W6):** sleep/wake with the helper fix (P2.19), the unplug test (RH3), guard live proof (P2.16); global capture is proven on Wi-Fi (10.48), the LAN adapter and a long hold are not
3. **Packaging (W8):** unsigned `.app` with bundled helper and core (P3.22), production helper install and upgrade (P2.20, P2.21)
4. **Security sign-off (P6.10)**, then the live hard-test subset H1-H12 with the user (P6.11)
5. **v1.0 stable macOS (M4)**, then the validation backlog (phase V); the Transparent Proxy extension is a v1.x idea (needs a paid Apple Developer account)

## Milestones

| Milestone | Meaning |
|---|---|
| M0 | Research done ✅ (2026-10-05) |
| M1 | Spikes proven, architecture frozen ✅ (2026-10-08, D1-D5 accepted) |
| M2 | Engine works: import a profile, run it, verify the exit IP |
| M3 | Profiles MVP: saved profiles, several VPNs, Start/Stop, Lightning-kit UI (W5) |
| M3b | Any app works (global capture proven live) + external VPNs (W6, W7) |
| M4 | **v1.0 stable macOS**, unsigned, installable (W8) |
| M5 | Linux build |
| M6 | Windows build |
| M7 | 1.0: three OSes, hardened, documented |

## Pending reminders

- **Worker policy v2 (2026-10-11):** Cursor Auto only for high-risk code reviews, agy only for script-checkable tables/docs, verify only high/medium rows, at most 3 Haiku jobs at once, fresh session at about 70% context (rule R15 amendment).

- **Real second connection tests (RH1–RH11, doc 7 section 7.9):** RH1 and RH8 passed, RH2 capacity proven; RH3, RH5 and RH7 partial; RH4, RH6, RH9–RH11 pending. Run the rest when a phone tether or a second network is available. Claude must remind the user.
- **Fake network lab:** build it first (P0.12a) so most tests do not wait for hardware.
- **S1 was proven with Wi-Fi plus an existing VPN, not two physical networks.**

## Risk register

| Risk | Impact | Plan |
|---|---|---|
| Process matching misses short connections on macOS | Wrong app gets a rule | Document, add retry/caching, cover with hard test H5, signed mode later |
| Helper crash leaves user offline | Severe | Recovery watchdog, restore tool, hard tests H1–H3 |
| Another VPN fights for the default route | Broken internet | Detect conflicts, warn, hard test H7 |
| sing-box GPL | Distribution limits | Sidecar only, ship GPL text and source offer for the exact version, keep it replaceable, do not use its name (doc 10, 10.11) |
| macOS update changes the sysctl struct layout used for process lookup | App matching breaks | Version check, fallback, test every macOS beta |
| macOS update changes behavior | Breakage | Pin tested macOS versions, CI on new betas where possible |
| Antivirus flags WinDivert | Windows install friction | Document, signed vendor binaries only |
| DNS leaks | Privacy | Hard tests H4, DNS follows traffic or is blocked |
| Scope creep | Never ships | Phase gates, R0, non-goals in doc 1 |
| A scoped lane stops by itself after about 126 s | Traffic drops mid-use | Fixed in P2.33 (guard heartbeat reads the live deadline); 250 s hold proven live (10.28) |
| Failover picks the fastest link, not the first chosen one | Preferred link not used; failover untested | P7.11 preferred-first order, then rerun RH3 (doc 10, 10.26) |
