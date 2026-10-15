# Changelog

All notable changes to roadmap-board are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [SemVer](https://semver.org/).
Each work package writes a fragment in `changes/WPn.md`; the fragments are merged here at release time.

## [Unreleased]

## [1.0.0] - Unreleased

First full release of roadmap-board: a local dashboard and job tracker for projects built with Claude Code. It runs
on your Mac only, from one Python 3.9+ standard-library package, with a `roadmap` command for people and for AI agents.
The store, HTTP server and API v1, hooks, the agent control surface, the research workflow, usage limits, and the
interactive GUI shell are all in place. The two security reviews (R1 and R2) are fixed.


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
- **Task, plan, and status commands** (WP16): `task show|list|done|start|hold|set`, `plan import|export|template`,
  and top-level `status`, backed by pure planfmt grammar parsing and tasks service.
- **Research, agent guide, and skill drafts** (WP17): `roadmap research new|list|check` for research notes,
  `roadmap agent-guide`, and skill drafts for roadmap updates and planning.
- **Extended data layer and snapshot** (WP20): data stores and parsers for issues, questions, comments, budget,
  queue, and activity JSONL, plus subtask support in the tasks service.
- **Command layer and interactive CLI** (WP21): command runner with undo log, CLI modules for issue, subtask,
  ask, comment, inbox, budget, and undo, plus plan view and move commands.
- **Control and hook enforcement** (WP22): agent guard, budget and weekly limit controls, rules engine synced to
  CLAUDE.md, PreToolUse hook gating, and SessionStart inbox lines.
- **Command route and security** (WP23): `POST /api/v1/cmd` endpoint with CSRF and rate limiting, phone app
  write allowlist, and task token spending integration with budget.
- **Usage ledger and limit rows** (WP27): 14-day usage ledger (points and tokens), limit rows per day, week or total window (global and project) evaluated
  to ok, warn, block or unknown, and limit lines in status.
- **Interactive web shell** (WP28): modern app shell with navigation rail, command dispatcher with undo toasts,
  design tokens, keyboard shortcuts, and view routing.

- **Interactive GUI shell, all sections** (WP29 to WP35): right panel, Overview with inbox and activity (WP30), Work
  board, list and tree (WP31), Roadmap lanes with phase approval and an issues view (WP32), Tokens, Limits, Rules and
  Settings (WP33), Agents, Research notes and question undo (WP34), and the final responsive and visual pass (WP35).
  The sections are Overview, Inbox, Roadmap, Work, Issues, Agents, Tokens, Rules, Research, Activity and Settings.
- **Agent and CLI control surface** (WP21, WP22, WP33b): `ask`, `answer`, `inbox`, `issue`, `subtask`, `comment`,
  `budget`, `limit`, `rules`, `stop`, `resume`, `override`, `undo`, and `agent-guide` for AI agents.
- **Usage ledger and limit rows** and the **research workflow** (WP27, WP17): `roadmap research new|list|check`.
- **Demo fixtures** (fixtures/demo/alpha, beta and gamma), used by the tests and the UI smoke.
- **UI smoke** (WP9, WP35b): `make check-ui` drives the shell in Google Chrome and skips when Chrome is not installed.
- **Release tooling** (WP37): `tools/install-skills.py` installs the three skill drafts with a backup and a dry run;
  `make release-check` runs the full gate; `docs/RELEASE.md` is the release and cutover checklist.
- **Copy references** (R7.12): every row and section has a copy button that puts `rb:<project>/<kind>/<id>` and a one-line state on the clipboard. `roadmap ref <ref>` resolves a pasted ref in one read-only call; the worker and lead skills and `docs/AGENT-INTERFACE.md` describe it.

### Limits and defaults

- The roadmap service is a launchd agent, `com.roadmap-board.agent`, on `127.0.0.1:8780`, and `roadmap serve` defaults to port 8780.
- The start queue holds at most 50 entries (`queue.json`). The activity log keeps the newest 500 operations, and each one can be undone.
- A project holds at most 60 planner features, accepted only by the user. A task links at most 3 features.
- A project holds at most 200 open issues and 50 open questions.
- Session presence reads as `watching` under 60 s, `open` under 10 min, and `none` otherwise. Hook presence is written at most once per 30 s.
- `launchOnStart` opens a Terminal session at most once per 10 min, and only when no session is open.
- `roadmap service` actions: install, uninstall, start, stop, restart, status, logs.
- `roadmap project` actions: add, list, show, init, remove, check, migrate, new.
- `roadmap job` actions: start, done, fail, progress, list, prune.

### Changed

- The server runs on `127.0.0.1` only, and its access log writes the path without the query string.
- Project settings live in each project's `docs/roadmap.config.json`, not in the code. The extras are configured
  there.
- Launchd logs are trimmed above 5 MB when the service starts.
- Hook uninstall now cleans up five settings entries instead of three to cover PreToolUse and SessionStart (WP22).

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
- R1 security fixes (WP14): symlink rejection on `.claude` and settings with `O_NOFOLLOW`, tunnel host allowlisting
  with strict host key checking, validated ssh pid signaling, and safe static file path resolution.
- R2 hook enforcement hardening (WP22-fixes): project resolution confined to payload cwd, lock-synchronized limit
  recomputation, safe normalised state directory parsing, and restricted commands while blocked.

### Deprecated

- `GET /data.json` is an alias of the first project's snapshot, and it sends `Deprecation: true`. It is removed in
  2.0. Use `GET /api/v1/projects/{id}/snapshot`.

### Known gaps

- Phone access (`roadmap phone start|stop|link|status`) needs one step by you first: add the tunnel host key to the
  `known_hosts` file in the state folder, as described in [docs/SECURITY.md](docs/SECURITY.md). Until then `phone start`
  exits 6.
- `roadmap usage sync` reads an endpoint that Anthropic does not document, and it can change. `roadmap usage push`
  is the manual fallback.
- The old single-file page is still served at `/legacy.html`, with its own CSP exception, until the cutover removes it
  (see [docs/RELEASE.md](docs/RELEASE.md)).
- `make check-ui` skips when Google Chrome is not installed in `/Applications`.

