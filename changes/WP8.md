# WP8: project view sections

- The project view (`#/p/<id>`) now shows Phases in the main column, and Running now, Needs you, Next up, Recent progress, Extras (only when the snapshot has spikes or real-hardware boards) and Legend (collapsed) in the side column. Narrow screens stack the side column below.
- Phase rows are buttons (Enter and Space toggle them). A running phase opens by itself outside the chosen Minimal view. Deferred lists are per phase.
- Running jobs show live timers. A timer is ticked once a second by text update only, so it does not re-render the section.
- Each section is a SectionHeader with a one-line summary. Minimal and Expanded set the default for the whole project. Phase and deferred-list choices persist per project in localStorage.
- Text contrast: tokens.css unchanged. Every text pair is at least 5.16:1 in light and 5.92:1 in dark. The lowest figures reported by tools/contrast.py (4.05 and 3.18) come from the `line` border token, which needs 3:1 and passes.
- Tests: tests/web/test_views.py renders the views in node from tests/fixtures/golden_snapshot.json (skipped without node); test_assets lists the new view modules.
- web/legacy.html is kept: roadmap/http/static.py, roadmap/http/security.py and tests/api/support.py still name it.
