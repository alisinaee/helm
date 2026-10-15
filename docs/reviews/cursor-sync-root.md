Different sections showing different data means the refresh path splits somewhere. I’ll trace loader → snapshot → routes → client state and the two recent commits, then name the few root causes and a permanent fix.

Those two commits only changed the ETag and the follow-up poll. I’ll check what still splits the snapshot so sections can disagree.

Sections disagree because the page has no single snapshot generation. `311ad45` only keeps clock fields (`elapsed_s`, `age`, `age_min`, `server_time`) out of the ETag (`roadmap/http/routes.py:96-112`). `5040843` only queues one more `refresh()` when a poll is already in flight (`web/js/app.js:281-298`). Neither makes Overview, Work, Head, Agents, Tokens, and Roadmap read one body.

**Cause 1 — three stores, two builds.** Each poll, `projects()` calls `load_snapshot` for every project and keeps a summary (`roadmap/http/routes.py:221-226` into `web/js/app.js:249-250`). The open section then calls `load_snapshot` again (`roadmap/http/routes.py:231` into `web/js/app.js:266-269`). Those reads can straddle a write. Each URL has its own ETag cache (`web/js/api.js:7`, `59-66`), so one answer can be 304 while the other is new. A project route refreshes only `route.id` (`web/js/app.js:259-260`); every other `store.snapshots[id]` stays on its last body while the summaries move. The project list mixes them: running and progress from the summary, questions, blockers, and control from the snapshot (`web/js/views/projects.js:32-58`). Overview, Work, Agents, and Roadmap use the snapshot. Tokens also uses `store.usage`, fetched at most every 30s (`web/js/app.js:29`, `275-276`), while the meters on that same page come from the snapshot (`web/js/views/tokens.js:61-74`). Limit math treats the usage file as fresh for 1800s (`roadmap/services/limits.py:32`, `183-195`). The band marks that reading stale at 240s (`web/js/state.js:23`, `458`).

**Cause 2 — a 304 is stored as a new read.** `getJson` returns the previous body (`web/js/api.js:59-60`). `refresh` still runs `normalizeSnapshot(res.data, now)` (`web/js/app.js:269`), so `fetchedAt` moves. `pendingValue` then drops the optimistic value (`web/js/cmd.js:32`) and the section paints the pre-write body. After `311ad45` that is the normal poll whenever only clocks changed, and it is also what a follow-up poll does when it races the write.

**Cause 3 — the open section can skip the paint.** `patch` writes nothing when focus is an input or select inside that node (`web/js/dom.js:34-40`). Nav and the top bar are other nodes and still update (`web/js/app.js:187-212`). Badges move. Work, Head, Tokens, or Roadmap stays on the previous HTML until blur.

**Cause 4 — Head text is a private cache.** The list is `snap.head` (`web/js/state.js:313`). An open row is `GET .../head?full=`, which builds another snapshot (`roadmap/http/routes.py:616`) and keeps it in `fullCache` for the life of the page (`web/js/views/head.js:41`, `570-578`). The summary line updates. The verbatim body does not. A failed read of `head.jsonl` omits `head` and still returns tasks and jobs (`roadmap/services/loader.py:58-66`, `roadmap/core/snapshot.py:560-564`), so Head clears and Work does not.

**Fix — one revision, one body, every section reads it.**

1. `projects()` returns registry id and name only. Remove the `load_snapshot` loop at `roadmap/http/routes.py:221`.
2. In `_snapshot_reply` (`roadmap/http/routes.py:148-156`), stat the project data files and the usage file before `build_snapshot` (`roadmap/services/loader.py:36-55`). The ETag is that revision. On a match, return 304 and do not build.
3. On 304, `web/js/app.js:269` must leave `store.snapshots[id]` and `fetchedAt` unchanged. Settle `web/js/cmd.js:32` only when the revision changes.
4. Copy the usage percents onto that same snapshot in the one build. Tokens and the top bar read them. Drop the 30s `store.usage` paint at `web/js/app.js:275`.
5. `web/js/dom.js:40` still writes the section and puts the focused value back. It does not skip the node.
6. Key `fullCache` by that revision and drop the entry when the revision changes (`web/js/views/head.js:572`). Take the row text from the snapshot already built. Do not call `load_snapshot` again at `roadmap/http/routes.py:616`.

