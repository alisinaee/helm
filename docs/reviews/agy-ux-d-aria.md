VERIFIED 15/20

# Accessibility Audit: Top Bar, Command Palette, and Settings

| file:line | issue | fix |
|---|---|---|
| web/js/views/topbar.js:51-52 | Project crumb panel toggle button lacks `aria-expanded` and `aria-controls` to announce open/closed panel state. | Add `aria-expanded="${open}"` and `aria-controls="panel"` reflecting current panel visibility. |
| web/js/views/topbar.js:68 | "Connecting" status pill lacks `role="status"` or live region, preventing screen readers from announcing connecting state. | Add `role="status"` to `<span class="pill is-wait">Connecting</span>`. |
| web/js/views/topbar.js:79 | Running/blocked agent status pill lacks `role="status"`, unlike the stopped state pill at line 72. | Add `role="status"` to `<span class="pill is-run|is-blocked">` so dynamic status updates are announced. |
| web/js/views/topbar.js:129 | Usage limits container `<div class="top-meters">` uses `aria-label` without a landmark or widget role, ignored by screen readers. | Add `role="region"` or `role="group"` alongside `aria-label="Usage limits"`. |
| web/js/views/topbar.js:133-141 | Connection status badge lacks `role="status"` and `aria-live="polite"`, so live/offline transitions are unannounced. | Add `role="status"` and `aria-live="polite"` to the connection indicator element. |
| web/js/views/topbar.js:156 | Side panel toggle button uses `aria-pressed` instead of `aria-expanded` for disclosing a panel. | Replace `aria-pressed` with `aria-expanded="${open}"` and add `aria-controls="panel"`. |
| web/js/views/topbar.js:164 | Command palette trigger button has `aria-haspopup="dialog"` but lacks `aria-expanded="false"` to indicate dialog closed state. | Add `aria-expanded="false"` to the button element. |
| web/js/views/palette.js:127 | `palette-status` live region is cleared when matches exist, omitting result count announcements for screen reader users. | Announce result count (e.g. `"${results.length} results available, use up/down arrows to navigate"`). |
| web/js/views/settings.js:40-42 | Mutually exclusive options (Theme, Density, Log) use `role="group"` and `aria-pressed` instead of radiogroup semantics. | Use `role="radiogroup"` on container and `role="radio"` with `aria-checked="true|false"` on options. |
| web/js/views/settings.js:40-46 | Choice button groups lack arrow key navigation (ArrowLeft/ArrowRight) between mutually exclusive options. | Add keydown handler supporting Arrow keys to cycle options per WAI-ARIA Radio Group pattern. |
| web/js/views/settings.js:50-54 | Keyboard shortcut list uses flat `<p>` elements without list semantics, impairing item-by-item navigation. | Render shortcuts in a semantic description list `<dl class="kbd-list">` with `<dt>` and `<dd>`. |
| web/js/views/settings.js:136 | "Show in a dialog" button opens keyboard help dialog but lacks `aria-haspopup="dialog"`. | Add `aria-haspopup="dialog"` to the button element. |
| web/js/views/settings.js:150-158 | `reportFallback` injects `<textarea>` into an auto-dismissing toast and focuses it; toast expiry causes lost focus. | Display debug report in a persistent modal dialog with a close button instead of an auto-dismissing toast. |
| web/js/keys.js:93-100 | Closing panel sheet with Escape does not return focus to trigger button (`panel-toggle`), dropping focus to `<body>`. | Save `document.activeElement` before opening panel and restore focus upon closing. |
| web/js/keys.js:114-127 | Global single-character hotkeys (`?`, `[`, `]`, `z`, `m`, and `g` chords) lack disable or remap options (WCAG 2.1 SC 2.1.4). | Add a setting in Settings to disable single-character hotkeys or require modifier keys. |
