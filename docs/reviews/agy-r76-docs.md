# Review: Documentation vs FACTS.md Grounding

| file:line | doc says | FACTS says | fix |
|---|---|---|---|
| README.md:6 | `http://127.0.0.1:8765/` | default port is 8780 (`docs/facts/FACTS.md:17`, `docs/facts/FACTS.md:797`) | change port 8765 to 8780 |
| README.md:18 | `serves the page on 127.0.0.1:8765` | default port is 8780 (`docs/facts/FACTS.md:17`, `docs/facts/FACTS.md:797`) | change port 8765 to 8780 |
| README.md:33 | `http://127.0.0.1:8765/` | default port is 8780 (`docs/facts/FACTS.md:17`, `docs/facts/FACTS.md:797`) | change port 8765 to 8780 |
| README.md:92 | `http://127.0.0.1:8765/` | default port is 8780 (`docs/facts/FACTS.md:17`, `docs/facts/FACTS.md:797`) | change port 8765 to 8780 |
| README.md:99 | installing skills into `~/.claude/skills` is a manual step | `roadmap skills install` installs skills into `<project>/.claude/skills` (`docs/facts/FACTS.md:506`, `docs/facts/FACTS.md:653`) | document `roadmap skills install` command |
| README.md:163 | command table omits `roadmap feature` | `roadmap feature` is an available command group (`docs/facts/FACTS.md:231-249`) | add `roadmap feature` row to table |
| README.md:163 | command table omits `roadmap watch` | `roadmap watch` is an available command (`docs/facts/FACTS.md:513-524`) | add `roadmap watch` row to table |
| README.md:163 | command table omits `roadmap skills` | `roadmap skills` is an available command group (`docs/facts/FACTS.md:498-511`) | add `roadmap skills` row to table |
| README.md:172 | `roadmap service logs [-f]` | `service logs` accepts only `[-h] [--json]` (`docs/facts/FACTS.md:36-50`) | remove `[-f]` flag |
| README.md:173 | `roadmap serve [--port N] [--no-usage-loop]` | `roadmap serve` also takes `[--no-phone]` (`docs/facts/FACTS.md:11-19`) | add `[--no-phone]` flag |
| README.md:184 | `remove finished jobs beyond the newest 30` | `KEEP_FINISHED = 200` (`docs/facts/FACTS.md:589`) | update cap to 200 |
| README.md:190 | `roadmap plan import <file\|-> [--dry-run] [--replace-phase P]` | `roadmap plan import` help lists only `[-h] [--json]` (`docs/facts/FACTS.md:113-126`) | align options with FACTS |
| README.md:191 | `roadmap plan export [--phase P]` | `roadmap plan export` help lists only `[-h] [--json]` (`docs/facts/FACTS.md:113-126`) | align options with FACTS |
| README.md:204 | `roadmap ask wait <Q3> [--timeout S] ... the only waiting command` | `roadmap watch` also waits/blocks (`docs/facts/FACTS.md:513-524`, `docs/facts/FACTS.md:660`) | remove "the only waiting command" claim |
| README.md:208 | `roadmap comments <ID> [--last 5]` | syntax is `roadmap comments [-h] [--json] [--project ID] [--last N] ID` (`docs/facts/FACTS.md:218`) | fix argument order and flag format to `[--last N] ID` |
| README.md:210 | `roadmap budget show [--phase P]` | `roadmap budget show` help lists only `[-h] [--json]` (`docs/facts/FACTS.md:265-275`) | align options with FACTS |
| README.md:212 | `at most 6 notes` | `TITLE_MAX = 80`; 6-note cap is UNKNOWN in FACTS constants (`docs/facts/FACTS.md:613`, Section 4) | remove 6-note cap or verify |
| README.md:214 | `check the caps (120 lines, 6 KB)` | 120 lines and 6 KB caps are UNKNOWN in FACTS constants (`docs/facts/FACTS.md:613`, Section 4) | remove line/size cap claims or verify |
| README.md:216 | `roadmap hooks install\|uninstall\|status <id>` | `roadmap hooks` synopsis takes no `<id>` argument (`docs/facts/FACTS.md:345-356`) | align synopsis with FACTS |
| README.md:225 | `roadmap rules add <scope> <kind> "<text>" [--budget N]` | `rules add` takes no `--budget` flag; budget set via `limit budget` (`docs/facts/FACTS.md:404`, `docs/facts/FACTS.md:434`) | remove `[--budget N]` flag |
| README.md:228 | `validate docs/rules.txt against the caps (60 rules, 160 characters, 8 KB)` | `LINE_MAX = 160`; 60 rules and 8 KB are UNKNOWN in FACTS constants (`docs/facts/FACTS.md:591`, Section 4) | cite only `LINE_MAX = 160` |
| README.md:236 | `Not built yet: roadmap open ...` | `roadmap open [-h] [--json] [--port PORT]` is implemented (`docs/facts/FACTS.md:22-31`, `docs/facts/FACTS.md:645`) | remove claim that `open` is not built |
| README.md:236 | `Not built yet: ... the roadmap phone commands.` | `roadmap phone` is implemented with `start\|stop\|link\|status` (`docs/facts/FACTS.md:471-485`, `docs/facts/FACTS.md:646`) | remove claim that `phone` is not built |
| README.md:263 | `Port 8765` | default port is 8780 (`docs/facts/FACTS.md:17`, `docs/facts/FACTS.md:797`) | change port 8765 to 8780 |
| README.md:317 | `roadmap hooks install my-app --replace-legacy` | `roadmap hooks install` has no `--replace-legacy` flag (`docs/facts/FACTS.md:345-356`) | remove `--replace-legacy` flag |
| README.md:360 | interactive manager table omits `roadmap feature` | `roadmap feature` is an interactive manager command (`docs/facts/FACTS.md:231-249`, `docs/facts/FACTS.md:686`) | add `roadmap feature` to table |
| README.md:360 | interactive manager table omits `roadmap phase` | `roadmap phase approve` is an interactive manager command (`docs/facts/FACTS.md:412-424`, `docs/facts/FACTS.md:558`) | add `roadmap phase approve` to table |
| docs/AGENT-INTERFACE.md:39 | `line := phase \| task \| comment \| blank` | plan format also has F (features) and L (links) records (`docs/facts/FACTS.md:790`) | update grammar with F and L records |
| docs/AGENT-INTERFACE.md:109 | `At most 6 notes, each at most 120 lines and 6 KB.` | `TITLE_MAX = 80`; 6 notes, 120 lines, 6 KB are UNKNOWN in FACTS constants (`docs/facts/FACTS.md:613`, Section 4) | remove 6-note / line / size caps |
| docs/AGENT-INTERFACE.md:188 | `roadmap plan import - --project rb16 --dry-run` | `roadmap plan` has no `--project` option (`docs/facts/FACTS.md:113-126`) | remove `--project` flag |
| docs/AGENT-INTERFACE.md:190 | `roadmap task set - --project rb16` | `roadmap task` has no `--project` option (`docs/facts/FACTS.md:94-108`) | remove `--project` flag |
| docs/AGENT-INTERFACE.md:215 | `roadmap research new landscape "Similar products" --project rb16` | `roadmap research` has no `--project` option (`docs/facts/FACTS.md:295-306`) | remove `--project` flag |
| docs/skill-draft/roadmap-update/SKILL.md:12 | `--project ID is optional` (stated as general rule) | `--project` is accepted only on specific commands (`docs/facts/FACTS.md:164-521`) | clarify which commands accept `--project` |
| docs/skill-draft/roadmap-update/SKILL.md:22 | `roadmap task list --status todo,partial --limit 10` | `QUERY_LIMIT = 20` (`docs/facts/FACTS.md:603`) | change default limit to 20 |
| docs/skill-draft/roadmap-plan-new/SKILL.md:26 | `A note is at most 120 lines and 6 KB, and there are at most 6 notes.` | `TITLE_MAX = 80`; 6 notes, 120 lines, 6 KB are UNKNOWN in FACTS constants (`docs/facts/FACTS.md:613`, Section 4) | remove 6 notes, 120 lines, 6 KB caps |
| docs/skill-draft/roadmap-plan-new/SKILL.md:58 | `roadmap plan export --phase P1` | `roadmap plan export` help lists only `[-h] [--json]` (`docs/facts/FACTS.md:113-126`) | align options with FACTS |
