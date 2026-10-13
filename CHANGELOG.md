# Changelog

All notable changes to roadmap-board are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [SemVer](https://semver.org/).
Each work package writes a fragment in `changes/WPn.md`; the fragments are merged here at release time.

## [Unreleased]

### Added

- **CLI skeleton** (WP1): the `roadmap` command with `--json` envelopes (`{"ok", "data" | "error"}`), fixed exit
  codes (0, 1, 2, 3, 4, 5, 6, 10), and `bin/roadmap` as a shim that follows its own symlinks. `version` works.
- **Store** (WP2): `ROADMAP_HOME` redirects every path. Atomic JSON writes (temp file, `fsync`, replace, directory
  `fsync`, original mode kept). Directory locks with a 10 second timeout (exit 4). Global `config.json` with
  project registry. Per-file `schemaVersion`, migrations (autonomy v1 to v2) and refusal of newer files. Backups
  that keep the newest 14.
- **Core** (WP3): pure parsers, snapshot and format functions for tasks, jobs, autonomy and the optional extras
  (`spikes`, `testing`, `roadmap`). The split-net fixture reproduces the old server's output exactly.
- **Jobs and hooks** (WP4): `roadmap job start|done|fail|list|prune`, with `--tokens K` and a note. The job registry
  is each project's `jobs.json`. Hook driver with detectors `agent`, `agy` and `cursor`, chosen per project by
  `hookDetectors`. `roadmap hook` never fails and prints nothing.
- **Usage** (WP6): `roadmap usage show|sync|push`. Global `usage.json`, mirrored into each project's
  `autonomy.json` (`usage` block). Background loop: 120 s, then 600 s after 3 failures in a row.
- **HTTP and API v1** (WP5): `roadmap serve [--port N] [--no-usage-loop]` on `127.0.0.1`. Routes for health, meta,
  project list, project snapshot (strong `ETag`, `304`), usage, and `POST /api/v1/usage/sync`. Deprecated
  `/data.json` alias.
- **Web shell** (WP7): native ES modules, no build step. Plan-usage band, six KPI tiles, Home with project cards,
  project frame, Minimal and Expanded toggle, dark and light themes, keyboard shortcuts. Each view renders in its
  own try/catch.
- **Projects and hook install** (WP10): `roadmap project init|add|list|show|remove|check|migrate` and
  `roadmap backup`. `roadmap hooks install|uninstall|status`, which merges three entries into the project's
  `.claude/settings.local.json`. Idempotent, backs up before a change, and `--replace-legacy` removes only the old
  `jobs_auto.py` entries.
- **Service and doctor** (WP11): `roadmap service install|uninstall|start|stop|restart|status|logs [-f]` with a
  launchd agent in the Aqua session. `roadmap doctor` prints `ok|warn|fail` and a fix for each check; exit 10 when
  a check fails. Log rotation (1 MB x 5, mode 0600) with a redaction filter.
- **Documentation and docs check** (WP12): README, architecture, contributing guide, API reference, security draft,
  and `tools/check_docs.py`, which runs every documented `roadmap` command against a temporary home.

### Changed

- The server runs on `127.0.0.1` only, and its access log writes the path without the query string.
- Project settings live in each project's `docs/roadmap.config.json`, not in the code. The extras are configured
  there.
- Launchd logs are trimmed above 5 MB when the service starts.

### Security

- The access log no longer writes the query string, so a `?k=` value cannot reach a log (the old server logged the
  full path).
- Every reply carries a Content-Security-Policy with no inline script or style, `X-Frame-Options: DENY`, `nosniff`,
  `Referrer-Policy: no-referrer` and `Cross-Origin-Resource-Policy: same-origin`.
- Requests with a foreign `Host` get `421`, which blocks DNS rebinding.
- The one write route needs a per-process CSRF token, a same-origin `Sec-Fetch-Site` or `Origin`, a JSON content type
  and a body of at most 4096 bytes.
- The keychain token is read with `security` as an argument list, held in memory, and sent only to
  `api.anthropic.com` over HTTPS. Redirects are refused.
- Data files and folders are private (0600 and 0700). Writes are atomic and locked.

### Deprecated

- `GET /data.json` is an alias of the first project's snapshot, and it sends `Deprecation: true`. It is removed in
  2.0. Use `GET /api/v1/projects/{id}/snapshot`.

### Not built yet

- `roadmap open` and the `roadmap phone` commands (WP13).
- Phone listener and tunnel (WP13).
- Full page sections: phases, tasks, running, needs you, next up, recent, extras and legend (WP8). Until then the old
  page is served at `/legacy.html`.
- Chrome smoke test `make check-ui` (WP9).
