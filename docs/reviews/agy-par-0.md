| file:line | problem | fix |
| --- | --- | --- |
| roadmap/core/snapshot.py:331 | `_newest(open_rows)[:HEAD_OPEN_MAX]` drops open entries beyond 40; newest entries are kept via `_newest`. | UNKNOWN |
| roadmap/core/snapshot.py:332 | `_newest(done_rows)[:HEAD_DONE_MAX]` drops done entries beyond 5; newest entries are kept via `_newest`. | UNKNOWN |
| roadmap/core/snapshot.py:344 | In byte-budget loop exceeding HEAD_BYTES_MAX, `done_at` selects oldest done row to drop first; newest done entries are kept. | UNKNOWN |
| roadmap/core/snapshot.py:345 | In byte-budget loop when no done rows remain, `done_at` defaults to 0 and `rows.pop(0)` drops oldest open row; newest open entries are kept. | UNKNOWN |
| roadmap/core/snapshot.py:301 | Entries with closed statuses other than `"done"` are excluded from `open_rows` and `done_rows`, dropping them unconditionally; newest are not kept. | UNKNOWN |
| roadmap/core/snapshot.py:290 | `_newest` sorts by `(str(ts or ""), str(id or ""))` descending; lexicographical sort on numeric IDs can misorder ties/missing ts so newest may not be kept. | Sort by parsed timestamp and numeric ID or UNKNOWN. |
| roadmap/core/snapshot.py:266 | `_head_sessions` drops session start records exceeding HEAD_PREV_MAX (3); newest sessions are kept. | UNKNOWN |
| roadmap/core/snapshot.py:240 | `head_row` truncates links to HEAD_LINKS_MAX (3); newest are not kept (preserves first in list order). | UNKNOWN |
