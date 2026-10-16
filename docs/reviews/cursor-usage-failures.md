Read-only review of the eight usage failures. I’ll read the failing tests and `roadmap/services/usage*.py`, then list each assertion, cause, and smallest fix in this message.

Tests and the usage service are in view. Next I’ll run the eight failures and read the store/push/sync paths they hit.

Same cause for every red test: `view()` drops `weeklyPercent` once `weeklyResetsAt` is at or before the real clock. The store still has the number. Today (2026-10-16 08:20 UTC, 11:50 +0330) is past each weekly reset these tests write. The 5-hour reset was already moved forward in `fresh_reply()` after 2026-10-13; the weekly reset was left at 2026-10-16 08:00 UTC, which passed at 11:30 +0330.

`view()` does this at [roadmap/services/usage.py](roadmap/services/usage.py) lines 346–350. `GOOD_REPLY["seven_day"].resets_at` is `2026-10-16T08:00:00+00:00` ([tests/unit/test_usage_collector.py](tests/unit/test_usage_collector.py) line 21). Both `fresh_reply()` helpers only rewrite `five_hour`.

Do not change `view()`. [tests/unit/test_usage_truth.py](tests/unit/test_usage_truth.py) requires a passed reset to publish null. Mirror checks and raw `usage.json` checks stay green because they read the stored record.

1. [tests/unit/test_usage_store.py](tests/unit/test_usage_store.py):95 `test_sync_stores_usage_with_schema_and_no_last_error` — `sync_once` returns `view()` of a reading whose weekly reset is `2026-10-16T08:00:00+00:00`, so `weeklyPercent` is null. `fiveHourPercent` 17 still holds (`fresh_reply` puts that reset 3 hours ahead). Smallest fix: in `fresh_reply()` at lines 25–28, set `seven_day.resets_at` the same way as `five_hour` (now plus a few hours).

2. [tests/unit/test_usage_store.py](tests/unit/test_usage_store.py):121 `test_failed_sync_keeps_last_good_values_and_records_reason` — `show()` runs that same view over the stored 62.4. Same fix as 1.

3. [tests/unit/test_usage_backoff.py](tests/unit/test_usage_backoff.py):127 `test_success_clears_the_code_and_the_backoff` — the success call passes `now=at(6*3600+5)` (2026-10-15 15:00:05 UTC), which is still before that reset, but `_result()` calls `view()` with the wall clock and drops 62.4. The fetch is `UsageCase._fake_fetch`, so this is the store `fresh_reply`, not the copy in the backoff file. Same fix as 1. Threading `moment` into `view()` would turn this one assert green and leave the others red.

4. [tests/unit/test_usage_backoff.py](tests/unit/test_usage_backoff.py):139 `test_failure_keeps_the_last_good_values` — `show()` with no injected clock nulls the weekly percent from that same stored reset. Line 140 (`fiveHourPercent == 17`) and line 141 (`syncError == denied`) are behind this assert. Same fix as 1.

5. [tests/unit/test_usage_store.py](tests/unit/test_usage_store.py):202 `test_push_stores_rate_limits_and_mirrors` — the push sets `resetsAt` to `2026-10-16T08:00:00Z` (the same instant). `view()` nulls 61. The autonomy file on line 206 still has 61; that line is not what fails. Smallest fix: use a reset after now, and point line 203 at that same string.

6. [tests/unit/test_usage_store.py](tests/unit/test_usage_store.py):356 `test_push_then_show_json` — `usage show` is `view()` of that same `Z` reset, so `data.usage.weeklyPercent` is null. Same literal change as 5 (the push body on lines 350–351).

7. [tests/unit/test_usage_backoff.py](tests/unit/test_usage_backoff.py):185 `test_stores_a_manual_entry_and_returns_the_view` — `weeklyResetsAt` is `2026-10-16T08:00:00+01:00` (07:00 UTC). `view()` nulls 61. `fiveHour` has no reset, so 12 would still match. Smallest fix: pass a reset after now, and point line 188 at that same string.

That is every `weeklyPercent` assert in `tests/unit/test_usage_*.py` that reads the public view while the weekly reset is already past. The sixth named test plus `test_failed_sync_keeps_last_good_values_and_records_reason` are the two beyond the first four sync/show cases. `test_show_plain_text` (line 367) pushes no `resetsAt`, so the view keeps 61 and `week 61%` still matches. Collector parse tests never call `view()`.

