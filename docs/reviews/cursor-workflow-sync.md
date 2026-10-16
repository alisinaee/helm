I'll read the workflow marker, the four views, snapshot job fields, and the poll loop, then list ranked causes in this message.

Marker logic is split across graph model, views, and the poll loop. I'll read those paths next and rank the real causes.

The live-job rule is already tested. Next I’ll compare how each view picks “current” against the snapshot fields the poll actually delivers.

The graph pins Now to the newest running job. I’ll compare that with how Table, Timeline, Phases, and Agents pick the current row.

Workflow fetches its own snapshot, separate from the poll. I’ll check whether Table, Timeline, and Agents read a different “current” field.

The spec and the graph disagree on what “current” means. I’ll pin the exact lines on disk before ranking causes.

Line numbers shifted while I was reading. I’ll recheck the spots I’ll cite so the findings match the file on disk.

The Map flag is the task that owns the newest running span, or nothing. The roadmap position (first doing task, otherwise the first todo after the last done) is never computed, and Table, Timeline, Agents, and Phases do not read that flag.

**Repro.** Tasks: `P1.1` done, `P1.2` partial with no job, `P1.3` todo. Jobs: `J-old` running on `P1.1`, `started` 8 days ago; `J-new` running on `P1.3`, `started` now. Open Workflow Map, then Table, Timeline, Agents, and the phase list. The flag sits on `P1.3`. Drop `J-new` and the flag disappears while Agents and the phase chip still show `J-old`. Start `J-new` again within 5 seconds of the last workflow fetch: Agents updates on the 2-second poll; the Map keeps the old flag until a later fetch and a later paint.

1. **[P1] Now is the newest running job, or null** — `web/js/graph/model.js:122` (`currentOf`), drawn only when live at `web/js/graph/render.js:425`. `liveTaskOf` (`model.js:104`) keeps the running span with the greatest `start`. A partial frontier with no job gets no flag. `web/js/graph/layout.js:621` then treats a null `current` as `"start"`, so Now (`N`) and the 300-node cap sit on Start. `docs/WORKFLOW-V2-SPEC.md:40` defines the point as the first doing task, else the first todo after the last done, else End (`taskStatus` at `model.js:73` already maps `partial` to doing). **Fix:** `currentOf(order)` returns that frontier. Draw the flag on it. Leave the running pulse separate.

2. **[P1] The flag’s job list is shorter than Agents and Phases** — `roadmap/core/snapshot.py:162`. Spans skip a job with no `started`, skip a running job whose `started` is older than 7 days (`:165`, because a running job has no end), then keep the newest 200 (`:171`). `running_jobs` (`:504`), `phase.running` (`:530`), and `agents.running` (`:638`) keep every `status == "running"` job. The graph reads only `workflow.spans` (`model.js:201`, and `:240` drops a span whose task id is missing). **Fix:** put every running job into `spans` before the 200-cut.

3. **[P1] The poll and the Workflow cache are two snapshots** — `web/js/app.js:292` writes `normalizeSnapshot`, which has no `workflow` field (`web/js/state.js:225`). Map, Table, and Timeline read a private cache (`web/js/views/workflow.js:143`). That fetch is skipped for 5 seconds (`:147`) and does not paint when it finishes (`:134`). The loop paints immediately (`app.js:315`). Agents and Phases therefore show the new `jobs` while the flag still uses the previous spans. The full-screen map uses the same cache (`app.js:182`). **Fix:** keep `workflow` on the normalized snapshot and render Workflow from that object. Delete the cache.

4. **[P1] Table and Timeline do not read the Map cursor** — `web/js/views/workflow.js:1149`. The Map calls `buildGraph`. The Timeline draws a clock line at `nowMs()` floored to 30 seconds (`:106`, `:640`) and pulses every bar with no end (`:495`). The Table marks every task that has a live job in the window as running (`web/js/views/wf_table.js:79`) and builds rows only from those jobs, plus queue and blocked items. `P1.2` with no span has no row. The legend line “You are here (Now)” is Map-only (`workflow.js:1104`). **Fix:** one current task id on the snapshot. The table row and the timeline scroll target use it. The clock line stays a clock.

5. **[P2] Several running jobs: latest start wins on the Map, the whole set shows in Agents** — `model.js:110` versus `web/js/views/agents.js:54`. Agents sorts every `snap.running` job, newest start first (`:69`), and marks no row. A worker that started after the lead takes the flag; the lead stays the tree root. **Fix:** the shared current id is the frontier task. `aria-current` goes on the Agents row for that task.

6. **[P2] Phases show a running count, not the position** — `web/js/views/phases.js:3`. A running job does not open its phase. The chip is `phase.runningCount` (`:46`). Task chips are `phase.running` plus recent ids (`:72`). The partial frontier with no job is unmarked; an old running job lights a different phase. **Fix:** open the frontier task’s phase and mark that row with the same id.

7. **[P2] Parallel brackets and the flag use different rules** — `model.js:351`. A bracket member is a non-done task that is doing, or that owns any running span. The flag is only the newest running span (`:364`). Two partials draw a bracket while the flag sits on another task, or on nothing. **Fix:** the bracket marks tasks that are doing together. The flag marks the frontier only.

8. **[P2] The same task is “doing” on the Map and “todo” on the Timeline card** — `web/js/views/workflow.js:125`. `cardClass` leaves `partial` in the todo class. `taskStatus` (`model.js:73`) maps `partial` to doing. **Fix:** treat `partial` as doing in `cardClass`.

9. **[P2] A Map filter moves Now; the other views ignore it** — `model.js:364`. `liveTaskOf` runs on the filtered task list. Hiding the running task sets `current` to null, and layout snaps to Start. Table, Timeline, Agents, and Phases still show that job. **Fix:** compute the frontier on the full task list. Filters only hide nodes.

10. **[P2] The live test locks this rule in** — `tests/web/test_wf_now_live.py:53`, `:60`, `:69`. No running job must yield `current: null`. The newest running job must win. A frontier fix fails those tests. **Fix:** assert the frontier id, and assert the flag still hides only when you intentionally have no current task.

