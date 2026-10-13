# Security

**Status: draft, WP13 built.** This describes what roadmap-board protects, against whom, and how. Items marked *built*
are in the code and tested. The phone mode is built (WP13), with two gaps listed in the review checklist at the end. The
review gate (WP13/R1) must be signed before the 1.0.0 release (WP14).

## What is worth protecting

| Asset | Where | Why it matters |
|---|---|---|
| Claude Code sign-in (OAuth access token) | the login keychain, item `Claude Code-credentials`. roadmap reads it only for a usage read | it can act for your account |
| Plan usage numbers | `usage.json` in the state folder, and `docs/autonomy.json` in each project | they are not secret, but they drive your agents' stop rules |
| Project data | each project's `docs/` folder | it is your roadmap; roadmap reads it and writes only the job registry, usage mirror and migrations |
| Phone token | `~/.config/roadmap-board/phone.token` | it would open the dashboard from another device |
| Logs | `~/Library/Logs/roadmap-board/` | logs must never contain a token or a query-string secret |

## Who could attack it

1. **Another website in your browser** that makes requests to `127.0.0.1` (cross-site request forgery, or a page that
   tries to read the dashboard).
2. **A DNS-rebinding page**: a hostile name that resolves to `127.0.0.1` so the browser treats the server as the
   name's own origin.
3. **Other software on this Mac** that connects to the port. Anything running as you can read your files anyway, so
   the goal here is to keep the dashboard from becoming a way in, not to defend against code running as you.
4. **Content in a project**: task descriptions, job titles and hook input come from files and from Claude Code. They
   are data, and they are shown escaped.
5. **Someone on the network**: the server is not reachable from the network. Only the phone listener and its
   tunnel are.
6. **Someone who reads your logs or your shell history.**

## Controls

### Built

- **Loopback only.** The server binds `127.0.0.1`. There is no option to change that.
- **Host allowlist.** Every request's `Host` must be `127.0.0.1:<port>` or `localhost:<port>`. Anything else gets
  `421`. This is the DNS-rebinding guard.
- **CSRF token and same-origin check on the one write route.** `POST /api/v1/usage/sync` needs `Sec-Fetch-Site:
  same-origin` (or an `Origin` of this server), the `X-Roadmap-CSRF` token of this process (32 random bytes, compared
  in constant time), `Content-Type: application/json`, and a body of at most 4096 bytes. The token is served only in
  `<meta name="csrf">` on the HTML page.
- **Content Security Policy on every reply**: scripts and styles only from `'self'`, no framing (`frame-ancestors 'none'`), no
  `base-uri`, no `form-action`. `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: no-referrer`,
  `Cross-Origin-Resource-Policy: same-origin`.
- **No file access from URLs.** Pages come from an allowlist built at start-up. A URL path is never turned into a
  file path, so `..`, encoded dots and double slashes give `404`.
- **No query strings in logs.** The access log writes method, path, status and time. Log lines also pass a redaction
  filter for `Bearer ...`, `sk-ant-...` and `k=...`.
- **The keychain token** is read by running `security find-generic-password -s "Claude Code-credentials" -w` as an
  argument list (no shell). It is held in memory for one request, is sent only in an HTTPS `GET` to
  `api.anthropic.com`, and redirects are refused. Failures carry a plain reason and the exception type, never the
  message of a library error, which could contain the token.
- **`doctor` does not read the secret.** It checks that the keychain item exists, without `-w`.
- **Files and folders are private.** Folders are created with mode 0700 and files with 0600. The launchd plist is
  0644 because launchd must read it, and it holds no secret.
- **Atomic writes and locks.** Data files are written through a temp file and `os.replace`, under a directory lock, so
  a crash cannot leave a half-written file, and two writers cannot interleave.
- **Newer files are never overwritten.** A data file written by a newer roadmap-board gives an error and is left alone.
- **Hooks never fail a tool call.** The hook entry prints nothing and exits 0, whatever it reads.
- **Subprocesses are argument lists.** `shell=True` is refused by the lint. Subprocesses run from `services/`, and from
  the `open` command, which only opens the loopback dashboard URL.
- **Standard library only.** No third-party code runs in the server or the CLI.

### Phone mode (WP13, built)

- **Phone listener** on `127.0.0.1:8766` (`phonePort`), read-only. Only GET reaches the routes and pages; any other
  method gets `405`. Without a usable `phone.token` every request gets `503`.
- **Token** from `secrets.token_urlsafe(32)`, written atomically with mode 0600, rotated by `roadmap phone start`, and
  deleted by `roadmap phone stop`. A token file that is readable by group or others is not used (`503`).
- **Entry.** `?k=<token>` is accepted once. The answer is a `302` to the same path without `k`, with the cookie. A wrong
  token gives `401`.
- **Cookie** `rb_phone` holds `HMAC-SHA256(key=token, msg="cookie")`, never the token. Attributes: `HttpOnly; Secure;
  SameSite=Strict; Path=/; Max-Age=604800` (seven days). Rotating the token invalidates every cookie.
- **Comparisons** of the token and the cookie use `hmac.compare_digest`.
- **Rate limit.** After 10 failed attempts within 60 seconds in one process, every phone request gets `429` with
  `Retry-After` until the oldest failure is a minute old.
- **Host.** The phone listener accepts `127.0.0.1:<port>`, `localhost:<port>`, and the tunnel host saved in config
  `phoneHost` (with or without `:443`). The tunnel host is written only by `phone start` from ssh's output, never from a
  request. Anything else gets `421`.
- **Redirect.** The redirect target is the request path only when it is a plain absolute path. A `//host` form becomes
  `/`, so the redirect never leaves the server.
- **Tunnel.** `phone start` runs `ssh -o ServerAliveInterval=30 -R 80:127.0.0.1:8766 nokey@localhost.run` with its
  output in `tunnel.log` (0600) and its pid in `tunnel.pid`. The tunnel URL is found with a regex and saved as
  `phoneHost`. `phone start` refuses to run while a tunnel is up (exit 4).
- **Stop.** `phone stop` signals the recorded pid only when `ps` shows an `ssh` command that names `localhost.run`. A
  pid that is not our ssh is never signalled (exit 4, `tunnel.pid` kept). The token, the pid file and `phoneHost` are
  removed in every case.
- **Link.** `phone link` prints `https://<host>/?k=<token>`. That link grants read access, and it is the only output in
  roadmap that prints the token. No other command prints or logs it (see the redaction audit in the checklist).

**First use of the tunnel host key (WP14).** `phone start` runs ssh with `StrictHostKeyChecking=yes` and a private `known_hosts` in the state folder, so the tunnel host key must be added once, by you. Run `ssh-keyscan localhost.run`, read the output and check the key yourself, then append the lines to `known_hosts` in the state folder. roadmap never fetches the key itself. Until the key is there, `phone start` exits 6 and `tunnel.log` shows a host key error.

### Control, the PreToolUse gate and agent refusals (WP22, built)
- **Control state.** Each write recomputes `<state>/control-<project>.json` (stop, stopped tasks, the limit that blocks,
  the override time). The sentinel `<state>/block-<project>` exists only while something blocks.
- **Gate.** The PreToolUse hook denies Edit, Write, MultiEdit, NotebookEdit, Bash, Agent, Task, WebFetch and WebSearch
  while blocked. Read, Grep and Glob are never denied. A Bash command passes only when it starts with `roadmap ` and
  chains nothing (no `;`, `&`, `|`, backticks, `$(`, redirects or new lines), so a stop cannot be bypassed by a
  chained command.
- **Fail open, on purpose.** A missing or unreadable state, an unknown project, an exception or a gate that takes longer
  than 300 ms lets the call through. The shell shim exits 0 before it starts Python when no sentinel exists.
  Normal sessions keep working whether or not the roadmap is running. The cost is that a damaged state file lifts
  the gate; the next write rebuilds it, and a corrupt control file refuses writes until someone fixes or removes it.
- **Agent refusals.** Ops that loosen control (`resume`, `override`, `limit set`, raising or clearing a budget, `phase
  approve`, `rules add|rm|sync`) are refused when `CLAUDECODE=1` or the source is `agent`. The refusal names
  `roadmap ask "<question>"`. Stopping is never refused.
- **Writes outside the project.** `rules sync` writes only between `<!-- roadmap:rules -->` and
  `<!-- /roadmap:rules -->` in the project's `CLAUDE.md`, makes a backup first, refuses broken markers and refuses a
  symlinked file.
- **Denials are logged** at most once a minute per project in `hooks.log`. Nothing the agent wrote is executed.

## Known limits

- The usage endpoint and its beta header are not a documented public API. A change on Anthropic's side fails the read
  with a plain reason; it cannot widen what roadmap sends.
- Hook jobs are inferred from tool calls and output file names. A wrong guess shows a wrong job; it cannot change any
  project file other than the job registry (`jobs.json`) and the usage mirror.
- The keychain prompt is the operating system's. Choosing Always Allow lets the `security` tool read that item without
  asking again. Revoke it in Keychain Access if you no longer want the usage feature.
- A process running as you can read the same files. roadmap does not add a boundary between you and your own code.

## Reporting a problem

If you find a way to read the token, to make a write the user did not ask for, to reach the server from another host, or
to get a secret into a log or a reply, please report it to the maintainer privately, not in a public issue. Include the
version (`roadmap version`), the request or command, and what you saw. Do not include your token or your keychain
entry. If a secret has already leaked, rotate it in Claude Code first, then report.

---

## Review checklist (WP13/R1)

Audit of `roadmap/http` against section 3 of `docs/roadmap-board-architecture.md`, done in WP13. Each row names the
code that implements the rule, the test that proves it (`tests/api/test_security*.py` and the other test modules named
in the row), and the status: `done`, or `gap` with the reason. Line numbers are as of WP13.

| Requirement | Where implemented | Test name | Status |
|---|---|---|---|
| Bind 127.0.0.1 only, both listeners | `roadmap/http/server.py:24`, `:268`, `PhoneServer.__init__` | `test_security.Loopback.test_main_listener_binds_127_0_0_1_only`, `test_phone_listener_binds_127_0_0_1_only` | done |
| Main listener: Host must be 127.0.0.1 or localhost on its port, else 421 | `roadmap/http/security.py:46` `host_allowed`; `server.py:77-84` `App.handle` | `test_security.HostAllowlist.test_foreign_host_is_421_everywhere`, `test_rebinding_name_and_wrong_port_are_421` | done |
| Phone listener: loopback names, plus the saved tunnel host only | `security.py:58` `phone_host_allowed`; `server.py:120-127` `configured_tunnel_host`; `server.py:146-148` | `test_security_phone.HostRules.test_tunnel_host_is_accepted_only_when_configured`, `test_an_invalid_configured_tunnel_host_allows_nothing` | done |
| Write route is POST only; other methods get 405 with Allow | `roadmap/http/routes.py:202-210` `match` | `test_routes.test_read_routes_refuse_post_with_allow_header`, `test_security_phone.ReadOnly.test_post_is_405_even_with_the_cookie_and_the_write_headers` | done |
| Phone listener is read-only (no write route reachable) | `server.py:149-151` (GET only, before any route) | `test_security_phone.ReadOnly.test_post_without_any_token_is_still_405_not_401` | done |
| Write needs Sec-Fetch-Site same-origin, or an Origin of this server | `security.py:73` `write_request_allowed`; `routes.py:104-108` `_write_guard` | `test_security.WriteChecks.test_cross_site_is_403_even_with_the_token`, `test_foreign_origin_is_403`, `test_no_sec_fetch_site_and_no_origin_is_403` | done |
| CSRF header equal to the per-process token (32 random bytes) | `security.py:32` `new_token`; `security.py:73-87` | `test_security.WriteChecks.test_no_csrf_header_is_403`, `test_wrong_csrf_is_403` | done |
| CSRF comparison is constant time | `security.py:37` `safe_equal` (`hmac.compare_digest`); `security.py:87` | `test_security.CsrfCompare.test_the_csrf_check_uses_hmac_compare_digest` | done |
| Write needs Content-Type application/json, else 415 | `routes.py:104-115` | `test_security.WriteChecks.test_wrong_content_type_is_415` | done |
| Write body at most 4096 bytes, 413 before anything runs | `security.py:14` `MAX_BODY_BYTES`; `server.py:48-62` `read_body`; `routes.py:160-162` | `test_security.WriteChecks.test_body_over_4_kb_is_413_before_anything_runs` | done |
| Chunked request bodies refused | `server.py:49-51` `read_body` | `test_security.WriteChecks.test_chunked_body_is_refused_with_400` | done |
| Phone listener: no token file gives 503 | `server.py:153-154` | `test_security_phone.TokenFile.test_no_token_is_503_for_every_request`, `test_default_token_source_reads_phone_token_and_503_when_missing` | done |
| Phone token file readable by others is not used | `server.py:101-117` `read_phone_token` | `test_security_phone.TokenFile.test_a_token_file_readable_by_others_is_not_used` | done |
| Wrong or missing token gives 401 | `server.py:174-176` `_refuse`; `server.py:169-172` | `test_security_phone.Auth.test_wrong_token_and_no_token_are_401` | done |
| `?k=` accepted once, then 302 without `k` and with the cookie | `server.py:159-166` | `test_security_phone.Auth.test_token_redirect_strips_k_keeps_other_params_and_sets_the_cookie`, `test_redirect_to_root_when_only_k_was_given` | done |
| Cookie is HMAC(token, "cookie"), never the token | `security.py:90` `cookie_value`; `security.py:96-101` `phone_cookie_header` | `test_security_phone.Auth.test_cookie_value_is_hmac_of_cookie_keyed_with_the_token`, `test_the_raw_token_never_appears_in_the_cookie_or_the_location` | done |
| Cookie flags HttpOnly, Secure, SameSite=Strict, Path=/, 7 days | `security.py:96-101` | `test_security_phone.Auth.test_token_redirect_strips_k_keeps_other_params_and_sets_the_cookie` | done |
| The raw token is not accepted as a cookie; rotation invalidates cookies | `server.py:169` | `test_security_phone.Auth.test_the_hmac_cookie_grants_access_and_the_raw_token_as_cookie_does_not`, `test_a_rotated_token_invalidates_old_cookies` | done |
| Token and cookie comparisons are constant time | `security.py:37`; `server.py:161`, `:169` | `test_security_phone.ConstantTime.test_hmac_compare_digest_is_used_for_the_token_and_the_cookie`, `test_safe_equal_never_matches_an_empty_expected_value` | done |
| 10 failed attempts per minute per process, then 429 | `security.py:116-152` `FailureLimiter`; `server.py:155-157` | `test_security_phone.RateLimit.test_ten_failures_in_a_minute_then_429_even_for_the_right_token`, `test_the_window_slides_and_access_comes_back_after_a_minute`, `test_nine_failures_do_not_block` | done |
| Redirect target never leaves the server (no `//host`, never from Host) | `security.py:111` `plain_redirect_path`; `server.py:163` | `test_security_phone.Auth.test_redirect_path_never_becomes_a_foreign_host` | done |
| Static pages come from an allowlist; a URL never reaches the filesystem | `roadmap/http/static.py:51` `lookup`; `server.py:86-98` `_static` | `test_static.test_traversal_and_odd_paths_are_404`, `test_static.test_unlisted_extension_is_404` | done |
| CSRF token only in index.html `<meta name="csrf">`; the phone page gets an empty one | `static.py:55-62` `render`; `server.py:146-172` (phone token "") | `test_static.test_slash_is_index_html_with_the_csrf_meta_tag`; `test_security_phone.ReadOnly.test_the_phone_page_carries_no_csrf_token_of_the_main_listener` | done |
| CSP on every reply, including errors, 421, 405, 401, 429, 503 and 302 | `security.py:15` `CSP`; `security.py:154-163` `security_headers`; `server.py:228-231` `_send` | `test_security.Headers.test_every_response_carries_the_security_headers`, `test_security_phone.Headers.test_every_phone_reply_carries_the_csp_and_security_headers`, `test_429_and_503_also_carry_the_headers` | done |
| CSP directives present, no unsafe-inline (legacy page excepted until WP8) | `security.py:15-22` | `test_security.Headers.test_csp_has_the_required_directives`; `test_static.test_legacy_page_gets_the_only_csp_exception` | done |
| X-Frame-Options DENY, nosniff, Referrer-Policy no-referrer, CORP same-origin | `security.py:154-163` | `test_security.Headers`; `test_security_phone.Headers` | done |
| Access log: method, path without query, status, ms, on both listeners | `server.py:43` (query split off), `server.py:220` | `test_logging.AccessLog.test_line_has_method_path_status_and_ms_but_no_query`; `test_security_redaction.ServerRedaction.test_phone_request_with_k_never_reaches_any_log` | done |
| server.log redacts Bearer, sk-ant and k= values; file mode 0600 | `roadmap/log.py:20-24` `_REDACTIONS`, `:44` `RedactingFilter`, `:17` `FILE_MODE` | `test_log.test_bearer_sk_ant_and_k_values_never_reach_the_file`, `test_log.test_server_log_and_rolled_files_are_mode_0600`, `test_security_redaction.ServerRedaction.test_server_log_file_is_owner_only_and_redacts_bearer_and_keys` | done |
| stderr log handler of `roadmap serve` redacts too | `roadmap/commands/serve.py:81-89` `_log_to_stderr` has no `RedactingFilter` | none | gap: the file is outside the WP13 list. Fix: add `log.RedactingFilter()` to the handler in `commands/serve.py`. No secret is logged on that path today (see the audit rows) |
| Keychain read as an argument list, no shell, held in memory | `roadmap/services/usage.py:54-75` `read_keychain_token` | `test_usage_collector.test_token_read_from_json` (argument list and no shell, lines 71-72) | done |
| Keychain endpoint: redirects refused | `usage.py:47-51` `_NoRedirect`; `usage.py:78-82` `_open` | `test_security_keychain.RedirectRefusal.test_a_redirect_is_refused_before_any_second_request` | done |
| Keychain and endpoint errors carry no token; unexpected errors give the type only | `usage.py:170-180` `collect`; `usage.py:85-110` `http_fetch` | `test_usage_collector.test_unexpected_error_hides_message_and_token`, `test_security_redaction.UsageSyncRedaction` (4 tests) | done |
| doctor never reads the keychain secret (no `-w`) | `roadmap/services/doctor.py:174-177` `check_keychain` | `test_doctor.test_security_check_never_shows_the_token_text` | done |
| Phone token file 0600, written atomically | `roadmap/services/tunnel.py:73-88` `_write_private` | `test_tunnel.StartTests.test_token_is_urlsafe_32_bytes_in_a_0600_file`, `test_pid_file_records_the_pid_and_is_private` | done |
| Token rotated on every start | `tunnel.py:68-70` `new_token`; `tunnel.py:185-195` `start` | `test_tunnel.StartTests.test_each_start_rotates_the_token` | done |
| Stop kills only a pid whose command is ssh to localhost.run | `tunnel.py:115-118` `is_our_tunnel`; `tunnel.py:217-232` `stop` | `test_tunnel.StopTests.test_stop_refuses_a_pid_that_is_not_our_ssh`, `test_stop_refuses_an_ssh_that_is_not_to_localhost_run`, `test_phone.PhoneCli.test_stop_of_a_foreign_pid_is_exit_4_and_kills_nothing` | done |
| Stop deletes token, pid file and phoneHost | `tunnel.py:217-238` | `test_tunnel.StopTests.test_stop_kills_our_tunnel_and_deletes_token_pid_and_host` | done |
| Tunnel URL from ssh output, never from a request | `tunnel.py:159-182` `find_tunnel_host`; `tunnel.py:185-215` | `test_tunnel.UrlParsingTests`, `test_tunnel.StartTests.test_start_runs_the_exact_ssh_command_and_saves_the_host` | done |
| Failed tunnel start kills its ssh and removes the token (exit 6) | `tunnel.py:199-213` | `test_tunnel.StartTests.test_no_url_in_time_kills_our_pid_and_removes_the_token`, `test_missing_ssh_is_exit_6_and_no_token_is_left` | done |
| Only `phone link` prints the token; status, start, stop and errors do not | `roadmap/commands/phone.py:29-56`; `tunnel.py:241-250` `status` | `test_security_redaction.PhoneStartRedaction.test_phone_start_stop_link_status_print_no_token_except_the_link`, `test_the_link_is_the_only_output_that_carries_the_token`, `test_a_refused_stop_prints_no_token` | done |
| No print or log call in roadmap/ names a secret (static audit) | whole `roadmap/` package, checked with `ast` | `test_security_redaction.StaticAudit.test_no_print_or_log_call_names_a_secret` | done |
| Keychain and usage sync print and log no secret, on success and on failure | `roadmap/services/usage.py`, `roadmap/commands/usage.py` | `test_security_redaction.UsageSyncRedaction` | done |
| Phone start and stop print and log no secret | `roadmap/services/tunnel.py`, `roadmap/commands/phone.py` | `test_security_redaction.PhoneStartRedaction` | done |
| HTTP server logs and redirects carry no `?k=` value | `server.py:43`, `:220`, `:163-166` | `test_security_redaction.ServerRedaction` (4 tests) | done |
| Subprocesses are argument lists, never `shell=True` | `tools/lint_py.py` (`shell=True` rule) | `make check` (lint_py) | done |
| `roadmap serve` starts the phone listener on 8766 | not wired: `commands/serve.py` (outside the WP13 list) only starts the main listener | none | gap: `make_phone_server()` exists and is tested. Fix: `serve` starts it in a second thread, with the same shutdown. Needs an edit to `commands/serve.py` |
| `roadmap open` opens the dashboard with the macOS `open` tool | `roadmap/commands/open.py` (`open_dashboard`, `handle`, `RUNNER`) | `test_phone.OpenCommand` (4 tests) | gap: not registered. The stub `open` is still added by `commands/serve.py`, and listing `open` in `cli.COMMAND_MODULES` would clash with it. Fix: remove the stub lines from `commands/serve.py`, then add `"open"` to `COMMAND_MODULES` |
| Exit codes: 4 for a busy or running state, 6 for an external failure, 3 for a missing token or host | `tunnel.py` raises `EXIT_CONFLICT`, `EXIT_EXTERNAL`, `EXIT_NOT_FOUND` | `test_phone.PhoneCli` | done |
| R1-1 Symlinks: `.claude`, `settings.local.json` and backup sources are refused when they are symlinks; the settings real path must stay in the project's `.claude`; reads use O_NOFOLLOW; a new file is 0600 unless the original regular file had another mode | `services/hooks_install.py` `settings_file`, `_read_raw`; `store/atomic.py` `write_json`, `_mode_of` (lstat); `store/backup.py` `backup_files` | `test_hooks_install.SettingsSafetyTests.test_symlinked_claude_folder_is_refused_and_the_target_is_untouched`; `test_store_backup.BackupSymlinkTests` | done (R1 finding 1) |
| R1-2 Tunnel host: only `*.localhost.run` and `*.lhr.life` are accepted; ssh runs with `StrictHostKeyChecking=yes` and a private `known_hosts`; the Host allowlist takes `phoneHost` only if it passes the same check | `services/tunnel.py` `valid_tunnel_host`, `find_tunnel_host`, `start` argv; `http/security.py` `phone_host_allowed` | `test_tunnel.HostAndPidSafetyTests.test_only_a_tunnel_domain_host_is_taken_from_the_banner`; `test_tunnel.StartTests.test_start_runs_the_exact_ssh_command_and_saves_the_host` | done (R1 finding 2) |
| R1-3 Pids: a pid is signalled only when `ps` still shows our ssh; a `ps` failure exits non-zero, keeps `tunnel.pid` and signals nothing | `services/tunnel.py` `ProcessListError`, `_kill_if_ours`, `stop`, `running_pid` | `test_tunnel.HostAndPidSafetyTests.test_start_never_signals_a_pid_that_is_not_our_ssh`, `test_stop_with_a_ps_failure_keeps_the_pid_file_and_signals_nothing` | done (R1 finding 3) |
| R1-4 Settings race: the file is re-read just before the replace; if its bytes changed the merge is repeated (3 attempts, then exit 4) | `services/hooks_install.py` `_edit` | `test_hooks_install.SettingsSafetyTests.test_settings_changed_by_claude_between_read_and_replace_are_kept` | done (R1 finding 4) |
| R1-5 Uninstall: a bootout failure other than not-loaded (3, 113) is an error and keeps the plist | `services/launchd.py` `uninstall` | `test_launchd_lifecycle.UninstallFailureTests.test_a_bootout_failure_keeps_the_plist` | done (R1 finding 5) |
| R1-6 Hook budget: each lock wait is at most 1 s (`lock.timeout_scope`); the state lock is not held while the project lock is awaited; a busy lock returns silently with exit 0 | `services/hooks.py` `_run_event`, `_close_some`, `HOOK_LOCK_TIMEOUT_S`; `store/lock.py` `timeout_scope` | `test_hooks.CommandTitleAndBusyLockTests.test_busy_project_lock_returns_quickly_and_registers_nothing` | done (R1 finding 6) |
| R1-7 Static map: each file is served from its realpath, and a symlink whose real file is outside `web/` is dropped | `http/static.py` `StaticFiles.__init__` | `test_static.SymlinksInWebRoot.test_a_symlink_whose_real_file_is_outside_web_is_not_served` | done (R1 finding 7) |
| R1-8 Hook titles (worker item): the cursor and agy titles never take text after a shell operator; the cursor output file is the last invocation's argument | `services/hooks.py` `_cursor_invocation`, `_before_operator` | `test_hooks.CommandTitleAndBusyLockTests.test_cursor_title_comes_from_the_invocation_in_a_chained_command`, `test_agy_title_stops_at_a_shell_operator` | done |

**Deviation from section 3.** The spec says `phone link` sets `phoneHost`. WP13 has `phone start` save it, from the
URL in ssh's output, because `phone start` is the step that knows the address. `phone link` only reads it.
`phone stop` clears it.

**Known gaps at WP13 close** (both are outside the WP13 file list and need a small edit by the head):
1. `roadmap serve` does not start the phone listener yet (row above).
2. `roadmap open` is not registered yet (row above).
3. The stderr log handler of `roadmap serve` has no redaction filter (row above). Nothing on that path logs a secret today.

Reviewer: __________   Date: __________   Result: __________
(The gate is not signed. WP14 starts only after a reviewer signs it.)
