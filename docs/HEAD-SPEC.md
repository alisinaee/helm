# Head section (R7.31, F25). Opus design, 2026-10-15. Source: docs/HEAD-SECTION-REQUEST.md

Head answers one question: "what did the person ask or decide, what did it become, and is it done?" It is the
persistent memory of the person's words. A new chat or account runs `/head`, reads `roadmap head brief`, and nothing needs
re-explaining.

## 1. Principles
1. **Two capture paths.** The hook is the safety net: every typed message is logged with no AI work. The head is the
   brain: it read the message, so its own one-line triage (kind, summary, binding) is cheap and accurate. A missed
   triage is still visible, as "unhandled 2 h".
2. **Append-only.** A hook appends one line and never rewrites. State is a pure fold of the lines, and the history is
   free.
3. **Status comes from links.** A bound ask moves with its tasks, issues and jobs. The head only says "done" when
   nothing is linked. Only the person accepts.
4. **Verbatim text stays out of git** (the repo is public). Summaries are committed; the full text stays local (0600).
5. Stdlib only, additive, old files parse unchanged. CSS ≤1.2 KB (the total is 70.5 KB of the 72 KB cap).

## 2. Data model
**Files** in the project's data dir (docs/):
- `head.jsonl` (committed): entries, updates and session records. Cap 5000 entries, about 300 B each.
- `head-text.jsonl` (added to .gitignore, mode 0600): `{"id":"H12","text":"<redacted verbatim ≤8000 chars>"}`.
- `head-spool.jsonl` (git-ignored): entries the hook wrote while the lock was busy, still without ids. The next
  writer adopts them in order.

**Records** (one JSON object per line; `v:1`; unknown `t` or a higher `v` is skipped, never fatal):
```
{"v":1,"t":"e","id":"H12","ts":"2026-10-15T09:12:03Z","src":"hook|cli|gui|import","sid":"a1b2c3d4","acct":"B",
 "kind":"ask","sum":"≤100 chars","len":812,"h":"sha1:12hex","from":"H9"?}
{"v":1,"t":"u","id":"H12","ts":"..","by":"head|person|auto","set":{"status":"bound","kind":"bug","sum":"..",
 "into":"H9"},"link":["+task:R7.31","-issue:I4"],"note":"≤160"}
{"v":1,"t":"s","ts":"..","sid":"a1b2c3d4","acct":"B","model":"Opus 5.5","ev":"claim|start|end","usage":{"h5":41,"wk":63}}
```
- **Ids:** `H1`..`H9999`, assigned under the data-dir lock (`lock.locked`, a 0.2 s timeout in the hook; on a timeout
  the entry goes to the spool). `sid` is the first 8 hex digits of sha256(session_id), so the raw id is never stored.
  `acct` is a label the person gives (A, B …); it is never an email.
- **Kinds:** `ask | decision | rule | bug | preference | question | review | info`.
- **Status:** `new → understood → bound → doing → done | declined | needs-you | merged`. `accepted` is a separate
  date that only the person sets, as with features.
- **Link refs:** `task:R7.31 sub:R7.31.s2 issue:I4 feature:F25 question:Q3 backlog:R8.9 review:docs/reviews/x.md
  rule:7 doc:docs/HANDOVER.md#2b commit:c23a5f1 job:j599`. At most 6 links per entry. The kinds match refs.py, plus
  `ask` and `review`/`rule`/`doc`/`commit`.

**Fold** (pure, in `roadmap/core/head.py`), first match wins:
- `merged`, `declined` or `needs-you` when one of them is set.
- `done` when it is set by hand, or when every link is done (task done, issue closed, question answered, review file
  exists, commit present). Auto-done shows the "done?" chip until the head confirms it.
- `doing` when any linked task is doing or partial, or a job runs on it.
- `bound` when it has at least one link.
- `understood` when the head triaged it (kind and summary set by the head).
- `new` otherwise.

The fold also derives:
- `age`: time since `ts` while the entry is new or understood.
- `stale`: unhandled for more than 2 h (amber after 30 min); the thresholds are config `head.staleMin` 30/120.
- `carried`: open, and from a session older than the current head's.
- `dup`: a suggestion only (see section 6).

## 3. Capture
**UserPromptSubmit hook** (new branch in `services/hooks.py`; added to the `EVENTS` list in hooks_install.py):
- **Payload:** `session_id`, `transcript_path`, `cwd`, `hook_event_name`, `prompt`, `permission_mode`. The project
  comes from `cwd`, as for the other events. The hook stays off unless the project config has `headCapture: true`.
- **Skipped:**
  - empty text, or acks of 3 words or fewer (ok, yes, go, continue, thanks);
  - text starting with `<task-notification`, `<system-reminder` or `<command-`;
  - a bare slash command with no args (`/head`, `/clear`), which is logged as a session `start` record instead;
  - text starting with `//nolog`.
- **Writes:** redact (section 7), then one `e` line with the heuristic kind and summary, plus one text line.
  Budget 0.3 s, fail-open: it never blocks or delays the prompt and never returns `decision:block`.
- **Reply:** `additionalContext`, one line of 120 chars or less:
  `head: logged H15 (ask?). triage: roadmap head t H15 <kind> "<sum>" [refs]`. Add ` · 2 untriaged` when others are
  waiting. `head.hint: false` turns it off.

**SessionStart** (existing `_session_start`, within the RULE_CHARS budget) adds up to 2 lines:
`head: 4 open asks (H9 3d, H12 2h …), 1 needs-you. Run roadmap head brief.`

**Manual** (head or person): `roadmap head log "<verbatim>" --kind decision --sum ".." --bind task:R7.31`. The head uses
it for decisions given in a reply ("yes" to "commit?"), which the hook skips: `"yes: commit WIP B+D"`.

**Backfill** (optional, person OK, head only, never workers: it reads ~/.claude):
`roadmap head import --transcript <path> [--dry-run]` reads the user text blocks of a Claude Code transcript JSONL and
skips tool_result and meta lines. `head import --doc docs/HANDOVER.md --section 2,2b` seeds rules and decisions as
`done` and bound to `doc:`.

## 4. CLI (`roadmap/commands/head.py`; output follows the agent grammar: `ok ..`, `next: ..`)
| Command | Output |
|---|---|
| `head log "<text>" [--kind K] [--sum S] [--bind REF..]` | `ok H15 ask new. next: roadmap head t H15 ..` |
| `head t H15 <kind> "<sum>" [REF..] [--status S]` (triage, one call) | `ok H15 ask bound task:R7.31` |
| `head list [--open\|--unhandled\|--doing\|--needs\|--done\|--all] [--kind K] [--n 20] [--q text]` | one line per entry: `H15 ask   bound   2h R7.31,+1  Head section design` |
| `head show H15` | summary, verbatim, links with their states, history (≤20 lines) |
| `head set H15 status=declined note=".."` / `bind` / `unbind H15 REF` | `ok ..` |
| `head split H15 "<sum a>" "<sum b>"` | new H16, H17 with `from:H15`; H15 becomes merged |
| `head merge H16 --into H9` | dup: H16 becomes merged, into H9 |
| `head convert H15 task [--phase R8] \| issue [--kind bug] \| backlog` | creates through the existing ops (task.add / issue.add / backlog.add), binds it, `ok H15 → task:R8.12` |
| `head claim --model "Opus 5.5" [--acct B]` | writes an `s` record, prints the carried-over open asks |
| `head brief [--md]` | the resume digest, ≤15 lines: previous head, open asks by age, needs-you, decisions and rules from the last 7 days |
| `head triage` | untriaged entries with suggestions: `H15 ask→task? dup H9 0.72 \| "make map open in new tab"` |
| `head accept H15` / `head forget H15` | person only (agentguard.person_context); forget blanks the verbatim, the summary stays |

`status` gains one line: `head: 3 unhandled (oldest 2h), 5 doing, 1 needs-you`. A rule (kind rule) cannot become
rules.txt through agents (`rules add` refuses them), so `convert rule` sets needs-you with "add to rules.txt?".

## 5. API and GUI
**Ops** (POST `/api/v1/cmd`, in a new `services/headops.py` registered by one import line in cmdops.py):
- public: `head.log`, `head.set`, `head.bind`, `head.unbind`, `head.split`, `head.merge`, `head.convert`;
- person only: `head.accept`, `head.forget`;
- internal: `head.restore` (undo).

Every op except the hook capture logs activity and undo. The capture is `logs=False`: one activity line per typed
message would be noise.

**Snapshot** (key `head`, ≤3 KB, no verbatim):
`head:{now:{model,acct,since,sid,usage},prev:[≤3],counts:{open,unhandled,doing,needs,doneUnacc},rows:[≤40 open +
5 newest done: {id,kind,sum,status,age,stale,carried,links:[≤3],more,dup}]}`.

**Read route:** `GET /api/v1/projects/{pid}/head?f=open|all&n=100&full=H12`. It gives the full list, and with `full`
one verbatim text and the entry's history. It uses the same-origin guard; the phone listener gets no `text` and no
history (`_phone_public`). The `refs.py` KINDS gain `ask`, so `rb:roadmap-board/ask/H12` works with Copy.

**Screen "Head"** (nav: after Inbox, icon `head`, deep link `#head?f=unhandled&id=H12`). At 1440 px, full width:
```
Head now  Opus 5.5 · acct B · since 09:02 (3h) · 5h 41% · week 63%      prev: Opus acct A until 08:55
! 3 unhandled (oldest 2h) [Show]   ! 1 needs you [Show]   4 done, not accepted [Review]
[/ search] [Open|Unhandled|Doing|Needs you|Done|All] [Kind▾] [Session: all▾]                [+ Log]
 ▸ ID    Kind      Summary                                   Bound to          Status     Age  S  Acc ⧉ ⋯
 ▾ H15   ask       Head section design (Opus, high)          R7.31 · F25       doing       2h  B  ☐   ⧉ ⋯
        "tell opus: very important feature: we need another section as head…"   [Show all]
        09:12 hook new · 09:13 head triage ask · 09:13 bound task:R7.31 · 10:40 auto doing
        Suggest: — · [Make task] [Make issue] [Dup of…] [Decline]
 ▸ H14   bug       Top bar scrolls at 375 px                 I12               bound      40m  B  ☐   ⧉ ⋯
 ▸ H9    rule      5h stop at 90%                            doc:HANDOVER#0    done ✓     1d  A  ☑   ⧉ ⋯
```
- **Grid** (UI rule 0, `.row-grid`, the same tracks for the header):
  `24px 56px 76px 1fr 160px 88px 52px 32px 32px 32px 32px`.
- **Columns:**
  - Age is right-aligned with tabular numbers, amber or red when stale.
  - S is the account or session label; a carried-over row shows `↺`.
  - Bound to shows at most 2 ref chips, then `+n`, each linking to its section (`→ Work` drawer, Issues, …).
  - The status chip carries text and an icon, never colour alone. `done?` is outlined until confirmed.
  - The Acc checkbox, copy ref and ⋯ always sit in the last three tracks.
- **Expanded row:**
  - the verbatim text, fetched on expand only (pre-wrap, 6 lines, then "Show all");
  - the history, one line;
  - the suggestion buttons.
- **⋯ menu:** Set status, Bind…, Split, Merge into…, Copy ref.
- **Empty state:** "Nothing logged yet. Every message you type is logged here. [+ Log]".
- **Phone (375 px):** cards, read-only on the phone listener:
  `H15 ask [doing] 2h` / a 2-line summary / ref chips. The filters move into a sheet.
- **Overview chip:** `3 asks unhandled` (→ `#head?f=unhandled`). The nav badge shows the unhandled count (the
  needs-you count also adds to the Inbox badge only when R8.22 lands).
- **CSS:** new `web/css/head.css` ≤1.2 KB, reusing the row-grid, chip and planner tokens. If that is not enough, it
  is the person's decision to raise the cap.

## 6. Smartness (stdlib heuristics + the head's own reading)
- **Summary:** greetings and filler are dropped ("tell opus:", "please", "also"). The first clause with a verb, cut at
  100 chars. The head replaces it on triage.
- **Kind:** an ordered regex table:
  - `bug`: bug, broken, error, does not work, wrong, fails, 404;
  - `rule`: always, never, must, rule, from now on, don't;
  - `decision`: yes / no / go with / decided / I choose;
  - `preference`: I like, I prefer, I want … to be;
  - `review`: review, audit, check;
  - `question`: ends with ? and has no imperative;
  - `ask` otherwise.

  Stored as `kind` with `?` (a guess) until the head triages it.
- **Conversion suggestion:**
  - ask → task (backlog when it says "later" or "after");
  - bug → issue (kind bug);
  - review → review job (cursor or agy);
  - rule or preference → rule, doc or memory (needs-you for rules.txt);
  - question → answer: the head answers in chat and sets done.
- **Duplicates:** Jaccard over stopword-free word sets, at 0.6 or more against open entries and the last 30 days.
  Shown as `dup? H9 0.72`; never merged automatically.
- **Multi-ask messages:** the hook's hint says "split?" when the text has 2 or more imperative sentences or a list.
  The head splits.
- **Continuity:** `claim` prints the carried asks; `brief` is what `/head` reads; `carried` rows rise to the top of
  Unhandled.
- **Head and memory sync:** at `/head save`, every rule or decision accepted since the last save is listed for
  HANDOVER section 2b (the head copies it, so there is one source per fact). HANDOVER section 0 points to
  `roadmap head brief` and does not duplicate it.

## 7. Security and redaction
- **Redaction** (new `roadmap/core/secrets.py`, pure, shared later by log.py) runs before any write to either file and
  before the summary is built. It masks:
  - `log._REDACTIONS`;
  - `sk-…`, `ghp_`/`github_pat_`, `xox[abp]-`, `AKIA…`, `AIza…`, JWTs (`eyJ…`), PEM blocks;
  - `password|token|secret|key=…`;
  - URLs with credentials, `?k=` style query keys, hex or base64 runs of 32 chars or more;
  - email addresses → `[email]`, card-like 13–19 digit runs → `[number]`;
  - `/Users/<name>` → `~`.

  Unit tests use a vector table (agy drafts the extra vectors; Haiku verifies them).
- **Text limits:** verbatim cut at 8000 chars, summary at 100, note at 160. Control chars are stripped. `<` and `>`
  are rendered as text (DOM textContent, never innerHTML).
- **Storage:** `head-text.jsonl` is mode 0600 and git-ignored; backups include it, but `export` and the phone never
  do.
- **Agents:**
  - Agents cannot accept, forget or rewrite text. `set` cannot change `ts`, `src` or `text`.
  - Declined or merged entries stay visible (filter All), and the person can reopen them.
  - No delete op exists.
- **Hook:** fail-open, a 0.3 s budget, no network, no subprocess, one lock attempt. A malformed payload is skipped and
  logged at DEBUG with no text.
- **Logging:** the debug log records `head.capture` with the id, kind and length only, never the text.

## 8. Build breakdown (Haiku; strict files; in order)
| # | Step | Files | Tests / acceptance | Size | When / overlap |
|---|---|---|---|---|---|
| H1 | Core fold + heuristics | new `roadmap/core/head.py` | `tests/unit/test_head_core.py`: fold order, every status rule, age/stale/carried, kind table, summary, Jaccard dup, unknown `v` skipped | 50k | now |
| H2 | Redaction | new `roadmap/core/secrets.py` | `tests/unit/test_secrets_scrub.py`: ≥30 vectors, no false hit on task ids/refs/shas | 30k | ∥ H1 |
| H3 | Store service | new `roadmap/services/head.py`, `roadmap/store/schema.py` (+`head` kind, 1 hunk), `.gitignore` (+2 lines) | `tests/unit/test_head_service.py`: append under lock, spool adoption, ids unique under 2 threads, 0600, caps, brief ≤15 lines | 50k | after H1+H2 |
| H4 | Ops | new `roadmap/services/headops.py`, `roadmap/services/cmdops.py` (1 import line) | `tests/unit/test_head_ops.py`: 9 ops + undo, person-only accept/forget refused for agent/phone/non-TTY, convert calls task/issue/backlog ops | 50k | after H3; cmdops.py shared: re-read before edit |
| H5 | CLI | new `roadmap/commands/head.py`, `roadmap/cli.py` (+"head"), `roadmap/commands/status.py` (+1 line) | `tests/unit/test_head_cli.py`: grammar `ok/next`, list line columns, `t` one-call triage | 40k | after H4; status.py also in Work v2 W2: sequence |
| H6 | Hooks | `roadmap/services/hooks.py` (UserPromptSubmit branch, SessionStart lines), `roadmap/services/hooks_install.py` (+event) | `tests/unit/test_head_hook.py`: skip rules, config gate, 0.3 s budget fail-open, lock busy → spool, reply ≤120 chars, no text in log | 40k | after H3; the head reads the diff; Cursor grok gate |
| H7 | Snapshot + API + refs | `roadmap/core/snapshot.py` (+`head` key), `roadmap/http/routes.py` (+GET route, phone scrub), `roadmap/core/refs.py` (+`ask`) | `tests/unit/test_head_snapshot.py` (≤3 KB for 40 rows, no `text`), `tests/api/test_head_api.py` (guard, phone strips text, `full=`) | 40k | after H3; snapshot.py also in Backlog 3/W2: minimal hunk, sequence; Cursor grok gate |
| H8 | View | new `web/js/views/head.js`, new `web/css/head.css` (≤1.2 KB), new `tests/web/render_head.mjs`, new `fixtures/demo/alpha/docs/head.jsonl` | `tests/web/test_head_view.py`: grid tracks, header same tracks, textContent only, empty state, 375 cards, CSS total ≤ cap | 60k | ∥ H4–H7 against the fixture |
| H9 | Wire-up | `web/js/routes.js` (+section), `web/icons.svg` (+`head`), `web/js/views/overview.js` (chip), `web/js/views/nav.js` (badge) | `tests/web/test_head_wire.py`; `make check-ui` at 1440/375, dark/light | 25k | after H7+H8; the head restarts the service (new static file) |
| H10 | Docs + skills | `docs/AGENT-INTERFACE.md`, `docs/API.md`, `roadmap/templates/skills/roadmap-lead/SKILL.md` (+3 lines), `docs/HEAD-RUNBOOK.md`, `CHANGELOG.md`; the head itself edits `~/.claude/skills/head/SKILL.md` (resume: `head claim` + `head brief`; save: list new rules/decisions) and CLAUDE.md (1 line) | `tests/unit/test_docs.py` passes | 20k | last |
| H11 | Turn on + seed | the person runs `bin/roadmap hooks install` in roadmap-board (or adds the one UserPromptSubmit entry); set `headCapture: true`; the head runs `head import --doc docs/HANDOVER.md --section 2,2b` and `--doc docs/HEAD-SECTION-REQUEST.md`; optional transcript backfill | `head brief` shows the seeded rules; one typed message appears in the GUI within 2 s | 15k | the person present; never a worker |

- **Order:** H1 ∥ H2 → H3 → (H4 → H5) ∥ H6 ∥ H7, with H8 in parallel from the start → H9 → H10 → H11. About 420k
  in total.
- **Gates:** a Cursor grok-4.7-xhigh review of H3+H4+H6+H7 (capture, redaction, person-only ops, phone scrub)
  before H11.
- **agy audits** (verified by Haiku):
  - (A) head.js rule 0 rows, aria, no colour-only status, 375 px no scroll;
  - (B) redaction vectors gap list;
  - (C) the brief and status strings in plain words.

## 9. Decisions for the person
1. Should the verbatim text stay local only (git-ignored), with summaries in git? I recommend yes: the repo is public.
2. Should the hook capture every typed message automatically (acks skipped, `//nolog` to opt out)? I recommend yes.
3. Who confirms done? I recommend the head confirms done and only you accept, as with features.
4. If head.css cannot fit in 1.2 KB, should we raise the CSS cap from 72 KB to 74 KB? I recommend reclaiming first;
   raise the cap only if needed.

## 10. Decisions taken (the person, 2026-10-15) - these override sections above
- Full ask text is NOT local-only: it ships with the project, in its own committed file/section (docs/head-text.jsonl is committed, not git-ignored; H3 must not add it to .gitignore). Redaction still runs before write (repo is public); keep secrets out.
- Capture every typed message automatically (headCapture on).
- The head may mark an ask done; the GUI gets a Review button so the person can confirm or reopen. Only the person accepts.
- CSS cap: raise if needed, as little as possible (head.css first, tidy others).

## 11. Head autopilot: the head must not need reminders (the person, 2026-10-15)
Problem: the head forgets open asks, goes idle, skips cursor/agy audits, registers jobs late. Fix = the ledger drives the head, not memory:
1. **Stop-hook gate (H12):** when the head tries to end a turn, the Stop hook runs `head brief --gate`. If open asks (new/understood/bound/doing/needs-head), queued tasks, or finished-but-uncommitted worker results exist, usage is under the stops (5h 90%, weekly 98%) and the person has not said "stop", the hook returns a block with the 5 top items ("continue: H12 unanswered 40m, task R7.29 step 2 free, no cursor/agy running"). Fail-open; max 1 block per 10 min; `head pause` / person "stop" disables it.
2. **Idle-resource check in the same brief:** lists "cursor idle", "agy idle", free non-overlapping tasks, unregistered running workers, uncommitted diffs, unpushed commits. Every head turn start (SessionStart + UserPromptSubmit reply, <=120 chars) shows the top 3.
3. **Every worker/agent completion note** triggers the runbook checklist printed by `head brief --done`: verify diff, close job with tokens, commit, push, launch next wave, run cursor/agy audit on it, tick asks.
4. **Ask coverage:** an ask with no link after 15 min is shown red in the GUI and in the gate; the person's Review button is the only way to close.
5. **Resume:** `/head` skill runs `head claim` + `head brief --gate` first, so a new account has the full list without re-explaining.
Build as step H12 after H6 (hook) and H5 (CLI); files: roadmap/services/hooks.py (Stop branch), roadmap/commands/head.py, tests/unit/test_head_gate.py.
