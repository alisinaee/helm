# Job staffer-mv7n55jv-1e212d38 (staffer, done)

| file:line | command | VALID/INVALID | reason |
|---|---|---|---|
| docs/skill-draft/roadmap-update/SKILL.md:16 | `roadmap status` | VALID | `status` is a valid top-level command; takes no required flags |
| docs/skill-draft/roadmap-update/SKILL.md:22 | `roadmap task list --status todo,partial --limit 10` | VALID | `task list` action exists; `--status` and `--limit` are valid action flags in CLI parser |
| docs/skill-draft/roadmap-update/SKILL.md:23 | `roadmap task show P1.2` | VALID | `task show` action exists; takes task ID argument |
| docs/skill-draft/roadmap-update/SKILL.md:24 | `roadmap inbox` | VALID | `inbox` is a valid top-level command |
| docs/skill-draft/roadmap-update/SKILL.md:25 | `roadmap ask "<question>" --opt A --opt B --default A` | VALID | `ask` exists; `--opt` (repeatable) and `--default` are explicitly listed in help |
| docs/skill-draft/roadmap-update/SKILL.md:27 | `roadmap ask get Q3` | VALID | `ask` positional syntax explicitly supports `get Q3` |
| docs/skill-draft/roadmap-update/SKILL.md:27 | `roadmap inbox` | VALID | `inbox` is a valid top-level command |
| docs/skill-draft/roadmap-update/SKILL.md:31 | `roadmap job start "Write the parser" sonnet P1.2` | VALID | `job start` action exists; accepts title, model, and task ID arguments |
| docs/skill-draft/roadmap-update/SKILL.md:32 | `roadmap job done j3 "parser done" --tokens 18` | VALID | `job done` action exists; accepts job ID, note, and `--tokens` flag |
| docs/skill-draft/roadmap-update/SKILL.md:33 | `roadmap job fail j3 "reason in a few words"` | VALID | `job fail` action exists; accepts job ID and note arguments |
| docs/skill-draft/roadmap-update/SKILL.md:36 | `roadmap rules show --for P1.2 --model sonnet --role worker` | VALID | `rules show` action exists; `--for`, `--model`, and `--role` are valid action flags |
| docs/skill-draft/roadmap-update/SKILL.md:40 | `roadmap task done P1.2 --tokens 20 --note "parser merged"` | VALID | `task done` action exists; accepts task ID, `--tokens`, and `--note` flags |
| docs/skill-draft/roadmap-update/SKILL.md:41 | `roadmap task start P1.3` | VALID | `task start` action exists; accepts task ID argument |
| docs/skill-draft/roadmap-update/SKILL.md:42 | `roadmap task hold P1.4 --note "Deferred: waits for the API key"` | VALID | `task hold` action exists; accepts task ID and `--note` flag |
| docs/skill-draft/roadmap-update/SKILL.md:49 | `roadmap task set --dry-run` | VALID | `task set` action exists; `--dry-run` is a valid action flag |
| docs/skill-draft/roadmap-update/SKILL.md:49 | `roadmap task set` | VALID | `task set` action exists; reads task updates from stdin |
| docs/skill-draft/roadmap-update/SKILL.md:53 | `roadmap inbox` | VALID | `inbox` is a valid top-level command |
| docs/skill-draft/roadmap-update/SKILL.md:60 | `roadmap status` | VALID | `status` is a valid top-level command |
| docs/skill-draft/roadmap-plan-new/SKILL.md:14 | `roadmap agent-guide` | VALID | `agent-guide` is a valid top-level command |
| docs/skill-draft/roadmap-plan-new/SKILL.md:14 | `roadmap project init <path>` | VALID | `project init` action exists; accepts project folder path |
| docs/skill-draft/roadmap-plan-new/SKILL.md:14 | `roadmap project add <path> --name "<name>"` | VALID | `project add` action exists; accepts path and `--name` flag |
| docs/skill-draft/roadmap-plan-new/SKILL.md:19 | `roadmap research check` | VALID | `research check` action exists |
| docs/skill-draft/roadmap-plan-new/SKILL.md:19 | `roadmap plan import docs/research/04-plan.md --dry-run` | VALID | `plan import` action exists; accepts plan file path and `--dry-run` flag |
| docs/skill-draft/roadmap-plan-new/SKILL.md:20 | `roadmap status` | VALID | `status` is a valid top-level command |
| docs/skill-draft/roadmap-plan-new/SKILL.md:22 | `roadmap research new <slug> "<title>"` | VALID | `research new` action exists; accepts slug and title arguments |
| docs/skill-draft/roadmap-plan-new/SKILL.md:27 | `roadmap research check` | VALID | `research check` action exists |
| docs/skill-draft/roadmap-plan-new/SKILL.md:30 | `roadmap plan template` | VALID | `plan template` action exists |
| docs/skill-draft/roadmap-plan-new/SKILL.md:57 | `roadmap plan export --phase P1` | VALID | `plan export` action exists; accepts `--phase` flag |
| docs/skill-draft/roadmap-plan-new/SKILL.md:58 | `roadmap plan import docs/research/04-plan.md --dry-run` | VALID | `plan import` action exists; accepts plan file path and `--dry-run` flag |
| docs/skill-draft/roadmap-plan-new/SKILL.md:64 | `roadmap ask "<question>" --opt A --opt B --default A` | VALID | `ask` exists; `--opt` and `--default` are supported flags |
| docs/skill-draft/roadmap-plan-new/SKILL.md:64 | `roadmap ask get Q3` | VALID | `ask` positional syntax explicitly supports `get Q3` |
| docs/skill-draft/roadmap-plan-new/SKILL.md:65 | `roadmap issue new "<title>"` | VALID | `issue new` action exists; accepts title argument |
| docs/skill-draft/roadmap-plan-new/SKILL.md:65 | `roadmap inbox` | VALID | `inbox` is a valid top-level command |
| docs/skill-draft/roadmap-plan-new/SKILL.md:66 | `roadmap rules show --for P2.4 --model haiku --role worker` | VALID | `rules show` action exists; `--for`, `--model`, and `--role` are valid action flags |
| docs/skill-draft/roadmap-plan-new/SKILL.md:67 | `roadmap inbox` | VALID | `inbox` is a valid top-level command |
| docs/skill-draft/roadmap-plan-new/SKILL.md:70 | `roadmap status` | VALID | `status` is a valid top-level command |

DONE
