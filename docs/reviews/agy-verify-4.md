# agy batch 4 verification

Checked 2026-10-15 against the working tree (dirty: other workers are editing planner.js, settings.js, topbar.js, work.js). Verdicts: KEEP = the claim is true now; WRONG = the claim is false now; UNVERIFIED = not settled from code read; SKIP = file is moving.

Source rows: p01 30, p02 36, p03 31, p04 27, p05 30. Every row was checked against the cited file and the surrounding function, not only the cited line (cites are off by a few lines in several places).

## p01 agy-p01-ref-coverage.md (copy-reference column)

| row | verdict | evidence |
|---|---|---|
| web/js/views/tasks.js:136 | KEEP | `taskRowHtml(t, [])` passes no copy argument; copy is optional (tasks.js:108) |
| web/js/views/needsyou.js:14 | KEEP | rows come from `taskListHtml`, which passes no copy; section gets `sectionRef` (needsyou.js:17) |
| web/js/views/phases.js:105 | WRONG | line 105 is the defer-toggle button; deferred task rows DO carry copy (phases.js:110 `taskCopyHtml`), task rows too (phases.js:97) |
| web/js/views/phases.js:139 | KEEP | `sectionHtml({id:"phases"})` passes no copy; dom.js:99 has no copy slot |
| web/js/views/roadmap.js:159 | KEEP | `pageHead` is the page title only; row copy is at roadmap.js:84 |
| web/js/views/inbox.js:148 | KEEP | `needRowHtml` has no copy; copy at inbox.js:128 belongs to question cards |
| web/js/views/inbox.js:168 | KEEP | project group heading is a link only |
| web/js/views/inbox.js:176 | KEEP | "Needs you" card heading has no copy; inbox.js:270 copy is for the questions section only |
| web/js/views/inbox.js:191 | KEEP | compact question row has no copy |
| web/js/views/research.js:66 | KEEP | `checklistHtml` renders no copy |
| web/js/views/research.js:68 | KEEP | checklist item row, no copy |
| web/js/views/research.js:101 | KEEP | note card, no copy; file does not use `sectionRef` |
| web/js/views/research.js:131 | KEEP | project link list item, no copy |
| web/js/views/research.js:133 | KEEP | page-head text only |
| web/js/views/rules.js:82 | KEEP | "Add a rule" form heading, no copy |
| web/js/views/rules.js:102 | KEEP | "Sync to CLAUDE.md" section, no copy |
| web/js/views/projects.js:113 | KEEP | "All projects" aggregate row, no copy (per-project rows have copy at projects.js:101) |
| web/js/views/projects.js:146 | KEEP | list wrapper with aria-label, no copy |
| web/js/views/running.js:89 | KEEP | sub-head text only |
| web/js/views/running.js:95 | KEEP | `sectionHtml({id:"running"})` with no copy |
| web/js/views/agents.js:87 | KEEP | finished-job row (`rg-fin`) has no copy; copy only on live rows (agents.js:76) |
| web/js/views/agents.js:99 | KEEP | project group heading, name only |
| web/js/views/agents.js:113 | KEEP | "Recently finished jobs" heading, no copy |
| web/js/views/agents.js:123 | KEEP | Agents page-head, no copy |
| web/js/views/overview.js:98 | KEEP | meter row, no copy |
| web/js/views/overview.js:151 | KEEP | issue row has no copy (task rows in the same card do) |
| web/js/views/overview.js:193 | KEEP | inbox card built with no copy options |
| web/js/views/next.js:20 | KEEP | next-list item, no copy (section copy comes from `sectionRef`, next.js:12) |
| web/js/views/work.js:107 | SKIP | work.js is moving |
| web/js/views/issues.js:55 | KEEP | "New issue" form heading, no copy |

p01 totals: KEEP 28, WRONG 1, UNVERIFIED 0, SKIP 1. The id column was not re-checked row by row; the copy column is what the review covers.

## p02 agy-p02-workflow-a11y.md

| row | verdict | evidence |
|---|---|---|
| graph/render.js:150 tabindex on every task node | KEEP | `tabindex: 0` on each task node; no roving tabindex code in render.js |
| graph/render.js:150 no aria-current on Now | KEEP | no `aria-current` anywhere in render.js |
| graph/render.js:165 running only by pulse | UNVERIFIED | pulse is graph.css:52, removed under reduced motion (graph.css:62); whether `nodeLabel` names the running state was not traced |
| graph/render.js:167 pill 20px | KEEP | layout.js:21 `PILL_H = 20`; 4px gap not checked |
| graph/render.js:167 model shown by stroke only | UNVERIFIED | stroke tokens confirmed (graph.css:48-51); `nodeLabel` text not traced |
| graph/render.js:182 issue node opens task | KEEP | `data-wf-task=n.task`; workflow.js `navigate()` (~line 1027) opens the task, not issue details |
| graph/render.js:191 queue node does nothing | KEEP | `data-wf-task=""` (render.js:192); `navigate()` returns early on empty task |
| graph/render.js:201 collapse node does nothing | KEEP | `collapseNode` has `data-wf-task=""` (render.js:202); no action. "collapse:" id prefix not checked |
| graph/render.js:213 card lacks aria-expanded | KEEP | card has no aria-expanded; only the fold has it (render.js:240) |
| graph/render.js:227 bands not nested under phase | UNVERIFIED | DOM nesting not traced |
| graph/render.js:239 fold lacks data-wf-item | KEEP | fold has `data-wf-fold`, no `data-wf-item` (render.js:240) |
| graph/render.js:248 endpoints do nothing | KEEP | role=button, tabindex 0, `data-wf-task=""` (render.js:249-250) |
| graph/render.js:257 parallel group has no members | KEEP | group holds only one decorative rect |
| graph/render.js:272 flag not linked to node | KEEP | role=img, no tabindex, no describedby |
| graph/render.js:305 edges not aria-hidden | KEEP | no aria-hidden in render.js |
| graph/render.js:433 aria-describedby reads legend | KEEP | render.js:434 `aria-describedby: "wf-legend"` |
| graph/render.js:443 dimmed nodes stay focusable | KEEP | render.js:443 only toggles `wfg-dim`; no tabindex or aria-disabled change |
| graph/viewport.js:166 bare-key shortcuts | KEEP | viewport.js:166-171 maps bare + - 0 Escape n s; only ctrl/meta/alt are guarded |
| graph/viewport.js:347 pointerdown steals focus | KEEP | viewport.js:347 focuses svg or node on any pan; comment at 345 says intentional |
| graph/viewport.js:398 Escape always prevented | KEEP | `preventDefault` after `keyPlan`; Escape maps to `clear` (viewport.js:169) |
| graph/viewport.js:412 arrows skip fold | KEEP | `moveFocus` uses `nodes()` keyed on `data-wf-item`; fold lacks it |
| graph/minimap.js:80 svg role=group, no tabindex | KEEP | minimap.js:80-81 role group, no tabindex, no keyboard control |
| graph/minimap.js:67 rects not aria-hidden | KEEP | minimap.js:67 rect has no aria-hidden |
| views/workflow.js:630 chips use aria-current | KEEP | `<a class="wfg-chip">` with `aria-current="true"` on toggles |
| views/workflow.js:752 toolbar without roving | UNVERIFIED | role=toolbar confirmed (workflow.js:752); arrow handling inside it not traced |
| views/workflow.js:1109 N and S global keys | KEEP | workflow.js:1109-1112 bare n/s active outside inputs and the diagram host |
| css/graph.css:20 glyph fill contrast | UNVERIFIED | `fill: var(--unknown)` confirmed (graph.css:20); contrast ratio not computed |
| css/graph.css:22 parallel bracket 1px | KEEP | graph.css:22 `stroke-width:1px` dashed accent |
| css/graph.css:23 edge 1.25px text-3 | KEEP | graph.css:23 confirmed |
| css/graph.css:24 dependency edge | KEEP | no own width; inherits 1.25px from `.wfg-e` (graph.css:23) |
| css/graph.css:25 handoff 1px | KEEP | graph.css:25 `stroke-width:1px` confirmed |
| css/graph.css:36 .wfg-n outline none | UNVERIFIED | `outline:none` confirmed, but fold elements carry class `wfg-fold`, not `wfg-n` (render.js:239), so the rule may not reach them |
| css/graph.css:44 deferred opacity .55 | KEEP | graph.css:44 confirmed |
| css/graph.css:48 pill rect 1px | UNVERIFIED | stroke token confirmed; no stroke-width in that rule, so "1px" not checked |
| css/graph.css:58 after opacity .6 | KEEP | graph.css:58 confirmed |
| css/graph.css:66 minimap frame | KEEP | graph.css:66 `fill-opacity` .55 and stroke text-3 confirmed |

p02 totals: KEEP 29, WRONG 0, UNVERIFIED 7.

## p03 agy-p03-log-client.md (web/js/log.js and related)

| row | verdict | evidence |
|---|---|---|
| log.js:92 relative URL query kept | KEEP | regex (log.js:92) requires `scheme://`; `/api/...?x` keeps its query |
| log.js:93 abs paths outside /Users, /home kept | KEEP | only `/Users|/home` replaced (log.js:93); LOGGING-SPEC.md:21 says no paths outside ~ |
| log.js:93 username with a space | KEEP | `[^\s/]` stops at space; `/Users/John` becomes `~`, ` Doe/...` remains (partial leak) |
| log.js:93 subdirectories under ~ | WRONG | home becomes `~` by spec (LOGGING-SPEC.md:21 "home path to ~"); `~/Works/...` is intended |
| log.js:107 routeNow ignores search | KEEP | routeNow reads only the hash; no change needed |
| log.js:143 denylist of keys | KEEP | SECRET_KEY denylist (log.js:20); other keys pass through (log.js:143) |
| log.js:166 stack paths | KEEP | `scrub(line,200)` is home-only |
| log.js:229 takeBatch stringify not in try | UNVERIFIED | no try at log.js:229; whether a buffered record can throw was not traced |
| log.js:238 send stringify outside try | KEEP | `JSON.stringify` at log.js:238 precedes the `try` |
| log.js:269 retry timer calls send unwrapped | KEEP | `failed()` setTimeout (log.js:269-271) has no wrapper; send's stringify can throw |
| log.js:294 value.message getter re-entry | UNVERIFIED | getter read confirmed; whether it reaches console.* was not traced |
| log.js:311 hostOf keeps query | KEEP | `hostOf` returns `scrub(text,40)`; scrub keeps relative query |
| log.js:318 onError filename query | KEEP | `scrub(event.filename)` keeps query on relative names |
| log.js:335 onCsp no ENDPOINT guard | KEEP | `onCsp` (log.js:335-340) has no check for /api/v1/log |
| log.js:346 onSubmit records names only | KEEP | records only `form` name (log.js:346) |
| log.js:354 console wrapper no re-entrancy flag | KEEP | `wrapConsole` (log.js:350-361) has no guard |
| log.js:360 apply outside try | KEEP | `original.apply` (log.js:360) is after the try block |
| log.js:384 no shared lock across error and warn | KEEP | separate `wrapConsole` calls (log.js:384-385), no shared flag |
| log.js:410 ui.mark note raw | KEEP | `String(note)` recorded with no sanitiser |
| log.js:424 TARGET_ATTRS values | KEEP | data-item and data-id read as-is |
| log.js:439 pathOf misses file:/// | KEEP | regex needs `[^/]+` after `://`, so `file:///x` is not stripped |
| log.js:450 noteRequest path not scrubbed | KEEP | `path = pathOf(url)`; pathOf does not call scrub(), so absolute paths pass |
| api.js:55 getJson raw url | KEEP | pathOf strips query and fragment; no other validation |
| api.js:88 postJson omits body | KEEP | no body passed to noteRequest |
| cmd.js:70 run omits args | KEEP | logs project only |
| cmd.js:125 runBatch omits payloads | KEEP | logs project and count only |
| app.js:369 click passes element | KEEP | `logAction(action, el, null)` as cited; attribute filtering is log.js:424 |
| app.js:464 installLog at boot | KEEP | `installLog()` at app.js:464; idempotency guard log.js:373-374 |
| LOGGING-SPEC.md:13 ui.submit whitelist | KEEP | spec says "whitelisted fields only"; client logs form name only (no code change needed) |
| LOGGING-SPEC.md:21 redaction rules | KEEP | spec says "Query strings never logged" and "home path to ~"; scrub gaps confirmed above |
| LOGGING-SPEC.md:29 no self-logging loop | KEEP | spec says "drop silently (no self-logging loop)"; onCsp self-logs (log.js:335) |

p03 totals: KEEP 28, WRONG 1, UNVERIFIED 2.

## p04 agy-p04-csp-new.md (inline attribute and handler check)

| row | verdict | evidence |
|---|---|---|
| views/workflow.js:639 op in attribute | KEEP | `data-wf-map-op="' + op + '"` unescaped; callers pass literals |
| views/workflow.js:440 it.status in class | KEEP | `wf-b-' + it.status` unescaped (status constrained by statusOf) |
| views/workflow.js:442 data-lane | KEEP | `g.lane` unescaped, numeric |
| views/workflow.js:443 data-x, data-y | KEEP | numeric, unescaped |
| views/workflow.js:439 x, y, width | KEEP | numeric, unescaped |
| views/workflow.js:443 rect attrs | KEEP | numeric, unescaped |
| views/workflow.js:475 lane rect | KEEP | numeric (`i * LANE_H`) |
| views/workflow.js:479 tick line x1 | KEEP | numeric |
| views/workflow.js:483 tick text x | KEEP | numeric |
| views/workflow.js:493 path d | KEEP | numeric |
| views/workflow.js:500 path d | KEEP | numeric |
| views/workflow.js:507 m.status in class | KEEP | `wf-m-' + m.status` unescaped (line 509 holds the class; cite off by 2) |
| views/workflow.js:509 path d | KEEP | d path sits on the lines next to 509; substance right |
| views/workflow.js:513 plot width/height | KEEP | numeric |
| views/workflow.js:515 now line | KEEP | numeric |
| views/workflow.js:516 axis width/height | KEEP | numeric |
| views/workflow.js:518 now text x | KEEP | numeric |
| views/workflow.js:919 cls param | KEEP | caller literal; unescaped |
| views/workflow.js:1049 setHtml | KEEP | goes through dom.js:57 setHtml (innerHTML); compliant, no change |
| views/tasks.js:75 cls | KEEP | static class tokens (tasks.js:73) |
| views/tasks.js:100 cls | KEEP | static class tokens (tasks.js:113) |
| views/details.js:129 aria-pressed boolean | KEEP | boolean string; safe |
| views/details.js:227 data-done boolean | KEEP | boolean string; safe |
| ref.js:99 data-ref | KEEP | `esc(ref)` applied |
| log.js:376 addEventListener | KEEP | no inline handlers |
| graph/render.js:21 el() | KEEP | createElementNS and setAttribute; no innerHTML or style in graph/*.js |
| graph/minimap.js:15 el() | KEEP | same pattern; no innerHTML or style |

p04 totals: KEEP 27, WRONG 0, UNVERIFIED 0. Nothing here is an active injection hole; the esc() wraps are hardening.

## p05 agy-p05-handover-stale.md (corrected text for every KEEP row)

| doc line | verdict | evidence | corrected text |
|---|---|---|---|
| HANDOVER.md:1 date | KEEP | tasks.json:2 `"updated": "2026-10-15"` | "# HANDOVER: ... (2026-10-15)" |
| HANDOVER.md:3 split-net "tools drive job registration" | KEEP | docs/AUTHORITATIVE:1-2; HEAD-RUNBOOK:15 | "Sibling project: split-net (...). Not used for job registration here: roadmap-board is authoritative (docs/AUTHORITATIVE); register jobs with bin/roadmap job start or done (docs/HEAD-RUNBOOK.md)." |
| HANDOVER.md:8 "ALL workers STOPPED" | UNVERIFIED | CLAUDE.md (project) still says the person said STOP; tasks.json:1308 (R3.6 note) and :1340 say "person: go full power". Conflict; the person must say which holds | Do not edit until the person confirms |
| HANDOVER.md:9 "1601 OK" | WRONG | ran `python3 -m unittest discover -s tests -t . -q` with temp ROADMAP_HOME: "Ran 2324 tests ... FAILED (failures=4, expected failures=1)" | "tests: 2324 run, 4 failures, 1 expected failure on 2026-10-15 (re-run before relying on it)" |
| HANDOVER.md:9 "100 page runs" | KEEP | tasks.json:574 "81 page runs, 65 screenshots" | "make check-ui (headless Chrome smoke, 81 page runs, 65 screenshots)" |
| HANDOVER.md:11 board regenerated from split-net | KEEP | docs/AUTHORITATIVE:1 sync skips while the file exists | "Tasks and jobs are edited in this repo (docs/tasks.json, docs/jobs.json); split-net sync-rb-board.py skips here." |
| HANDOVER.md:11 hooks run jobs_auto.py | KEEP | HEAD-RUNBOOK:15 "hooks do not fire here" | "Hooks do not register jobs in this project; the head registers by hand with bin/roadmap job start or done (docs/HEAD-RUNBOOK.md:15-17)." |
| HANDOVER.md:11 rb-done.py closes task | KEEP | HEAD-RUNBOOK:19 "Never use ... rb-done.py" | "Close a task with bin/roadmap task done <TASK>; close a job with bin/roadmap job done <jid> --tokens <K> (docs/HEAD-RUNBOOK.md:17-19)." |
| HANDOVER.md:12 autonomy.json from split-net | KEEP | local docs/autonomy.json exists (436 B); AUTHORITATIVE:1 | "Work limit (weekly): stop at 95% (local docs/autonomy.json; split-net sync is skipped per docs/AUTHORITATIVE)." |
| HANDOVER.md:21 tools/agy-queue.py path | KEEP | repo has no tools/agy-queue.py; split_net/tools/agy-queue.py exists; script default AGY_MAX 3 (matches) | "Run via ~/Works/split_net/tools/agy-queue.py (AGY_MAX env, default 3; HEAD-RUNBOOK uses AGY_MAX=2)." |
| HANDOVER.md:23 "everything is stopped now" | UNVERIFIED | same conflict as line 8 | Do not edit until the person confirms |
| HANDOVER.md:24 hooks register jobs | KEEP | HEAD-RUNBOOK:15-16 | "Register jobs by hand here: bin/roadmap job start ... then job done --tokens K (hooks do not fire in roadmap-board)." |
| HANDOVER.md:33 "no launcher at MVP" | KEEP | tasks.json R7.1 done; FACTS.md:696 `roadmap/services/launcher.py` opt-in | "Start in the GUI = queue request for an agent; an opt-in launcher exists (roadmap/services/launcher.py, R7.1 T4)." |
| HANDOVER.md:38 "22 seeded features" | KEEP | features.json has 23 entries (F23 linked at tasks.json:1077) | "23 features (docs/features.json)." |
| HANDOVER.md:41 "nothing queued" | KEEP | tasks.json: R7.5 partial, R7.12 partial, R7.16 partial, R3.6 todo, R7.22 todo | "5. NOT done / open (partial or todo): R7.5 row alignment, R7.12 copy-ref icon, R7.16 logs, R3.6 Cursor review, R7.22 backlog." |
| HANDOVER.md:42 register split-net as a project | KEEP | HEAD-RUNBOOK:19 "split-net is registered as its own project" | Remove the item (done). Keep hooks install and port 8765 items. |
| HANDOVER.md:42 tools/install-skills.py | WRONG | file exists in repo: tools/install-skills.py; FACTS.md:509 documents `skills install` | Keep the reference as written |
| HANDOVER.md:43 Opus final review (WP18) open | KEEP | tasks.json R4.4 status done | Remove "Opus final review (WP18)" from the NOT done list. |
| HANDOVER.md:43 Cursor review of Planner backend open | KEEP | tasks.json R3.3 status done | Remove the sentence. |
| HANDOVER.md:44 GUI Start not gated | KEEP | tasks.json R7.20 done; FACTS.md:803 | Remove the line. |
| HANDOVER.md:45 snapshot rows ~14 KB | KEEP | tasks.json R7.10 done | Remove the item. |
| HANDOVER.md:45 status hides features line | KEEP | tasks.json R7.11 done | Remove the item. |
| HANDOVER.md:46 Planner/Workflow gap-test lists | KEEP | tasks.json R7.4 and R7.8 done | Remove the item. |
| HANDOVER.md:46 plain-words strings pass | KEEP | tasks.json R7.7 done | Remove the item. |
| HANDOVER.md:46 aria fixes | KEEP | tasks.json R7.9 done | Remove the item. |
| HANDOVER.md:46 docs API.md citations | KEEP | tasks.json R7.6 done | Remove the item. |
| HANDOVER.md:48 /Users/ali paths | KEEP | commit a445f00 "docs: use ~ instead of absolute home paths" (FACTS.md:799) | Remove the item. |
| HANDOVER.md:53 split-net hooks drive job registration | KEEP | AUTHORITATIVE:1-2; HEAD-RUNBOOK:14-19 | "Claude Code settings: split-net hooks (~/Works/split_net/.claude/settings.local.json) do not drive roadmap-board; jobs are registered by hand (docs/HEAD-RUNBOOK.md)." |
| HANDOVER.md:61 Opus final review in resume order | KEEP | tasks.json R4.4 done | "Suggested order: cutover steps with the person -> remaining gaps in section 5." |
| HEAD-RUNBOOK.md:34 weekly stop from split_net | KEEP | local docs/autonomy.json exists; AUTHORITATIVE:1 | "Weekly stop 95% (local docs/autonomy.json; split_net's copy is not synced)." |

p05 totals: KEEP 26, WRONG 2 (tests count; install-skills reference), UNVERIFIED 2 (the STOP status at lines 8 and 23).

## Safe to apply

- p01: change the phases.js:105 row to a copy-Y row citing phases.js:97 and phases.js:110. Do not touch the others. work.js:107 waits until work.js stops moving.
- p02 (apply): render.js:213 add `aria-expanded="false"` on the folded card; render.js:191, :201 and :248 drop `role="button"` and `tabindex` on nodes with `data-wf-task=""`; render.js:305 add `aria-hidden="true"` to the edges group; render.js:150 add `aria-current="step"` on the Now node; minimap.js:67 add `aria-hidden="true"` on decorative rects.
- p02 (needs a decision first): render.js:239 fold `data-wf-item`, render.js:443 aria-disabled on dimmed nodes, render.js:433 describedby, viewport shortcuts (bare keys), workflow.js:630 aria-pressed (needs a button, not an anchor), and every graph.css contrast row (measure first).
- p03 (apply): onCsp skip `/api/v1/log` (log.js:335); wrap JSON.stringify in try at log.js:229 and log.js:238; hostOf and scrub strip query on relative URLs (log.js:92, :311); file:/// in pathOf (log.js:439); scrub() on the noteRequest path (log.js:450); one shared re-entrancy flag for the console wrappers (log.js:354, :384).
- p03 (do not apply): log.js:93 subdirectories (WRONG); log.js:294 and :229 (UNVERIFIED); log.js:410 and :424 need a design decision.
- p04 (hardening, low value): esc() on workflow.js:639 op, :440 it.status, :507 m.status, :919 cls. Other rows need nothing.
- p05 (apply to docs/HANDOVER.md and docs/HEAD-RUNBOOK.md after the person confirms): all 26 KEEP rows with the corrected text above. Do not apply the test count (2324 run with 4 failures; re-run after the other workers stop), do not apply install-skills removal, do not change the STOP status (lines 8, 23) until the person confirms.
