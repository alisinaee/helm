# WP6: usage

- `roadmap/services/usage.py`: the collector ported from `tools/roadmap-web/usage_collector.py` (token in memory only, https to api.anthropic.com, redirects refused, UsageError reasons), plus the global `usage.json` store (schema kind `usage`, state-dir lock), `sync_once`, mirror into each project's `autonomy.json` (keeps `limit` and other keys, v1 migrated, missing file skipped), `push`, `show` with `stale` (age > 2x interval), `run_loop` (wait before each attempt, 120 s, 600 s after 3 failures in a row, interval never below 30 s).
- `roadmap/commands/usage.py`: `usage show|sync|push`; sync failure exits 6 (`external`); push reads JSON on stdin (bad input exits 2).
- Tests: `tests/unit/test_usage_collector.py` (old collector tests, ported; the old route tests belong to WP5), `tests/unit/test_usage_store.py` (store, mirror, push, backoff schedule, lock under concurrent syncs, token never in output or logs, CLI).
- Not in this package: the server route `POST /api/v1/usage/sync` (WP5) and starting `run_loop` from the service (WP11).
