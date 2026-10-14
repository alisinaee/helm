# Security

**Status: draft, WP13 built.** This describes what roadmap-board protects, against whom, and how. Items marked *built*
are in the code and tested. The phone mode is built (WP13). No gap is open in the review checklist after WP22. The
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
  `roadmap ask "<question>"`. Stopping is never refused. A dashboard write is `gui` only with the browser proof
  described below; any other write on the main listener is `agent`, so it cannot loosen control.
- **Writes outside the project.** `rules sync` writes only between `<!-- roadmap:rules -->` and
  `<!-- /roadmap:rules -->` in the project's `CLAUDE.md`, makes a backup first, refuses broken markers and refuses a
  symlinked file.
- **Denials are logged** at most once a minute per project in `hooks.log`. Nothing the agent wrote is executed.

### Command route, rate limit and phone allowlist (WP23, built)

- `POST /api/v1/cmd` takes the same guard as usage sync (same-origin or Origin, `X-Roadmap-CSRF`, JSON, 4 KB),
  then runs only ops registered in the command registry. Unknown ops are 404, and invalid arguments 422.
- At most 10 ops per second per process; the 11th is `429` with `Retry-After`. The limiter counts ops that reach
  dispatch, so a rejected request does not spend it.
- **Browser proof (WP22).** A dashboard write is `gui` only when its request carries an `Origin` of this server and
  `Sec-Fetch-Site: same-origin` (`security.browser_proof`). The HTTP layer sets a thread-local flag for that one
  request (`services/agentguard.py` `browser_proven`), so the guard lets the person's click through. The process
  environment is never changed, so no other thread sees a cleared `CLAUDECODE`. Any other write on the main listener
  is labelled `agent` and cannot loosen control. Calls from `cli` and `phone` keep the guard. Phone calls never run a
  loosening op.
- **Activity source.** A CLI write inside an agent's shell is logged as `agent`, and as `cli` otherwise.
- **Undo.** `undo` claims a change under the folder lock before it runs the inverse, so two undos of one change
  cannot both run. A phone may undo only a change whose own activity line came from the phone.
- Phone listener: the route is `403` unless `phoneWrites` is true. Then the allowlist is `question.answer`,
  `comment.add`, `task.status`, `control.stop` and `undo`. The phone's csrf value is `HMAC(phone token, "csrf")`,
  served only on the cookie-authenticated phone `/api/v1/meta`; the main token never reaches the phone.
- Every accepted op writes one activity line: time, source, op and a summary of at most 60 characters with no free text.
  The activity log keeps the newest 500 lines. Rejected requests are not logged as writes.

## Known limits

- The usage endpoint and its beta header are not a documented public API. A change on Anthropic's side fails the read
  with a plain reason; it cannot widen what roadmap sends.
- Hook jobs are inferred from tool calls and output file names. A wrong guess shows a wrong job; it cannot change any
  project file other than the job registry (`jobs.json`) and the usage mirror.
- The keychain prompt is the operating system's. Choosing Always Allow lets the `security` tool read that item without
  asking again. Revoke it in Keychain Access if you no longer want the usage feature.
- A process running as you can read the same files. roadmap does not add a boundary between you and your own code.
- **The agent guard is a speed bump, not a security boundary (WP22).** A local process running as you can send the
  two browser headers itself, and it can read the CSRF token from `GET /`. That process is then taken for the person's
  browser. The guard catches accidents (an agent that does not know it should ask), not a deliberate local attacker.
- **A project whose own files cannot be read gets none of its own limit rows** (`autonomy.json` or `budget.json` with
  a newer schema or a corrupt value). The global day and week rows still apply, and the log says so once a minute.
  This is fail open for that project's own rows, by design (`unknown` never blocks).
- **Undo is last write wins.** Undoing an old change does not check that the object still holds the value the change
  set; a later change to the same object is overwritten.
- **Weekly readings.** A reading above 100 percent is kept (it is real over-allowance), up to 1000. A drop of less than
  10 points is treated as jitter and adds nothing; a larger drop is the weekly reset.
- **Ledger size.** The ledger keeps the current week whole. When a week does not fit in 4 KB, the oldest day's
  per-project tokens are merged into one `_other` entry: the total stays right, the per-project split does not.

## Reporting a problem

If you find a way to read the token, to make a write the user did not ask for, to reach the server from another host, or
to get a secret into a log or a reply, please report it to the maintainer privately, not in a public issue. Include the
version (`roadmap version`), the request or command, and what you saw. Do not include your token or your keychain
entry. If a secret has already leaked, rotate it in Claude Code first, then report.

---

## Review checklist (WP13/R1)

Audit of `roadmap/http` against section 3 of `docs/roadmap-board-architecture.md`, done in WP13. Each row names the
code that implements the rule, the test that proves it (`tests/api/test_security*.py` and the other test modules named
in the row), and the status: `done`, or `gap` with the reason. Line numbers were re-checked against the code in WP22;
the test names were checked against `tests/`. Paths in the R1 and R2 rows are under `roadmap/`.

| Requirement | Where implemented | Test name | Status |
|---|---|---|---|
| Bind 127.0.0.1 only, both listeners | `roadmap/http/server.py:24` `BIND_HOST`; `server.py:317` `RoadmapServer.server_bind`; `server.py:337` `PhoneServer.__init__` | `test_security.Loopback.test_main_listener_binds_127_0_0_1_only`, `test_phone_listener_binds_127_0_0_1_only` | done |
| Main listener: Host must be 127.0.0.1 or localhost on its port, else 421 | `roadmap/http/security.py:48` `host_allowed`; `roadmap/http/server.py:92` `App.handle` | `test_security.HostAllowlist.test_foreign_host_is_421_everywhere`, `test_rebinding_name_and_wrong_port_are_421` | done |
| Phone listener: loopback names, plus the saved tunnel host only | `roadmap/http/security.py:55` `phone_host_allowed`; `server.py:135` `configured_tunnel_host`; `server.py:176` `PhoneApp.handle` | `test_security_phone.HostRules.test_tunnel_host_is_accepted_only_when_configured`, `test_an_invalid_configured_tunnel_host_allows_nothing` | done |
| Write route is POST only; other methods get 405 with Allow | `roadmap/http/routes.py:362` `match` (405 with Allow when the method is wrong); `server.py:103` (static pages GET only) | `test_routes.test_read_routes_refuse_post_with_allow_header`, `test_security_phone.ReadOnly.test_post_is_405_even_with_the_cookie_and_the_write_headers` | done |
| Phone listener is read-only (no write route reachable) | `roadmap/http/server.py:182` `PhoneApp.handle` (GET only, before any route) | `test_security_phone.ReadOnly.test_post_without_any_token_is_still_405_not_401` | done |
| Write needs Sec-Fetch-Site same-origin, or an Origin of this server | `roadmap/http/security.py:70` `write_request_allowed`; `roadmap/http/routes.py:110` `_write_guard` | `test_security.WriteChecks.test_cross_site_is_403_even_with_the_token`, `test_foreign_origin_is_403`, `test_no_sec_fetch_site_and_no_origin_is_403` | done |
| CSRF header equal to the per-process token (32 random bytes) | `roadmap/http/security.py:34` `new_token`; `security.py:70` `write_request_allowed` | `test_security.WriteChecks.test_no_csrf_header_is_403`, `test_wrong_csrf_is_403` | done |
| CSRF comparison is constant time | `roadmap/http/security.py:39` `safe_equal` (`hmac.compare_digest`); `security.py:84` | `test_security.CsrfCompare.test_the_csrf_check_uses_hmac_compare_digest` | done |
| Write needs Content-Type application/json, else 415 | `roadmap/http/routes.py:115-118` `_write_guard` | `test_security.WriteChecks.test_wrong_content_type_is_415` | done |
| Write body at most 4096 bytes, 413 before anything runs | `roadmap/http/security.py:17` `MAX_BODY_BYTES`; `server.py:48` `Request.read_body`; `routes.py:171` `usage_sync`, `routes.py:191` `cmd` | `test_security.WriteChecks.test_body_over_4_kb_is_413_before_anything_runs` | done |
| Chunked request bodies refused | `roadmap/http/server.py:50-51` `Request.read_body` | `test_security.WriteChecks.test_chunked_body_is_refused_with_400` | done |
| Phone listener: no token file gives 503 | `roadmap/http/server.py:186-187` `PhoneApp.handle` | `test_security_phone.TokenFile.test_no_token_is_503_for_every_request`, `test_default_token_source_reads_phone_token_and_503_when_missing` | done |
| Phone token file readable by others is not used | `roadmap/http/server.py:116` `read_phone_token` (mode check) | `test_security_phone.TokenFile.test_a_token_file_readable_by_others_is_not_used` | done |
| Wrong or missing token gives 401 | `roadmap/http/server.py:212` `PhoneApp._refuse`; `server.py:191-210` (auth checks) | `test_security_phone.Auth.test_wrong_token_and_no_token_are_401` | done |
| `?k=` accepted once, then 302 without `k` and with the cookie | `roadmap/http/server.py:196-205` `PhoneApp.handle` | `test_security_phone.Auth.test_token_redirect_strips_k_keeps_other_params_and_sets_the_cookie`, `test_redirect_to_root_when_only_k_was_given` | done |
| Cookie is HMAC(token, "cookie"), never the token | `roadmap/http/security.py:107` `cookie_value`; `security.py:113` `phone_cookie_header` | `test_security_phone.Auth.test_cookie_value_is_hmac_of_cookie_keyed_with_the_token`, `test_the_raw_token_never_appears_in_the_cookie_or_the_location` | done |
| Cookie flags HttpOnly, Secure, SameSite=Strict, Path=/, 7 days | `roadmap/http/security.py:113` `phone_cookie_header` | `test_security_phone.Auth.test_token_redirect_strips_k_keeps_other_params_and_sets_the_cookie` | done |
| The raw token is not accepted as a cookie; rotation invalidates cookies | `roadmap/http/server.py:206-207` `PhoneApp.handle` | `test_security_phone.Auth.test_the_hmac_cookie_grants_access_and_the_raw_token_as_cookie_does_not`, `test_a_rotated_token_invalidates_old_cookies` | done |
| Token and cookie comparisons are constant time | `roadmap/http/security.py:39` `safe_equal`; `server.py:199`, `server.py:207` | `test_security_phone.ConstantTime.test_hmac_compare_digest_is_used_for_the_token_and_the_cookie`, `test_safe_equal_never_matches_an_empty_expected_value` | done |
| 10 failed attempts per minute per process, then 429 | `roadmap/http/security.py:133` `FailureLimiter`; `server.py:188-190` | `test_security_phone.RateLimit.test_ten_failures_in_a_minute_then_429_even_for_the_right_token`, `test_the_window_slides_and_access_comes_back_after_a_minute`, `test_nine_failures_do_not_block` | done |
| Redirect target never leaves the server (no `//host`, never from Host) | `roadmap/http/security.py:128` `plain_redirect_path`; `server.py:201` | `test_security_phone.Auth.test_redirect_path_never_becomes_a_foreign_host` | done |
| Static pages come from an allowlist; a URL never reaches the filesystem | `roadmap/http/static.py:56` `StaticFiles.lookup`; `server.py:101` `App._static` | `test_static.test_traversal_and_odd_paths_are_404`, `test_static.test_unlisted_extension_is_404` | done |
| CSRF token only in index.html `<meta name="csrf">`; the phone page gets an empty one | `roadmap/http/static.py:60` `render`; `server.py:167` `PhoneApp.page_token` (empty) | `test_static.test_slash_is_index_html_with_the_csrf_meta_tag`; `test_security_phone.ReadOnly.test_the_phone_page_carries_no_csrf_token_of_the_main_listener` | done |
| CSP on every reply, including errors, 421, 405, 401, 429, 503 and 302 | `roadmap/http/security.py:18` `CSP`; `security.py:206` `security_headers`; `server.py:274` `_Handler._send` | `test_security.Headers.test_every_response_carries_the_security_headers`, `test_security_phone.Headers.test_every_phone_reply_carries_the_csp_and_security_headers`, `test_429_and_503_also_carry_the_headers` | done |
| CSP directives present, no unsafe-inline (legacy page excepted until WP8) | `roadmap/http/security.py:18` `CSP`; `security.py:22` `CSP_LEGACY` | `test_security.Headers.test_csp_has_the_required_directives`; `test_static.test_legacy_page_gets_the_only_csp_exception` | done |
| X-Frame-Options DENY, nosniff, Referrer-Policy no-referrer, CORP same-origin | `roadmap/http/security.py:206` `security_headers` | `test_security.Headers`; `test_security_phone.Headers` | done |
| Access log: method, path without query, status, ms, on both listeners | `roadmap/http/server.py:42` (query split off in `Request`); `server.py:266` (access log line) | `test_logging.AccessLog.test_line_has_method_path_status_and_ms_but_no_query`; `test_security_redaction.ServerRedaction.test_phone_request_with_k_never_reaches_any_log` | done |
| server.log redacts Bearer, sk-ant and k= values; file mode 0600 | `roadmap/log.py:17` `FILE_MODE`; `log.py:20` `_REDACTIONS`; `log.py:44` `RedactingFilter` | `test_log.test_bearer_sk_ant_and_k_values_never_reach_the_file`, `test_log.test_server_log_and_rolled_files_are_mode_0600`, `test_security_redaction.ServerRedaction.test_server_log_file_is_owner_only_and_redacts_bearer_and_keys` | done |
| stderr log handler of `roadmap serve` redacts too | `roadmap/commands/serve.py:107` (`_log_to_stderr` adds `RedactingFilter`) | none | done (closed after WP13; checked in WP22) |
| Keychain read as an argument list, no shell, held in memory | `roadmap/services/usage.py:55` `read_keychain_token` | `test_usage_collector.test_token_read_from_json` (argument list and no shell, lines 71-72) | done |
| Keychain endpoint: redirects refused | `roadmap/services/usage.py:48` `_NoRedirect`; `usage.py:79` `_open` | `test_security_keychain.RedirectRefusal.test_a_redirect_is_refused_before_any_second_request` | done |
| Keychain and endpoint errors carry no token; unexpected errors give the type only | `roadmap/services/usage.py:171` `collect`; `usage.py:86` `http_fetch` | `test_usage_collector.test_unexpected_error_hides_message_and_token`, `test_security_redaction.UsageSyncRedaction` (4 tests) | done |
| doctor never reads the keychain secret (no `-w`) | `roadmap/services/doctor.py:191` `check_keychain` | `test_doctor.test_security_check_never_shows_the_token_text` | done |
| Phone token file 0600, written atomically | `roadmap/services/tunnel.py:84` `_write_private` | `test_tunnel.StartTests.test_token_is_urlsafe_32_bytes_in_a_0600_file`, `test_pid_file_records_the_pid_and_is_private` | done |
| Token rotated on every start | `roadmap/services/tunnel.py:79` `new_token`; `tunnel.py:224` `start` | `test_tunnel.StartTests.test_each_start_rotates_the_token` | done |
| Stop kills only a pid whose command is ssh to localhost.run | `roadmap/services/tunnel.py:126` `is_our_tunnel`; `tunnel.py:258` `stop` | `test_tunnel.StopTests.test_stop_refuses_a_pid_that_is_not_our_ssh`, `test_stop_refuses_an_ssh_that_is_not_to_localhost_run`, `test_phone.PhoneCli.test_stop_of_a_foreign_pid_is_exit_4_and_kills_nothing` | done |
| Stop deletes token, pid file and phoneHost | `roadmap/services/tunnel.py:258` `stop` | `test_tunnel.StopTests.test_stop_kills_our_tunnel_and_deletes_token_pid_and_host` | done |
| Tunnel URL from ssh output, never from a request | `roadmap/services/tunnel.py:198` `find_tunnel_host`; `tunnel.py:208` `_wait_for_host` | `test_tunnel.UrlParsingTests`, `test_tunnel.StartTests.test_start_runs_the_exact_ssh_command_and_saves_the_host` | done |
| Failed tunnel start kills its ssh and removes the token (exit 6) | `roadmap/services/tunnel.py:224` `start` (cleanup on failure) | `test_tunnel.StartTests.test_no_url_in_time_kills_our_pid_and_removes_the_token`, `test_missing_ssh_is_exit_6_and_no_token_is_left` | done |
| Only `phone link` prints the token; status, start, stop and errors do not | `roadmap/commands/phone.py:49` `handle_link`; `tunnel.py:290` `status` | `test_security_redaction.PhoneStartRedaction.test_phone_start_stop_link_status_print_no_token_except_the_link`, `test_the_link_is_the_only_output_that_carries_the_token`, `test_a_refused_stop_prints_no_token` | done |
| No print or log call in roadmap/ names a secret (static audit) | whole `roadmap/` package, checked with `ast` | `test_security_redaction.StaticAudit.test_no_print_or_log_call_names_a_secret` | done |
| Keychain and usage sync print and log no secret, on success and on failure | `roadmap/services/usage.py`, `roadmap/commands/usage.py` | `test_security_redaction.UsageSyncRedaction` | done |
| Phone start and stop print and log no secret | `roadmap/services/tunnel.py`, `roadmap/commands/phone.py` | `test_security_redaction.PhoneStartRedaction` | done |
| HTTP server logs and redirects carry no `?k=` value | `roadmap/http/server.py:42`, `server.py:266`, `server.py:201` | `test_security_redaction.ServerRedaction` (4 tests) | done |
| Subprocesses are argument lists, never `shell=True` | `tools/lint_py.py` (`shell=True` rule, lines 116-117) | `make check` (lint_py) | done |
| `roadmap serve` starts the phone listener on 8766 | `roadmap/commands/serve.py:56-61` (starts it unless `--no-phone`), `serve.py:82-86` (thread and shutdown) | none | done (closed after WP13; checked in WP22) |
| `roadmap open` opens the dashboard with the macOS `open` tool | `roadmap/commands/serve.py:31-32` registers `open` through `roadmap/commands/open.py` `register` (`:47`) and `handle` (`:55`) | `test_phone.OpenCommand` (4 tests) | done (registered through serve; checked in WP22) |
| Exit codes: 4 for a busy or running state, 6 for an external failure, 3 for a missing token or host | `tunnel.py` raises `EXIT_CONFLICT`, `EXIT_EXTERNAL`, `EXIT_NOT_FOUND` | `test_phone.PhoneCli` | done |
| R1-1 Symlinks: `.claude`, `settings.local.json` and backup sources are refused when they are symlinks; the settings real path must stay in the project's `.claude`; reads use O_NOFOLLOW; a new file is 0600 unless the original regular file had another mode | `services/hooks_install.py` `settings_file`, `_read_raw`; `store/atomic.py` `write_json`, `_mode_of` (lstat); `store/backup.py` `backup_files` | `test_hooks_install.SettingsSafetyTests.test_symlinked_claude_folder_is_refused_and_the_target_is_untouched`; `test_store_backup.BackupSymlinkTests` | done (R1 finding 1) |
| R1-2 Tunnel host: only `*.localhost.run` and `*.lhr.life` are accepted; ssh runs with `StrictHostKeyChecking=yes` and a private `known_hosts`; the Host allowlist takes `phoneHost` only if it passes the same check | `services/tunnel.py` `valid_tunnel_host`, `find_tunnel_host`, `start` argv; `http/security.py` `phone_host_allowed` | `test_tunnel.HostAndPidSafetyTests.test_only_a_tunnel_domain_host_is_taken_from_the_banner`; `test_tunnel.StartTests.test_start_runs_the_exact_ssh_command_and_saves_the_host` | done (R1 finding 2) |
| R1-3 Pids: a pid is signalled only when `ps` still shows our ssh; a `ps` failure exits non-zero, keeps `tunnel.pid` and signals nothing | `services/tunnel.py` `ProcessListError`, `_kill_if_ours`, `stop`, `running_pid` | `test_tunnel.HostAndPidSafetyTests.test_start_never_signals_a_pid_that_is_not_our_ssh`, `test_stop_with_a_ps_failure_keeps_the_pid_file_and_signals_nothing` | done (R1 finding 3) |
| R1-4 Settings race: the file is re-read just before the replace; if its bytes changed the merge is repeated (3 attempts, then exit 4) | `services/hooks_install.py` `_edit` | `test_hooks_install.SettingsSafetyTests.test_settings_changed_by_claude_between_read_and_replace_are_kept` | done (R1 finding 4) |
| R1-5 Uninstall: a bootout failure other than not-loaded (3, 113) is an error and keeps the plist | `services/launchd.py` `uninstall` | `test_launchd_lifecycle.UninstallFailureTests.test_a_bootout_failure_keeps_the_plist` | done (R1 finding 5) |
| R1-6 Hook budget: each lock wait is at most 1 s (`lock.timeout_scope`); the state lock is not held while the project lock is awaited; a busy lock returns silently with exit 0 | `services/hooks.py` `_run_event`, `_close_some`, `HOOK_LOCK_TIMEOUT_S`; `store/lock.py` `timeout_scope` | `test_hooks.CommandTitleAndBusyLockTests.test_busy_project_lock_returns_quickly_and_registers_nothing` | done (R1 finding 6) |
| R1-7 Static map: each file is served from its realpath, and a symlink whose real file is outside `web/` is dropped | `http/static.py` `StaticFiles.__init__` | `test_static.SymlinksInWebRoot.test_a_symlink_whose_real_file_is_outside_web_is_not_served` | done (R1 finding 7) |
| R1-8 Hook titles (worker item): the cursor and agy titles never take text after a shell operator; the cursor output file is the last invocation's argument | `services/hooks.py` `_cursor_invocation`, `_before_operator` | `test_hooks.CommandTitleAndBusyLockTests.test_cursor_title_comes_from_the_invocation_in_a_chained_command`, `test_agy_title_stops_at_a_shell_operator` | done |
| R2-1 Gate project: PreToolUse resolves the project from the payload cwd only; `ROADMAP_PROJECT` is never read by the gate | `services/hooks.py` `_project_quiet` (`jobs.resolve_project(None, {}, cwd)`) | `test_hook_enforce_r2.Finding1ProjectFromCwdOnly` (2 tests) | done (R2 finding 1) |
| R2-2 Stale limit block: a limit block is recomputed inside the 300 ms budget before a deny; a failed or late recompute fails open and drops the sentinel; a budget raise or clear and its control recompute share the data-folder lock | `services/hooks.py` `_refresh_limits`, `_drop_sentinel`; `services/control.py` `set_budget_limit`, `set_weekly_limit`; `services/budget.py` `set_limit_locked` | `test_hook_enforce_r2.Finding2StaleLimitAndOneLock` (4 tests) | done (R2 finding 2) |
| R2-3 Shim state folder: `bin/roadmap` strips and expands `ROADMAP_HOME` like `paths.state_dir()`; a relative or unnormalised root is left to Python | `bin/roadmap` | `test_hook_enforce_r2.Finding3ShimStateFolder` (3 tests) | done (R2 finding 3) |
| R2-4 Blocked allowlist: while stopped or blocked a Bash roadmap command runs only as `inbox`, `status`, `ask` or `rules show`; any non-empty `CLAUDECODE` is an agent; `hooks uninstall` is refused from an agent | `services/hooks.py` `ALLOWED_WHILE_BLOCKED`, `_pre_tool_use`; `services/agentguard.py` `is_agent`; `commands/hooks.py` `_uninstall` | `test_hook_enforce_r2.Finding4BlockedAllowlist` (5 tests); `test_agentguard` | done (R2 finding 4) |
| R2-5 Rules sync: the lines between the markers must all be the generated intro or `- R…` rules; the write re-reads CLAUDE.md under the data-folder lock and refuses if its bytes changed | `services/rules.py` `_generated_only`, `_splice`, `sync` | `test_hook_enforce_r2.Finding5RulesSync` (3 tests) | done (R2 finding 5) |
| R2-6 Budget loosen check: the current limit is read under the data-folder lock, so an agent cannot raise a limit a person set meanwhile | `services/control.py` `set_budget_limit` | `test_hook_enforce_r2.Finding6BudgetRaiseUnderLock` (2 tests) | done (R2 finding 6) |
| R2-7 Stop pickup: any truthy `stop_hook_active` means already active; the three-block cap is also kept per queued task set in the control state, so a new session id or a deleted pickup file does not reset it | `services/hooks.py` `_stop_pickup`, `_task_set_key`; `services/control.py` `record_pickup`, `pickup_record` | `test_hook_enforce.StopPickupTests` (new tests); `test_hook_enforce_r2.Finding7PickupCap` (2 tests) | done (R2 finding 7) |
| R2-8 No free text in logs or context: logs carry ids and detector names; job titles take a 60-character summary with secret-looking tokens replaced; SessionStart lines carry question and task ids, never question text or answers | `services/hooks.py` `_summary`, `_SECRET_RE`, `_start`; `services/control.py` `pending_lines` | `test_hook_enforce_r2.Finding8NoFreeTextInLogs` (3 tests), `SummaryTests` | done (R2 finding 8) |

**Deviation from section 3.** The spec says `phone link` sets `phoneHost`. WP13 has `phone start` save it, from the
URL in ssh's output, because `phone start` is the step that knows the address. `phone link` only reads it.
`phone stop` clears it.

**Gaps at WP13 close, all closed:** `roadmap serve` starts the phone listener, `roadmap open` is registered, and the
stderr log handler has the redaction filter. Each is checked in its row above (WP22).

Reviewer: __________   Date: __________   Result: __________
(The gate is not signed. WP14 starts only after a reviewer signs it.)
