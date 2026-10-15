# R7.16 Debug log for UI and core (spec)

Goal: while the person tests, record what matters so an agent can later run one cheap command and find the bug.

## 1. Event model

One JSON line per event:
`{ts, sid, src, lvl, ev, route, ref?, msg, data?}`
- ts: ISO local, seconds + ms. sid: 8 hex, new per page load (core: `core-<pid>`; hook: `hook`). src: `ui|core|hook`. lvl: `DEBUG|INFO|WARN|ERROR`. route: hash route or HTTP path (never the query). ref: `rb:project/kind/id` (R7.12). msg: short text.
- Caps: msg 300 chars, route 120, ref 120, ev 32, data 1 KB serialized (keys 20, strings 200, arrays 10). Longer values cut with `…`. Stacks: 12 frames, 1.5 KB.

Event names (closed list; unknown names refused):
- UI: `ui.load` (viewport, theme, dpr, ua short, version), `ui.route`, `ui.action` (data-action/data-kind name + ref), `ui.submit` (form id, whitelisted fields only), `ui.error` (message, file:line, stack), `ui.reject` (unhandled promise), `ui.csp` (violatedDirective, blockedURI host only), `ui.api` (method, path, status, ms; only failed or >800 ms), `ui.render` (view, ms; only >150 ms), `ui.console` (error/warn, first arg), `ui.resize`, `ui.theme`, `ui.mark`.
- Core: `core.api` (method, path, status, ms; INFO only for errors/slow >500 ms, otherwise DEBUG), `core.write` (op, args summary, result or error code), `core.guard` (refusal: csrf, origin, ctype, body_cap, rate, phone), `core.limit` (usage stop, budget), `core.exc` (type, msg, stack), `core.start`, `core.stop`.
- Hook: `hook.event` (hook name, job id, result), `hook.error`.

## 2. Storage

- File: `<state dir>/logs/debug.jsonl` (same dir as the service log), global, every line has `route`/`ref` carrying the project. Never in a repo; `roadmap logs` refuses a path inside a git work tree.
- Rotation: 5 MB x 3 (`debug.jsonl.1..3`), owner-only 0600, reuse `_OwnerOnlyRotatingHandler` from roadmap/log.py.
- Redaction: every line passes `log.redact()` plus: home path to `~`, no paths outside `~`, tokens/cookies/CSRF/Authorization dropped, no form values except whitelist (`kind`, `status`, `phase`, `model`, `effort`, lengths of text fields). Query strings never logged (same as access log). Clipboard text never logged.
- Phone: the phone listener writes core events (src core, route only) but never accepts UI events. Logs never leave the machine; no network sink.
- Separate from activity.jsonl (undo truth) and the service log (process output); `core.write` lines are a short mirror only.

## 3. UI to core transport

- `POST /api/v1/log`, body `{sid, events:[...]}`, max 50 events.
- Guard: same `_write_guard` (CSRF header + Sec-Fetch-Site/Origin + JSON type), own body cap 16 KB (`LOG_BODY_BYTES`), rate limit 20 req/min per sid and 600 events/min total (over: 429, one `core.guard` line per minute). Localhost listener only; phone listener answers 404. Server re-validates names, levels and caps; never trusts client lvl above WARN for unknown errors.
- Client `web/js/log.js`: ring buffer 200, flush every 5 s or at 20 events or on ERROR, via `fetch(..., {keepalive:true})` with the CSRF header on `pagehide`/`visibilitychange=hidden`. No sendBeacon (it cannot send the CSRF header). Never awaits in UI paths; all calls wrapped in try/catch; failures drop silently (no self-logging loop).
- Off switch: Settings > Logging, stored in localStorage, default ON on localhost, OFF and hidden on phone. Header shows a small "Logging on" chip when on. CSP unchanged: no inline script, no new origins.

## 4. Agent interface

- `roadmap logs`: last 20 WARN/ERROR lines, one line each: `hh:mm:ss src ev route ref msg`.
- Filters: `--since 10m|2h`, `--src ui|core|hook`, `--ev name`, `--ref rb:...`, `--session last|<sid>`, `--lvl`, `--n 50`, `--json` (raw lines).
- `roadmap logs summary`: counts by ev, top 5 errors (msg + count + last ts), sessions in range, marks.
- `roadmap logs marks`: each mark with 5 events before it.
- Every output <=15 lines and ends with `next:` hints (e.g. `next: roadmap logs --session last --ev ui.error --json`).
- Skill lines (roadmap-worker, roadmap-lead): "When the person says they hit a bug: run `roadmap logs --session last`, then `roadmap logs marks`." Add to docs/AGENT-INTERFACE.md and TOKEN-COST.md (default output ~300 tokens).

## 5. GUI

Settings > Logging: toggle, line "Saving to ~/…/logs/debug.jsonl", buttons Copy debug report (last 10 errors + last mark + viewport/theme/version + sid, as text, via R7.12 `copyRef` mechanism and fallback), Open log folder (localhost only, existing open route). Grid-aligned per UI-CHECKLIST.

## 6. Test session marks

A Mark button in the header (and key `m`): optional one-line note, writes `ui.mark` {route, ref of the focused/selected row, note} and flushes at once. Toast "Marked". The agent finds the moment with `roadmap logs marks`.

## 7. Breakdown (Haiku, in order, no file overlap)

1. Core writer: roadmap/log.py (`debug_event()`, caps, redaction, rotation), tests/test_debug_log.py.
2. Endpoint: roadmap/http/routes.py (`log_post`, route table), roadmap/http/security.py (`LOG_BODY_BYTES`, rate limiter), tests/test_log_route.py. Core emitters for `core.api/guard/exc/start/stop` in the same files plus roadmap/http/server.py.
3. Command: roadmap/commands/logs.py, roadmap/cli.py (register), tests/test_logs_cmd.py. Emitters in roadmap/services/commands.py (`core.write`) and roadmap/commands/hook.py (`hook.*`).
4. Client: web/js/log.js (new), hooks in web/js/app.js (error, rejection, csp, console, route, render, load), web/js/api.js (timings, failures), web/js/cmd.js (`ui.action`, `ui.submit`).
5. Settings UI: web/js/views/settings.js, header chip + Mark in web/index.html, web/css/components.css (budget <=600 B; total cap 72 KB, about 4.7 KB free).
6. Docs/skills: docs/AGENT-INTERFACE.md, docs/TOKEN-COST.md, docs/SECURITY.md, skills/ worker+lead lines, CHANGELOG.

Audits (agy, verified by head): A1 redaction and guard (no secrets, no query, phone refused, caps hold); A2 coverage (every listed ev emitted somewhere, no UI await on log paths, CSP clean).

## 8. Risks and questions

Risks: log flood from render/resize loops (rate limits + DEBUG off by default); personal text in errors (redaction + caps); a self-logging loop (log.js never logs its own failures); disk growth (20 MB total cap).

Questions for the person:
1. Global log file, or one per project?
2. Keep how long: rotation only, or also delete older than 7 days?
3. Mark button always visible, or only when logging is on?
4. Log DEBUG (every click) by default, or only WARN/ERROR plus actions?
5. Phone: no UI logs at all (proposed), or allow with the phone cookie?
