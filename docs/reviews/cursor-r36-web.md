Read-only review of the listed web JS. Findings stay in this chat; no plan or report file.

Real bugs only.

1. `web/js/graph/model.js:114` — `currentOf` does `"task:" + order[last].id` when `last` is still `-1`. Any kept set with a deferred task and no done or todo task throws, while `started` is true if any task in the project is done. Map filter `defer`, or a phase that only has deferred work, replaces the section with the error banner. Fix: if `last < 0`, return `"end"` (or that deferred task’s id).

2. `web/js/views/workflow.js:787` and `:803`, with `web/js/dom.js:38` — the Map SVG is mounted into an empty host and is not part of the HTML string. `patch` skips when that string is unchanged, and `mountMaps` returns if the host already has a child. A status, title, or Now change that does not change node count, cap text, or (on a phone) the phase chip leaves the old diagram up. Fix: put a fingerprint of ids, statuses, titles, and Now on the host so the shell changes, or replace the SVG when `pendingMap` differs.

3. `web/js/graph/viewport.js:407` — `pointercancel` calls `gest.up(id, 0, 0, t)`. A press that never moved is a tap (`:152`). A second tap within 300 ms zooms 2× at the origin (`:155`), and a lone cancel stores `taps.last` at `(0,0)`, so the next tap in the corner double-zooms. Fix: drop that pointer and reset the pinch without tap or zoom.

4. `web/js/graph/render.js:383` — End is drawn as `"End"` and `""`. `buildGraph` sets `end.label` to `"n left"` (`model.js:387`), and the comment at `render.js:249` says the pill shows that. Fix: pass `g.end.label` as the subtitle.

5. `web/js/graph/render.js:115` — Start’s date is `toISOString().slice(0, 10)` (UTC). The timeline uses local hours. Just after local midnight the pill shows the previous day. Fix: format with local `getFullYear` / `getMonth` / `getDate`.

6. `web/js/views/details.js:208` — the on-screen launch line is `launchLine(redactPath(path))` with no shell quotes. Copy uses `shellQuote` (`:207`). A path with spaces or `;|&$` is a different command if someone copies the `<code>` text. Fix: show `launchLine(shellQuote(redactPath(path)))`, or show the path alone and not a `cd … &&` line.

