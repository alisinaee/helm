# WP5: HTTP and API v1

- `roadmap serve [--port N] [--no-usage-loop]` runs the dashboard on 127.0.0.1. A busy port exits 4 and names the
  process (read-only `lsof`). SIGINT and SIGTERM shut it down cleanly. With `--json` it prints the bound port first.
- API v1: health, meta, projects, project snapshot (strong ETag, 304), usage, and `POST /api/v1/usage/sync` (the only
  write). `/data.json` is kept as a deprecated alias. Contract in `docs/API.md` and `tests/api/schemas/`.
- Security: Host allowlist (421), CSRF token and same-site check (403), content type (415), 4 KB body limit (413),
  CSP and related headers on every response, static allowlist, and an access log with no query strings.
- `web/legacy.html` is the old page, with its sync call moved to the v1 route and the CSRF header. It has a temporary
  CSP exception that is removed with the file in WP8.
