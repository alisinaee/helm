# UX review: Work section (R10.4)

Screenshots: build/ui-smoke/alpha-work-{board,list,tree,planner}-1440x900-dark.png (before and after, same names; "after" is the second pass).
Rule sources: docs/UI-CHECKLIST.md (rule 0 = fixed columns), docs/ux/web-interface-guidelines.md, ui-ux-pro-max ux domain.

| # | issue (element + what) | screenshot | rule source | fix | P | after |
|---|---|---|---|---|---|---|
| 1 | List: Task column squeezed to about 230 px while Flags sat empty; fixed widths summed too high | alpha-work-list | rule 0 (fixed tracks) | narrower fixed numeric/ID/status tracks, Est/Spent/Cap right-aligned in header too | P1 | title about 260 px, numbers aligned under headers |
| 2 | Board: each card kept an empty action row (hidden buttons took space), tall dead areas | alpha-work-board | modern minimal (Linear-like) | actions float over the card on hover/focus (fine pointer); in flow on phone | P2 | cards sized to content |
| 3 | Board: column title and count run together ("Todo17") | alpha-work-board | typography | count gets a gap and a pill | P3 | "Todo 17" |
| 4 | Tree: phase row and task rows on different columns (phase name and task title did not line up; status/model drifted) | alpha-work-tree | rule 0, tree indentation | shared track template: caret, id, title, status, chips; tasks indented by one track; subtasks under the title column | P1 | phase and task columns align; status and count right edges match |
| 5 | Tree: phase header box heavy (border plus surface) | alpha-work-tree | minimal look | flat band with surface-1 only | P3 | lighter |
| 6 | Planner: second "Plan" heading under "Work" (duplicate title) | alpha-work-planner | consistency with other views | heading kept for screen readers (sr-only), "+ Plan phase" sits in the top row | P2 | one title |
| 7 | Planner: orphan and linked rows were loose chip/text flow with ragged Assign/Unlink buttons | alpha-work-planner | rule 0 | same 4-column grid (id, state, title, action) for orphan and linked rows; action column fixed 6.5 rem | P1 | buttons in one column |

Open (not fixed here):
- List: Flags column is mostly empty at 1440 px; the Task column still truncates. Needs a column-visibility or density choice (product decision).
- Planner: empty state text ("No plan yet. Ask your agent...") is centred and bold, unlike the Board/List empty states; it lives in planner.js (screenHtml) and is checked by tests/web/test_planner_view.py, so left as is.
- ui_smoke: at this run, failures are on other sections (workflow page-title, overview ov-card, tokens met-row); Work routes pass. Not Work's files.
- Shared CSS total is at 81803 bytes vs the 81920 cap, which leaves 117 bytes. Work and Planner CSS were trimmed to fit (dead/duplicate rules merged). work.css itself is at its 6144-byte budget.
