Read-only security review of those commits — no plan/report files. Checking the named paths and diffs first.

Shell got blocked — retrying diff/read with read-only access.

Verifying findings against the actual source for accurate line numbers.

## R7.1 security / correctness review

Scope: `presence.py`, `launcher.py`, `queue.py`, `hooks.py` (presence touch), `loader.py`, `routes.py` (`_phone_public`), `agentguard.py` / `featops.py` (`person_context`). Commits `bae27a0..b9bcbf2`, `0e4016e`, `29e6e58`.

**Verdict:** no critical; injection + opt-in gates look sound. Main gaps: PreToolUse I/O stall, person-gate bypasses, launch TOCTOU, partial phone scrub.

---

1. **medium** | `roadmap/services/hooks.py:367-369` + `roadmap/services/presence.py:61-72` | PreToolUse calls sync `touch_hook` after the 300 ms check; throttle still does a full JSON read (no mtime fast-path from R7.1 SPEC). Hung/slow `state_dir` I/O can block the hook process with no I/O timeout → tool call stalls (fail-closed). | Mtime skip before read; or skip touch when remaining budget &lt; margin; hard-cap presence I/O.

2. **medium** | `roadmap/services/agentguard.py:84-94` + `roadmap/services/featops.py:160-164` | `person_context("cli")` is true for dual-TTY + empty agent markers. Agent can strip `CLAUDECODE` / `CURSOR_*` / `AGY_*` and run under PTY/`script` → `feature.accept` without a person. | Treat accept as `gui`+`gui_proven()` only, or require out-of-band confirm; do not equate bare TTY CLI with person for accept.

3. **medium** | `roadmap/http/routes.py:244-253` + `roadmap/http/security.py:86-95` + `featops.py:162-164` | Local process can forge `Origin` + `Sec-Fetch-Site: same-origin` + CSRF from `GET /` → `_cmd_source` yields proven `gui` → `person_context` passes for accept (WP22 speed-bump, but accept is person-only control). | Second factor / typed confirm for accept; or refuse HTTP accept.

4. **medium** | `roadmap/services/launcher.py:98-104` + `roadmap/services/queue.py:56-58,74-75` | `maybe_launch` checks presence/`_recent`, then `_stamp`, then runs — no lock. Concurrent Start enqueues (daemon threads) can both pass and spawn multiple Terminal/`claude` sessions when `launchOnStart: true`. | Atomic gate (lockfile or CAS on `launch.json`); stamp after successful launch; serialize per `data_dir`.

5. **medium** | `roadmap/http/routes.py:97-113` | `_phone_public` drops `project.path` and rewrites only `$HOME` / `$HOME/...`. Other absolute paths in nested snapshot strings stay (`tests/api/test_phone_path.py:20` encodes `HOME+"2/x"` unchanged). | Scrub all absolute path shapes, or allowlist phone snapshot keys.

6. **medium** | `roadmap/services/presence.py:34-51` + `roadmap/store/atomic.py:41-44` | `write_json` refuses symlink targets; `read_json` follows them. Symlink `presence-*.json` → attacker-controlled file can forge `none` while writes fail → sticky false idle → opt-in launcher fires. | `lstat` and refuse/ignore symlink reads; or open with `O_NOFOLLOW`.

7. **medium** | `roadmap/services/presence.py:61-72,77-84` | Unlocked RMW: concurrent `touch_hook` / `set_watch` can clobber each other’s stamps → false `none` → unwanted launch under opt-in. | Single-writer lock or merge under file lock; compare-and-swap.

8. **low** | `roadmap/services/queue.py:66-71` | Idle Start notification body embeds full project path (`cd … && claude`), surfaced via Notification Center (not phone, but path leak). | Use project id only, or `~`-shorten after scrub; keep path out of notify text.

9. **low** | `roadmap/services/launcher.py:59-68,102` | Corrupt/missing `launch.json` makes `_recent` false (fail-open). Any writer in `state_dir` can delete the stamp and re-arm launch on next Start when opted in (rate-limit bypass, not opt-in bypass). | Fail-closed on unreadable stamp, or bind stamp to presence generation / HMAC.

10. **low** | `roadmap/services/launcher.py:20-21,75` | One global `launch.json` for all projects — rate limit is shared, not per `data_dir` (correctness / fairness, not injection). | Per-project stamp (`launch-<hash>.json`) matching presence naming.

---

**Checked, no medium+ issue**

| Area | Result |
|---|---|
| Shell / AppleScript injection | Path from registered config only; `_valid_dir` rejects controls; `shlex.quote` + AS escape; argv-only `osascript` (`launcher.py:52-56,80-83`). |
| Launch without opt-in | Requires `launchOnStart is True` (`launcher.py:93-94`); queue only via `maybe_launch`. |
| Hook fail-open on exceptions | `run_hook` never raises (`hooks.py:217-229`); `_touch_presence` swallows (`399-404`). |
| `project.path` on phone key | Removed (`routes.py:111-112`); localhost keeps it for Copy (`loader.py:61-67`). |
| Phone `feature.accept` | Not in `PHONE_OPS`. |

**Bottom line:** launcher injection/opt-in OK. Fix first: PreToolUse presence I/O budget, person-gate for accept (PTY/env + header spoof), launch TOCTOU, phone path scrub / presence symlink+race integrity.

