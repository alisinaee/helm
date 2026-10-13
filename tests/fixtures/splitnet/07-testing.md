# 7. Testing

Network-touching code can lock the user out of the internet, so testing is a first-class part of
the plan. A phase is not done until its tests and its hard tests pass (R8).

## 7.1 Test levels

| Level | What | Tools |
|---|---|---|
| Unit | Parsers, rule matching, config generation, stats math, state machines | Vitest or the runner used by the repo, fast-check for property tests |
| Component | Helper with a fake backend, policy engine with a fake core, IPC with fake peers | Same runner, in-process fakes |
| Integration | Real core + real TUN on a test machine, local test servers behind named interfaces | Shell and Node scripts, iperf3, curl, local HTTP/DNS servers |
| End-to-end UI | UI against a real helper | Playwright |
| Hard tests | Failure, leak, load, long-run, hostile cases (below) | Test lab |
| Manual | Real apps (browsers, Slack, Steam, Spotify, Zoom, torrent client, curl) | Checklist per release |

## 7.2 Test lab

| Item | Purpose |
|---|---|
| Mac with Wi-Fi + second interface (USB tether, or a USB Ethernet dongle on a second router) | Real multi-network tests |
| Virtual second network on macOS (second interface or `pfctl`/`dnctl` for shaping, a local network simulator) | Repeatable CI-style tests when no second real network |
| Linux VMs: Ubuntu LTS, Fedora, Arch (UTM, multipass, or cloud) | Linux backend |
| Windows 10 and Windows 11 VMs, one with Defender and a third-party AV | Windows backend |
| Local servers: HTTP, TCP echo, UDP echo, DNS (with query logging), an IP-echo service per interface | Verify which path traffic took |
| A throwaway VPN endpoint per protocol (VLESS, VMess, WireGuard, Hysteria2, TUIC, Trojan, SS) | Protocol tests with generated test keys, never real credentials |
| `tcpdump` / Wireshark | Prove which interface carried what |
| `iperf3`, `wrk` or `hey` | Throughput and connection-count tests |
| Network impairment: `tc netem` (Linux), `dnctl` (macOS), `clumsy` (Windows) | Loss, delay, jitter, flapping |

## 7.3 Core functional tests

- Each rule action: use interface, use profile, direct, block, DNS profile.
- Rule priority and conflicts (property tests: order changes result only as defined).
- Hot reload: change a rule while connections are active.
- Profile import: valid, invalid, hostile, huge, unicode inputs for every share-link type.
- Stats: totals equal the bytes seen by `tcpdump` within a tolerance, per app and per network.
- Interface discovery: add/remove/rename interfaces, tether plug/unplug.
- App discovery: installed vs running apps, renamed apps, apps with helpers (browsers spawn many
  processes: one app, many processes).

## 7.4 Hard tests

Each must pass on every supported OS before its phase exit gate. `H` ids are used in the dev plan.

| ID | Name | Scenario | Pass condition |
|---|---|---|---|
| H1 | Kill helper | `kill -9` the helper while rules are active | Network restored automatically, no manual step |
| H2 | Kill core | `kill -9` the core during transfers | Helper restores or restarts the core, kill-switch rules respected |
| H3 | Power and reboot | Hard power off, or reboot with rules active | Normal internet after boot, no stale routes or DNS |
| H4 | DNS leak | Browse, resolve and use DoH/system resolver for a ruled app, record DNS on every interface | No query for the ruled app on the wrong interface, or the query is blocked |
| H5 | Short connection race | 10,000 `curl` calls of 1 ms to 50 ms to many hosts, from two different apps with different rules | Miss rate measured and within the documented limit, no wrong-app rule applied silently |
| H6 | IPv6 leak | Dual-stack target for a VPN-only app | IPv6 goes through the profile or is blocked, never direct |
| H7 | VPN conflict | Third-party VPN already active, then enable ours, then disable either | No route loop, clear warning, clean state after both stop |
| H8 | Interface flapping | Drop and restore Wi-Fi/tether every few seconds under load | No crash, rules re-applied, downloads recover |
| H9 | Sleep/wake | Sleep with active connections, wake on a different network | Rules re-applied within seconds, no leak window |
| H10 | Kill-switch window | Start, stop and crash the profile with a "no leak" rule | Zero packets leave on the direct path (verify with `tcpdump`) |
| H11 | UDP and QUIC | HTTP/3 browser, UDP echo, game-like UDP | Works through the profile, or documented fallback, counted correctly |
| H12 | Throughput | `iperf3` through TUN vs direct, many parallel streams | Overhead within target (to be set after spike S1), no memory growth |
| H13 | Many connections | 10,000+ concurrent connections | Stable CPU and memory, no file-descriptor exhaustion |
| H14 | Long run | 72 hours with traffic and rule changes | No leaks (memory, fds, routes), stats still correct |
| H15 | Hostile config | Malformed or oversized rules, profiles, share links, IPC messages | Rejected safely, no crash, no root command injection |
| H16 | IPC security | Unprivileged process and other users try to talk to the helper | Rejected, only the intended caller works |
| H17 | Upgrade | Upgrade the app, helper, core with rules active, and downgrade | State kept or migrated, network never left broken |
| H18 | Uninstall | Uninstall with rules active | All routes, DNS, firewall rules, daemons and files removed |
| H19 | Low disk and permissions | Full disk, read-only state file, missing permissions | Clear error, no half-applied network state |
| H20 | Time and clock | Big clock jumps, time zones, DST | Quotas and schedules behave correctly |
| H21 | Antivirus / OS defenses | Run with Defender (Windows), Gatekeeper (macOS), AppArmor/SELinux (Linux) | Install works with the documented steps, no silent failures |
| H22 | Big apps | Real browsers, torrent client, video call, game launcher, system updater | Apps work normally under each rule type |
| H23 | Fuzzing | Fuzz the share-link parsers, rule engine and IPC decoder | No crashes or hangs |
| H24 | Resource limits | Run on low-end hardware and battery | CPU and battery use within the budget set after P2 |
| H25 | Controller hang | Our own controller or test script hangs with the TUN up (this happened on 2026-10-05) | Watchdog stops the core within its limit, routes and DNS restored, UI shows that capture is on and offers one-click Restore |

## 7.5 Platform-specific hard tests

| OS | Tests |
|---|---|
| macOS | Process matching for helper-heavy apps (Chrome, Electron apps, Safari), apps under a different user, Apple silicon vs Intel, new macOS beta, Wi-Fi/Ethernet service order changes, Rosetta apps |
| Linux | Kernel without eBPF or old cgroup layout, systemd-resolved stub DNS inside netns, AppArmor limits on user namespaces, Wayland and X11 apps in a netns, rp_filter asymmetric routes |
| Windows | UWP apps and package SIDs, apps with several processes, antivirus flagging WinDivert, Wintun adapter conflicts, WFP rule persistence across reboot, Wi-Fi + Ethernet simultaneous connection policy |

## 7.6 CI

- Per commit: unit, component, lint, type check on all three OS runners.
- Nightly: integration tests on VMs with virtual second interface.
- Before each phase exit gate and release: the full hard-test list on real hardware.
- Keep a results table per release: test id, OS, version, result, notes.

## 7.7 Manual release checklist

1. Fresh install on a clean VM per OS, onboarding without docs.
2. Create three rules (interface, profile, block) and verify with an IP-echo service.
3. Kill everything and check the network recovers.
4. Uninstall and check that nothing is left.

## 7.8 Fake network lab (no second connection needed)

We can simulate most multi-network tests on one machine. This follows the same idea Lightning's
test setup uses (a local fake server with per-network speed control and scenarios). We copy the
idea, not the code (rule R9).

| Tool | What it simulates |
|---|---|
| Fake IPs (198.51.100.x) redirected by the core (`override_address`) to local servers, scoped TUN `utun9` with one route (`spikes/lab/`). Used so far | Two fake networks plus UDP, no second interface needed |
| macOS `feth` pair (not used yet; may not route between two local addresses) | A second interface the OS can see |
| Fake server bound to each fake interface's IP | Tells us which path a connection used (it sees the source and the listener) |
| `dnctl` + `pfctl` (macOS), `tc netem` (Linux), `clumsy` (Windows) | Per-network speed limits, delay, loss, blocking, flapping |
| Scenario scripts: collapse, recover, flap, network dies, VPN-like second path | Repeatable failure tests |
| Existing system VPN as a second path | Already proven in spike S1 |

Cannot be simulated, so real hardware is still needed (section 7.9): real carrier or router
behavior (NAT, real latency and loss), USB tether driver quirks, Wi-Fi roaming, real captive
portals, real VPN server behavior.

## 7.9 Real-hardware test reminders (do when a second connection is available)

> **Reminder for Claude:** when the user says they have another connection (phone tether, second
> Wi-Fi, USB LAN with another router), stop and remind them to run this list before moving on.

| ID | Test | Status |
|---|---|---|
| RH1 | Re-run spike S1 with two physical networks (Wi-Fi + tether): per-app interface choice | ✅ passed 2026-10-06 (en0 + en7, packet capture proof) |
| RH2 | Spread mode across two real networks: measure real throughput gain | 🟡 capacity proven 2026-10-06 (+38%, networks add up); sing-box spread mode itself still to test |
| RH3 | Unplug and replug the tether under load (H8 on real hardware) | 🟡 attempted 2026-10-09, not proven (10.26): the group picks the fastest link, so the unplug missed the active path; rerun after P7.11 |
| RH4 | Sleep/wake on a different network (H9) | pending |
| RH5 | DNS leak test on real networks (H4) | 🟡 partial 2026-10-09 (10.25): 5 lookups ok, nameservers unchanged; leak not proven (needs root tcpdump) |
| RH6 | QUIC/HTTP3 browser through each network (H11) | pending |
| RH7 | Short-connection match miss rate with real apps (H5) | 🟡 partial 2026-10-09 (10.25): 7 % apparent miss over the 5 % limit on 100 requests; not a verdict, rerun with 300 and stats polling |
| RH8 | Crash recovery with two networks (H1, H2) | ✅ passed 2026-10-09 (10.27): kill -9 of the core with two lanes, routes and DNS restored; helper vs guard not separated |
| RH9 | Existing system VPN plus two networks (H7) | pending |
| RH10 | Real app behavior: browser, Telegram, torrent client, video call on separate networks | pending |
| RH11 | Re-run S4b (system DNS pointed at our plain-DNS server, per-rule DNS answers) with the third-party VPN turned off, then on | pending |

## 7.10 Test safety and lessons (2026-10-05)

- Default test mode is **scoped** (rule R11): no global routes or DNS changes. Global capture runs only
  after the user says "ready", with a watchdog, and ideally in a VM.
- A bare `wait` in a test script also waits on background daemons it started. Always wait on
  specific PIDs.
- Copies of system binaries need `codesign -s - --force` to run.
- Stats tests must match on process path, not on destination address.
- Each privileged run needs a password prompt unless the S3 helper is installed.
