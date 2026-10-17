# UI checklist for UI packages (from the installed ui-ux-pro-max skill + our decisions)

Skill installed at `~/.claude/skills/ui-ux-pro-max` (MIT, stdlib python, no network). Do NOT use its landing-page / palette recommendations (we have our own tokens). USE its UX guidelines for your section, once per package:
`python3 ~/.claude/skills/ui-ux-pro-max/scripts/search.py "<your topic>" --domain ux -n 3`   (no `-I` flag; read only the lines you need)

Rules every UI package must satisfy (priority order from the skill):
0. TOP PRIORITY, row alignment: numbers and actions align in fixed columns so the user can read and act at a glance. Every list of rows that shows numbers or actions uses the shared `.row-grid` utility (web/css/components.css) with fixed column tracks: chip, title (1fr, ellipsis, full text in title attr), task, elapsed, tokens (right-aligned, tabular-nums), action (fixed width, same position on every row). The header row, if any, uses the same tracks. On narrow screens the row collapses to two lines with numbers and actions kept right-aligned. Checked by tests/web/test_rows.py.
1. Accessibility: text contrast >= 4.5:1 (tools/contrast.py), visible focus ring on every control, aria-labels on icon-only buttons, full keyboard operation, status never by colour alone, `prefers-reduced-motion` respected.
2. Touch/interaction: targets >= 44x44 px on phone (>= 24 px desktop), 8 px+ between targets, loading/feedback within 100 ms (optimistic update + toast), no hover-only actions.
3. Dragging: drag is NEVER the only way (WCAG 2.2): every drag has Move up/down or menu buttons and a keyboard path.
4. Feedback: toasts auto-dismiss in 3-5 s with Undo, pause on hover/focus; confirm only irreversible actions (none are: we use Undo instead).
5. Layout: mobile-first, no horizontal scroll at 375/768/1024/1440, reserve space (no layout shift), tables become stacked rows on phone.
6. Typography/colour: semantic tokens only (no raw hex outside tokens.css), body >= 13 px, line-height ~1.5, tabular numbers.
7. Icons: SVG sprite only, no emoji as icons in the UI (wireframe glyphs in the spec are placeholders).
8. Forms: visible labels, error next to the field, helper text, progressive disclosure.
9. Navigation: predictable back, deep links (hash routes), bottom nav <= 5 items, no overloaded nav.
10. Tables/boards: filters + bulk actions, empty states with one sentence and one action.

Pre-delivery: check light and dark, 375 and 1440, console errors empty, CSP clean, `wc -c web/css/*.css` <= 72 KB (CSS_TOTAL_MAX in tests/web/test_shell.py).

Splitters (R11.3, web/js/splitter.js): any two-region view gets a drag divider with no JS of its own. Host: `data-splitter-host="KEY"`, a grid whose last track is `var(--split-KEY, DEFpx)` (tracks: `minmax(0,1fr) 6px var(--split-KEY,..)`). Between the regions put `<div class="spl" role="separator" tabindex="0" aria-orientation="vertical" aria-label="Resize ..." data-splitter="KEY" data-min="320" data-max="720" data-def="416">`. The region after the separator is the one resized; width persists per KEY in localStorage `rb.splits` (try/catch); arrows (Shift x4), Home/End, double-click reset. System: add the host attribute and separator in system.js with KEY `system`. Nav and side panel keep web/js/resize.js (`rb.widths`).

Section toolbars: one compact row, filters collapsed (R11.7, docs/TOOLBAR-PATTERN.md, web/js/toolbar.js). Top of a section = ONE row <= 40 px: view switcher (segmented), optional search, one "Filters" button with an active-count badge, max 2 primary actions, "..." overflow menu. Filter groups go in the collapsed popover (checkbox groups); applied filters show as removable chips in one wrapped line only when active. Never stack chip rows above the content.
