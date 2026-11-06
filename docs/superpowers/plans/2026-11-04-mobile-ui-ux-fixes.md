# Helm Mobile View UI/UX Comprehensive Fix Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide a polished, accessible, bug-free mobile UI/UX experience across all 18 routes, headers, navigation bars, buttons, and drawers in the Helm dashboard at standard (375px/390px) and small (320px) viewports.

**Architecture:** Refine mobile CSS rules across `web/css/glass.css`, `web/css/shell.css`, `web/css/components.css`, `web/css/system.css`, `web/css/toolbar.css`, and update navigation and view bindings in `web/js/` without breaking desktop layouts or exceeding CSS size budgets (`SHELL_CSS_MAX` <= 11KB, `CSS_TOTAL_MAX` <= 192KB).

**Tech Stack:** Vanilla JavaScript (ES modules), CSS3 (CSS Grid, Flexbox, Custom Properties, Media Queries, Backdrop Filter), HTML5, Python (unit tests & CDP headless Chrome verification).

**Spec:** [docs/UI-SPEC.md](file:///Users/ali/works/helm/docs/UI-SPEC.md), [docs/UI-CHECKLIST.md](file:///Users/ali/works/helm/docs/UI-CHECKLIST.md), and [docs/HANDOVER.md](file:///Users/ali/works/helm/docs/HANDOVER.md).

## Global Constraints
- Preserve CSS budget: `SHELL_CSS_MAX <= 11264` bytes, total CSS <= 196,608 bytes.
- Do not add inline `style=""` attributes in JS views.
- Ensure all touch targets meet HIG/WCAG minimum ($\ge 44\text{px}$).
- Mobile viewports (320px, 375px, 390px, 414px) must have zero horizontal overflow.
- No letter-splitting or hyphenless word-breaking on buttons, chips, or labels.
- Maintain existing dark and light modes for all 3 themes (`classic`, `obsidian`, `black`).
- Maintainer rule: never touch port 8780 or kill user processes; use ephemeral test ports or existing server read-only.

## Review Focus
1. **Bottom Nav Layout:** 4 items distributed evenly (`grid-template-columns: repeat(4, 1fr)`), no blank 5th column.
2. **Bottom Nav "More" Sheet:** Opens cleanly above bottom nav without clipping by parent `overflow: hidden`.
3. **Bottom Nav Background:** Solid/high-opacity backdrop so scrolling page content does not bleed through icons/labels.
4. **Active Item Indicator:** Clean pill/glow styling without crescent-moon clipping on mobile.
5. **Button Typography:** Clean labels with `white-space: nowrap` on toolbars/chips; no single-letter vertical stacking.

---

### Task 1: Navigation Bar (`bnav` & `sheet`) Refinement

**Files:**
- Modify: `web/css/shell.css`
- Modify: `web/css/glass.css`
- Modify: `web/js/views/nav.js`
- Test: `tests/web/test_mobile_view.py`

**Steps:**
- [ ] Update `.bnav-row` to use 4 columns matching the 4 bottom nav items (`grid-template-columns: repeat(4, minmax(0, 1fr))`) instead of 5 columns.
- [ ] Remove `overflow: hidden` from `.bnav` in `web/css/glass.css` so that `.sheet` (`#bnav-more`) can float above `.bnav` without clipping.
- [ ] Set an opaque/high-contrast background on `.bnav` (`background: var(--surface-1)` or solid glass fill) to prevent scrolling page text from bleeding through the navigation bar.
- [ ] Replace crescent-moon left-shadow (`box-shadow: inset 2px 0 0 var(--accent)`) on `.bnav-i[aria-current="page"]` in `web/css/glass.css` with a clean, fully-rounded active pill highlight (`background: var(--glass-fill-strong); color: var(--accent); box-shadow: 0 0 0 1px var(--accent)`).
- [ ] Adjust safe-area and floating positioning of `.bnav` so it sits comfortably above the iOS home indicator without obscuring page content.
- [ ] Run `python3 -m unittest tests/web/test_mobile_view.py` to verify mobile nav checks pass.

---

### Task 2: Top Header Bar (`top`) & Background Glow Polishing

**Files:**
- Modify: `web/css/shell.css`
- Modify: `web/css/glass.css`
- Modify: `web/css/components.css`
- Test: `tests/web/test_mobile_view.py`

**Steps:**
- [ ] In `web/css/glass.css`, remove mobile `.top` margin (`margin: var(--sp-2) var(--sp-2) 0`) that causes `.top` to overflow its fixed-height grid row into `.main`.
- [ ] In `web/css/glass.css`, adjust the top-right neon radial gradient in `body::before` (`at 85% 5%`) on mobile (`@media (max-width: 640px)`) to reduce intensity or reposition away from top header buttons to eliminate blinding glare behind controls.
- [ ] In `web/css/shell.css`, update `.pill.is-run` on mobile (`<=640px`) so that if space is constrained, it shows the pulsing dot with clean compact padding rather than clipping the text into `"Ru"`.
- [ ] Align `.top-tools` buttons (`.theme-switch`, `.side-toggle`, `[data-action="stop"]`) to have consistent 44px hit-targets and centered SVG icons.
- [ ] Run `python3 -m unittest tests/web/test_shell.py` and `tests/web/test_mobile_view.py` to ensure budget and rules pass.

---

### Task 3: Button Typography & Destructive Word-Breaking Fixes

**Files:**
- Modify: `web/css/components.css`
- Modify: `web/css/system.css`
- Modify: `web/css/toolbar.css`
- Test: `tests/web/test_mobile_view.py`

**Steps:**
- [ ] Remove `overflow-wrap: anywhere` from `.btn`, `.btn-small`, and `.chip` under `@media (max-width: 639px)` in `web/css/components.css`. Use `overflow-wrap: normal` or `word-break: normal` so normal words don't get split into single characters (e.g., "Cla sse s", "Comp onent s", "F i t", "Ful l scr ee n").
- [ ] For toolbar and filter buttons that shouldn't wrap (e.g. zoom controls, view tabs, chips), enforce `white-space: nowrap`.
- [ ] In `web/css/system.css`, allow `.sys-tabs` and `.sys-bar` to scroll horizontally on mobile (`overflow-x: auto; -webkit-overflow-scrolling: touch; scrollbar-width: none`) so category pills and controls retain their legible pill shapes.
- [ ] In `web/css/toolbar.css`, ensure `.tb-row` wraps controls cleanly without overlapping.
- [ ] Run `python3 tools/lint_py.py` and `python3 tools/lint_js.py`.

---

### Task 4: Section-Specific Mobile UI/UX Polish

**Files:**
- Modify: `web/css/work.css`
- Modify: `web/css/system.css`
- Modify: `web/css/tokens.css`
- Modify: `web/css/components.css`
- Modify: `web/js/views/rules.js` / `web/css/base.css`
- Test: `tests/web/test_mobile_view.py`

**Steps:**
- [ ] **System View:** Fix the architecture map toolbar (`-`, `1.0x`, `+`, `Fit`, `Fullscreen`) so buttons don't break vertically or clip. Enable responsive touch-friendly graph container.
- [ ] **Tokens View:** Enable horizontal scroll on the token section tabs (`.tk-tabs`): "Overview", "History", "By task", "Limits", "Account" so "Account" is never clipped. Fix form inputs for manual usage to stack cleanly.
- [ ] **Head View:** Fix search input and counter layout (`/ search` and `Showing 0 of 0`) so they stack or space evenly on mobile. Ensure session info chips wrap gracefully.
- [ ] **Rules View:** Stack "Scope" and "Task/Phase" inputs vertically on mobile screen widths so neither input is squished to 30px width.
- [ ] **Work View:** Verify Board, List, Tree, and Planner views on mobile; check card tap actions and column switcher buttons.
- [ ] Run `python3 -m unittest discover -s tests/web -t .`.

---

### Task 5: Interactive Real-Device & Headless CDP Verification

**Files:**
- Test runner: temporary Node CDP verification script
- Test: `tests/web/test_mobile_view.py`

**Steps:**
- [ ] Run CDP automated verification across all 18 routes at `390x844` and `320x568`.
- [ ] Test interactive "More" menu opening and confirm the sheet is fully visible, clickable, and navigates to sub-routes.
- [ ] Capture fresh screenshots of all 18 routes and inspect each one to verify:
  - No text bleeding through bottom nav.
  - No weird glowing circle arcs or clipped button pills.
  - No letter-split text in buttons or toolbars.
  - No clipped form fields.
  - No horizontal overflow.
- [ ] Run full test suite: `python3 -m unittest discover -s tests/web -t .`, `python3 tools/lint_js.py`, `python3 tools/lint_py.py`, `python3 tools/contrast.py`.
- [ ] Commit all changes to branch `fix/mobile-view-dashboard`.
