# UX Review: App Shell Audit (G5)

## Shell Audit Issues

| Issue | Evidence File:Line | Fix | Severity |
| :--- | :--- | :--- | :--- |
| Topbar tools crush breadcrumb at 768px | `web/css/shell.css:28`, `web/js/views/topbar.js:180` | Make `.top-tools` wrap/collapse secondary actions (Mark/⌘K) below 1024px; enforce `min-width: 120px` on `.crumb` | High |
| Mobile topbar leaks "Enter usage" button outside hidden meters | `web/js/views/topbar.js:131`, `web/css/shell.css:74` | Wrap `.top-enter` inside `.top-meters` container or add `.top-enter { display: none }` at `<=640px` | Medium |
| JS/CSS mobile breakpoint mismatch (599px vs 640px) | `web/js/views/topbar.js:28`, `web/css/shell.css:65` | Align `phoneWidth()` media query to match CSS breakpoint `(max-width: 640px)` | Low |
| Redundant "Close" button in side panel on desktop | `web/js/views/panel.js:41`, `web/css/panel.css:4` | Hide `.side-close` at `@media (min-width: 1200px)` since topbar toggle owns panel state in grid layout | Medium |
| Left nav lacks scroll container on short viewports | `web/css/shell.css:3` | Replace `overflow: hidden` on `.nav` with `overflow-y: auto; overflow-x: hidden` to prevent foot truncation | Medium |
| Nested vertical scroll containers cause double scrollbars (Head) | `web/css/head.css:42`, `web/css/shell.css:39` | Unify scrolling: remove `overflow: auto` from `.hd-list` or set `.main` to `overflow: hidden` for full-height views | High |
| Mobile Head controls cut off behind fixed bottom bar | `web/css/head.css:3`, `web/css/shell.css:70` | Remove `.main:has(>.hd-screen){padding-bottom:0}` on mobile; retain `padding-bottom: var(--h-bnav)` | High |
| Mobile body scroll vs desktop `.main` container conflict | `web/css/shell.css:66`, `web/css/shell.css:67` | Keep `.main` as single scroll container across all breakpoints using `height: 100dvh` instead of body scroll | Medium |
| Drag resize handles hidden at 768-1199px despite JS supporting it | `web/css/resize.css:4`, `web/js/resize.js:4` | Harmonize breakpoints: show `.rz-side` and `.rz-nav` whenever panels are in grid mode (or update `MIN_W`) | Medium |
| Resize handles have narrow 6px hit target without grab boundary | `web/css/resize.css:1`, `web/js/resize.js:68` | Add `::before` pseudo-element providing a 14px hit target; add `user-select: none` to `body` while dragging | Low |
| Ultra-wide viewports (1920px+) lack max-width constraints | `web/css/shell.css:1`, `UNKNOWN` | Add `max-width: 1600px` centering container to `.main` content to avoid extreme visual dispersion | Low |

## Implementation Plan: Resizable Left/Right Panels

- **Target Files**: `web/js/resize.js` (logic), `web/css/resize.css` (handle styles), `web/css/tokens.css` (defaults), `web/css/shell.css` (layout).
- **CSS Variables**: `--w-nav` (Nav width, default `232px`), `--w-side` (Side panel width, default `320px`), `--w-rail` (`56px`, fixed).
- **Bounds & Specs**:
  - Left Nav: `min: 180px`, `max: 380px`, `def: 232px`. Snaps to rail (`--w-rail: 56px`) if dragged below `120px`.
  - Right Side: `min: 280px`, `max: Math.min(720, Math.round(window.innerWidth * 0.5))`, `def: 320px`.
- **Drag Handle (`div.rz`)**:
  - Positioned fixed along column boundaries (`.rz-nav` at `left: calc(var(--w-nav) - 3px)`, `.rz-side` at `right: calc(var(--w-side) - 3px)`).
  - Visual width `6px`, transparent hit zone `14px` via `::before` (`inset: 0 -4px`), hover/focus highlight with `var(--accent)`.
  - Uses `setPointerCapture(e.pointerId)` on `pointerdown`, updates CSS vars in `requestAnimationFrame`, toggles `.rz-drag` and `body[data-resizing]`.
- **Persistence (`localStorage`)**:
  - Serialized as JSON under key `"rb.widths"`.
  - Loaded at boot and applied to `:root.style`. Persisted on `pointerup` and keyboard commit.
- **Keyboard A11y**:
  - Attributes: `tabindex="0"`, `role="separator"`, `aria-orientation="vertical"`, `aria-valuenow`, `aria-valuemin`, `aria-valuemax`, `aria-label`.
  - Keys: `ArrowLeft` / `ArrowRight` adjust by `STEP = 16px` (`spec.sign * dir`). `Home` sets min, `End` sets max.
- **Double-Click Reset**:
  - `dblclick` event removes property from `:root.style`, resets current value to `spec.def`, updates `aria-valuenow`, and clears key in `localStorage`.

## Plan: One-Scroll-Container-Per-Section

- **Golden Rule**: Exactly ONE element owns vertical scrolling per section. Never allow nested vertical scrollbars.
- **Root Shell Container**:
  - `#app` remains `height: 100vh; overflow: hidden; display: grid`. Body never scrolls.
  - `.nav`: `overflow-y: auto; overflow-x: hidden` for nav links; footer pinned with `margin-top: auto`.
  - `.side`: Container is `overflow: hidden`; `.side-body` is the sole scroll container (`overflow-y: auto`).
- **Standard Flow Sections** (Overview, Work, Roadmap, Tokens, Settings, Rules, Inbox):
  - `.main` owns vertical scrolling (`overflow-y: auto; overscroll-behavior: contain`).
  - Child elements never set `overflow-y: auto` or `max-height: Xvh`. Table overflow wrappers (`.wk-tablewrap`) only allow `overflow-x: auto`.
- **Full-Height App Sections** (Head, Workflow Map/Graph):
  - When `.main:has(>.hd-screen)` or Map is active: `.main` sets `overflow: hidden; padding: 0`.
  - The dedicated child container (`.hd-list` or `.wfg-svg`) becomes the single viewport scroll container with `height: 100%`.
- **Mobile Unification (`<=640px`)**:
  - Stop toggling `.main { overflow-y: visible }`. Keep `.main` as `overflow-y: auto; min-height: 0; flex: 1`.
  - Use `padding-bottom: calc(var(--h-bnav) + var(--sp-4))` inside `.main` to guarantee content is never obscured by the bottom nav.

## Breakpoint Matrix

| Viewport (px) | Left Nav Layout | Main Area Layout | Right Side Panel Layout | Top Bar Layout |
| :--- | :--- | :--- | :--- | :--- |
| **500** (Mobile) | Hidden (`display: none`). Bottom nav `#bnav` active (4 tabs + More sheet). | Single-col flow, cards replace tables, padding `12px 16px`. | Fullscreen overlay sheet (`inset: 0; width: 100%`). Scrim active. | Crumb shows project only (`alpha ▾`). Tools: Status pill, Theme, ?, Toggle. |
| **768** (Tablet Port.) | Icon rail (`--w-rail: 56px`), labels hidden in `.sr-only`, badge dots. | Single-col grid, 2-col KPI cards, horizontal-scroll tables. | Slide-out overlay drawer (`width: 320px; position: fixed`). Scrim active. | Crumb truncated with ellipsis. Compact tools (Mark/⌘K hidden or menu). |
| **1024** (Tablet Land.) | Collapsed rail (`56px`) or expanded (`232px`) via toggle; resizable. | 2 to 3-col grids, 3-col KPI, Kanban board columns side-by-side. | Slide-out overlay drawer (`320px`) or docked grid column if toggled. | Full crumb (`alpha › View`). Full tools: Control, Meters, Live, ⌘K, Theme, ?. |
| **1440** (Desktop Def.) | Expanded docked nav (`var(--w-nav)` 232px, drag-resizable 180-380px). | Full grid layout, 6-col KPI row, multi-column Kanban/Table views. | Docked grid column (`var(--w-side)` 320px, drag-resizable 280-720px). | Full breadcrumb, project pill, stop/weekly meter, Live dot, Mark, ⌘K, full tools. |
| **1920** (Widescreen) | Expanded docked nav (`var(--w-nav)` resizable, persisted). | Max-width `1600px` content container, expanded board columns. | Docked grid column (resizable up to 720px, persisted width). | Spanned header bar; crumb and tools pinned to content boundaries. |
| **2560** (Ultra-wide) | Expanded docked nav (`var(--w-nav)` resizable, persisted). | Centered content wrapper capped at `1800px` to prevent stretching. | Docked grid column (resizable up to 800px or 35% screen width). | Spanned bar, aligned with content grid boundaries. |
