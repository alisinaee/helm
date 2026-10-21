# Themes plan: 3 palettes x own light mode

Goal (the person's words): keep the two current looks, add a plain black one, make the 3 selectable, and give each its
own light mode.

## Model

Two independent settings replace the single `theme` value:

| Setting | Values | Stored in | HTML attribute on `<html>` |
|---|---|---|---|
| palette `ui.theme` | `obsidian` (Obsidian & Lime, the default), `classic` (the blue look, today's "Dark"/"Light"), `black` (new, plain black) | localStorage `ui` | `data-theme` |
| mode `ui.mode` | `dark` (default), `light`, `auto` (match system) | localStorage `ui` | `data-mode` (always `dark` or `light`: JS resolves `auto` with `matchMedia` and listens for changes) |

So 6 looks: obsidian/dark, obsidian/light, classic/dark, classic/light, black/dark, black/light.

Migration of the stored value (state.js `loadUi`): old `theme: "dark"` -> classic + dark; `"light"` -> classic + light;
`"auto"` -> classic + auto; `"obsidian"` -> obsidian + dark. New installs: obsidian + dark (same as today).

## CSS contract (worker CSS)

Selectors (no more `data-theme="dark"|"light"`, no `:not([data-theme="dark"])`):

- `:root` = classic dark (the existing default values, unchanged).
- `:root[data-mode="light"]` = classic light (today's `[data-theme="light"]` values, tokens and glass tokens).
- `:root[data-theme="obsidian"]` = obsidian dark (existing block, unchanged).
- `:root[data-theme="obsidian"][data-mode="light"]` = NEW obsidian light.
- `:root[data-theme="black"]` = NEW black dark. `:root[data-theme="black"][data-mode="light"]` = NEW black light.
- No-JS first paint fallback: keep one `@media (prefers-color-scheme: light) { :root:not([data-mode]) { ...classic light... } }`.
- Keep `color-scheme: dark|light` in every block.

New palettes (starting values; `tools/contrast.py` must pass: text 4.5:1, line/focus 3:1; adjust a value only if it fails):

Obsidian light (lime-olive on warm white):
`surface-0 #f2f4ea; surface-1 #ffffff; surface-2 #e8ebdd; line #6b7060; track #d9ddcc; text-1 #14170a; text-2 #4a4f3a;
text-3 #5a5f4a; accent #4d6600; on-accent #ffffff; focus #4d6600; success #0b7a55; warning #8a5a00; danger #b42318;
info #0b6a9e; unknown #5a5f4a; sel rgba(77,102,0,.14); drop rgba(77,102,0,.7)`. Glass tokens like classic light.
Mirror whatever other tokens the obsidian dark block sets (`--defer`, `--m-*`, shadows): light-mode values that pass.

Black dark (flat, monochrome, no glow):
`surface-0 #000000; surface-1 #0a0a0a; surface-2 #161616; line #6e6e6e; track #222222; text-1 #f2f2f2; text-2 #a0a0a0;
text-3 #8c8c8c; accent #ffffff; on-accent #000000; focus #ffffff;` status colours = classic dark values.
Glass: flat. `--glass-fill rgba(255,255,255,.04)`, no blur, `--field-a/b/c` transparent (no coloured blobs).

Black light:
`surface-0 #f5f5f5; surface-1 #ffffff; surface-2 #ebebeb; line #707070; track #dcdcdc; text-1 #0a0a0a; text-2 #4d4d4d;
text-3 #5c5c5c; accent #111111; on-accent #ffffff; focus #111111;` status colours = classic light values. Flat glass.

glass.css: its `:root[data-theme="obsidian"] ...` rules stay for both modes but must look right in light (no lime glow
on white: soften or switch off `body::before/::after` glow and the lime gradient button for `[data-mode="light"]`).
Add `black` rules that switch the glass/blob effects off (flat panels, 1px borders) in both modes.

`tools/contrast.py`: parse the new selectors and check all 6 looks (classic, obsidian, black x dark, light). Keep the
exit codes and output style. Update its docstring.

## JS contract (worker JS)

- `state.js`: `THEME_ORDER` becomes the palette list `["obsidian","classic","black"]`; add `MODE_ORDER = ["dark","light","auto"]`;
  `ui.mode` default `"dark"`; migration above in `loadUi`; `loadTheme()`/`saveTheme()` keep working for the palette;
  add `loadMode()`/`saveMode()`. `nextTheme` cycles palettes.
- `app.js`: `applyTheme(theme, mode)` sets `data-theme` and `data-mode` (resolve `auto` through
  `matchMedia("(prefers-color-scheme: light)")`, and re-apply on its `change` event while mode is `auto`). Init applies both.
  The topbar sun/moon button (`theme-toggle`) toggles the MODE (dark <-> light, from the resolved mode) and keeps the
  circular View Transition. Keep the other uncommitted edits in this file.
- `topbar.js`: `isLightNow(mode)` is based on the resolved mode; the labels/aria for the toggle stay; `themeLabel` gets the
  3 palette names. Keep the other uncommitted edits.
- `settings.js`: Appearance card gets two choice rows: **Theme** (Obsidian & Lime, Classic, Black) with action
  `set-theme`, and **Mode** (Dark, Light, Match system) with action `set-color-mode` (`set-mode` is the board/list view switch in app.js); both apply at once and persist.
- `log.js`: report `theme` and `mode` (attributes) in the debug snapshot.
- Update the tests that mention themes (`tests/web/test_admin.py`, `test_assets.py`, `test_head_states.py`) to the
  new model and add a small python test that checks the migration table and the selector contract in tokens.css
  (`tests/web/test_themes.py`, stdlib only, reads the files as text).

## Rules for both workers

- Edit only your own files (lists below). Use Edit on existing files, never rewrite a whole file, never revert changes
  that are already uncommitted in the tree (`web/js/app.js`, `web/js/views/topbar.js` and `web/css/shell.css` have
  other people's edits).
- Do not commit, do not run the service, `usage sync` or `hooks install`, and do not touch port 8780.
- Node render tests cannot run in this environment (Node 26 rejects `--experimental-default-type=module`). Verify JS with
  `node --check` on a `.mjs` copy in the scratchpad, and run the python tests that do run.
- UI rules: docs/UI-CHECKLIST.md (contrast 4.5:1, visible focus, no raw hex outside tokens.css, SVG icons only).

Files: CSS worker = `web/css/tokens.css`, `web/css/glass.css`, `tools/contrast.py`, `docs/ux/DESIGN-SYSTEM.md` (theme section only).
JS worker = `web/js/state.js`, `web/js/app.js`, `web/js/views/topbar.js`, `web/js/views/settings.js`, `web/js/log.js`,
`tests/web/test_admin.py`, `tests/web/test_assets.py`, `tests/web/test_head_states.py`, `tests/web/test_themes.py`.

Done when: `python3 tools/contrast.py` exits 0 for all 6 looks, the python tests above pass, `node --check` passes for every
edited JS file, and Settings > Appearance shows Theme and Mode rows.

## Added by the person (second message)

1. **Good, modern look** for all 3 themes in both modes: consistent radii and spacing from the tokens, 1px soft
   borders, subtle (not loud) depth, readable type scale, smooth hover/focus transitions that stop under
   `prefers-reduced-motion`. Black = flat and sharp; Obsidian = lime accent used sparingly; Classic = the calm blue.
2. **Responsive app.** Check 375, 768, 1024 and 1440 px: no horizontal page scroll, toolbars and button rows wrap.
3. **Button text must not run out of its button** when the screen is small. Rules for every `.btn` (and the
   `.chip`, segmented `.seg` buttons, `.theme-switch`, account action buttons, nav items):
   - `min-width: 0; max-width: 100%`; a label never overflows: either it wraps (`white-space: normal`,
     `overflow-wrap: anywhere`, `line-height: 1.25`, `height: auto; min-height: var(--h-control)`, centred) below
     640 px, or it truncates with `text-overflow: ellipsis` where a single line is required (full text in `title`).
   - Rows of buttons use `display: flex; flex-wrap: wrap; gap: var(--sp-1)` so they move to a second line instead of
     squeezing the labels.
   - Tap targets stay >= 36 px high on phone widths.

### Responsive worker (runs after the CSS worker, separate file list)
Files: `web/css/components.css`, `web/css/toolbar.css`, `web/css/shell.css` (it holds other people's uncommitted
edits: Edit small exact spots only), `web/css/tokens.css` (only the account-actions block `.tk-acct-*`).
Method: for each file, find fixed widths / `white-space: nowrap` on buttons and rows that break at 375 px and fix them
per the rules above. Verify by reading the CSS and, if a browser pane is available, resizing it (`resize_window`
presets mobile / tablet / desktop; reset to desktop at the end) and looking at Overview, Tokens > Account, Settings.

## Names and colour dots (third message)

UI labels (ids unchanged): `obsidian` = "Obsidian & Lime", `classic` (the blue palette) = **Midnight**, `black` = **Classic**.
Each Theme choice shows a colour dot (`.theme-sw`, tokens `--sw-obsidian/--sw-midnight/--sw-classic` in tokens.css).
