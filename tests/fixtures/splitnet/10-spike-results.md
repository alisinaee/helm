# 10. Spike results (what happened)

Single place to see every experiment: what we tried, what happened, what it means. Raw notes and
configs are in `spikes/`. **Rule: after every spike or test run, add an entry here in the same
change** (date, setup, result, findings, decisions affected).

Test machine: macOS 27.0.1 arm64, sing-box 1.14.2 (Homebrew), unsigned, run as root through an
admin password prompt, Wi-Fi `en0` plus an already-running third-party VPN on `utun6`.

## 10.1 Scoreboard

| Spike | Topic | Status | Date | Details |
|---|---|---|---|---|
| S1 | Per-app interface choice (TUN + process rules + `bind_interface`) | ✅ passed | 2026-10-05 | 10.2 |
| S2 | Per-app stats from the core API | ✅ passed | 2026-10-05 | 10.9 |
| S3 | Unsigned app installs a root helper (admin prompt) | ✅ passed | 2026-10-05 | 10.14 |
| S4 | Per-rule DNS in TUN mode | ✅ core (Docker); macOS system resolver still in the validation backlog | 2026-10-08 | 10.3, 10.4, 10.20 |
| S5 | Crash recovery (routes) | ✅ passed (routes) | 2026-10-05 | 10.3 |
| S6 | Short-connection match misses | ✅ passed (1000/1000 in the harder test) | 2026-10-05 | 10.3, 10.9 |
| S7 | UDP / QUIC through TUN | ✅ passed (UDP 2000/2000; HTTP/3 through the TUN works, Docker) | 2026-10-08 | 10.3, 10.9, 10.20 |
| S8 | Linux netns / cgroup | ✅ passed (nft socket match missing on the VM kernel) | 2026-10-06 | 10.15 |
| S9 | Windows Wintun / WFP / ETW | ⏸ deferred (rule R13, macOS only) | | |
| S10 | Coexistence with another VPN | ✅ passed in Docker (both start orders); real VPN toggling in the validation backlog | 2026-10-08 | 10.5, 10.20 |
| S11 | OpenVPN in the core | ✅ supported (schema verified, no real server test) | 2026-10-05 | 10.6 |
| S12 | Licenses of chosen stack | ✅ researched | 2026-10-05 | 10.11 |
| S13 | Process lookup details per OS | ✅ researched (source read) | 2026-10-05 | 10.12 |

Real-hardware tests (RH1–RH11): RH1 passed (10.16), RH2 capacity proven (10.17), the rest pending, see [07-testing.md](07-testing.md) section 7.9.

## 10.2 S1: per-app interface choice, PASSED

Folder: `spikes/S1-per-app-interface/` (config, scripts, RESULT.md).

- Setup: two paths, Wi-Fi `en0` (home IP) and the existing VPN `utun6` (VPN exit IP). Two ad-hoc
  re-signed copies of `curl` named `curlA` and `curlB`. Rules: `curlA` → direct bound to `en0`,
  `curlB` → direct bound to `utun6`, everything else → direct.
- Result: curlA showed the home IP, curlB the VPN IP, plain curl the home IP. Routes returned to
  baseline afterward.
- Findings:
  1. `stack: system` carried no TCP here. `stack: gvisor` worked. **Use gvisor.**
  2. Copies of system binaries are killed (`Killed: 9`) until re-signed: `codesign -s - --force`.
  3. macOS resolver traffic (mDNSResponder) went to `1.1.1.1:443` through the TUN and failed → DNS
     needs work (S4).
  4. sing-box sees the app path and user of every flow, including system daemons.
  5. Each root run needed one admin password prompt (can't be automated).
- Not proven: two real physical networks (RH1).
- Decisions affected: confirms A3 (unsigned root helper + TUN is viable). Supports D1 (sing-box).

## 10.3 Lab run 1: S5, S6, S7, fake networks

Folder: `spikes/lab/` (fake server, config, scripts, RESULT.md).

- Setup: fake networks are fake IPs `198.51.100.x` redirected by sing-box (`override_address`) to a
  local fake server (net A port 8101, net B port 8102, UDP echo 8103). No second real network.
- Results:

| Test | Spike | Result |
|---|---|---|
| Two fake networks via TUN | S1 (lab) | ✅ `.1` → net A, `.2` → net B |
| UDP echo via TUN | S7 | ✅ works |
| 300 short connections, same destination, 2 apps, 10 parallel | S6 | ✅ 300 correct, 0 wrong, 0 missing |
| `kill -9` sing-box with TUN active | S5 | ✅ no stale routes, internet back in 2 s |

- Findings: the TUN cleans itself when the process dies. We still need our own watchdog for
  anything we change in DNS or firewall settings. S6 needs a harder test (H5): more parallelism,
  real multi-process apps (browser), very short flows.
- Decisions affected: lowers the "process matching misses" risk for macOS unsigned (still keep H5).

## 10.4 S4: DNS, PARTIAL

Files: `spikes/lab/RESULT.md` (T2), `spikes/lab/RESULT-S4b.md`.

- Plain DNS (port 53) through the TUN: ✅ sing-box answered a rule-based name.
- System lookups (`curl a.split.test`, real names): ❌ failed in both runs.
  - Run 1: the resolver used encrypted DNS to `1.1.1.1:443`. That address is not reachable
    directly over this Wi-Fi (only through the VPN), so lookups died when sent direct.
  - Run 2: system DNS for Wi-Fi set to `9.9.9.9`: `scutil --dns` showed it, `dig @9.9.9.9` was
    answered by sing-box, but `curl` still failed. The other VPN's DNS settings appear to win.
- Cleanup verified: Wi-Fi DNS back to empty, no leftover processes.
- Conclusion: per-app DNS on macOS stays "rule-based, best effort" (doc 3). Needs a retest with the
  other VPN off (RH11), and probably setting DNS on the highest-priority network service or on our
  own utun service.
- Open: how do we fix DNS when another VPN or encrypted-DNS app owns it? (D-open-1 below)

## 10.5 S10: coexistence with another VPN, partial evidence

- S1 and the lab ran while a third-party VPN was active, with a default route on `utun6`. Our TUN
  worked for per-app rules and `bind_interface utun6` reached the VPN.
- Not yet tested: turning either VPN on and off while the other runs (H7), route loops, DNS
  ownership (see 10.4).

## 10.6 S11: OpenVPN

- sing-box has an OpenVPN **client and server** since v1.14.0, as endpoints `openvpn-client` and
  `openvpn-server` (not outbounds). Verified locally: `outbounds: openvpn-client` is rejected,
  `endpoints: openvpn-client` is accepted and asks for `server`. Brew 1.14.2 has `with_openvpn`.
- Supports tls-crypt, tls-auth, tls-crypt-v2, UDP and TCP, static key mode, AES-GCM and
  CHACHA20-POLY1305, pulled routes (`route_no_pull` controls them), interactive auth via the
  dashboard only. Not marked experimental in the docs.
- mihomo has an `openvpn` outbound too but looks younger (open requests for pushed routes).
- Not tested against a real OpenVPN server. Full detail: `research/04-openvpn-licenses-process-lookup.md`.
- Decision effect: OpenVPN can be a profile type through the same core (D1 sing-box).

## 10.7 Open questions raised by the results

| ID | Question | Where it came from |
|---|---|---|
| D-open-1 | How do we reliably control DNS on macOS when another VPN or encrypted DNS owns it? | 10.4 |
| D-open-2 | Is the gvisor stack fast enough (H12 throughput)? | 10.2 |
| D-open-3 | How do we avoid the password prompt on every privileged run? (helper install, S3) | 10.2 |
| D-open-4 | Does S6 hold for real browsers and heavy parallelism? | 10.3 |

## 10.8 Incident: test script hung with the TUN up (2026-10-05)

- What happened: the combined S2/S6/S7 run (`root-run2.sh`) used a bare `wait`, which also waited
  for the sing-box and fake-server background jobs, so it never finished. The TUN stayed up and
  captured the machine's traffic for several minutes. The user noticed network problems. I killed
  it with a second admin prompt. Afterwards routes, DNS and internet were normal. No S2/S6/S7
  results were produced by that run.
- Root cause: my script bug, not sing-box.
- Fixes: wait only on specific PIDs; a 150 s watchdog kills sing-box no matter what.
- Lessons for the product (add to hard tests): H1/H2 must also cover "our own controller hangs",
  the helper needs its own watchdog and a visible "network is being captured" indicator, and a
  one-click Restore must work even when the controller is stuck. Test scripts that raise a TUN
  must always have a hard time limit, and the user should be told before every run.

## 10.9 Scoped lab run: S2, S6 (harder), S7 (2026-10-05)

Safety change after the incident (10.8): the lab now runs in **scoped mode**. `auto_route` is off,
the TUN is named `utun9`, and one route `198.51.100.0/24 → utun9` is added. Only the lab's own test
traffic enters the TUN. Default routes were identical before and after (checked), and a 150 s
watchdog removes the route and stops sing-box. Files: `spikes/lab/config3.json`, `root-run3.sh`,
`user-stats.sh`, `poll2.py`.

| Test | Result |
|---|---|
| S6 harder: 500 + 500 short connections, 40 parallel each, A and B interleaved, same destination | ✅ all 1000 went to the right network. (The log showed "502 / 1 wrong" for curlB: that was the 2 bulk `/big` downloads being counted in the same list. Not a miss.) |
| S7 UDP: 2000 datagrams of 1200 bytes | ✅ 2000 of 2000 echoed |
| S7 UDP/443 `reject` rule | UDP gets no reply (silent drop, client times out). TCP to another fake host works. Browser fallback from QUIC to TCP still has to be tested with a real browser |
| S2 per-app stats (clash API, unprivileged run through a SOCKS inbound) | ✅ curlA 25,165,953 bytes down for a 24 MiB file, curlB 12,583,041 for 12 MiB: exact (+129 header bytes each). Upload 84 bytes each |

S2 details and gotchas:
- `/connections` gives per connection: `upload`, `download`, `start`, `rule`, `chains`, and
  `metadata.processPath` as `"/usr/bin/curl (ali)"` (path plus user in brackets).
- `metadata.destinationIP` shows the address **after** a destination override, not the original.
  Our stats collector must match on process path, not on destination.
- Closed connections disappear from `/connections`. The collector must poll often (about 200 ms
  here) and keep the highest value per connection id, or use the traffic stream.
- The first attempt (`root-run2/3` S2 part) returned `{}` because my filter used the original
  destination. That was a script bug, not an API problem.

Open: the first privileged S2 run attributed nothing, so process attribution for stats through the
TUN (not SOCKS) was shown by logs only (S1) and still needs the fixed filter in one more run.

## 10.11 S12: licenses (research)

Full table with links in `research/04-openvpn-licenses-process-lookup.md`. Highlights:

- sing-box, sing-tun, sing: GPL-3.0-or-later (sing-box has an extra "no derivative work may use
  the name" clause). mihomo: GPL-3.0 on the `Meta` branch (GitHub shows MIT from a stub branch).
- MIT or Apache: gVisor (Apache-2.0), wireguard-go, tun2socks, hev-socks5-tunnel, boringtun
  (BSD-3). MPL-2.0: Xray-core, gotatun. WinDivert: LGPL-3.0 or GPL-2.0. Wintun: prebuilt DLL may be
  redistributed only with software that uses it through its public API (our case).
- Correction: tun2socks (xjasonlyu) is **MIT**, not GPL as the first research guessed.
- What we must do to ship sing-box as a separate unmodified executable: include the GPL text and
  notices, offer the source of that exact version (link or written offer, host the tag next to
  the download), do not link it as a library or merge it into our binary, keep it replaceable,
  do not use the name "sing-box" for our product. This is the research's reading, not legal advice.

## 10.12 S13: how the cores find the app that owns a connection (research)

- macOS: both read the `net.inet.{tcp,udp}.pcblist_n` sysctl with hard-coded struct offsets
  (could break with a macOS update) and take the path via `proc_pidpath`. sing-box caches 200 ms,
  mihomo does not cache. Linux: netlink sock_diag plus a `/proc` scan (needs privilege to see other
  users' processes). Windows: iphlpapi tables plus `QueryFullProcessImageName`.
- Lookup runs after the connection arrives, so very short connections can be "process not found"
  and a reused port inside the cache window can return a stale owner. Our tests (S6) did not hit
  this, but keep H5.
- Risk to watch: a macOS update changing the struct layout breaks matching. We need a version
  check and a fallback (see risk register).

## 10.14 S3: unsigned root helper, PASSED

Folder: `spikes/S3-helper/` (helper.mjs, ctl.mjs, install.sh, uninstall.sh, RESULT.md).

- One admin prompt installs a LaunchDaemon; after that the user starts and stops the core with typed
  commands over a Unix socket, with no more prompts. Bad input is rejected, stop cleans up, a
  120 s watchdog stops the core on its own.
- Blocker B4 is **lifted**: the helper does not need Apple signing.
- The prototype's caller check is only socket file permissions. The product needs peer
  credentials (LOCAL_PEERCRED), strict validation, root-owned config directory (see RESULT.md).
- Still to test: kill -9 of the helper, reboot and sleep, upgrade, second user.

## 10.15 S8: Linux netns, WireGuard, cgroup (Docker VM), PASSED

Folder: `spikes/S8-linux/` (test.sh, run-final.log, RESULT.md). Ran in a privileged alpine container
inside Docker Desktop's Linux VM (kernel 6.12.76), so the Mac network was untouched.

- netns + veth works; per-namespace `resolv.conf` works; **WireGuard confined to a namespace works and is
  fail-closed** (tunnel down means no network for the app).
- cgroup v2 block + counters work with `iptables -m cgroup --path`. The nftables `socket cgroupv2` match
  failed because this VM kernel lacks `CONFIG_NFT_SOCKET`; real distros usually have it (5.13+), so the
  helper must probe features and choose a backend.
- Decision effect: Linux backend = netns + WireGuard/proxy for isolation (best), cgroup + iptables/nft or eBPF
  for block and counting, with a feature probe at start. Confirms the Linux column of doc 3.
- Not tested: eBPF programs, rootless fallback, real distros, IPv6, systemd scopes.

## 10.16 RH1: per-app interface choice on two real networks, PASSED

Folder: `spikes/lab/` (`RESULT-RH1.md`, `config-rh1b.json`, `root-run-rh1b.sh`, `root-run-rh1c.sh`).

- Two real networks (Wi-Fi `en0`, USB LAN `en7`) plus the VPN, scoped mode, one host route into the TUN.
- Process matching exact: 10/10 for the plain app (fallback to VPN), 10/10 for the app pinned to `en7`.
- The app pinned to `en0`: packet capture shows 162 packets on `en0`, none on `en7` or the VPN. By exit IP it
  looked wrong in 6 of 10 rounds, but plain `curl --interface en0` shows the same variation: the `en0` router
  load-balances over two upstream links.
- Lessons: prove egress interface with packet capture, not exit IP; background children keep `osascript`
  attached; cleanup belongs to the helper.
- Decision effect: confirms A3 and D1 (sing-box) on real hardware. Product note: users on multi-WAN networks may
  see different public IPs for one interface.

## 10.17 RH2: throughput of two real networks, capacity proven

Folder: `spikes/RH2-throughput/RESULT.md`. No root, nothing changed on the system.

- `en0` alone 0.17 MB/s, `en7` alone 0.34 MB/s, both at once 0.15 + 0.32 = 0.47 MB/s: about +38% over the best single
  network and about 92% of the sum measured alone, so the two networks do not share a bottleneck.
- Slow lines, single sample, 40 s cap: indicative only.
- Still open: sing-box spread mode (per-connection distribution across interfaces through the TUN) and a real app test.

## 10.18 RH3 + RH8 first attempt: INVALID (script bug) (2026-10-06)

- `root-run-rh3.sh` started sing-box with `nohup`, which fails without a terminal ("can't detach from console"),
  so sing-box never ran. Every request fell back to the VPN, so no RH3/RH8 conclusion can be drawn.
- It did show the network side of the flap: turning the `en7` service off and on restored `en7` with its IP after
  19 s, the default routes were identical afterwards, and nothing of ours was left running.
- Fixed (no `nohup`); needs a re-run (one password prompt, `en7` drops for ~20 s).

## 10.19 VPN app error report (2026-10-06)

- The user showed a Happ (Xray core 6.0.0) error: "vless without TLS or other encryption is prohibited unless the
  server address is a private IP or domain", on a `VLESS | TCP` profile with no TLS/Reality. This is Xray refusing
  that specific server profile (public IP, no TLS), not something our tests do: we never touched Happ's config
  or profiles. Our footprint was checked right after: no sing-box, tcpdump or TUN running, no lab routes, no DNS
  changes, only the idle test helper daemon. Exit IP through the VPN was fine.
- Cannot be 100% excluded that earlier global-capture runs (S1, lab, the hung run) briefly disturbed the VPN while
  they ran; they are over and cleaned up.
- Evidence checked later the same day (read-only): Happ is a Mac App Store app (`_MASReceipt` present). Its executable, PlugIns and receipt were all rewritten at 08:23 local on 2026-10-06, i.e. a full App Store update to 6.0.0 installed that morning, and Happ was not running our tools. A newer Xray core rejecting unencrypted VLESS on a public IP fits that update. The timing is close to one of our test runs (08:21-08:22), which is a coincidence we could not rule out but a test script cannot replace an App Store bundle. The user still believes the tests broke Happ; unresolved, the user should check whether Happ updated.
- Action: rule R11 extended (VPN is the user's lifeline); the RH3 re-run (which flaps `en7`) is on hold because it
  could drop a VPN riding on a physical interface.

## 10.20 P0 closing runs: S4, S10, S7, RH3, RH8 in Docker (2026-10-08)

Run by Haiku workers inside Docker's Linux VM only (never touching the Mac network, rule R11). They test the
OS-neutral core (sing-box) behavior; the macOS-specific routing around it stays in the validation backlog.
Folders: `spikes/docker-s4-s10/` (jobA, jobB) and `spikes/docker-s7-rh3/`, each with a RESULT.md.

| Item | Result |
|---|---|
| S4 per-app DNS, TUN mode | ✅ 6/6. **`process_name` in DNS rules works in TUN mode**: two copies of `dig` got different answers for the same name (digA .11, digB .22, plain .1). Plain-DNS hijack, system resolver path, fake-IP and no-leak check pass. Only UDP DNS tested |
| S10 coexistence with an existing VPN | ✅ 6/7. Works with the VPN first and with sing-box first; SIGTERM restores routes and rules exactly. ❌ SIGKILL left `ip rule` entries 9000-9010 behind (Linux-specific; macOS showed no stale routes in S5). One baseline probe right after the VPN came up failed once, unexplained |
| S7 real QUIC | ✅ HTTP/3 request served through the TUN (aioquic client, Caddy server); same over TCP/H2 works; with `udp/443 reject` QUIC times out silently (no error) while TCP still works |
| RH3 interface flap (Docker) | ✅ sing-box survived an 8 s link-down; the 40 MB download stalled for the outage, then **resumed and completed** (41,943,040 bytes); the other app kept working; new requests worked 0.03 s after link-up |
| RH8 crash (Docker) | ✅ after `kill -9` and after SIGTERM the TUN and its route were removed and plain traffic worked at once; the TUN path returned 0.28 s after restart. Apps with a download in flight **hung until their own timeout after kill -9** (aborted at 5 s after SIGTERM) |

Findings that change the build:
1. **sing-box syntax moved in 1.13**: the direct outbound `override_address/override_port` were removed; use a `route-options` rule, and for UDP add `"udp_connect": true` (without it the QUIC packets were not redirected). Pin the config generator to the core version (1.14.2 on the Mac) and test the generated config with `sing-box check`.
2. The product needs a **fast restart / watchdog** for the core: after a hard kill, in-flight connections hang until the app's own timeout.
3. Per-app DNS is feasible as designed (process rules in DNS rules). The remaining macOS risk is who owns the system resolver (other VPN, encrypted DNS): validation backlog.
4. Caveats: Docker had sing-box 1.13.21, not 1.14.2; Linux specifics (`ip rule` cleanup) are TODO(linux) notes for later.

**P0 is closed (2026-10-08).** D1-D5 accepted by default. Items that need the user's hands moved to the validation backlog (phase V in tasks.json): RH2 spread (P7 feature), RH4 sleep/wake, RH5 DNS leak on real networks, RH6 browser QUIC, RH7 real apps, RH9 VPN + two networks, RH10 real apps, RH11 DNS with the VPN off, real RH3/RH8 on the Mac.

## 10.21 P2 code pieces by Haiku workers (2026-10-08)

Unit-tested code only (no live network, no install, no TUN). Tests: core 178 pass (1 skip), helper 137 pass.
- `helper/src/platform/macos/`: interface discovery, snapshot, diff, restore plan as data (never touches default
  routes of interfaces that existed before: R11), command allowlist (read-only commands only).
- `helper/src/{protocol,auth,server,daemon}.ts`, `install/`: strict typed protocol, token auth, rate limit,
  Unix-socket server, installer/uninstaller text (tested for symmetry and safe `rm`), daemon skeleton.
- `helper/src/{apps,stats}.ts`: app discovery with helper-to-app mapping; stats aggregator with `node:sqlite`
  store (Node prints an ExperimentalWarning) and a JSON fallback.
- `core/src/policy.ts`, `buildTunConfig` in `singbox-config.ts`: rules to a sing-box 1.14.2 TUN config
  (scoped mode, `allowGlobal` required for global capture), per-app DNS, block, bind to interface/profile.
Worker doubts to resolve next: (1) `launcher.ts` still refuses TUN configs, needs a privileged variant (the helper
owns the TUN); (2) per-app DNS queries leave via the default route, not the app's interface (no `detour` yet);
(3) `route-options udp_connect` unverified in a live TUN run on macOS; (4) no typecheck (no `tsc`), types unverified;
(5) the rate limiter is global, so a block also refuses the legitimate client; (6) `Rule` shape is the workers'
reading of docs/04; (7) DNS tls/https upstreams needed `domain_resolver`.

## 10.22 Helper backend, protocol gaps, typecheck, UI scaffold (2026-10-08)

Code only, fakes only. Tests: helper 203, core 185 (1 skip), app 37; `tsc` clean for core and helper (the app needs a
follow-up migration to the new rule shape).
- **Backend** (`helper/src/backend.ts`): start = snapshot, core start, validated route add; stop = core stop, route
  delete, post snapshot; restore idempotent; crash triggers automatic restore; one watchdog (120 s lease, extended by
  `status`); hot reload on `set-rules`; stats poller feeds the aggregator. **Mutating command allowlist**: `route -n add
  -net <cidr> -interface utunN` (canonical IPv4, /8 or longer, RFC1918 or caller-listed scoped routes),
  `route -n delete -net <cidr>` (scoped routes only), `ifconfig utunN down` (own tun). Refused: default, 0/0, 0/1,
  128/1, any networksetup (DNS is reported, never changed).
- **Protocol** (13 commands): ping, version, status, snapshot, restore, get-stats, core-start {profile}, core-stop,
  list-apps, list-interfaces, get-rules, set-rules {rules}, set-profiles {profiles}. `set-rules` takes the core `Rule`
  shape and refuses the old shape. The limiter is per connection; no second lease in the server.
- **Launcher** gained an opt-in TUN mode for the helper (scoped; global only with an explicit flag).
- **UI scaffold** (`app/`): Electron + React + TS, 5 screens, mock helper, 95 MB node_modules (Electron binary not
  downloaded). Never launched, so the UI has not been seen on screen.
Open: app migration to the new Rule shape; peer credentials (P6.4); profile secrets in a 0600 file, not the keychain
(R6 prefers keychain); a client can reset its own auth budget by reconnecting; bundleApp rules unit-tested only;
live runs of everything above on the Mac still pending (scoped run, needs the user's ready).

## 10.23 FIRST LIVE RUN of the product code: Telegram through the user's VPN profile (2026-10-08)

Setup: real helper installed by the real installer (`--only-for-test --allow-user-owned-binaries`: the user accepted the
Homebrew-node risk for this test), profile imported from `~/vpn.txt` (VLESS, unencrypted `security=none` profile of the
user's own server; output masked), `telegram on` in scoped mode (10 Telegram IPv4 ranges routed into utun9), a status
ping every 2 s keeping the 120 s watchdog lease alive.

| Check | Result |
|---|---|
| Install attempt 1 | ❌ failed at the first `chown`: **macOS (BSD) `chown`/`chmod` treat `--` after the owner/mode as a filename**; fixed by putting `--` before the owner/mode. Nothing new was installed by the failed run (it died at the first command) |
| Install attempt 2 | ✅ exit 0; `doctor` all 6 checks ok (node, sing-box 1.14.2, socket, token, ping, protocol 1); daemon runs from the root-owned copy; sing-box root-owned 0555 copy |
| profile add / telegram on | ✅ profile stored 0600 (masked output), helper accepted it; 10 scoped routes added; detection found 0 extra /24 |
| Default route | ✅ unchanged (no /1 routes, only the 10 scoped routes to utun9) |
| Telegram | ✅ connected with ~10 active connections, up ~15 KB / down ~610 KB growing; helper reports core running on the profile |
| Contrast | a plain `curl` to a Telegram server (not the Telegram app, so it goes direct) timed out, while the Telegram app is connected: the app's traffic is using the profile |
| User's VPN apps | all showed **disconnected** at check time (exit IP = home IP); we added only the 10 scoped routes and touched no VPN; who disconnected them is unknown |

Findings:
1. Generated privileged shell scripts must be exercised with the real macOS tools in a sandbox before the first real run
   (fakes and text checks missed the BSD `--` rule). Added to the test backlog.
2. The CLI prints "outbound chain per connection: not exposed by the helper yet": add per-connection chain info to
   get-stats so the proof does not rely on the contrast with `curl`.
3. Per-app routing with scoped ranges works end to end on the Mac: app rule (process_name) -> profile outbound, stats per app.
Still open: A/B proof by `off` then `on`, per-connection outbound chain, other rule types live, uninstall check.

## 10.13 Log (newest last)

| Date | Entry |
|---|---|
| 2026-10-05 | sing-box 1.14.2 installed via Homebrew |
| 2026-10-05 | S1 passed (10.2) |
| 2026-10-05 | Lab run 1: S5, S6, S7 passed; S4 failed on first try (10.3) |
| 2026-10-05 | S4b: plain DNS hijack works, system DNS still blocked by the other VPN (10.4) |
| 2026-10-05 | Combined S2/S6/S7 run hung with TUN up (script bug), killed, system normal; script fixed with PID waits and watchdog (10.8) |
| 2026-10-05 | Scoped lab mode introduced (no global capture). S6 harder 1000/1000, S7 UDP 2000/2000, S2 stats exact (10.9) |
| 2026-10-05 | S11 OpenVPN supported (endpoint), S12 licenses and S13 process lookup researched (10.6, 10.11, 10.12) |
| 2026-10-05 | S3 passed: unsigned root helper via LaunchDaemon, no repeat prompts, watchdog works (10.14). Helper left installed for further tests |
| 2026-10-06 | S8 passed: netns, WireGuard sandbox (fail-closed), cgroup block; nft socket match absent on the Docker VM kernel (10.15). Two real networks now present (en0, en7) |
| 2026-10-06 | RH1 passed on two real networks (en0 + en7): exact process matching, packet capture proves egress interface; en0 router load-balances exit IP (10.16) |
| 2026-10-06 | RH2: two real networks add up (0.34 alone, 0.47 MB/s together, +38%); spread mode itself still to test (10.17) |
| 2026-10-06 | RH3/RH8 first attempt invalid (nohup bug); en7 service flap recovered in 19 s; repo layout created (app/, helper/, core/, tests/); D1–D5 proposed defaults recorded (10.18, doc 9) |
| 2026-10-06 | User reported a Happ/Xray profile error; our footprint verified clean; rule R11 extended: never risk the user's VPN; RH3 re-run on hold (10.19) |
| 2026-10-08 | P0 closed: S4, S7, S10, RH3, RH8 ran in Docker (10.20); validation backlog created (phase V); D1-D5 accepted by default |
| 2026-10-08 | P2 code pieces done by 4 Haiku workers: macOS inspection, helper protocol/server/installer text, apps+stats, TUN config+policy (10.21) |
| 2026-10-08 | Helper backend (fakes), protocol 13 commands, typecheck clean, per-connection limiter, Electron UI scaffold (10.22) |
| 2026-10-08 | FIRST LIVE RUN: real helper installed, Telegram routed through the user's profile in scoped mode (10.23); BSD chown bug found and fixed |

## 10.24 Live: apply-lanes, two lanes and VPN over a chosen connection (2026-10-09, scoped, iPhone USB tether en8 + Wi-Fi en0)

- Setup: helper reinstalled (test-only install), two lanes at once (curl on en8, python on en0), then one lane with the user's VPN profile over en8 and over en0. Destination pinned to two /32 routes; a few KB of data in total; guard armed; stop in `finally`.
- Result: both lanes start, status lists them, stop restores everything (routes and DNS identical to the baseline, no sing-box left, default stays en0). VPN exit IP was the VPN server both times. Bytes out: over en8 about 1.5 KB on en8 and nothing extra on en0 per request; over en0 zero bytes on en8. This proves the VPN dial follows the chosen connection (RH-style, byte counters).
- Not proven: global capture, failover by unplugging the tether, sleep/wake, per-lane exit IP (exit IPs on this Mac change per call, something else rewrites them).

## 10.25 Live: hard-test scripts, Wi-Fi only (2026-10-09, tools/hard-tests)

- RH7 match-miss (curl, Wi-Fi-only lane, 100 tiny requests, 41 KB): curl made 100 new connections (3 requests failed), the core counted 93 for curl: 7 % apparent miss, over the 5 % placeholder limit. NOT a verdict: the spike S6 result was 1000/1000, the 3 failed requests and the stats poll timing (connections closed before the final get-stats) can explain part of it. Next: poll stats during the run, compare with the TUN's own connection log, repeat with 300.
- RH5 DNS (5 lookups, Wi-Fi lane): nameserver lines unchanged before, during and after; all 5 lookups ok; the lane added only its own /32 routes and a 172.19/30 TUN route. Leak itself NOT PROVEN (needs root tcpdump).
- Both runs: routes and DNS identical after stop, no sing-box left, default stayed en0. Nothing was sent over the iPhone.
- Also done: helper `list-external-vpns` and `get-activity` (synthetic fixtures only, 574 helper tests), app per-app speed, detected external VPNs in the editor, global window default 10 min (app 469 tests).

## 10.26 RH3 failover watch, first attempts (2026-10-09, en8 iPhone + en0 Wi-Fi)

- Run 1 stopped itself after 30 s: the data budget counted Wi-Fi background traffic (247 KB). Fixed: the budget now counts only the interface labelled iPhone.
- Run 2 (90 s, 25 requests, all ok, you unplugged and replugged the cable): only request 1 left through the iPhone; the other 24 went out Wi-Fi, because the failover group picks the fastest working connection, not the first. So the unplug did not hit the active path and nothing was proven about failover timing. No leftover routes or DNS changes.
- Finding: with Wi-Fi faster, an iPhone-first order cannot be forced. New task P7.11 (preferred-first order), then rerun RH3.

## 10.27 RH8 crash recovery with two lanes, live (2026-10-09)

- Two scoped lanes (Wi-Fi and iPhone), `kill -9` of the sing-box core (admin prompt). Result: within one poll (about 6 s including the password prompt) helper status was core false, lanes empty, no utun routes left; routes (default, utun, /32) and DNS identical to before; no sing-box process left; default stayed en0. Not separated: whether the helper or the guard did the cleanup (both exist). Zero data used.

## 10.28 The 120 s lane stop: found and fixed (2026-10-09)

- Symptom (live): a scoped lane stopped by itself about 125 s after start although the app pinged `status` every 3 s; helper log: `backend crash-restore (exited)`.
- Root cause (helper job j60, read from code): `startGuardWatch` captured the lease deadline by value, so the guard process kept the start-time deadline (start + 120 s + grace) while status pings only moved the helper's own lease; the guard then restored and killed the core. Fix: the heartbeat reads the live deadline on every beat; `get-diagnostics` also returns `lastCoreExit` (code, signal, redacted log tail).
- Live proof after reinstalling the helper: one lane held 250 s, 70 of 70 checks core up, no stop, routes and DNS identical afterwards, nothing left running. Regression tests with a 300 s fake clock fail on the old code.
- Also built today (fakes only): unsigned `.app`/`.dmg` packaging (spctl rejects it as expected; never launched).

## 10.29 Session summary 2026-10-09 (end of day)

- Proven live: scoped lanes on Wi-Fi + iPhone tether, VPN over a chosen connection, core kill recovery (RH8), 250 s lane hold after the guard lease fix; Little Snitch active during all runs.
- Built with fakes only: lane limits (quotas, schedules), per-app DNS in lanes, preferred-first failover loop, IPv6 split halves, diagnostics, Keychain, notifications, Wi-Fi auto-switch, helper install flow, agent CLI, unsigned packaging (never launched).
- Not proven live: global capture, failover unplug, sleep/wake, per-app DNS, limits, external VPN detection.
- Security review 2 (docs/research/10-security-review-2.md): global capture live = conditional yes for short supervised runs; shipping v1.0 unsigned = not yet (fixes S1-S9 queued; S1 half done).
- Test counts at the end: core 355, helper 668, app 625, cli 118, hard-tests 43, packaging 18.

## 10.30 Cloud session 2026-10-10: built with fakes only, nothing proven live

This session ran in a cloud sandbox with no access to the user's Mac, helper, network or VPN. Everything below is **built, fakes only**. None of it counts as proven live.

- Merged the night branch: the app and the CLI fetch `get-consent-challenge` and send `I-UNDERSTAND-GLOBAL-CAPTURE:<nonce>` for global windows; the bundle installer uses the bundled, hash-pinned sing-box. The 9 known red app tests are green.
- Helper install (P2.20, P2.21): the install script now stops the helper, lets the guard restore the network, stops the guard, keeps the previous code, plist and sing-box in a `.prev` folder, moves the new copy in, and puts the old one back if the new helper does not start. The rollback function is run against fake tools in a test. No install was run.
- `probe-vpn` (new helper command, budget 1024 to 20480 bytes): one plain request to a fixed address, only while a lane runs. The CLI `vpn test` uses it. Open question for the live test: the request leaves from the helper's own node process, so it only goes through the test lane if the lane's app match covers that node; the CLI test lane matches the CLI's node path, which is normally the same file.
- Added tests: restore after adoption reaches the guard; a global stop deletes each split half (IPv6 included) only on fresh evidence; the connection cap and the idle timeout through the real server.
- S9 (peer credentials): not built. Node cannot read `LOCAL_PEERCRED`; the design note is in `helper/README.md`.
- App: Silent mode switch in Settings; plain wording for a VPN app that cannot be used in a profile yet; one error banner with "Try again" and a "Go to profiles" button in the empty Activity, Connections and Log screens.
- Test counts: core 301, helper 779 (1 fails only on Linux: a BSD `stat` flag in `install-stage.test.ts`, passes on macOS), app 651, cli 129, hard-tests 88, packaging 29.

Live tests still for the user's Mac: install and upgrade with a real password prompt (and an upgrade that fails on purpose to see the rollback), `vpn test` through a real VPN, failover with Wi-Fi off, sleep and wake, one short global capture with the new one-time consent, and the hard-test scripts that still send the retired consent string.

## 10.31 Session 2026-10-10/11 (fakes, reviews, one on-screen check)

Everything here is **built with fakes or checked by read-only review**, except the one on-screen check, which looked at the app's screens only. No new live run happened in this session. The only live results are the ones from 10.23 to 10.28.

**Built with fakes**

- Human-bound consent for global capture (S10, S11). The helper shows a native macOS dialog as the console user (`launchctl asuser`). Only the exact Allow button counts, the answer is bound to the request and spent by the start, and at most 3 dialogs run per 10 minutes (`E_HUMAN_DECLINED`, `E_RATE_LIMITED`). The app shows an Electron confirm dialog first, and the CLI exits with code 4 when a start is refused.
- Read-only control API in the running app (P7.15). Loopback only, bearer token in `control.json` (0600), GET only, Host and Origin checked, off by default, Settings switch under Advanced.
- `splitnet report` (P6.8): one redacted Markdown file for a bug report, plus a GitHub bug report template.
- Upgrade and downgrade guard (P6.3): refuses an older helper unless `--allow-downgrade` is given, `--rollback` swaps the previous copy back, state files carry `schemaVersion` with migrations, and a newer state file is refused.
- `probe-vpn` (20 KB budget) behind `splitnet vpn test`. It refuses unless one running lane covers the helper's own node.
- Install (2026-10-10 and C2 fixes): the app checks the new helper's version before it reports success, and the root install path checks the pinned sing-box hash and runs `codesign`.

**What the three Cursor Auto reviews found** (read-only, pinned CLI 2026.08.04, each finding checked against the code; docs/research/18 to 20)

- C1, guard, lease, canary, restore, route policy and consent: 6 of 6 real, all fixed with tests. A refused state made the guard inert (it now restores from the last valid state, or stops with NEEDS ATTENTION). Scoped routes had no cap (now 256). An armed guard with a baseline TUN never exited. Restore with no live guard now adopts the state. The consent digest lost the interface order. A no-op re-apply spent the consent (now spent only on start).
- C2, install, upgrade and probe-vpn: 4 of 6 real and fixed, 1 wording, 1 not real. The critical one was the app building the root install from live hashes with no pin or `codesign` check; the app now uses the pins and `codesign` as the CLI does. Per tasks.json the other fixed items are the rollback and install trust. The probe findings (the 20 KB cap is checked after the first chunk, and the probe request is cleartext HTTP to a fixed address) have no status recorded in tasks.json.
- C3, agent CLI, consent token and store lock: 5 of 6 real, fixed. The token no longer goes into `--json` or onto argv, redeem is atomic, the data folder is 0700, and a global start asks in the main process. Still open: the helper hands out challenges to any socket client. The S10 dialog is the answer to that gap, and it is not live yet.

**The one on-screen check (2026-10-11)**

- Dark theme, empty states and the helper-error state. It found 3 problems: the same helper error repeated in three banners, a stale Running state, and speed text that wrapped. All three are fixed, and the banner fix was confirmed on screen.
- Not yet seen on screen: onboarding, Settings, Activity, Connections, Log, the light theme on every screen, and a 1024 px width.

**Test counts**: core 377 (1 skipped), helper 858, app 741, cli 150, hard-tests 97, packaging 29.

**Still not proven live**

- The human dialog from the root daemon (the console session via `launchctl asuser`), and whether an agent running as the same user could click Allow through accessibility. In principle it can, if the user has granted accessibility control; this is not a sandbox.
- Global capture itself, failover by unplugging, sleep and wake, per-app DNS, data limits.
- Real install, upgrade, downgrade refusal and `--rollback`, including the osascript password prompt, launchd, and a rollback with a running core.
- The control API on a real run of the app.
- `probe-vpn` through a real VPN (only a lane that covers the helper's node counts).
- `splitnet report` run on the Mac; redaction is checked by tests only.
- External VPN detection with a live external VPN (P2.23).

**Notes for the next task pass** (tasks.json was not edited in this session): P6.3 is still `todo` although it is built with fakes; P6.8 says "issue template not built", but the template exists; P7.15 says "drafted but not wired in", but the control API is built with tests; P3.44 says 3 problems, which matches this section.

## 10.32 Session 2026-10-11 afternoon (fakes, one first helper dialog check)

Everything below is **built with fakes or unit tests**, except the first live check of the helper's Allow dialog, which has an open question. No new live run of the lanes happened in this session.

**Built with fakes**

- "All other apps" lane in the editor (P3.19): the macOS Allow dialog flow, a 10-minute window, a countdown and Keep running.
- Menu bar title with live speed, and a speed line for each running profile.
- Ask on first connect: "Telegram is using the network. Add it to a profile?" is wired from the helper to the app notification.
- Signed update check: ed25519 signature, https only, never installs by itself. The real signing key is not set.
- Per-app stats history with 35 days of retention, and lifetime totals.
- Performance bench in core, and a fix for the overlap check, which was O(n^2). At 8 lanes x 1000 apps it went from 11 s to 2.4 s.
- App icon pipeline, a checksums script and a release checklist in packaging (W8).
- Plain-language user guide (docs/27) and a refreshed install guide (docs/15).
- Dashboard: a whole-project progress row.

**First live check of the helper dialog (open question)**

- The helper was reinstalled on the Mac as a test install.
- A global consent challenge was issued in 6 seconds.
- It is **not known yet** whether a person clicked Allow, or whether the dialog did not appear. NOT PROVEN either way.
- Open question for the user: did you click Allow, or did no dialog appear? The answer goes into docs/10 and docs/26 section 12.

**Test counts**: core 384, helper 876, app 808, cli 150, hard-tests 97, packaging 47.

**Still not proven live**

- The Allow dialog itself (who clicked, see above), and the Cancel and fourth-dialog refusals.
- The All other apps flow with the 10-minute window and countdown on a real run.
- The menu bar title with live speed on the real menu bar.
- The ask-on-first-connect notification and a click on it.
- The signed update check with a real key.
- Everything listed in section 11 and the new section 12 of docs/26.

## 10.33 First live check of the helper Allow dialog (2026-10-11, test install, no capture started)

- Setup: helper reinstalled (test install). `get-consent-challenge` (global) and the raw macOS dialog call were run by hand; the person at the Mac clicked. No capture was ever started (only the consent code was requested).
- Dialog shown by the root helper as the console user: title "split-net", text with the minutes and a request code, Cancel is the default button, second button "Allow for 1 minutes". Works from the root daemon with `launchctl asuser`.
- Allow click: the helper returned a one-time code (2 to 9 s). The earlier "approved by itself" worry was the person clicking Allow.
- Cancel click (raw macOS call): exit 1, no button, `isAllowed` false, so refused. Cancel through the helper (E_HUMAN_DECLINED) still to be repeated after the rate window.
- Rate limit: the 4th request within 10 minutes was refused with E_RATE_LIMITED and no dialog (limit is 3 per 10 minutes).
- Agent click attempt: a script run from the shell tried to click "Allow" through System Events: macOS refused with "osascript is not allowed assistive access (-1719)". So a shell-run agent cannot approve the dialog on this Mac. (An app that already holds the Accessibility permission could; the permission list was not read.)
- Not yet proven: Cancel through the helper, the 60 s give-up path through the helper, a global start after Allow.

## 10.34 RH3 failover with the iPhone unplugged, live (2026-10-11, en8 iPhone preferred, en0 Wi-Fi backup)

- Setup: one lane over [en8, en0] (preferred-first selector), one tiny request every 3 s for 140 s, iPhone data counted only (cap 200 KB); the person unplugged the iPhone cable at about 27 s and plugged it back at about 60 s. The system VPN and default route were not touched.
- Result: before the unplug all requests left through the iPhone. At the unplug one request failed (curl exit 52, the connection in flight), then every request succeeded through Wi-Fi: 38 of 39 OK, failover within about 3 to 7 s. Routes and DNS identical after the run; nothing left running.
- NOT as designed: after the replug (about 60 s) traffic did NOT return to the iPhone during the remaining 80 s; requests kept going out Wi-Fi (the iPhone interface showed only small background bytes). The design says the loop returns to the preferred member after 3 healthy probes. Possible causes: probes through the re-created iPhone interface not healthy yet, or the bound interface needing a new dial. To investigate (task P7.17).
- Proven: preferred-first failover on unplug. Not proven: return to the preferred connection.

## 10.35 P7.17 failover return to the preferred connection: code review and fixes (2026-10-11, no live run)

- Read, no live run: the probe is the clash API delay of the member's own outbound (bind_interface en8 or en0). sing-box keeps no history for a selector, and the probe result is not cached on our side. The healthy streak starts at the first answer after a member was declared down.
- Both selectors (lanes.ts) already set interrupt_exist_connections true, so a switch back closes the Wi-Fi connections and new requests follow the selector. The loop does not look at connections.
- Fixed: one busy flag covered probing and selector writes. A write waiting in the core queue (for example behind a limit restore) stopped every probe round, so the counters froze. Probing and deciding now have separate guards (core/src/failover.ts).
- Diagnostics: one debug event per member per round (failover-probe, member, alive, healthy and failed counts, no secrets) in the log ring, and status.lanes[].probe for the preferred member.
- Not proven: the return itself. Next RH3 run: "not alive" in failover-probe lines points at the re-created interface (bind or DHCP not up yet); "alive" with the count stuck below 3 points at the loop; 3 healthy and no switch points at the selector write.

## 10.36 RH4 sleep and wake with a Wi-Fi-only lane, live (2026-10-11)

- Setup: one lane over en0, status poll every 3 s for 200 s; the person used Apple menu > Sleep twice (about 60 s and about 12 s asleep). Data used 1.3 KB. System VPN and default route untouched.
- First wake: the lane survived (status up, 1 lane, a request through it OK on the second try after one curl timeout).
- Second wake: helper log `backend watchdog (guard lost)` then `backend stopped (guard lost)`: the helper stopped the lane and restored the routes (fail-safe), and the lane stayed down (core down, 0 lanes) for the remaining 110 s. Routes and DNS identical to the baseline at the end; nothing left behind.
- FINDING: a sleep/wake can look like a lost guard (stale ack or heartbeat against the clock jump), so the helper ends the running lane. Safe, but every running profile is lost at sleep. Task S14: wake awareness (re-arm and grace window before declaring the guard lost, lanes restart on the fresh baseline).
- Proven: after sleep the routes/DNS come back clean and nothing leaks. Not proven: lanes surviving sleep.

## 10.37 RH4 rerun after the wake-awareness fix, live (2026-10-11)

- Setup: the new helper reinstalled (test install), one Wi-Fi lane over en0, status every 3 s for 220 s; the person slept the Mac once for about 44 s. 773 bytes used. System VPN and default route untouched.
- Result: LANE SURVIVED: after the wake status up, 1 lane, a request through the lane OK on the first try; routes and DNS identical to the baseline; nothing left behind.
- Proven: a lane survives one sleep of about 44 s after the wake-grace fix (before the fix a 12 s sleep ended the lane with "guard lost").
- Not proven: very short sleeps (the 12 s case that failed before), several sleeps in a row, a wake onto another network.

## 10.38 Global capture refused while the system VPN is on (live, 2026-10-11)

Two helper-client bugs found and fixed first: `get-consent-challenge` and `apply-lanes` can wait for the Allow dialog, so the clients now wait up to 75 s (they gave up after 5 s). `global-short` now prints NOT HELD when the hold never ran. Proven live: the 60 s dialog give-up through the helper (no click, nothing started, routes and DNS unchanged). Then the helper refused the global start with `E_BAD_REQUEST: global capture needs exactly one IPv4 default route, found 2`: the Mac has two default routes while the system VPN (utun5) is up. This is the designed safety check, not a bug. The global capture itself is NOT proven live; it needs a Mac with one default route (system VPN off), which is the user's lifeline here, so it stays untested on this machine.

## 10.39 `vpn test` through the stored VPN over Wi-Fi (live, 2026-10-11)

`splitnet vpn test 99aaf1c8d9 --via en0`: reachable, latency 220 ms, exit IP = the VPN server's address, 1 KB used of the 20 KB budget, test lane stopped again. Own core, not the system VPN. Three bugs found on the way and fixed: the app-path rule rejected `@` (brew `node@22`), the probe's plain HTTP request got a 301 from 1.1.1.1 (now HTTPS), and the CLI hid the helper's reason (now shows it plus the HTTP status or error code).

## 10.40 Failover run found a pause instead of a failover (live, 2026-10-11)

RH3 rerun (iPhone en8 + Wi-Fi en0, 200 s, 33 KB used): on unplug the helper restarted the lanes after the network change and the restart refused the missing member, so the lane PAUSED ("the connection en8 is not available now"); traffic only kept working because it left on the normal route. After replug the lane did not resume. This means the earlier failover note (10.34) shows a pause, not a proven failover. Fix (code + tests, fakes only, not yet proven live): a restart after a network change drops missing members of a lane with 2 or more connections and keeps the original request, so the member returns at the next restart (`keepUpConnections`, core 396, helper 923). Known gaps: no interface-up event (replug relies on the default-interface change event seen live at replug), and a limits change while a member is down is still refused.

## 10.41 Failover and return to the preferred connection (live, 2026-10-11, proven)

RH3 with the fix (iPhone en8 first, Wi-Fi en0): 59 requests, 59 ok, 0 failed, 51 KB used. At the unplug (18 s) the helper restarted the lanes on Wi-Fi only (network-restarted, no pause) and traffic kept flowing over en0. At the replug the default-interface change event restarted the lanes with both connections, and traffic returned to the iPhone (first en8 growth 92 s, then steady). Supersedes the 10.40 gaps for this case: the replug did not need an interface-up event. Two earlier runs failed for test reasons only: the script did not ping the helper (lease stop at 120 s, fixed in `failover-watch.ts`), and one run had no unplug. Not proven: a limits change while a member is down, repeated plug cycles, the guard under many network changes (3 per 2 min pauses by design).

## 10.42 Global capture, short supervised run (live, 2026-10-11, proven for the hold)

System VPN off (one default route, en0), `global-short --no-system-vpn --seconds 30`, stored VLESS profile, curl only matched. The helper's Allow dialog was shown and allowed by the person; the lane held 30 s with the core up on all 16 checks, the default route and 4 nameservers unchanged every tick, and the teardown left routes and DNS identical to the baseline. No data was used (no request sent). Not proven: that curl traffic exits through the VPN in global mode (no request sent), leaks of other apps (no capture), longer holds, global with the system VPN on (refused by design: needs exactly one default route).

## 10.43 LAN adapter unplug for 20 s (live, 2026-10-12)

Lane over the USB LAN adapter (en7) and Wi-Fi (en0), 100 s, no data limit. The helper saw the unplug (interface-down, default-interface-changed, dns-changed), stopped the lane and, because the network had changed more than 3 times in 2 minutes (an earlier restart plus the cable events), paused it ("start it again by hand"). One request failed, the others went out over the normal route. This is the designed safe pause, and it is the behaviour the user chose as the v1.0 default (pause and notify; auto-continue later). An earlier run, where the cable was not touched, showed that the helper sees no change without a real unplug.

## 10.44 Sleep for about 2 minutes (live, 2026-10-12)

Wi-Fi lane over en0, system VPN on. The Mac slept for 120.4 s (one sleep): at wake the core was up, one lane listed, and a request through the lane succeeded on the first try. Routes and DNS identical to the baseline; 918 B used. This is a second live proof of the sleep fix (10.37, 44 s) at a longer sleep. Not yet proven: a 12 s sleep, several sleeps in a row, a wake on another network. (The first attempt of the day did not sleep, so it tested nothing.)

## 10.45 Pause on network change and resume-lanes (live, 2026-10-12, proven)

New v1.0 default, `tools/hard-tests/pause-resume.ts`, lane over the USB LAN adapter (en7) and Wi-Fi (en0), system VPN on. The LAN cable was unplugged: within about 24 s the lane was paused and status said `paused` with the plain reason "lane connection en7 is down" and `canResume: true`; requests kept going out on the normal route. After 10 s the script called `resume-lanes`: accepted at 35 s, the core was back up (core true, paused no) and the requests carried on. Then the cable was plugged back in; no further pause. Default routes at the end: en7 and en0, as before. Not proven live: the app notice (buttons), a wake with unchanged connections in pause mode, resume after replug of the missing connection (the resume ran on the remaining connection, Wi-Fi).

## 10.46 The network-change notice in the real app (live, 2026-10-12, driven by computer use)

Dev app (electron-vite), profile over the USB LAN adapter and Wi-Fi, no VPN, Telegram. Start: running. LAN cable unplugged: within about 30 s the app showed the notice "The network changed: lane connection en7 is down. Your apps are using the normal connection now." with the buttons Continue on what is left and Stop. Continue: the profile was Running again and the app said "Apps that were already connected may need to reconnect." Found: a wrong red banner ("The core stopped because the app did not check in with the helper...") during the pause and after Continue (task H60). Also found: after the app migrated the VPN library to the Keychain, the CLI could not read the secrets (`vpn test` said missing uuid) and Start with a VPN said "The VPN of this profile is not known to the helper" (task H59).

## 10.47 Telegram through a subscription VPN, started from the app (live, 2026-10-12)

Profile "test 2" in the dev app: Telegram, VPN 11c1a5dec0 (VLESS over WebSocket and TLS from a subscription link), scoped lane over Wi-Fi (en0). The person pressed Start anyway; Telegram connected (3 active connections, traffic growing in the helper's per-app counters) and the person confirmed it works. Before that, the pre-Start check blocked three good VPNs: the app's test lane used the Electron path instead of the helper's node ("test lane does not cover this helper's node", found in the app log, task L5). Also found and fixed from the logs the same day: Stop timed out at 5 s (L1), duplicate React keys (L2: ColumnVpn group key), the picker spacing tokens not reaching portaled dialogs. The subscription had 28 entries: 23 usable (VLESS ws+tls), 15 of them answered a real test over Wi-Fi (744 ms to 2131 ms).

## 10.48 Global (All apps) capture on Wi-Fi: the missing route found and fixed (live, 2026-10-12, proven)
Mac on one default route (en0, iPhone hotspot), system VPN off, test helper reinstalled for each fix. Probe `tools/hard-tests/global-probe.ts` (30 s hold, auto abort): before the fix DNS and TCP connects passed (the TUN answers them) but every unmatched HTTPS failed ECONNRESET; the core log (root-only `sing-box.log`) showed `dial tcp ...: connect: network is unreachable` on `direct[if-en0]` for every unmatched connection. Cause: with the TUN's 0/1 routes in place, a socket bound to en0 had no usable route. Fix: the helper adds an interface-scoped default (`route -n add -net 0.0.0.0/0 -ifscope en0 <gw>`, policy-allowlisted, recorded in the guard first, removed on stop). Result: 30 s held, HTTPS over IPv4 11/11 ok, routes and DNS identical after the stop. Then the user started "test antigravity" (Antigravity, VPN agy, Wi-Fi en0): the models load and the internet stays up; an unmatched curl got 200 in 0.4 s while it ran. Also changed: the Xray hop is bound to lo0, global DNS uses the local resolver, the TUN drops IPv6 when the Mac has no IPv6 default route. Not proven: the LAN adapter case (en7), global with the system VPN on (refused by design), long holds, sleep/wake.

## 10.49 Profile isolation: the VPN is really used, other apps are not (live, 2026-10-12, proven)
`tools/hard-tests/isolation.ts` (scoped lane over en0, no global capture, system VPN not touched): matched /usr/bin/curl and an unmatched node call to the same IP-echo host (its addresses routed into the TUN as /32). Direct IP 2.177.x.x; agy: matched 162.55.x.x, unmatched 2.177.x.x: PASS. Sweep of all 27 saved VPNs: 23 PASS (matched exit IP differs per VPN, e.g. CH, AT, RO), 4 FAIL with "echo failed (matched)" (VPN server gave no reply; in all four the other app kept the direct IP, so isolation held). Routes and DNS identical after every run (27 of 27). About 20 KB per VPN. The same test is a hard self-test in the app Debug panel (built, not yet looked at in the running app). Not proven: groups of several apps (C), the global variant (D), long holds.
