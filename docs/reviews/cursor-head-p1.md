Read-only check of snapshot trim and head list order. Findings stay in this message.

Byte-cap trim and client sort are the two spots. Reading those next.

Byte trim keeps the newest head rows. It never removes a row. The 40/5 count cut keeps the newest, then stores that window oldest-first. `head.js` paints that same window newest-first.

1. `roadmap/core/snapshot.py:324` — open rows are `_newest(open_rows)[:HEAD_OPEN_MAX]` (`HEAD_OPEN_MAX` is 40 at `:30`), then `[::-1]`. The newest 40 stay. The array order is oldest of that window first, newest open last.
2. `roadmap/core/snapshot.py:325` — done rows are the newest 5 (`HEAD_DONE_MAX` at `:31`), same reverse. Newest done is the last element of `rows`.
3. `roadmap/core/snapshot.py:288-290` — “newest” is string `ts`, then string `id`, descending. Equal timestamps rank `H9` ahead of `H10`.
4. `roadmap/core/snapshot.py:38` and `:335-338` — over `HEAD_BYTES_MAX` (8192) the only cut is `linked[].title` via `pop("title")` once. No `rows.pop`. Newest rows stay. If titles are absent or still too big, the head key ships over 8192.
5. `roadmap/core/snapshot.py:328-333` — `counts` are `len(shown_open)` / `len(shown_done)` of that same array. The badge matches the rows placed.
6. `roadmap/core/snapshot.py:296-297` — docstring matches the code: rows stay; titles drop once.
7. `tests/unit/test_head_snapshot.py:377-385` — `test_titles_then_rows_are_dropped_to_fit_and_prog_stays` expects `len(rows) < 40` with `counts.open == 40` under the byte cap. Current trim never shortens `rows`.
8. `tests/unit/test_head_newest.py:57-70` — expects a shorter id list and `H40` kept. `test_c` expects newest-first ids. The snapshot array is oldest-first after `:324` `[::-1]` (`expectedFailure`).
9. `web/js/views/head.js:301-312` — `sortRows` sorts ascending by `Date.parse(ts)`, then numeric id. `sort === "old"` keeps that. Every other value, including default `"new"`, `reverse()`s to newest-first.
10. `web/js/views/head.js:173-175` and `:822` — the Order control and the hash default are `"new"`. `"old"` is the only oldest-first path.
11. `web/js/views/head.js:526-545` — cards and list both render that one sorted array. Snapshot oldest-first order is not what the screen shows.
12. `web/js/views/head.js:45-47` and `:828` — the screen paints only `snapshot.head.rows`. It does not drop or reorder by a second trim. Ledger rows older than the 40/5 window never appear.
13. Tie-break: `snapshot.py:290` uses string id (`H9` > `H10`). `head.js:307` uses numeric id (`H10` > `H9`). Equal `ts` can disagree between the count cut and the painted order.

