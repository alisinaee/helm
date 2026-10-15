# Job staffer-mv9f9fs4-a1ad2b41 (staffer, done)

roadmap/core/secrets.py:25: `scrub` masks Stripe keys with prefixes `sk_test_` and `rk_live_` (only `sk_live_`/`rk_test_` tested).
roadmap/core/secrets.py:53: `_keyed_mask` preserves quoted task and job IDs like `key="H2"` or `token='P1.2'` without redacting.
roadmap/core/snapshot.py:288-292: `_newest_key` sorts entries with identical timestamps by numeric ID descending (e.g. H10 before H2).
roadmap/core/snapshot.py:291: `_newest_key` defaults timestamp to 0 when `ts` is None or unparseable.
roadmap/core/snapshot.py:343-345: `_head_view` recalculates `unhandled`, `doing`, `needs`, `doneUnacc` counts when byte trim drops rows.
roadmap/services/headops.py:147: `_guard_status` rejects agent attempting to reopen an entry with `status="open"` (`agent_refused`).
roadmap/services/headops.py:147: `_guard_status` rejects agent attempting to change status on an entry closed by a person (`_person_closed`).
roadmap/services/headops.py:163: `umbrella_only_asks` returns IDs when open asks are bound only to umbrella tasks (tests only check empty list).
roadmap/services/hooks.py:78: `AgentDetector.on_tool` extracts and normalizes valid `effort` when tool is `Task` rather than `Agent`.
roadmap/services/hooks.py:567: `_session_model` falls back to `_transcript_model` from `transcript_path` when `model` is absent in payload.
roadmap/services/hooks.py:569: `_session_model` returns `None` (defaulting job model to `"unknown"`) when model is not in `jobs.MODELS`.
roadmap/http/routes.py:96: `content_etag` strips nested `age_min` keys so changing `age_min` does not alter the ETag.
web/js/app.js:282-297: `loop()` while busy sets `followUp` and schedules next refresh at 0ms (only tested by regex, not executed).
web/js/views/head.js:87-89: `countsOf` clamps `unhandled`, `needs`, `doneUnacc` to painted rows when server counts are higher (untested).
web/js/views/agents.js:27: `engineLabel` returns bare `"opencode"` when `model="opencode"` and `engineModel` is empty/null.
web/js/views/agents.js:35: `effortLabel` prioritizes explicit `job.effort` over `engineModel` suffix (e.g. `medium` with `grok-4.7-xhigh`).
web/js/views/agents.js:134: `finishedHtml` displays parsed `effort` and `engineModel` chips for completed jobs in recently finished list.

[unrestricted] agy modified the working tree during this staffer run — verify the task asked for it. Delta (`git status --porcelain` entries that appeared or changed during the run):
   M tests/web/test_head_paging_view.py
   M web/css/head.css
   M web/js/views/head.js
  ?? docs/reviews/agy-375-roadmap.md
  ?? docs/reviews/cursor-sync-root.md
ACTION FOR THE CALLING AGENT: inspect these changes (`git diff`) before trusting this staffer. Rollback: `git checkout -- <path>` for tracked files, delete the new untracked ones.
