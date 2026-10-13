# WP7: web shell

- `web/index.html` with the TopBar, usage band, KPI row and main section. Native ES modules, no build step, no
  external hosts. `web/js/app.js` polls snapshots every 2 s and usage every 30 s (30 s while the tab is hidden).
  Each view renders in its own try/catch; a failure shows that section's error and sets `data-render-error` on `#app`.
- Views: topbar (project switcher as a native select, Minimal/Expanded toggle, Auto/Dark/Light theme toggle, live
  badge), usage band (weekly and 5-hour meters, reset countdown, stale and old markers, Sync now), KPI row (six tiles),
  Home (project cards and Running now across projects), and the project frame (phases placeholder, running jobs).
- Theme: dark by default, light under `prefers-color-scheme` or the toggle (kept in localStorage, guarded).
  `web/css/tokens.css` is the only file with hex colours. `tools/contrast.py` checks 53 text and graphic pairs in
  both themes (text 4.5:1, borders, focus and meters 3:1).
- Keyboard: `[` and `]` collapse or expand all sections, `g` then `h` goes Home, `/` focuses the switcher.
- `tests/web/test_assets.py` (stdlib) checks that every referenced file and JS import exists, that markup has no
  inline script, `on*=` or `style=`, that every `var(--x)` is defined in tokens, that no hex colours appear outside
  tokens, that there are no external hosts, and that the contrast gate passes.
- `web/dev/tests.html` runs the shared format cases through `web/js/format.js` and reports PASS or FAIL.
