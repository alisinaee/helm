# UX review: Agents (R10.4)

Screenshots: build/ui-smoke/alpha-agents-*.png (500, 768, 1024, 1440, 1920, 2560; dark, plus 1440 light).
Rules: UI-CHECKLIST rule 0 (grid columns), web-interface-guidelines (tabular numbers, touch targets, labels).

| # | issue (element + what) | screenshot | rule source | fix | P | after |
|---|---|---|---|---|---|---|
| 1 | Header "Task", "Elapsed", "Tokens" centred or offset from their values (1440, 2560) | alpha-agents-1440x900-dark | rule 0 | header and body cells share justify-self: start for model/effort/job/task, end for elapsed/tokens, centre for action | P1 | fixed, aligned at 1440 |
| 2 | Effort column reported 191px for 26-42px text | alpha-agents-1440x900-dark | rule 0 | not reproduced: the effort track is 4.5rem (72px) at 640px and up; no change to the track | P2 | open (confirm with the old 191px capture) |
| 3 | Phone rows show no field labels (effort, task, elapsed, tokens look alike) | alpha-agents-500x900-dark | web-interface-guidelines (content, labels) | CSS label before each value on phone (under 640px): Effort, Task, Elapsed, Tokens | P1 | fixed |
| 4 | Phone Stop button under 44px tall | alpha-agents-500x900-dark | touch targets 44px | min-height 44px on the action button under 640px | P2 | fixed |
| 5 | Claimed jobs looked like nothing (status 'claimed' is in the running list) | none (no claimed fixture) | state shown, not colour only | 'claimed' chip in the Model cell (agents.js) and Running now list (running.js) | P1 | fixed, unit test |
| 6 | Shared CSS total (web/css) over CSS_TOTAL_MAX once work.css and plan.css grew in parallel | none | CSS caps | not fixed here (other workers' files); Agents adds about 0.6 KB | P1 | open, for the head |

Open: #2 (confirm), #6 (CSS total cap needs a trim in work.css or plan.css).
