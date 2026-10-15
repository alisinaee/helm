# Job staffer-mv9h7ru0-30184aaf (staffer, done)

roadmap/http/routes.py:652 [MEDIUM] Info leak / ID enumeration oracle: `project_head` checks head ID existence (404) before origin authorization (403), allowing cross-origin/unauthorized callers to probe valid head IDs.
roadmap/http/routes.py:157 [MEDIUM] Info leak / Cache collision: `_snapshot_reply` issues identical strong ETags (`snap["rev"]`) for path-scrubbed phone responses and unscrubbed local responses, risking cache poisoning across listener boundaries.
roadmap/http/routes.py:90 [LOW] Input validation / RFC flaw: `etag_matches` strips `W/` from `If-None-Match` header values but not from the target `etag` argument, failing weak ETag matching despite docstring claims.
roadmap/http/routes.py:100 [LOW] Dead code: `content_etag` and `_without_volatile` are uncalled dead code; despite claiming support for head row `age` volatility in docstrings, no handler references them.
roadmap/http/routes.py:621 [LOW] Limits / Missing caching: `project_head` implements no ETag or 304 handling, forcing full disk read, fold, link resolution, and payload transfer on every poll.
roadmap/http/routes.py:552 [LOW] Input validation: `_head_query` error message on unknown/duplicate keys is outdated, claiming query accepts only `f`, `n`, and `full` while ignoring `offset` and `limit`.
roadmap/http/routes.py:552 [LOW] Input validation: `HEAD_QUERY_KEYS` permits mixing `n` with `offset`/`limit`; `n` is validated but silently ignored in paged mode instead of rejecting mutually exclusive parameters with 400.
roadmap/http/routes.py:545 [LOW] Limits: `HEAD_OFFSET_MAX` (1,000,000) is excessively high given ledger capacity (`MAX_ENTRIES` 5,000; `MAX_ID` 9,999), forcing full ledger fold/sort in memory before returning an empty slice.
roadmap/http/routes.py:586 [LOW] Info consistency: Paged queries enrich rows with `counts`, `suggest`, `linked`, `prog`, and `acc`, whereas unpaged queries (`head_row`) silently omit these fields.
roadmap/http/routes.py:233 [LOW] Cache consistency: `projects` ETag relies only on `loader.project_revision`; updating a project's display name in `config.json` does not bump the ETag, causing stale 304 responses.
roadmap/http/routes.py:550 [LOW] Input validation / Redundancy: `parse_qsl` is invoked up to three separate times per request across `_head_query`, `_head_is_paged`, and `_head_page_query`.
roadmap/http/routes.py:662 [LOW] Resource consumption: Requesting `full` alongside pagination causes `head.jsonl` to be read and parsed twice (once in `head_service.page` and once in `_records`).
roadmap/http/routes.py:165 [LOW] Cache headers: Responses altered by listener context (`_phone_public` scrubbed paths) omit `Vary` headers, risking client or proxy cache pollution across listeners.
roadmap/http/routes.py:548 [INFO] Path traversal: Head route parameters (`f`, `offset`, `limit`, `full`) and `pid` are strictly validated against allowlists, integer bounds, and regex, preventing path traversal.

[unrestricted] agy modified the working tree during this staffer run — verify the task asked for it. Delta (`git status --porcelain` entries that appeared or changed during the run):
  M docs/activity.jsonl
   M docs/head-text.jsonl
   M docs/head.jsonl
   M docs/jobs.json
   M roadmap/core/head.py
   M roadmap/core/snapshot.py
   M roadmap/services/headops.py
   M tests/unit/test_head_core.py
   M tests/unit/test_head_snapshot.py
   M tests/web/render_head.mjs
   M tests/web/test_head_view.py
   M web/js/views/head.js
  ?? docs/WAVE-PLAN.md
  ?? docs/reviews/agy-api-drift.md
  ?? docs/reviews/agy-api-drift.prompt.txt
  ?? docs/reviews/agy-readme-drift.md
  ?? docs/reviews/agy-readme-drift.prompt.txt
  ?? docs/reviews/agy-ux-agents.prompt.txt
  ?? docs/reviews/agy-ux-head.md
  ?? docs/reviews/agy-ux-head.prompt.txt
  ?? docs/reviews/agy-ux-overview.prompt.txt
  ?? docs/reviews/agy-ux-roadmap.prompt.txt
  ?? docs/reviews/agy-ux-settings.prompt.txt
  ?? docs/reviews/agy-ux-tokens.md
  ?? docs/reviews/agy-ux-tokens.prompt.txt
  ?? docs/reviews/agy-ux-work.md
  ?? docs/reviews/agy-ux-work.prompt.txt
  ?? docs/reviews/agy-ux-workflow.prompt.txt
  ?? tests/unit/test_r753_head_fixes.py
ACTION FOR THE CALLING AGENT: inspect these changes (`git diff`) before trusting this staffer. Rollback: `git checkout -- <path>` for tracked files, delete the new untracked ones.
