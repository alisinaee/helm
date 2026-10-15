| file:line | what it does | drops newest? | fix |
|---|---|---|---|
| roadmap/core/snapshot.py:190 | Trims links to first 6 (HEAD_LINKED_MAX) for link resolution | Yes | Slice `[-HEAD_LINKED_MAX:]` if newest links preferred |
| roadmap/core/snapshot.py:201 | Truncates resolved link title to 60 (HEAD_TITLE_MAX) characters | No | None needed |
| roadmap/core/snapshot.py:224 | Truncates head entry summary to 60 (HEAD_SUM_MAX) characters | No | None needed |
| roadmap/core/snapshot.py:237 | Trims visible links to first 3 (HEAD_LINKS_MAX); excess counted in more | Yes | Slice `[-HEAD_LINKS_MAX:]` if newest links preferred |
| roadmap/core/snapshot.py:262 | Trims previous session records to at most 3 (HEAD_PREV_MAX), newest first | No | None needed |
| roadmap/core/snapshot.py:287 | Sorts head entries newest first by timestamp ts, then id | No | None needed |
| roadmap/core/snapshot.py:298 | Filters entries into open and done lists, dropping closed non-done entries (declined, merged) | Yes | Include declined and merged rows in snapshot rows |
| roadmap/core/snapshot.py:328 | Trims open rows to 40 (HEAD_OPEN_MAX) newest entries, reversed to oldest first | No | None needed |
| roadmap/core/snapshot.py:329 | Trims done rows to 5 (HEAD_DONE_MAX) newest entries, reversed to oldest first | No | None needed |
| roadmap/core/snapshot.py:336 | Drops titles from resolved links when compact JSON exceeds 3072 bytes (HEAD_BYTES_MAX) | No | None needed |
| roadmap/core/snapshot.py:341 | Pops oldest done row, then oldest open row while compact JSON exceeds 3072 bytes (HEAD_BYTES_MAX) | Yes | Increase HEAD_BYTES_MAX or truncate row fields instead of dropping rows |
| web/js/views/head.js:94 | Trims previous sessions in head banner to first 3 | No | None needed |
| web/js/views/head.js:240 | Trims visible bound link chips to first 2 (BOUND_MAX) | Yes | Slice `[-limit:]` if newest links preferred |
| web/js/views/head.js:273 | Trims attachment assets to first 20 | Yes | Slice `[-20:]` if newest assets preferred |
| web/js/views/head.js:290 | Truncates verbatim summary text to first 240 (SUM_SHOW) characters | No | None needed |
| web/js/views/head.js:302 | Sorts rows by timestamp then numeric ID; defaults to newest first | No | None needed |
| web/js/views/head.js:432 | Trims suggested bind task refs to first 2 | UNKNOWN | UNKNOWN |
| web/js/views/head.js:523 | Filters rows by tab and search criteria, then sorts via sortRows | No | None needed |
