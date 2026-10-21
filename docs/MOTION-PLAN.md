# Motion and loading plan

The person's words: make the open/close animations of the panel and the buttons smoother, and add a loading state to
the buttons that need one.

## Contract between the two workers

- **Motion tokens and all new motion/loading CSS live in ONE new file `web/css/motion.css`**, linked LAST in
  `web/index.html` (after every other stylesheet) so it overrides earlier rules without editing them. Other CSS files
  are being edited by another worker (shell.css, components.css, toolbar.css): do not touch them.
- **Loading state = the attribute `aria-busy="true"` on the button** (plus `disabled` while the request runs). The CSS worker
  draws the spinner from that attribute, the JS worker only sets/removes the attribute. Button width must not jump:
  the label stays (dimmed), the spinner sits inside via `::before`/`::after`.

## CSS worker (files: `web/css/motion.css` NEW, `web/index.html` one link line, `tests/web/test_shell.py` SHELL_FILES entry)

Motion tokens in `:root` of motion.css: `--ease-out: cubic-bezier(.22,1,.36,1)`, `--ease-in-out: cubic-bezier(.65,0,.35,1)`,
`--t-quick: 140ms`, `--t-med: 260ms`, `--t-slow: 380ms`.

1. **Side panel** (`.side`, `[data-panel="open|closed"]`, the scrim/backdrop on narrow screens): open and close slide
   with `--t-med` and `--ease-out`, fade opacity and `visibility` with it (closed = not focusable, not hit-testable,
   `visibility` switched at the end of the close), the scrim fades. On wide screens, if the panel pushes the layout
   (grid column), animate `grid-template-columns` instead of jumping. Read shell.css to see how it works today.
2. **Nav rail collapse/expand**: width and label fade animate smoothly (no text wrapping jump while narrowing: labels
   `overflow: hidden; white-space: nowrap` during the transition).
3. **Menus, popovers, dropdowns** (`.tk-menu-list`, toolbar filter popover, help/shortcut sheet, toasts): fade + 6px
   translate + slight scale in, reverse out, `--t-quick`.
4. **Buttons**: hover/active/focus feedback with `--t-quick` (background, border-color, color, transform: `scale(.98)` on
   `:active`), no layout shift. Theme change: `background-color, color, border-color` transition `--t-med` on body, panels
   and buttons (not on every element).
5. **Loading**: `.btn[aria-busy="true"]` (also `.btn-primary`, `.btn-small`, `.seg button`): `pointer-events: none`,
   label opacity .55, a 14px spinner (border 2px, `currentColor`, top border transparent, `animation: spin .7s linear
   infinite`) centred before the label without changing the button's width/height (reserve the space only while
   busy via `position: absolute` spinner + `min-width: max-content`). Also a quieter `.chip[aria-busy="true"]` and
   `.theme-switch[aria-busy="true"]`. Spinner colour follows the button text colour so it works in all 6 looks.
6. **`prefers-reduced-motion: reduce`**: all durations 0.01ms, transforms none, spinner replaced by a static
   three-dot "..." (`::after { content: "…" }`) so loading is still visible.
7. Keep motion.css small (<= 6 KB), no raw hex, tokens only. Add `motion.css` to `SHELL_FILES` in
   `tests/web/test_shell.py` so `test_index_links_every_shell_stylesheet` passes. Add `tests/web/test_motion.py`
   (stdlib, reads files as text): motion.css is linked last in index.html, defines the 3 durations and 2 easings,
   contains `[aria-busy="true"]` and a `prefers-reduced-motion` block.

## JS worker (files: `web/js/busy.js` NEW, `web/js/views/tokens_history.js`, `web/js/views/git.js`, `web/js/views/rules.js`,
`web/js/views/limits_v2.js`, `web/js/cmd.js`, `web/js/app.js`, `tests/web/test_busy.py` NEW)

1. `busy.js` (ES module, no DOM at import): `setBusy(el, on)` sets/removes `aria-busy` and `disabled` (remembers if it was
   disabled before); `withBusy(el, promise)` sets busy, awaits the promise, ALWAYS clears busy in `finally`, returns the
   promise result and rethrows errors; both are safe when `el` is null or not in the DOM any more.
2. Find every user-triggered async request (`postJson(`, `fetch(`, the usage "Update"/sync button and "Enter usage",
   account Refresh/Connect/Disconnect/Log in/Remove/Add, git actions, rules save/sync, limits save, command palette
   actions) and make the pressed button show loading while the request runs:
   - views that already keep a busy flag in their state (e.g. `acct.busy` + `acct.busyId` in tokens_history.js) render
     `aria-busy="true"` on THE pressed button (and keep `disabled` on the others), not a different label;
     keep the existing "Refreshing…" text for Refresh.
   - views without such state use `withBusy(event target button, promise)`.
   Only buttons that wait on the server need it; instant UI toggles (theme, density, panel) do not.
3. A busy button never double-submits (the existing guards stay).
4. `tests/web/test_busy.py` (stdlib; node cannot run here): checks `busy.js` exports `setBusy`/`withBusy`, that
   `withBusy` has a `finally`, and that tokens_history.js emits `aria-busy="true"` for the busy button.
5. Verify every edited JS file with `cp file <scratchpad>/x.mjs && node --check <scratchpad>/x.mjs`.

## Rules for both workers

- Edit only your own files. Never rewrite whole existing files, never revert uncommitted changes already in the tree
  (`web/js/app.js`, `web/js/views/topbar.js`, `web/css/shell.css` hold other people's edits).
- Do not commit. Do not run the service, `usage sync` or `hooks install`. Do not click buttons in the browser that change data.
- Node render tests cannot run here (Node 26 flag problem); report such failures separately.
- Done when the python tests you added and `python3 -m unittest tests.web.test_shell tests.web.test_assets
  tests.web.test_themes` show no new failures (known: Node flag errors and `test_flow_css_holds_the_overview_inbox_and_activity_styles`).
