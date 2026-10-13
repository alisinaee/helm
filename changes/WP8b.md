# WP8b: minimal view and narrow layout polish

- Minimal view (the default for a project too) no longer opens any phase by itself, running or active. Expanded view opens every phase. A phase the person opens or closes keeps that choice. This supersedes the WP8 note that a running phase opens outside Minimal.
- Recently finished rows: the job title wraps to two lines with an ellipsis after that and the full text in the title attribute. Duration and tokens sit in fixed right-aligned columns. A leading "haiku: " or "opus: " is dropped from the text when the model chip shows that model.
- Narrow layout (under 640 px), checked in the browser pane at 375, 768 and 1280:
  - The usage band stacks: Week and 5 hours full width, then the status message and the Sync now button. No cut-off text.
  - Phases: Items and Tokens left move under each title, and the percent stays right-aligned. The column header is hidden on narrow.
  - Task rows: title on the first line, model chip below, tokens right-aligned.
  - KPI tiles: two per row. No horizontal overflow at 375, 768 or 1280.
- Desktop side column (360 px): Needs you task rows use the stacked layout. The check chip and thinking level are left out there. The seven-column row overflowed the page at 1280.
- tools/ui_smoke.py: its "375" screenshot is really about 500 px wide, because headless `chrome --window-size` cannot go below roughly 500 px. Narrow layouts are verified in the browser pane at 375 px.
- Tests: tests/web/test_views.py checks that no phase opens in Minimal, that Expanded shows task rows, and that the finished-title helper strips only the matching model prefix.
