| file:line | problem | fix |
|---|---|---|
| roadmap/commands/head.py:219 | `_find` raises `commands._usage` (exit code 2) for missing entry IDs instead of not-found error (exit code 1) | Raise dedicated not-found exception or return exit code 1 |
| roadmap/commands/head.py:292 | `_log` sets next command grammar with incomplete placeholder `".."` (`roadmap head t %s ..`) | Change to `'roadmap head t %s <kind> "<sum>"' % data["id"]` matching line 428 and 465 |
| roadmap/commands/head.py:316 | `_set` formats `", ".join(...)` without fallback when `changed` is empty, producing `"ok H15 set . next: ..."` | Add fallback `", ".join(reply["data"]["changed"]) or "nothing"` matching line 321 and 327 |
| roadmap/commands/head.py:346 | `_convert` rule message ends with `?` which `_ok` follows with `.`, producing invalid double punctuation `?.` | Remove question mark from message or format punctuation conditionally in `_ok` |
| roadmap/commands/head.py:405 | `_claim` returns raw `data` dict on `--json` rather than standard `{ok, data}` envelope | Wrap with `commands.json_data(data)` or return through standard envelope helper |
| roadmap/commands/head.py:409 | `_claim` write command prints multi-line carried items before `ok` and bypasses `_ok`/`_emit_write` | Route output through `_emit_write` or emit single `ok` line and move list lines under read command |
| roadmap/commands/head.py:492 | `_gate` prints `"ok nothing pending"` without required `"next: ..."` trailer specified in docstring line 5-6 | Append `"next: roadmap head list"` or invoke `_ok("nothing pending", NEXT)` |
| roadmap/commands/head.py:495 | `_gate` prints `"continue: ..."` lines but fails to conclude with `"next: ..."` trailer required for reads | Call `_next(BRIEF)` after printing continue items |
| roadmap/commands/head.py:504 | `_pause` prints text and returns `None` (exit code 0), ignoring `--json` flag and envelope requirement | Check `_json(args)` and return envelope via `commands.json_data({"paused": True})` |
| roadmap/commands/head.py:514 | `_resume` prints text and returns `None` (exit code 0), ignoring `--json` flag and envelope requirement | Check `_json(args)` and return envelope via `commands.json_data({"resumed": was})` |
| roadmap/commands/head.py:523 | `_brief --done` prints text checklist unconditionally, ignoring `--json` flag | Check `_json(args)` and return `{"checklist": list(DONE_CHECKLIST)}` |
| roadmap/commands/head.py:532 | `_brief` read subcommand prints content lines but fails to end with `next: ...` trailer | Call `_next(NEXT)` after printing lines matching other read subcommands |
