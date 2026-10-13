# roadmap-board HTTP API (v1)

The server runs on `127.0.0.1` only (`roadmap serve [--port N] [--no-usage-loop]`, default port from config, 8765).
All responses are JSON except the pages under `/`. The contract is this file plus `tests/api/schemas/*.json`.

## Routes

| Method | Path | Returns |
|---|---|---|
| GET | `/api/v1/health` | `{ok, version, server_time}` |
| GET | `/api/v1/meta` | `{version, api_version, snapshot_schema_version, schema_versions, poll_intervals_s, usage_interval_s}` |
| GET | `/api/v1/projects` | `{projects: [{id, name, progress, tasks_left, running, need_user, errors_count, stale}]}` |
| GET | `/api/v1/projects/{id}/snapshot` | the project snapshot (see below); `ETag`, and `304` on `If-None-Match` |
| GET | `/api/v1/usage` | `{weeklyPercent, fiveHourPercent, weeklyResetsAt, fiveHourResetsAt, updated, source, lastError, stale, ageS}` |
| POST | `/api/v1/usage/sync` | runs one usage read, then returns the `/api/v1/usage` object. The only write route |
| GET | `/data.json` | deprecated alias of the first project's snapshot (`Deprecation: true`); removed in 2.0 |
| GET | `/`, `/<file>` | pages from `web/` (see below) |

Field notes:
- `progress` in the project list is a fraction from 0 to 1 (whole project, deferred tasks excluded).
- `running` and `need_user` are counts. `errors_count` is the length of the snapshot's `errors`.
- `stale` in the project list is true when `tasks.json` is missing or unreadable.
- `progress`, `tasks_left` and the other numbers come straight from the snapshot.
- Within v1 fields are only added. Existing camelCase keys stay; new keys are snake_case.

## Snapshot

The v1 snapshot is the old `build()` shape plus `project: {id, title}` and `schemaVersion`. `server_time` is ISO 8601
with whole seconds. Problems with individual files are listed in `errors: [{file, error}]` and never fail the request.
A project that is not registered gives 404.

`ETag` is a strong hash of the snapshot content without `server_time`. A running job's duration moves with the clock,
so its ETag changes while that job runs.

## Errors

Every error body is `{"error": {"code", "message"}}`. The message is short and plain and never contains a secret.

| Status | Code | When |
|---|---|---|
| 400 | `invalid_input` | bad JSON body, bad `Content-Length`, chunked body |
| 403 | `forbidden` | write without the CSRF header, or from another site |
| 404 | `not_found` | unknown route, page, or project |
| 405 | `method_not_allowed` | wrong method (the `Allow` header says which) |
| 413 | `too_large` | write body over 4096 bytes |
| 415 | `unsupported_media_type` | write without `Content-Type: application/json` |
| 421 | `misdirected_request` | `Host` is not `127.0.0.1:<port>` or `localhost:<port>` |
| 500 | `internal` or a data code | unexpected error, or a data file this build cannot read (for example `newer_schema`) |
| 502 | `usage_unavailable` | the usage read failed (keychain or endpoint); the reason is plain text |

## Writes

`POST /api/v1/usage/sync` needs all of these:
- `X-Roadmap-CSRF` equal to the per-process token. The token is in `<meta name="csrf" content="...">` in every HTML page.
- `Sec-Fetch-Site: same-origin`, or an `Origin` equal to this server's origin. Anything else gives 403.
- `Content-Type: application/json`, and a body of at most 4096 bytes. The body may be empty or a JSON object.

Checks run in this order: Host, route and method, CSRF and origin, content type, size, then the work.

## Headers on every response

- `Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'none'`
- `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`,
  `Cross-Origin-Resource-Policy: same-origin`
- `Cache-Control: no-cache`

**Exception (temporary):** `/legacy.html` (the old page, served while `web/index.html` does not exist) gets
`'unsafe-inline'` for scripts and styles. It is removed with the page in WP8. No other page gets it.

## Pages

`/` serves `web/index.html`, or `web/legacy.html` while index.html does not exist. Only files under `web/` with a known
extension are served, from an allowlist built at startup. URL paths are never turned into file paths, so `..`, `%2e`,
double slashes and unlisted names all give 404. Page MIME types: `.html`, `.css`, `.js`, `.json`, `.svg`, `.png`, `.jpg`,
`.ico`, `.woff2`, `.txt`.

## Access log

One line per request on stderr: `<time> roadmap.http.access INFO <METHOD> <path> <status> <ms>ms`. The query string is
never logged. Requests with a query string, such as `?k=...`, are logged without it.
