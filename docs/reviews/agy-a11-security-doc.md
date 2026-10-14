# Job staffer-mv7ne2ny-63ceb17d (staffer, done)

| requirement | citation OK? | problem (moved line, missing test, wrong file) |
|---|---|---|
| Bind 127.0.0.1 only, both listeners | No | moved line (`roadmap/http/server.py:268` points at `_raw_target`; `PhoneServer.__init__` is at line 337) |
| Main listener: Host must be 127.0.0.1 or localhost on its port, else 421 | No | moved line (`server.py:77-84` points at token helpers; `App.handle` is at lines 92-99) |
| Phone listener: loopback names, plus the saved tunnel host only | No | moved line (`server.py:120-127` points at `read_phone_token`, `configured_tunnel_host` is at lines 135-141; `server.py:146-148` points at `configured_phone_port`, Host check in `PhoneApp.handle` is at lines 176-177) |
| Write route is POST only; other methods get 405 with Allow | No | moved line (`roadmap/http/routes.py:202-210` points into `cmd`; `match` is at lines 349-359) |
| Phone listener is read-only (no write route reachable) | No | moved line (`server.py:149-151` points at docstring; GET-only check is at lines 182-184) |
| Write needs Sec-Fetch-Site same-origin, or an Origin of this server | No | moved line (`routes.py:104-108` points at `_now_iso`; `_write_guard` is at lines 110-118) |
| CSRF header equal to the per-process token (32 random bytes) | No | moved line (`security.py:73-87` shifted; `write_request_allowed` is at lines 69-84) |
| CSRF comparison is constant time | No | moved line (`security.py:87` points at `cookie_value` docstring; `safe_equal` call is at line 83) |
| Write needs Content-Type application/json, else 415 | No | moved line (`routes.py:104-115` points at `_now_iso` and origin checks; Content-Type check is at lines 115-118) |
| Write body at most 4096 bytes, 413 before anything runs | No | moved line (`security.py:14` points at import, `MAX_BODY_BYTES` is at line 16; `routes.py:160-162` points at `project_snapshot`, `read_body` call in `usage_sync` is at line 171) |
| Phone listener: no token file gives 503 | No | moved line (`server.py:153-154` points at docstring; token check in `PhoneApp.handle` is at lines 185-187) |
| Phone token file readable by others is not used | No | moved line (`server.py:101-117` points at `_static`; `read_phone_token` is at lines 116-132) |
| Wrong or missing token gives 401 | No | moved line (`server.py:174-176` and `:169-172` point at Host check and helpers; `_refuse` is at lines 212-214, auth checks at lines 191-210) |
| `?k=` accepted once, then 302 without `k` and with the cookie | No | moved line (`server.py:159-166` points at `PhoneApp.__init__`; `?k=` check and redirect is at lines 196-205) |
| Cookie is HMAC(token, "cookie"), never the token | No | moved line (`security.py:90` and `:96-101`: `cookie_value` is at line 86; `phone_cookie_header` is at lines 92-95) |
| Cookie flags HttpOnly, Secure, SameSite=Strict, Path=/, 7 days | No | moved line (`security.py:96-101` points at `cookie_from`; `phone_cookie_header` is at lines 92-95) |
| The raw token is not accepted as a cookie; rotation invalidates cookies | No | moved line (`server.py:169` points at `page_token`; cookie check is at lines 206-207) |
| Token and cookie comparisons are constant time | No | moved line (`server.py:161`, `:169` point at `__init__` and `page_token`; comparisons are at lines 199, 207) |
| 10 failed attempts per minute per process, then 429 | No | moved line (`security.py:116-152`: `FailureLimiter` is at lines 112-148; `server.py:155-157` points at class header, rate limit check is at lines 188-190) |
| Redirect target never leaves the server (no `//host`, never from Host) | No | moved line (`security.py:111` points at blank line, `plain_redirect_path` is at line 107; `server.py:163` points at `csrf_token`, redirect is at line 201) |
| Static pages come from an allowlist; a URL never reaches the filesystem | No | moved line (`roadmap/http/static.py:51` points at `__init__`, `lookup` is at line 56; `server.py:86-98` points at `op_allowed`/`sync`/`handle`, `_static` is at lines 101-113) |
| CSRF token only in index.html `<meta name="csrf">`; the phone page gets an empty one | No | moved line (`static.py:55-62` points at `paths` and `lookup`, `render` is at lines 60-71; `server.py:146-172` points at class header, empty token in `page_token` is at line 169) |
| CSP on every reply, including errors, 421, 405, 401, 429, 503 and 302 | No | moved line (`security.py:154-163` points at `PHONE_OPS`/`phone_csrf`, `security_headers` is at lines 185-193; `server.py:228-231` points at handlers, `_send` is at lines 274-288) |
| X-Frame-Options DENY, nosniff, Referrer-Policy no-referrer, CORP same-origin | No | moved line (`security.py:154-163` points at `PHONE_OPS`/`phone_csrf`; `security_headers` is at lines 185-193) |
| Access log: method, path without query, status, ms, on both listeners | No | moved line (`server.py:220` points at `phone_writes_enabled`; access log emission is at line 266) |
| stderr log handler of `roadmap serve` redacts too | No | moved line (`roadmap/commands/serve.py:81-89` points at thread worker; `_log_to_stderr` moved to lines 97-107 and now attaches `RedactingFilter`) |
| Phone token file 0600, written atomically | No | moved line (`roadmap/services/tunnel.py:73-88` points at runner globals; `_write_private` is at lines 84-97) |
| Token rotated on every start | No | moved line (`tunnel.py:68-70` points at `PS`, `new_token` is at lines 79-81; `tunnel.py:185-195` points at helpers, `start` is at lines 224-255) |
| Stop kills only a pid whose command is ssh to localhost.run | No | moved line (`tunnel.py:115-118` points at `read_pid`, `is_our_tunnel` is at lines 126-128; `tunnel.py:217-232` points at `_wait_for_host`, `stop` is at lines 258-287) |
| Stop deletes token, pid file and phoneHost | No | moved line (`tunnel.py:217-238` points at `_wait_for_host`; `stop` is at lines 258-287) |
| Tunnel URL from ssh output, never from a request | No | moved line (`tunnel.py:159-182` points at `valid_tunnel_host`/`_save_host`, `find_tunnel_host` is at lines 198-205; `tunnel.py:185-215` points at helpers, `start` is at lines 224-255) |
| Failed tunnel start kills its ssh and removes the token (exit 6) | No | moved line (`tunnel.py:199-213` points at `find_tunnel_host`; failure cleanup in `start` is at lines 248-252) |
| Only `phone link` prints the token; status, start, stop and errors do not | No | moved line (`tunnel.py:241-250` points into `start`; `status` is at lines 290-300) |
| HTTP server logs and redirects carry no `?k=` value | No | moved line (`server.py:220` points at `phone_writes_enabled`, access log is at line 266; `server.py:163-166` points at `csrf_token`, redirect is at lines 201-204) |
| `roadmap serve` starts the phone listener on 8766 | No | moved line (`commands/serve.py` now wires and starts phone server at lines 53-58, 80-88; gap is resolved) |

Total rows with a problem: 35  
Total OK rows: 29  
Total rows verified: 64

DONE

[unrestricted] agy modified the working tree during this staffer run — verify the task asked for it. Delta (`git status --porcelain` entries that appeared or changed during the run):
  M CHANGELOG.md
   M Makefile
   M README.md
   M docs/UI-CHECKLIST.md
  ?? changes/WP37.md
  ?? docs/RELEASE.md
  ?? tests/integration/
  ?? tests/unit/test_install_skills.py
  ?? tools/install-skills.py
ACTION FOR THE CALLING AGENT: inspect these changes (`git diff`) before trusting this staffer. Rollback: `git checkout -- <path>` for tracked files, delete the new untracked ones.
