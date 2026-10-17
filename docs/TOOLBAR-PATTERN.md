# Section toolbar pattern (R11.7)

Problem: sections stack their filters above the content. Work shows the view tabs, then Kind, Show, Model, Phase
(9 chips, 2 rows) and Status chips: about 5 rows, roughly 180 to 200 px at 1440x900, before the first card. Head
shows tabs, a filter bar, 9 status chips and a view switch (3 to 4 rows). Space goes to controls instead of the work.

Rule: **one compact row per section, filters collapsed.** Pattern taken from GitHub Issues, Linear, Jira and Notion
database views, plus the WAI-ARIA disclosure and menu patterns.

## Anatomy (left to right, one row)

| Slot | Control | Rule |
|---|---|---|
| 1 | View switcher | Segmented buttons (`aria-pressed`), only when the section has 2+ views. Max 4 visible; more go into a select. |
| 2 | Search | Optional `type="search"`, 200 px, grows on phone. |
| 3 | Filters | ONE button "Filters" with an active-count badge (`Filters, 3 active` as its label). Opens the popover. |
| 4 | gap | Flexible space. |
| 5 | Primary actions | At most 2 buttons (one `btn-primary`). Anything else goes in the overflow. |
| 6 | More (...) | Overflow menu (`aria-haspopup="menu"`) for secondary and rare actions (export, copy, refresh all). |

Under the row, only when needed:

- **Filter popover** (collapsed by default): grouped multi-select. Each group is a `fieldset` with a `legend` and
  checkbox options (label + optional count, right aligned, tabular numbers). Groups flow in a grid of 150 px+
  columns. Footer: Clear all, Done. Changes apply live (no Apply button), as GitHub and Linear do.
- **Applied line**: removable chips `Group: Value x` in ONE wrapped line, plus a Clear link. Rendered only when at least
  one filter is on. This keeps the active state visible after the popover closes (users forget applied filters).

## Heights

- Toolbar row <= 40 px on desktop (controls are `--h-small` / `--h-control`). On phone (< 768 px) targets are 44 px,
  so the row is <= 52 px.
- Collapsed state: 40 px total for the whole toolbar when no filter is active; 40 + 28 px with active filters.
- The popover overlays the content (absolute, `--z-over`, max-height 60vh, scrolls); on phone it is a bottom sheet
  (fixed, max-height 70vh). It never pushes the content down.
- The toolbar is `position: sticky; top: 0` inside the section scroller so filters stay reachable while scrolling.

## Behaviour and a11y

- Filters button: `aria-expanded` + `aria-controls="tb-KEY-pop"`. The popover is `role="dialog" aria-label="Filters"`
  and uses the `hidden` attribute (CSP forbids style attributes). Opening by click moves focus to the first checkbox
  only when opened from the keyboard path (`openFilters()`); Tab is trapped inside the popover; Esc closes it and
  returns focus to the Filters button; Done does the same; a click outside closes it.
- More menu: `role="menu"`, items `role="menuitem"`, ArrowUp/ArrowDown move, Esc closes and returns focus, focus
  goes to the first item on open; choosing an item closes the menu.
- Applied chips are buttons with `aria-label="Remove filter Group: Value"`; the line is `role="group"
  aria-label="Active filters"`.
- Status never by colour alone: the badge carries a number, chips carry text.
- Persistence: popover open/closed per toolbar key in localStorage `rb.toolbar` (every read/write in try/catch;
  storage failure = closed). The filter VALUES stay where each section keeps them today (route `f=` / `rb.ui.v2`),
  so links keep working. Re-renders keep the popover open because toolbarHtml reads the stored state; checkboxes have
  stable ids (`tb-KEY-oG-O`) so `dom.patch` keeps focus.
- Keyboard shortcut: `f` opens the Filters of the toolbar on screen. keys.js owns single keys, so keys.js calls
  `openFilters()` (to add with the first section migration; respect the single-key setting and the `g` chord).

## Helper contract (web/js/toolbar.js, web/css/toolbar.css)

```js
import { toolbarHtml, initToolbars, toggleToken, activeCount, openFilters } from "../toolbar.js";
toolbarHtml({
  key: "work",                       // [a-z0-9-]; ids are tb-work-pop, tb-work-menu, tb-work-q, tb-work-oG-O
  label: "Work toolbar",
  views: [{ id: "board", label: "Board", current: true }, { id: "list", label: "List" }],
  search: { value: "", placeholder: "Search tasks", label: "Search tasks" },   // optional
  groups: [{ id: "status", label: "Status",
             options: [{ token: "status:todo", label: "To do", on: true, count: 12 }] }],
  actions: [{ id: "new", label: "New task", primary: true }],                // max 2 rendered
  overflow: [{ id: "export", label: "Export" }],
  open: undefined,                   // boolean overrides the stored state (tests, deep links)
});
```

Markup classes: `.tb[data-tb=KEY]` > `.tb-row` (`.tb-seg` > `.tb-seg-btn[data-tb-view]`, `.tb-search[data-tb-search]`,
`.tb-filters[data-tb-toggle=pop]` > `.tb-count`, `.tb-gap`, `.btn[data-tb-act]`, `.tb-more-wrap` > `.tb-more
[data-tb-toggle=menu]` + `.tb-menu` > `.tb-menu-item[data-tb-act]`), `.tb-pop` > `.tb-grps` > `.tb-grp` (fieldset) >
`.tb-opt` > `input[data-tb-token]`, `.tb-pop-foot` (`[data-tb-clear]`, `[data-tb-close]`), `.tb-applied` >
`.tb-chip[data-tb-remove]` + `.tb-clear-link[data-tb-clear]`.

Events: `initToolbars()` (call once from app.js, like `initSplitters`) wires everything by document delegation and
dispatches a bubbling `CustomEvent("rb:toolbar", {detail: {key, type, value}})` from the toolbar root.
`type`: `view` (id), `token` (checkbox toggled; value = token), `remove` (token), `clear`, `search` (text),
`action` (id). The section turns that into its existing state change (e.g. Work: `toggleToken(f, value)` then save and
re-render). Open/close of the popover and menu is handled inside the helper; sections never touch it.

Wiring still needed (not done in R11.7, to avoid clashing with view workers): link `/css/toolbar.css` in
web/index.html, call `initToolbars()` in app.js, service restart (new files 404 until the service restarts).

## Per-section application

| Section | In the bar | In Filters popover | In More (...) | Notes |
|---|---|---|---|---|
| Work | Views Board/List/Tree/Planner; search; Filters; New task | Kind, Show (needs, blocked), Model, Phase, Status; Group by (List) as a radio group | Clear done, export, density | Biggest win: 5 chip rows -> 1 row (+1 applied line). Bulk bar stays contextual (only when rows are selected). Phone column tabs stay. |
| Head | Tabs Chat/Questions; search; Filters; View List/Cards as segmented | Status (9 states), Kind (was select), Session (was select), Order | Expand/Collapse all, log | Alerts stay as one banner line only when non-zero. |
| Inbox | Filter as segmented (All/Questions/Head asks/Rules/Blockers, with counts) | none | Mark all read (if any) | Already ~1 row; just move into `.tb`. |
| Overview | none (KPI row is content) | none | none | Banners stay conditional. No toolbar. |
| Roadmap | Views Lanes/Timeline/Map; summary text on the right | none | none | Summary notes go into the gap slot as muted text. |
| Agents | Filters (if lists grow: model, state) | Model, State | Remove selected, Load more stay in list footers | No bar needed today. |
| Workflow | Views Timeline/Map/Table; range segmented (2h/Today/Week/All); Now | Map: Status, Agent, Phase | Map ops: Show all, Reset focus, 100%, Open full screen | Zoom +/- and Fit stay as an on-canvas control cluster, not in the bar. |
| System | Views (7) -> segmented for the 3 most used + select for the rest | none | Full screen, stats | Zoom buttons move onto the canvas corner. |
| Tokens | Tabs Overview/History/By task/Limits | History: Models (4 chips) | Range + Metric as segmented in the bar on History only | Notices stay as conditional banners. |
| Rules | Group tabs as segmented | none | Copy section | 1 row. |
| Activity | Filters (kind, agent) when added | Kind, Agent | Copy | No controls today. |
| Git | Tabs Changes/History/Branches | none | Refresh | 1 row. |
| Settings | none | none | none | Settings is a form, not a list; keep its cards. |

## Priority order (for the Sonnet that applies the helper)

1. Work (5 rows -> 1; the complaint).
2. Head (3-4 rows -> 1).
3. Workflow Map (3 rows -> 1 + canvas controls).
4. Tokens History, System.
5. Inbox, Roadmap, Rules, Git (move into `.tb` for consistency; small gain).
6. Agents, Activity (only when they gain filters).

Each migration: keep the existing state keys and `data-*` handlers in the section's state logic, swap only the markup
for `toolbarHtml(cfg)`, listen to `rb:toolbar`, update that section's render test, check 375 and 1440 in light and
dark.

## Live audit note

The live app at 127.0.0.1:8780 could not be screenshotted on 2026-10-17: the running service 404s the new
web/js/splitter.js that app.js now imports, so sections did not render (restart needed). Row and pixel counts above
come from the view sources and the person's Work screenshot.
