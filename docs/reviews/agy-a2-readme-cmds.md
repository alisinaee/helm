# Job staffer-mv6zxbx6-b590dd1d (staffer, done)

### Table 1: Roadmap Command Examples in README.md Not in Real Command List

| file:line | the command | closest real command |
|---|---|---|
| `README.md:188` | `roadmap task set [-] [--dry-run]` | `roadmap task set` (reads from stdin without `[-]` / `--dry-run` flag) |
| `README.md:189` | `roadmap plan import <file\|-> [--dry-run] [--replace-phase P]` | `roadmap plan import [FILE]` (no `--dry-run` or `--replace-phase`) |
| `README.md:190` | `roadmap plan export [--phase P]` | `roadmap plan export` (no `--phase`) |
| `README.md:194` | `roadmap issue new "<title>" [--kind bug\|risk\|question\|blocker] [--sev 1-3] [--task ID]... [--note "..."]` | `roadmap issue new <title>` |
| `README.md:195` | `roadmap issue list [--all]` | `roadmap issue list` (no `--all`) |
| `README.md:209` | `roadmap budget show [--phase P]` | `roadmap budget show` (no `--phase`) |
| `README.md:220` | `roadmap limit set <pct>` | `roadmap limit set PCT` |
| `README.md:226` | `roadmap rules sync [--dry-run]` | `roadmap rules sync` (no `--dry-run`) |
| `README.md:320` | `roadmap hooks install my-app --replace-legacy` | `roadmap hooks install [PROJECT]` (no `--replace-legacy`) |

---

### Table 2: Real Command Groups Never Mentioned in README.md

README.md mentions all 32 top-level CLI command groups. There are no omitted command groups.

| Real Command Group | Status in README.md |
|---|---|
| *(None)* | All 32 real command groups are documented in README.md. |

DONE
