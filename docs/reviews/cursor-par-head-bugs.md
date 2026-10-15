Read-only hunt on the head service, head ops, and snapshot head path. Findings stay in this chat.

Working tree already touches these files. Comparing the head path against the spec and the fold rules.

Twelve bugs still in the head store, the head ops, and the snapshot head key.

1. `roadmap/services/head.py:67` — `clean_text` treats every unclosed `[` as a cut-off mask. A short message such as `fix arr[i] and the draft` is stored as `fix arr`. This runs on capture, reply, and spool adopt, even when the text is under 8000 characters. Fix: drop a trailing `[` only when the 8000-character slice actually split a mask (`[secret]`, `[email]`, `[number]`).

2. `roadmap/services/head.py:234` — Adopt reads the spool with `splitlines()`. `json.dumps(..., ensure_ascii=False)` leaves U+2028, U+2029, and U+0085 inside the text, and `splitlines()` breaks that one record into two. The pieces fail `json.loads` and are discarded (`continue` at line 245), not put back. Fix: split the spool on `\n` only, and keep any line that does not parse.

3. `roadmap/services/head.py:249` — A crash after the `head.jsonl` append and before the `head-text.jsonl` append still records the nonce. The next adopt sees the nonce, counts the line as adopted, and never writes the verbatim. Fix: if the nonce is already in the ledger, append the text when that id has no text line; only then drop the spool line.

4. `roadmap/services/head.py:230` and `:297` — The writer holds the directory lock and a blocking exclusive flock on the spool for the whole adopt. `capture` treats a directory-lock timeout as "spool it", then `_spool_append` needs that same flock and the same already-spent timeout. The hook budget expires and the prompt is written nowhere. Fix: copy the spool lines out under the flock, release the flock, then append to `head.jsonl`. Give the spool append its own timeout.

5. `roadmap/services/head.py:411` — `latest_hook_entry` reads only `head.jsonl`. A spooled hook capture is invisible, so the Stop path (`hooks.py` around the `set_reply` call) attaches the assistant reply to the previous entry of that session when it falls inside the 5-second slack, or drops the reply. After adopt, the new entry has no reply. Fix: consider the newest spooled hook line for that session id as well.

6. `roadmap/services/headops.py:241` — `head.log` with `--bind` returns success and `bound: []` when `capture` spools. The spool payload (`head.py:300`) has no link field, so the later adopt has nothing to bind. Fix: keep the refs on the spool object and apply them when that entry is adopted, or refuse the call instead of reporting success.

7. `roadmap/services/headops.py:331` — Split creates both children, then `_guard_status` runs. An agent splitting an entry the person already marked done gets `agent_refused` after the two new entries exist; the parent stays done and there is no undo. If `capture` spools, the parent is still marked merged and the undo steps skip the `None` ids, so the children show up later and cannot be declined. Fix: run the guard before any `capture`. If an id is missing, do not mark the parent merged.

8. `roadmap/services/headops.py:157` — Undo stores `status: "open"` when the entry had no manual status. The fold keeps `manual == "open"`, and auto-done only runs when `manual is None`. After undoing `needs-you`, `declined`, or a confirm, an ask whose links are all done stays `bound` and never returns to `done?`. Fix: teach the fold that `open` clears the manual override, and use a different stored value when a reopen must stay open.

9. `roadmap/core/snapshot.py:173` — `head_link_state` only writes `task:`, `job:`, and `issue:`. `head convert … backlog` binds `backlog:BL.n`. A running job writes `task:BL.n = running`. The ask stays `bound`, `prog` (line 211) ignores it, and `askOf` (line 346, via `ask_backlinks`) only indexes `task:`. The same hole is `sub:`, `feature:`, `question:`, `doc:`, `commit:`, and `review:`. Fix: alias `backlog:` and `sub:` to the task state, and resolve the other kinds to `done` or `open` the way the spec fold describes.

10. `roadmap/core/snapshot.py:226` — `head_row` omits `amber`, `sid`, and `acct`, and sets `dup` to the id string (line 248). The list paints amber only from `row.amber`, the session filter compares `row.acct || row.sid`, and Merge runs only when `row.dup.id` is set. A 45-minute unhandled duplicate shows no amber and no Merge. Fix: copy `amber` when true, copy `sid` and `acct`, and send `dup` as `{id, score}`.

11. `roadmap/core/snapshot.py:288` — `_newest` tie-breaks on the id string. `"H9" > "H10"`, so the higher id sorts as older. Import stamps every new entry with one `now` (`headimport.py` `_build`). Past 40 open rows, or 5 done rows in that same second, the cap keeps low numbers and drops `H10` and above. Fix: tie-break on the numeric id.

12. `roadmap/core/snapshot.py:330` — `doneUnacc` is `len(done_rows)`, so a person accept still counts. The Head alert is `N done, not accepted`, and it stays up after every done row is accepted. Auto-done and head-done rows should still count. Fix: count done rows whose id is not in `_accepted_ids`.

