Project sections and auto-sync drift — I'll read the poll loop and the snapshot/load path and report causes with file:line, a repro, and the smallest fix.

Sections drift because the 2 s loop is one shared snapshot, and several panes keep a second copy or an older build. Auto sync is a background usage read on a 120 s clock. The page only re-reads that file every 30 s. Nothing pushes.

## Findings

**1. The open section waits until every project is rebuilt.** `roadmap/http/routes.py:208-214` `projects()` calls `loader.load_snapshot` for every registered project and returns summaries with no ETag. `web/js/app.js:244-267` awaits that call before `GET /snapshot` for the page you are on.

Repro: two projects with a large `tasks.json`. Edit a task in the open project. Work and Roadmap stay old until both full builds finish, then the next 2 s tick.

Fix: on a project route, fetch that snapshot first, in parallel with `/projects`. Make `projects()` return id and name from the registry and skip `load_snapshot`.

**2. The ETag is hashed after the expensive build, and clock fields change it every call.** `roadmap/http/routes.py:96-101` drops only `server_time`. `roadmap/http/routes.py:136-144` returns 304 only after that hash. `roadmap/services/loader.py:36-55` always parses. `roadmap/core/parsers.py:177-188` sets `elapsed_s` from `now` for every running job, and `roadmap/core/snapshot.py:511` puts it in the body. `roadmap/core/head.py:226-230` sets `age_min` from `now`.

Repro: one job with status `running`. The access log shows `200` on `/snapshot` every poll, never `304`.

Fix: stat the data files and return 304 before `build_snapshot`. Leave `elapsed_s` and `age_min` out of that check. Agents already ticks elapsed on the client (`web/js/views/agents.js:187-198`).

**3. A write’s immediate refresh is dropped when a poll is already running.** `web/js/cmd.js:85-94` sets `doneAt` and calls `schedule(0)`. `web/js/app.js:279-297`: if `busy` is set, `loop` skips `refresh()`, then `schedule(2000)` or `schedule(30000)` clears that zero timer. The same clear hits route changes (`web/js/app.js:507-510`).

Repro: slow the server. Close an issue or move a plan card while the 2 s poll is in flight. The new value shows on the poll after that, or up to 30 s later in a background tab.

Fix: set `pendingRefresh` when a refresh is skipped or a timer is replaced. When `busy` clears, run `refresh()` once more.

**4. Auto usage sync never tells the page, and the first read waits a full interval.** `roadmap/commands/serve.py:63-64` starts `usage.run_loop`. `roadmap/services/usage.py:34` sets `DEFAULT_INTERVAL_S = 120`. `roadmap/services/usage.py:475-484` waits before every attempt, including the first. `roadmap/http/routes.py:217-218` `GET /api/v1/usage` only calls `usage.show()`. The only write is `POST /api/v1/usage/sync` (`roadmap/http/routes.py:221-235`). The client calls that only from the Sync button (`web/js/app.js:300-314`, `381-382`). The 2 s loop reads usage with `GET` at most every 30 s, and only after the snapshot work (`web/js/app.js:27-29`, `233-241`, `274-276`). After a keychain failure the background loop returns without a new reading for 6 hours (`roadmap/services/usage.py:39`, `353-354`).

Repro: `roadmap serve`, then change the account percent. Tokens can sit for two minutes. Right after start, the first automatic read is about 120 s out.

Fix: call `sync_once` once before the first wait. On the client, read usage in the same `refresh()` as the snapshot.

**5. The Tokens band and the limit rows are two stores.** The band is `store.usage` from `GET /usage`. Spend, weekly stop, and block state are `snap.meters` / `snap.weekUse`, filled when the snapshot is built (`roadmap/services/limits.py:32`, `183-195`; `web/js/views/tokens.js:43`, `57-74`). The band marks a reading stale at 240 s (`web/js/state.js:23`, `454-458`). Limit math still treats it as fresh for 1800 s. `syncUsage` updates the band and does not call `schedule(0)`, so meters wait for the next poll.

Repro: click Sync now. The top percent changes. The weekly-stop row changes on the next snapshot poll. Leave the page up after the server loop: meters move, the band stays on the old percent for up to 30 s.

Fix: have `syncUsage` call `schedule(0)`. Put the usage view on the same snapshot the meters use.

**6. A focused field freezes the whole main section while the shell keeps updating.** `web/js/dom.js:34-40` returns without writing HTML when focus is an `INPUT` or `SELECT` inside that node. `web/js/app.js:186-211` patches `nav`, `topbar`, and `main` separately, so badges move and the open list does not.

Repro: on Issues, Planner, or Tokens, focus a text field. Change a task in another terminal. The list stays until blur, then the next poll.

Fix: patch the list and leave the focused control alone.

**7. A project route refreshes one snapshot. The side list mixes that with a fresh summary.** `web/js/app.js:257-264` fetches only `route.id`. `web/js/views/projects.js:32-38` takes `running` from `/projects` and questions, blockers, and control from `store.snapshots`.

Repro: two projects, each with a running job. Open A. Finish B’s job. B’s row says Idle from the summary while B’s cached snapshot still has the job until you open All projects.

Fix: drive the panel from the summary fields, or revision-check every snapshot.

**8. The home card and the open section are two builds.** Same `projects()` build as finding 1, then a second `load_snapshot` per id (`web/js/app.js:265-268`). The card’s `running` is the first build. Agents and Roadmap use the second.

Repro: All projects, one short job. Refresh as it ends. The card says Running and Agents shows none, for one poll.

Fix: one build per project per poll. Hand that body to both the list and the section.

**9. Workflow and the drawer do not read the polled snapshot.** `web/js/state.js:226-314` keeps `head`, `tasks`, `jobs`, and `issues`. It drops `workflow`, `session`, `askOf`, and `project.path` (`roadmap/core/snapshot.py:518`, `536-544`). `web/js/views/details.js:189` reads `snap.session`, which is always missing. `web/js/views/workflow.js:25` and `114-130` fetch their own copy at most once per 5 s and do not call `render`.

Repro: a watching terminal and a queued task. The drawer never says a session is listening. Open Workflow and Work. Work updates on the 2 s poll. The diagram lags until its 5 s cache and the next app render.

Fix: copy `workflow`, `session`, `askOf`, and `project.path` in `normalizeSnapshot`. Delete the workflow cache.

**10. Expanded head text is a second response, cached for the life of the page.** `web/js/views/head.js:38` and `561-569` store `fullCache` and never drop it. The URL is `GET .../head?f=all&n=200&full=Hn`. `roadmap/http/routes.py:570-574` builds another full snapshot and sends no ETag. The list itself is capped at 40 open and 5 `done` rows (`roadmap/core/snapshot.py:30-31`, `301-302`). `declined` and `merged` are closed (`roadmap/core/head.py:17`) and are in neither list.

Repro: expand one head row. Edit that entry’s text in `head.jsonl`. The summary line changes on the next poll. The expanded body stays the first fetch after collapse and expand.

Fix: drop `fullCache` for that id when `snap.head` changes, and `getJson` again.

**11. A failed snapshot leaves the old rows up, and the shell still says connected.** `web/js/app.js:267-272` sets `snapshotErrors[id]` and leaves `store.snapshots[id]`. `web/js/app.js:247-255` sets `conn.ok` from `GET /projects` only. A head read that throws is swallowed (`roadmap/services/loader.py:58-66`), and `roadmap/core/snapshot.py:540-544` then omits `head` while tasks and jobs still load.

Repro: force one snapshot `500` after a good load. Work, Head, Issues, and Agents keep the last rows. Or `chmod 000` on `docs/head.jsonl`: Head clears, Work does not.

Fix: when `snapshotErrors[id]` is set, show a retry banner and the previous `fetchedAt`. On a head read failure, add an `errors[]` line and keep the previous `head` until a good read.

**12. Agents and Roadmap cut the same jobs differently, so a finished job vanishes in one section only.** Agents keeps the last 10 ended jobs, any age (`web/js/views/agents.js:11`, `70-76`). Roadmap’s phase strip keeps jobs ended within 30 minutes, at most 2 (`roadmap/core/snapshot.py:22-23`, `398-425`). Both come from one snapshot.

Repro: finish 3 jobs, wait 31 minutes. Agents still lists them. The phase recent strip is empty.

Fix: build the phase strip from the same `jobs` list, with one shared limit.

**13. A hidden tab polls every 30 s.** `web/js/app.js:292` and `503-504`. Showing the tab schedules one immediate poll. A change made while hidden waits.

Repro: hide the tab, append a head line or finish a job, wait 20 s, show the tab. Head and Agents are still old until that wake-up poll returns.

Fix: keep the 30 s hidden interval. Pair it with the file-stat 304 from finding 2 so the wake-up poll is cheap.

## Least-effort fix

Three edits, no new channel:

1. `web/js/app.js`: fetch the open snapshot in parallel with `/projects`. If `schedule(0)` fires while `busy`, set `pendingRefresh` and run one more `refresh()` when the in-flight call ends. Call that same `schedule(0)` at the end of `syncUsage`. Read `/api/v1/usage` inside that refresh, not after a 30 s gate.
2. `roadmap/http/routes.py` `projects()`: return registry id and name only. Stop calling `load_snapshot` there.
3. `roadmap/services/usage.py` `run_loop`: `sync_once` once, then wait `intervalS`. In `load_snapshot` / `_snapshot_reply`, if `If-None-Match` equals a token of file mtime and size, return 304 before `build_snapshot`.

Roadmap, Work, Head, Agents, Issues, Planner, and Tokens then share one body. Elapsed time stays on the Agents ticker.

