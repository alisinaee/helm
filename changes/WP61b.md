# WP61b: command palette hook-up

- `web/js/views/palette.js` (reviewed and fixed from the agy draft): Cmd+K / Ctrl+K (`isPaletteKey`) opens a modal `<dialog>` with a combobox input and a `listbox` of up to 10 results. Results search the open project's tasks, issues and questions (`searchPalette`, ranked id exact, id prefix, title prefix, substring). In command mode (`>`): `>stop`, `>resume` (project only), `>go <section>`, `>start <id>`, `>done <id>`. Commands go through `cmd.js` `run()`. Ops: `control.stop`, `control.resume`, `task.start`, `task.status` (all registered in `roadmap/services/commands.py` / `cmdops.py`, checked by a test). Arrows move, Enter runs, Esc closes, Tab stays in the input, focus returns to the opener. Rows are `.row-grid` (id | title ellipsis | kind right) and bound by delegation. Inline style removed.
- `web/js/keys.js`: the palette key is checked before the modifier early-return; `openPalette` hook; one help row.
- `web/js/app.js`: imports `openPalette` and passes the open project's snapshot (null in All projects).
- `web/css/palette.css` (new, about 1.5 KB, tokens only) and its `<link>` line in `web/index.html`.
- Tests: `tests/web/test_palette.py` (16 tests; node probe `tests/web/palette_probe.mjs` for key detection and ranking; op names checked against `commands.OPS`; CSP, token and track checks).
- Browser check on a temp home, server 127.0.0.1:8808, demo alpha: Cmd+K opens, `P1` lists P1.x, Enter opens the task route, `>stop` stops and `>resume` resumes, 500 px and 800 px light/dark checked, console clean.
