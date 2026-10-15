# Interface Documentation Review

Review of command, flag, and output discrepancies in `docs/AGENT-INTERFACE.md` and `README.md` against the implementation files (`roadmap/commands/*.py`) and `docs/facts/FACTS.md`.

| doc line | doc says | code says (file:line) | fix |
|---|---|---|---|
| `README.md:163-237` | `roadmap logs` omitted from command table | `roadmap/commands/logs.py:31-48` | Add `roadmap logs [view] [--since] [--src] [--ev] [--ref] [--session] [--level] [--limit] [--on\|--off]` to command table |
| `docs/AGENT-INTERFACE.md:23-35` | `roadmap logs` omitted from agent interface table | `roadmap/commands/logs.py:31-48` | Add `roadmap logs` to command table for event and error debugging |
| `README.md:163-237` | `roadmap ref` omitted from command table | `roadmap/commands/ref.py:19-23` | Add `roadmap ref <ref> [--json]` to command table |
| `docs/AGENT-INTERFACE.md:23-35` | `roadmap ref` omitted from agent interface table | `roadmap/commands/ref.py:19-23` | Add `roadmap ref <ref>` to agent interface commands table |
| `README.md:232` | `roadmap feature add\|list\|show\|link\|unlink\|accept\|rm` | `roadmap/commands/feature.py:44-46` | Add `tree` action: `roadmap feature tree [--project ID]` |
| `README.md:232` | `roadmap feature add\|list\|show\|link\|unlink\|accept\|rm` | `roadmap/commands/feature.py:53-59` | Add `move` action: `roadmap feature move <F3> --up\|--down\|--parent <F2\|->` |
| `README.md:232` | `roadmap feature add\|list\|show\|link\|unlink\|accept\|rm` | `roadmap/commands/feature.py:48-51` | Add `set` action: `roadmap feature set <F3> --ask\|--no-ask` |
| `docs/AGENT-INTERFACE.md:23-35` | `roadmap feature` omitted from agent interface table | `roadmap/commands/feature.py:27-30` | Add `roadmap feature` group and actions (add, list, tree, show, set, move, link, unlink, accept, rm) to table |
| `README.md:163-237` | `roadmap backlog` omitted | UNKNOWN (`docs/facts/FACTS.md:6-538`) | None; no `backlog` command exists in the codebase |
| `README.md:174-180` | `roadmap project new` omitted from project actions | `docs/facts/FACTS.md:67-68` | Add `roadmap project new` action to project command table |
| `README.md:181-184` | `roadmap job progress` omitted from job actions | `docs/facts/FACTS.md:85` | Add `roadmap job progress` action to job command table |
| `README.md:184` | `remove finished jobs beyond the newest 200` | `docs/facts/FACTS.md:87` | Update doc to newest 30 (or update CLI help string to 200) |
| `README.md:172` | `roadmap service logs [-f]` | `docs/facts/FACTS.md:46` | Remove `[-f]` flag from `roadmap service logs` syntax |
| `README.md:190` | `roadmap plan import <file\|-> [--dry-run] [--replace-phase P]` | `roadmap/commands/plan.py:33-34` | Add `[--project ID]` to `roadmap plan import` syntax |
| `docs/AGENT-INTERFACE.md:30` | `roadmap plan import <file\|-> [--dry-run]` | `roadmap/commands/plan.py:55-56` | Add `[--replace-phase P]` and `[--project ID]` to `plan import` row |
| `README.md:192` | `roadmap plan template` | `roadmap/commands/plan.py:64` | Add `[--tree]` flag to `roadmap plan template` syntax |
| `docs/AGENT-INTERFACE.md:32` | `roadmap plan template` | `roadmap/commands/plan.py:64` | Add `[--tree]` flag to `roadmap plan template` row |
| `docs/AGENT-INTERFACE.md:23-35` | `roadmap plan view` omitted from table | `roadmap/commands/plan.py:67-69` | Add `roadmap plan view [--project ID]` to commands table |
| `docs/AGENT-INTERFACE.md:23-35` | `roadmap plan move` omitted from table | `roadmap/commands/plan.py:71-75` | Add `roadmap plan move <id> --before ID \| --after ID` to commands table |
| `docs/AGENT-INTERFACE.md:41` | `feature := "F" SP fid SP ("-"\|"hold") SP prio SP (phase\|"-") SP (parentFid\|"-") SP "\|" SP title [SP "#" SP acceptance]` | `roadmap/commands/plan.py:163` | Update grammar to include `[SP "ask"]` flag after parentFid |
| `docs/AGENT-INTERFACE.md:43` | `task := "T" SP id SP status SP tokensK SP model "/" thinking [SP "!"] [SP "c:" check "/" checkK] SP "\|" SP title [SP "#" SP note]` | `roadmap/commands/plan.py:168-169` | Update grammar to include `[SP "f:" features]` linking features to tasks |
| `docs/AGENT-INTERFACE.md:42` | `link := "L" SP fid SP taskId (SP taskId)*` | `roadmap/commands/plan.py:168-169` | Deprecate `L` lines; document inline `f:<features>` on task records |
| `docs/AGENT-INTERFACE.md:84-87` | `next:` lines listed before `you:` and `run:` | `roadmap/commands/status.py:37-38` | Reorder output example: `run` comes after head, `you` before `next`, and `next` is last |
| `docs/AGENT-INTERFACE.md:81-87` | Status output example omits gate, ask, queue, issues, plan, budget, and meter lines | `roadmap/commands/status.py:37-38` | Update example to show current composition including gate, ask, queue, issues, plan, budget, limits lines |
| `docs/AGENT-INTERFACE.md:87` | `run: j12 sonnet P2.4 14m` | `roadmap/commands/status.py:42-48` | Document running line aggregation format: `running N: j1,j2,...` when >2 running jobs |
| `README.md:203-205` | `roadmap ask get <Q3>`, `wait <Q3>`, `list` listed as subcommands | `docs/facts/FACTS.md:171-172` | Clarify that `get`, `wait`, `list` are positional `TEXT` choices for `roadmap ask` |
| `README.md:202` | `roadmap ask "<question>" [--task ID] [--opt A]... [--default A] [--block] [--timeout S]` | `docs/facts/FACTS.md:167,177` | Add `[--project ID]` to `roadmap ask` syntax |
| `README.md:207` | `roadmap comment <ID> "<text>"` | `docs/facts/FACTS.md:205,214` | Add `[--project ID]` to `roadmap comment` syntax |
| `README.md:208` | `roadmap comments <ID> [--last 5]` | `docs/facts/FACTS.md:221` | Update syntax to `roadmap comments [--project ID] [--last N] ID` |
| `README.md:209` | `roadmap inbox` | `docs/facts/FACTS.md:257,262` | Add `[--project ID]` to `roadmap inbox` syntax |
| `README.md:211` | `roadmap undo <A812>` | `docs/facts/FACTS.md:283,291` | Add `[--project ID]` to `roadmap undo` syntax |
| `README.md:218` | `roadmap stop [--task ID]` | `docs/facts/FACTS.md:365,371` | Add `[--project ID]` to `roadmap stop` syntax |
| `README.md:220` | `roadmap override --hours N` | `docs/facts/FACTS.md:388,394` | Add `[--project ID]` to `roadmap override` syntax |
| `README.md:221-222` | `limit set` and `limit budget` only in table | `docs/facts/FACTS.md:405-406` | Add `roadmap limit rm <L3>` and `roadmap limit show` to command table |
| `README.md:221` | `roadmap limit set <pct>` | `docs/facts/FACTS.md:404` | Update description: set a limit row, or stopAtPercent with a bare PCT |
| `README.md:232` | `roadmap feature add\|list\|show\|link\|unlink\|accept\|rm` | `roadmap/commands/feature.py:33-38` | Document `feature add` options: `[--acc TEXT] [--prio 1\|2\|3] [--phase R6] [--parent F2] [--ask\|--no-ask]` |
| `README.md:232` | `roadmap feature accept` | `roadmap/commands/feature.py:77-78` | Document `feature accept` options: `[--off] [--yes]` |
| `README.md:167` | `roadmap backup [--project ID]` | `docs/facts/FACTS.md:493,498` | Change metavar from `ID` to `PROJECT` (`[--project PROJECT]`) |
