# roadmap-board HTTP API (v1)

The server listens on `127.0.0.1` only. It is started by `roadmap serve` (or by the launchd service, which runs the
same command). The default port is 8780; `roadmap serve --port N` picks another one, and `roadmap open --port N`
opens that port for one call.

- Every `/api/v1/*` reply is JSON, UTF-8.
- The contract is this file plus the schemas in `tests/api/schemas/*.json`. The tests start a real server and check
  each route's reply against those schemas.
- Within v1, only new fields are added. Existing camelCase keys (such as `tokensK` and `weeklyPercent`) stay as they
  are. New keys are snake_case.

The examples below are real replies from a server with one registered project (`demo-app`, a fresh `docs/` folder
made by `roadmap project init`), with the usage numbers set by `roadmap usage push`. Long values are cut short and
marked `...`.

## Routes

| Method | Path | Reply |
|---|---|---|
| GET | `/api/v1/health` | `{ok, version, server_time}` |
| GET | `/api/v1/meta` | versions, schema versions, poll intervals |
| GET | `/api/v1/projects` | `{projects: [summary, ...]}` |
| GET | `/api/v1/projects/{id}/snapshot` | the project snapshot. `ETag`; `304` on a matching `If-None-Match` |
| GET | `/api/v1/projects/{id}/notes` | the project's research notes: `{notes: [{name, title, size, lines}]}` (read only) |
| GET | `/api/v1/projects/{id}/notes/{name}` | one research note as plain text, UTF-8 (read only) |
| GET | `/api/v1/usage` | the stored plan usage |
| POST | `/api/v1/usage/sync` | reads the plan usage now, then returns the `/api/v1/usage` object |
| POST | `/api/v1/cmd` | runs one command-registry op: body `{op, args, project?}`, reply `{ok, data, activity, undo}` (see below) |
| GET | `/data.json` | **deprecated** alias of the first registered project's snapshot. Removed in 2.0 |
| GET | `/`, `/<file>` | the pages under `web/` (not JSON; see [Pages](#pages)) |

Any other path under `/api/v1/` gives `404 not_found`. A path that matches but has the wrong method gives
`405 method_not_allowed` with an `Allow` header.

### GET /api/v1/health

```json
{"ok": true, "version": "0.1.0", "server_time": "2026-10-13T18:08:50+03:30"}
```

`server_time` is local time with its offset, to the second. Use it to check the clock; the snapshot ETag ignores it.

### GET /api/v1/meta

```json
{
  "version": "0.1.0",
  "api_version": "v1",
  "snapshot_schema_version": 1,
  "schema_versions": {"config": 1, "autonomy": 2, "tasks": 1, "jobs": 1, "roadmap_config": 1, "usage": 1, "hooks": 1},
  "poll_intervals_s": {"snapshot": 2, "usage": 30, "hidden_tab": 30},
  "usage_interval_s": 120
}
```

`usage_interval_s` is the config's `usage.intervalS`. `schema_versions` is what this build writes for each data file
kind (see [ARCHITECTURE.md](ARCHITECTURE.md#data-files-schema-versions-and-migrations)).

### GET /api/v1/projects

```json
{"projects": [
  {"id": "demo-app", "name": "Demo App", "progress": 0.0, "tasks_left": 0, "running": 0,
   "need_user": 0, "errors_count": 0, "stale": false}
]}
```

| Field | Meaning |
|---|---|
| `id`, `name` | from the registry |
| `progress` | a fraction from 0 to 1 for the whole project. Deferred tasks are not counted |
| `tasks_left` | tasks that are `todo` or `partial` |
| `running` | jobs in `running` state |
| `need_user` | open tasks (`todo` or `partial`) whose `needsUser` flag is true |
| `errors_count` | the length of the snapshot's `errors` |
| `stale` | true when `tasks.json` is missing or cannot be read |

A project whose folder or `tasks.json` is missing still appears, with `stale: true`. Projects are listed in the order
they were added.

### GET /api/v1/projects/{id}/snapshot

`{id}` is a registered project id: lowercase letters, digits and dashes, up to 40 characters. An unknown id gives
`404` with `not_found`.

```json
{
  "server_time": "2026-10-13T18:08:50+03:30",
  "errors": [],
  "jobs": [],
  "project": {"id": "demo-app", "title": "demo-app"},
  "schemaVersion": 1,
  "tasks_updated": "2026-10-13",
  "summary": {"tasks_total": 1, "tasks_left": 1, "tokens_left_k": 20, "running_count": 0,
              "need_user": 0, "jobs_tokens_k": 42.5, "jobs_with_tokens": 1, "...": "..."},
  "overall": {"project": {"done": 0, "partial": 0, "todo": 1, "total": 1, "progress": 0.0}, "...": "..."},
  "phases": [{"id": "P1", "name": "Engine", "status": "todo", "...": "..."}],
  "tasks": [{"id": "P1.1", "phase": "P1", "title": "Example task", "status": "todo", "...": "..."}],
  "spikes": {"...": "..."},
  "rh": {"...": "..."},
  "next": [],
  "log": []
}
```

The snapshot is the dashboard's data, in the shape the original server produced (`build()`), plus `project` and
`schemaVersion`. Since WP20 it also has these keys, empty when the project lacks the files behind them:
`issues` (open and doing issues), `questions` (open questions), `comments` (the newest 3 per target, keyed by target),
`budget` (limits, spend and percent of limit per total, phase, model and task; `{}` without `budget.json`),
`blocked` (task ids with an open blocker issue), `needsYou` (needs-you tasks and open blocking questions), `agents`
(`running` jobs with `parent` and `role`, `groups` of child job ids by parent, and `roots`), `control` (`{}` for now),
`queue` (the start queue) and `activity` (the newest 15 log lines). The `summary` also carries the mirrored `autonomy` block. Problems with a single file never fail
the request: they are listed in `errors`, as `{"file": "<name>", "error": "<ExceptionType>: <reason>"}`, for example
`{"file": "tasks.json", "error": "FileNotFoundError: file not found"}`. A missing `tasks.json` is listed there too,
and the project's `stale` flag is set.

Since WP27 the snapshot also has `meters`, computed from the limit rows and the usage ledger (`services/limits.py`,
`services/ledger.py`). `limits` lists each row that applies to the project: `id` (L3, AUTO or BUD), `scope`
(global or project), `window` (day, week or total), `kind` (pct, tok or acct), `used`, `limit`, `state` (ok, warn,
block or unknown), `est` (true for a project's share estimate, shown with "≈"), `paceAt` (the local time the pace of
the last two hours reaches the limit, or null) and `src` (config, limits, autonomy or budget). `today` holds `pts` (the
account's measured points today), `tokK` (the project's tracked thousands of tokens today) and `estPts` (its estimate).
`week` holds `pct` (the weekly account percent), `tokK` and `estPts` for seven days. Unknown values are null. Each `limits` item also has `action` (block or warn, the row's own action;
read-through rows from autonomy.json and budget.json give theirs, default block). A snapshot without these keys is
unchanged.

Since WP33b the snapshot also has `rules`: the list of rules from the project's `docs/rules.txt`, each `{id, scope,
kind, value, text}` (`value` is the number for a budget rule, else null). At most 60 rules; a line that is not a valid
rule, or whose text is over 160 characters, is skipped. A missing or unreadable file gives `[]`. Without the key the
snapshot is unchanged.

Since WP47 the snapshot also has `workflow`, always present (empty lists for a project with no jobs or tasks).
`spans` holds the newest 200 jobs in start order, each as `[id, task, model, role, parent, startEpoch, endEpoch,
status, tokensK]`: epochs are whole seconds, `endEpoch` is null while the job runs, `role` and `parent` are null
when unset. Jobs whose last moment (end, or start while running) is more than 7 days old are dropped. `edges.after`
is `[from, to]` for each task's `after` list (from is the task waited for, to the waiting task; only ids that are
tasks in tasks.json). `edges.block` is `[issueId, taskId]` for each open blocker issue and its tasks.

`ETag` is a strong tag: the first 32 hex characters of a SHA-256 over the snapshot content with `server_time` left
out, in quotes, for example `"c8f6148f5af0d6c7135ea34e7b0bf70e"`. Send it back as `If-None-Match`. When nothing has
changed the reply is `304` with no body, and the `ETag` header again. A running job's duration moves with the
clock, so the tag changes while a job runs.

`ETag` and `Cache-Control: no-cache` are sent on every snapshot reply, so a browser or proxy always revalidates.

### GET /api/v1/projects/{id}/notes and /notes/{name}

Read-only access to the research notes that `roadmap research` writes under the project's data folder
(`research/`, see `roadmap research list`). Only files named `NN-slug.md` (two digits, then lowercase letters, digits
and dashes) are listed or read; `INDEX.md` and every other name are not. Symlinks are never followed.

- The list reply is `{notes: [{name, title, size, lines}]}`. `title` is the first `# ` heading (or null), `size` is in
  bytes, and `lines` is null for a note over the size cap.
- The note reply is the file's bytes as `text/plain; charset=utf-8`. The client must show it as plain text, not as
  markup.
- A name that does not match the pattern gives `400 invalid_input`. A missing note, a non-file or a symlink gives
  `404 not_found`. A note over 64 KB gives `413 too_large`. An unregistered project gives `404 not_found`.

### GET /api/v1/usage

```json
{"weeklyPercent": 61, "fiveHourPercent": 13,
 "weeklyResetsAt": "2026-10-16T07:59:00+00:00", "fiveHourResetsAt": "2026-10-13T18:00:00+00:00",
 "updated": "2026-10-13T18:08:26+03:30", "source": "manual push", "lastError": null,
 "ageS": 24, "stale": false}
```

| Field | Meaning |
|---|---|
| `weeklyPercent`, `fiveHourPercent` | whole percentages of the weekly and five-hour limits. `null` when nothing is stored yet |
| `weeklyResetsAt`, `fiveHourResetsAt` | when each window resets, as ISO 8601 with an offset, or `null` |
| `updated` | when the last good reading was stored |
| `source` | `"Anthropic usage endpoint"` for a sync, `"manual push"` for `usage push` |
| `lastError` | the reason the newest read failed, or `null`. The good numbers stay when a read fails |
| `ageS` | seconds since `updated`, or `null` |
| `stale` | true when `ageS` is more than twice the configured interval (240 s by default), or when nothing was ever read |

Before any reading, the reply has `weeklyPercent: null`, `updated: null`, `ageS: null` and `stale: true`.

### POST /api/v1/usage/sync

Reads the plan usage now: the keychain item, then one HTTPS request to `api.anthropic.com`. It stores the result and
mirrors it into each project's `autonomy.json` (see the README's [Plan usage](../README.md#plan-usage) section). On
success the reply is the same object as `GET /api/v1/usage`.

The request needs all of the write rules below, and the body may be empty or a JSON object:

```http
POST /api/v1/usage/sync HTTP/1.1
Host: 127.0.0.1:8780
Content-Type: application/json
Sec-Fetch-Site: same-origin
X-Roadmap-CSRF: <the token from the page's <meta name="csrf">>
Content-Length: 0
```

Failure to read gives `502` with code `usage_unavailable`. The message is the plain reason, for example
`keychain item not found, sign in to Claude Code first`, `keychain access denied or failed (exit 36)`, or
`usage endpoint answered HTTP 401`. The token is never in a message.

### POST /api/v1/cmd

The single write path for the GUI (WP21 registry, WP23 ops). Body: JSON, at most 4 KB, `{"op": "<name>", "args": {...}, "project": "<id>"}`.
`project` is optional and defaults to the first registered project. The reply is `{ok, data, activity, undo}`: the
activity id (for example `A812`) and whether `POST /api/v1/cmd {"op":"undo","args":{"activity":"A812"}}` can reverse it.

Ops: `task.status` (args `id`, `status`, optional `note`, `tokensK`), `task.start`, `task.stop`, `task.cap` (`id`,
`value`), `subtask.toggle` (`addr`, `done`), `plan.move` (`id`, `before` or `after`), `phase.approve` (`phase`),
`question.answer` (`id`, `value`), `comment.add` (`on`, `text`, `by`), `issue.new`, `issue.close` (`id`),
`budget.set` (`scope`, `key`, `value`), `limit.set` (`pct` 1 to 100, or the WP27 row form `scope`, `window`, `kind`,
`value`, `action` and optional `id`), `limit.rm` (`id`: L3, AUTO or BUD), `control.stop` (`task`?), `control.resume`,
`control.override` (`hours` 1 to 4), `rules.add` (`scope`, `kind`, `text`, `value`?), `rules.rm` (`id`),
`rules.sync` (`dryRun`?), `undo` (`activity`).

Errors, in the order checked: `403 forbidden` (CSRF, origin, or not allowed on this listener), `413` (body over
4 KB), `415` (not JSON), `404 unknown_op`, `422 invalid_args` (`error.problems` lists the first problem), `429
rate_limited` (more than 10 ops per second in this process), `409` (conflict or agent refused), `404 not_found`.

Agent guard: ops that loosen control (`control.resume`, `control.override`, `budget.set`, `task.cap`, `limit.set`,
`limit.rm`, `rules.*`, `phase.approve`) are refused from an agent shell, with `409 agent_refused`. A browser (`gui`) call is not an
agent call and is not refused for that reason.

Phone listener: `POST /api/v1/cmd` is `403` unless config `phoneWrites` is `true`. With it, only `question.answer`,
`comment.add`, `task.status`, `control.stop` and `undo` run, and the phone's own csrf value (from `GET /api/v1/meta`
on the phone, cookie-authenticated) is required. A resume, a limit change or an undo that would resume is refused.

### GET /data.json (deprecated)

Returns the snapshot of the first registered project, exactly as `/api/v1/projects/{id}/snapshot` does, with the same
`ETag` and `304` behaviour. Its headers add:

```http
Deprecation: true
Link: </api/v1/projects/demo-app/snapshot>; rel="successor-version"
```

With no registered project it gives `404` with `not_found`. Use the v1 snapshot route in new code. `/data.json` is
kept until 2.0, when it is removed.

## Errors

Every error body is one object:

```json
{"error": {"code": "not_found", "message": "no project with id 'nosuch'"}}
```

`message` is short and plain, and never contains a secret. Clients should branch on `code`.

| Status | Code | When |
|---|---|---|
| 400 | `invalid_input` | a bad `Content-Length`, a chunked body, or a body that is not JSON (for the sync route) |
| 403 | `forbidden` | a write without a valid CSRF token, or one that is not same-origin |
| 404 | `not_found` | an unknown route, page or project id |
| 405 | `method_not_allowed` | the wrong method. The `Allow` header names the right ones |
| 413 | `too_large` | a write body over 4096 bytes |
| 415 | `unsupported_media_type` | a write without `Content-Type: application/json` |
| 421 | `misdirected_request` | the `Host` header is not `127.0.0.1:<port>` or `localhost:<port>` |
| 500 | `internal`, or a data code such as `newer_schema` | an unexpected error, or a data file this build cannot read |
| 502 | `usage_unavailable` | the usage read failed (keychain or endpoint). The message gives the plain reason |

Example, a foreign `Host` header:

```http
HTTP/1.1 421 Misdirected Request

{"error": {"code": "misdirected_request", "message": "this server answers only on 127.0.0.1 or localhost"}}
```

A project file that is broken does not produce any of these: the reply is `200` with an `errors` entry.

## Write rules

`POST /api/v1/usage/sync` and `POST /api/v1/cmd` are the only routes that change anything. Their checks run in this order,
and the first failure stops the request before any work is done:

1. `Host` is allowed (421 otherwise).
2. The route and method exist (404 or 405).
3. `Sec-Fetch-Site` is `same-origin`, or `Origin` is this server's origin (`http://127.0.0.1:<port>` or
   `http://localhost:<port>`), and `X-Roadmap-CSRF` equals the server's token for this process (403 otherwise).
   The token is 32 random bytes, generated when the server starts, and is compared in constant time. The page reads
   it from `<meta name="csrf" content="...">`.
4. `Content-Type` is `application/json` (415).
5. The body is at most 4096 bytes (413).
6. The body, when it has any content, is a JSON object (400).

A request with neither `Sec-Fetch-Site` nor `Origin` is refused. A cross-site `Sec-Fetch-Site` is refused.

Job writes are not HTTP routes on purpose. Jobs are recorded by the CLI and the hooks, so the server has one write
route to protect.

## Headers on every reply

```http
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'none'
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
Referrer-Policy: no-referrer
Cross-Origin-Resource-Policy: same-origin
Cache-Control: no-cache
```

Plus `Content-Type: application/json; charset=utf-8` on JSON replies, `ETag` on snapshots, and `Allow` on `405`.

**Exception (temporary):** `/legacy.html`, the old single-file page, keeps `'unsafe-inline'` for scripts and styles so it
still runs. It is removed with the file in WP8. No other reply gets that exception.

## Pages

`/` serves `web/index.html`. `/<file>` serves the files listed in an allowlist that is built when the server starts:
the files under `web/` with a known extension (`.html`, `.css`, `.js`, `.json`, `.svg`, `.png`, `.jpg`, `.ico`,
`.woff2`, `.txt`). URL paths are never turned into file paths. `..`, percent-encoded dots, double slashes and names
that are not in the list all give `404`. Pages are served with the same security headers as the JSON.

## Access log

One line per request goes to stderr and to `server.log`:

```
2026-10-13 18:08:50,780 roadmap.http.access INFO GET /api/v1/usage 200 0ms
```

The line has the method, the path, the status and the time in milliseconds. The query string is never written, so a
`?k=...` value does not reach the log. Log lines pass through a redaction filter that also removes `Bearer ...`,
`sk-ant-...` and `k=...` values.
