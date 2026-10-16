# UX review: Git section (R10.9)

Rules: `docs/UI-CHECKLIST.md` (rule 0 grid, 5 layout, 8 forms, 10 tables), `docs/ux/web-interface-guidelines.md` (tabular-nums, touch, focus).
Screenshots: no `build/ui-smoke/alpha-git-*` existed when checked (another ui_smoke run was active, so none was started). Verification used a static preview of the render output (`tests/web/render_git.mjs`) in headless Chrome at 500 px, dark theme.

| # | issue (element, what) | screenshot | rule source | fix | P | after |
|---|---|---|---|---|---|---|
| 1 | Changes: checkbox rows show raw XY code ("M.", "??") in a right-aligned column | - | checklist 0 (fixed columns) | status letter column (M / U) then path; checkbox first | P1 | fixed |
| 2 | Changes: commit form is a tall stack (label, 2-row textarea, label, input, button) | - | checklist 8 (forms), 0 | one row: message (1fr) / task (7rem) / Commit selected; labels wrap their field | P1 | fixed (500 px) |
| 3 | History: 5 fixed tracks overflow at 500 px, author pushes age off the row | - | checklist 5 (phone) | author column hidden under 640 px (class `git-au`); tracks reflowed | P1 | fixed (500 px) |
| 4 | History: graph lanes can drift from rows (row height came from content) | - | checklist 0 | rows and graph cell pinned to `--h-control` (28 px), so lanes meet row centres | P1 | fixed (2 rows checked) |
| 5 | Commit diff: diff2html light palette in dark theme | - | checklist 6 (semantic tokens only) | `.d2h-wrapper` overrides diff2html variables with tokens: surface, line, success/danger tints, labels; follows dark/light via tokens | P1 | fixed in CSS; not seen rendered |
| 6 | Commit diff: side-by-side default is cramped on phones | - | checklist 5 | default "Inline" under 640 px | P2 | fixed |
| 7 | Push block shared the `git-form` grid and wrapped oddly | - | checklist 0 | plain block: Push button, then note | P3 | fixed |
| 8 | Changes rows have no +/- counts (status payload has no counts) | - | checklist 0 (numbers in columns) | none in this pass; needs a counts field from the status route or per-file reads | P2 | open (server/route, not in my files) |
| 9 | 768 px and 1440 px, light theme, and the real app shell not checked in a browser | - | pre-delivery list | layout is by media query (stack below 1100 px); left for the next ui_smoke run | P2 | open |
| 10 | Commit row copy button is faint (opacity 0.4) and sits in the shared ref column | - | checklist 1 (contrast) | left as is (shared `.ref-copy` rule, not in my files) | P3 | open (shell/components owner) |

Byte budget: `web/css/git.css` 2036 B (cap 2048 in its test, was 1814). Shared `web/css` total was 81766 B against the 81920 B cap at the last run.
