Read-only review of `2b83d5b..a36834f`. I'll pull the commit list and diffs, then list only real bugs.

Shell was blocked. Retrying the commit range read-only.

Bugs in `2b83d5b..a36834f` (line numbers on the current tree):

1. **`roadmap/core/snapshot.py:345`** — `doneUnacc` is every painted done row (`len(pairs) - len(opened)`). A person confirm sets `acc` (`snapshot.py:234`), and the alert at `web/js/views/head.js:132` says "N done, not accepted", so the alert stays after every done row is accepted. **`web/js/views/head.js:99`** lets that number through when it is `<=` all done rows, so the clamp ignores the unaccepted rows it already counted. Fix: count painted done rows whose id is absent from `_accepted_ids`, and compare the server number to that unaccepted count. Update `test_counts_follow_the_fold` (it expects 1 for person-done H2).

2. **`roadmap/services/headops.py:433`** — `_h_review` writes `status=open` and never calls `_check_real_bind`. **`roadmap/services/headops.py:307`** — `_h_set` can write `needs-you` on a head-closed ask the same way. A closed ask bound only to `task:R7.31` becomes open and still only on the umbrella. Fix: call `_check_real_bind` with the new status and the current links before both updates.

3. **`roadmap/core/head.py:150`** — a mentioned `R7.31` scores 1.0, and **`web/js/views/head.js:852`** sends `head.bind` with that single ref. **`roadmap/services/headops.py:159`** rejects an open ask bound only to the umbrella, so the suggested Bind button always errors. Fix: drop umbrella ids from `suggest_binds` when they would be the only ref, and send that button to `head convert`.

4. **`roadmap/http/routes.py:157`** — a matching file revision returns 304, and **`web/js/app.js:268`** keeps the old snapshot. Age and stale are fixed at build time (`roadmap/core/head.py:231`, copied at `roadmap/core/snapshot.py:228`) and the card prints those fields (`web/js/views/head.js:419`). On a quiet board a 2-hour ask never turns stale. Fix: derive age and stale (120 min) from `row.ts` in the view, and keep the 304.

