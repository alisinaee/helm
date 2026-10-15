| doc file:line | claim | code file:line | mismatch |
|---|---|---|---|
| docs/API.md:27 | GET /api/v1/projects/{id}/head reply shape is `{entries: [...]}` | roadmap/http/routes.py:564 | Route returns top-level key `"rows"` instead of `"entries"`, plus `"f"`, `"n"`, and `"total"`. |
| docs/API.md:158 | `GET .../head` query parameter `n` is `(the number of rows, at most 100)` | roadmap/http/routes.py:513 | `HEAD_N_MAX` is 200 and line 531 validates `1 <= int(n_text) <= HEAD_N_MAX` (100 is default, not cap). |
| docs/API.md:163 | `GET .../head` response JSON root contains `"entries"` array | roadmap/http/routes.py:564 | Response dict contains `"rows"`, not `"entries"`. |
| docs/AGENT-INTERFACE.md:179 | Each command prints `ok ..` then `next: ..` | roadmap/commands/head.py:424 | Read commands (`list`, `show`, `brief`, `triage`, `review`) print data directly without `ok ..`. |
| docs/AGENT-INTERFACE.md:181 | Command table lists all head command actions | roadmap/commands/head.py:133 | Command parser also registers `pause` (line 133), `resume` (line 134), and `import` (line 152). |
| docs/AGENT-INTERFACE.md:184 | `head t` output is `one-call triage: ok H15 ask bound task:R7.31` | roadmap/commands/head.py:306 | Output is emitted via `_ok(text, NEXT)` which appends `. next: roadmap head list`. |
| docs/AGENT-INTERFACE.md:186 | `head show H15` verbatim output is unbounded in length | roadmap/commands/head.py:34 | Line 34 defines `TEXT_SHOW_MAX = 200` and line 455 caps verbatim display at 200 chars. |
| docs/AGENT-INTERFACE.md:189 | `head convert H15 task\|issue\|backlog\|rule` creates through existing ops and binds it | roadmap/services/headops.py:354 | Target `rule` creates nothing and binds no ref; it sets status to `needs-you` with note `add to rules.txt?`. |
| docs/AGENT-INTERFACE.md:189 | `head convert` syntax takes only `target` positional argument | roadmap/commands/head.py:118 | Parser supports `--phase` (line 118) for tasks and `--kind` (line 119) for issues. |
| docs/AGENT-INTERFACE.md:191 | `head brief` options are `[--md]` | roadmap/commands/head.py:129 | Parser also defines `--gate` (line 129) and `--done` (line 130) flags. |
| docs/AGENT-INTERFACE.md:196 | Statuses are `new, understood, bound, doing, done, declined, needs-you, merged` | roadmap/services/headops.py:384 | Reopening sets status to `"open"`, and `roadmap/commands/head.py:72` allows status `"open"`. |
| docs/HEAD-USER.md:10 | Links are `(task, issue, feature, doc, commit, job)` | roadmap/services/headops.py:63 | Code supports additional ref kinds (`sub:`, `question:`, `backlog:`, `review:`, `rule:`, `ask:`). |
| docs/HEAD-USER.md:16 | `bound` status means "linked to a task, issue, doc or commit" | roadmap/commands/head.py:290 | Any valid link ref kind (e.g. `feature:`, `job:`, `backlog:`) transitions status to `bound`. |
| docs/HEAD-USER.md:20 | Status list omits `open` | roadmap/commands/head.py:72 | `--status` accepts `"open"`, and `roadmap/services/headops.py:384` sets status to `"open"`. |
| docs/HEAD-USER.md:25 | Click Confirm to accept an ask marked done | roadmap/commands/head.py:144 | `review confirm` confirms done, while `accept` is a separate command with note `"accepted"`. |
| docs/HEAD-USER.md:40 | `roadmap head review` lists done entries awaiting confirmation | roadmap/commands/head.py:140 | Parser accepts `[id]` and `confirm|reopen` (lines 140-141) to decide on an entry. |
