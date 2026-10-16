# UX review: Overview (R10.13)

Screens: build/ui-smoke/alpha-overview-*, alpha-activity-* (500, 768, 1024, 1440, 1920, 2560; dark and light).
Rule sources: docs/UI-CHECKLIST.md (rule 0), docs/ux/web-interface-guidelines.md, ui-ux-pro-max ux domain.

| # | issue (element + what) | screenshot | rule source | fix | P | after |
|---|---|---|---|---|---|---|
| 1 | Activity row text breaks mid-word ("R10.4 done-" / "done"); the source chip wraps to its own line | alpha-activity-500x900-dark | web-interface-guidelines (content overflow) | one line per row: age, text with ellipsis + title, source chip, icon slot; "->" shown as a no-break "→" | P1 | fixed, 500px: one line each |
| 2 | Undo is a ~200px outlined box that dominates the row | alpha-overview-500x900-dark | ui-ux-pro-max (row density) | icon-only 28px ghost button with aria-label and title, shown on hover or focus, always on touch (hover: none) | P1 | fixed (CSS; no undoable lines in fixtures to show it) |
| 3 | Row heights differ; text column squeezed by a 9.5rem action track | alpha-activity-768x1024-dark | UI-CHECKLIST rule 0 (fixed grid columns) | fixed grid 3.25rem / 1fr / auto / 1.75rem, min-height var(--h-row) | P2 | fixed |
| 4 | Undo target 28px, under the 44px touch guidance | - | web-interface-guidelines (touch targets) | kept 28px on request (dense list); the row action is also reachable by keyboard focus | P3 | open (decision for the head) |
| 5 | Overview shows "Coming soon" on some runs (1024, 1440, 1920, 2560). Module import is fine in node (no cycle, all exports present). | alpha-overview-1440x900-dark | app.js latches a failed section import in missingSections and never retries | retry the import on the next render (shell owner, web/js/app.js) | P1 | open (shell) |
| 6 | ui_smoke reports missing markers (.ov-card, .met-row, .page-title) for overview, tokens, head, workflow. A loading or skeleton state has no marker; dump_ready only waits for the nav. | - | harness (tools/ui_smoke.py) | wait for the marker, not only the nav (harness owner) | P2 | open (harness) |
| 7 | web/css total 82534 bytes against the 81920 cap. flow.css is 5394 bytes (budget 5632), and this pass adds +54 net. Overage comes from git.css (+296) and shell.css (+81). | - | tests.web.test_shell CSS cap | trim by the git.css and shell.css owners | P1 | open (other owners) |
| 8 | components.css 418-421 (.row-grid.act-row) styles no longer used by the Activity rows | - | dead CSS | delete (shell owner) | P3 | open (shell) |
