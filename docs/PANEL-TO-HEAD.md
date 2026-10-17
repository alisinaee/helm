# Panel to head (R11.2)

Question: when the person acts on the board (answers a question, accepts a rule, presses Mark, Update, sets a limit,
runs a command, comments in Head chat), does the head AI agent learn about it?

Short answer before R11.2: mostly no. Every board write was logged (activity.jsonl), but the hooks never read that
log. A live head saw only a few things, and only by side effect. After R11.2 every board action becomes a panel line
that the next hook event hands to the head session, and the board shows sent / seen / acted for each line.

## 1. The path, end to end

```
board click -> web/js/cmd.js run(op) -> POST /api/v1/cmd (routes.cmd) -> commands.run -> handler + activity line
            -> [R11.2] headpanel.record_op -> docs/head-panel.jsonl  (src gui or phone only)
Mark        -> log.js mark() -> POST /api/v1/log (ui.mark) -> [R11.2] panel line "Mark: ..." (needs logging on)
Update      -> app.js syncUsage -> POST /api/v1/usage/sync -> [R11.2] panel line "usage Update pressed"

head session (Claude Code) <- `roadmap hook` (settings.local.json) on:
  UserPromptSubmit -> additionalContext   (panel lines first, then the capture triage line)
  PostToolUse      -> additionalContext   (mid-turn: after any Agent/Task/Bash/SendMessage call)
  Stop             -> decision block      (the head reads them before it ends its turn; never on stop_hook_active)
  SessionStart     -> additionalContext   (a new /head session)
idle head sitting in `roadmap watch` <- wakes with "panel P5 <summary>"
```

Each delivered line is written to `docs/head-panel-seen.json` with the time, the event (`via`) and the session key.

## 2. Table: every panel action

Before = the code before R11.2 (measured with a temp ROADMAP_HOME, a port-0 server and `hooks.run_hook`).
After = now. "next event" means the first of: the next prompt, the next tool call of the head, the Stop of its turn.

| Panel action (op) | Logged before | Live head saw it before | Idle head at next /head before | After R11.2 (live and idle) |
|---|---|---|---|---|
| Answer a question (question.answer) | activity | no (only `roadmap watch` printed `answer Q3 ..`) | yes, SessionStart "answered Q3" line | next event, value quoted |
| Ask a question from the board (question.ask) | activity | no | no | next event |
| Accept / reject a rule proposal (rules.accept/reject) | activity | no; rules.txt changes, CLAUDE.md only after rules sync + new session | no | next event, rule text quoted |
| Add / remove a rule (rules.add/rm), rules sync | activity | no | only via CLAUDE.md after sync | next event |
| Head chat note / reply on an ask (head.set note) | head.jsonl u record + activity | no (brief shows sum, not the note) | no | next event, note quoted |
| Head status, bind, merge, split, accept (head.*) | head.jsonl + activity | partly: Stop gate lists open asks | partly: SessionStart open-ask count | next event |
| Mark button (ui.mark) | debug log only, when logging is on | no | no | next event (logging must be on: the button refuses otherwise) |
| Update / usage sync (POST usage/sync) | usage.json + request flag | only "usage refresh requested" in a Stop gate block | no | next event |
| Set / remove a limit, budget, task cap (limit.*, budget.set, task.cap) | activity + control state | only as a PreToolUse deny once a limit blocks | no | next event, value quoted |
| Stop / resume / override (control.*) | activity + control state | stop: PreToolUse deny; resume/override: no | stop: SessionStart "stopped by user" line | next event |
| Start / stop a task (task.start/stop) | queue.json + activity | Stop pickup block, `roadmap watch` | SessionStart queued line | unchanged + next event |
| Task status, rename, move, add, subtask, backlog, plan.move, phase.approve | activity | no | no | next event |
| Feature, work, issue, comment ops | activity | no | no | next event |
| git.commit / git.push from the board | activity + git | no | no | next event |
| Undo | activity | no | no | next event |
| Command palette op | same as the op it runs | as that op | as that op | next event |

Not panel actions (never sent): CLI writes and unproven writes (source cli or agent: that is the head or a worker
itself), and pure reads (filters, opening rows, theme).

## 3. Design

- One ledger, `docs/head-panel.jsonl` (`roadmap/services/headpanel.py`): `{id P<n>, ts, src, op, sum, ref}`, newest
  300 kept. Written in `routes.cmd` after a successful op when the source is `gui` (the proven browser) or `phone`;
  in `log_post` for `ui.mark` (scoped to the project in the route); in `usage_sync`. The summary is the op's activity
  line plus the person's free text (note, value, text, reason) in quotes, 160 characters at most. A separate file so
  head.jsonl's record types, the sqlite mirror and the fold are untouched. Writing it never fails the person's op.
- Delivery in `roadmap/services/hooks.py` (`_panel_text`): up to 6 unseen lines per event, marked seen under the data
  lock with a share of the 0.3 s budget (a busy lock just waits for the next event). Skipped for a subagent's hook
  (`agent_id` in the payload) and off with `"head": {"panel": false}` in roadmap.config.json. Not tied to
  headCapture. Stop blocks once with the lines (joined to a pickup or gate block when there is one).
- Idle head: Claude Code cannot be pushed into from outside. An idle head that sits in `roadmap watch` wakes on a
  panel line (`panel P5 <summary>`). A head with no session gets the lines at SessionStart or its first prompt.
- `roadmap head panel` lists the newest lines with their state (and marks unseen ones seen, via cli);
  `roadmap head panel ack P3 P4|all` marks them acted. The hook text ends with that ack hint.
- States: sent (logged, not delivered), seen (handed to a head session), acted (acked, or a later cli/agent activity
  line names the line's ref, for example the head setting P0.1 after the person moved P0.1).
- Board: the cmd reply carries `panel: {id, head: watching|open|none}`; `GET /api/v1/projects/{pid}/panel` returns
  the rows, counts and head presence; `web/js/views/headseen.js` shows one collapsed "Sent to head: n sent · n seen ·
  n acted (head session open)" line at the top of the project Inbox, opening to the newest 8 rows.

## 4. Remaining risks

- Any main session in the project folder takes the lines (no check that it is the claimed head). A second non-head
  session open in the repo can mark them seen first. The seen stamp records the session key so it can be traced.
- "seen" means delivered into context, not understood. "acted" by inference is a heuristic (ref mention); explicit
  ack is the reliable signal.
- A truly idle head (turn ended, no `roadmap watch`) learns nothing until the person types; no notification is sent
  for panel lines (the person is the one acting).
- Mark reaches the head only when logging is on (the button refuses otherwise; topbar.js unchanged).
- A large burst is delivered 6 lines per event; the rest are counted with a pointer to `roadmap head panel`.
- The person's free text goes into the head's context verbatim (capped 100 characters), the same trust as a prompt.
- Writes made through `bin/roadmap` in the person's own terminal are source cli and are not panel lines.
