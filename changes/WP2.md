# WP2: store

- `roadmap/store/paths.py`: config, state and log directories. `ROADMAP_HOME` redirects all three under one root; new directories are created 0700.
- `atomic.py`: `write_json` (temp file, fsync, replace, fsync dir, existing mode kept, new files 0600) and `read_json` (bad JSON gives `invalid_data`, exit 5).
- `lock.py`: `locked(dir)` takes flock on the data directory fd, the same mechanism as split_net `jobs.py`; 10 s timeout gives `locked`, exit 4.
- `config.py`: global `config.json` (schema v1) with add, list, get and remove. Ids and names are unique (names ignore case); the project path must exist.
- `schema.py` and `migrations.py`: per-kind schema versions, a missing version counts as 1, reads upgrade in memory and never write. A newer file gives a `newer_schema` error and is never overwritten. Autonomy v1 to v2 keeps only `limit`; `split_usage` returns the usage block.
- `backup.py`: timestamped copies under `backups/<project>/`, newest 14 kept.
