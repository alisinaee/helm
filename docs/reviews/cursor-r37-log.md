Read-only review of the logging routes and core log. I'll locate the handlers and the log services, then list only real issues with file, line, and fix.

Routes sit in `routes.py`. Log service path missed the glob, so I'll open the handlers and the log module next.

The debug log and `server.log` still store secrets that `roadmap/core/secrets.py` already treats as sensitive. Five issues:

1. **`roadmap/log.py:30`** `redact()` is case-sensitive `Bearer` plus `sk-ant-`, `k=`, `token=`, `ghp_`, `sk-proj-` only. `bearer`, `github_pat_`, `gho_`/`ghu_`/`ghs_`/`ghr_`, `token:` / `password=` / `api-key:`, JWTs, Slack `xox*-`, `AKIA`, PEM, and Google/Stripe keys are kept. `ui.console` / `ui.error` / `ui.mark` are WARN, ERROR, or marks, so they are returned by `GET /api/v1/log/report` (`roadmap/log.py:568`). The same `redact()` is all `server.log` gets (`roadmap/log.py:61`). A malformed request line is also logged with its raw target (`roadmap/http/server.py:343`, via `BaseHTTPRequestHandler.send_error`). **Fix:** copy the bearer, vendor, and `name[=:]value` patterns from `roadmap/core/secrets.py:16` into `redact()` (this module cannot import it). Re-apply in `roadmap/commands/logs.py:116` so already-stored lines are masked on print.

2. **`roadmap/log.py:123`** Denied keys are substrings, so `x-api-key`, `private_key`, `credentials`, and `pwd` are stored. `POST /api/v1/log` forwards any `data` object (`roadmap/http/routes.py:358`). **Fix:** drop keys matching `api[-_]?key`, `private[-_]?key`, `credential`, `pwd`. For `src=ui`, keep only the known fields (`kind`, `status`, `phase`, `model`, `effort`, `method`, `path`, `status`, `ms`, `form`, `stack`, `at`, `view`, `target`, `project`, `hook`, `decision`).

3. **`roadmap/log.py:173`** `route` and `ref` never go through `_scrub`. `_HOME_PATH` (`roadmap/log.py:126`) stops at a space, so `/Users/John Doe/secret` becomes `~ Doe/secret`. `/private`, `/tmp`, `/var`, and `/etc` stay. `_strip_query` (`roadmap/log.py:227`) removes `?` and leaves `#fragment`, so a fragment token is stored and copied into the report. **Fix:** strip `#` the same way as `?`, replace the real home prefix, and scrub those filesystem roots without collapsing `/api/...` or `#/` routes.

4. **`roadmap/log.py:61`** `RedactingFilter` does not scrub paths. `roadmap/http/server.py:131` writes the absolute `phone.token` path, and `roadmap/services/ledger.py:104` writes the ledger path, both with `/Users/<name>/...`. **Fix:** run the same home-path scrub in the filter before the line is written.

5. **`roadmap/http/server.py:259`** `core.exc` logs the concrete path and `str(exc)[:200]` cut before redaction. `core.guard` does the same with the path (`roadmap/http/routes.py:179`). Both are WARN/ERROR, so they show up in the copied report. `core.api` already uses `route_template`. **Fix:** log `route_template(path)` and redact the exception text before the 200-character cut.

