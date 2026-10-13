# WP3: core

- `roadmap/core/`: pure functions with no I/O and no project imports. `mdtables` (table rows, sections, status), `parsers` (tasks, jobs, autonomy: each returns `(data, errors)` and never raises), `extras` (registry for spikes, testing and roadmap, configured by `roadmap.config.json` "extras"), `snapshot.build_snapshot(files, config, now)`, `format` (tokens, percent, duration, count).
- The snapshot equals the old `server.py` `build()` output for the split-net fixture. Extra keys: `project`, `schemaVersion`. `server_time` is still present.
- Differences from the old server, only when a file is bad or missing: `errors[].file` is the bare file name (no `docs/` prefix). A bad `jobs.json` now adds an errors entry (it used to be silent). A missing `jobs.json` stays silent. `autonomy.json` that fails to parse adds an errors entry.
- Fixtures: `tests/fixtures/splitnet/` (copies of split-net's `docs/` data files plus `roadmap.config.json`), `tests/fixtures/golden_snapshot.json` (old server output with `server_time` removed and `now` pinned to 2026-10-13T12:00Z), `tests/fixtures/format_cases.json`.
