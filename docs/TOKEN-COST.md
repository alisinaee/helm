# Full-cycle agent token cost (R7.2)

Measured with the repo CLI (`bin/roadmap`) on a temp `ROADMAP_HOME` and a temp project folder.
Tokens are estimated as bytes / 4 per command, rounded up. Bytes are stdout plus stderr.

| # | Command | Bytes | Est. tokens | Exit | Note |
|---|---|---:|---:|---:|---|
| 1 | `project new <tmp> --research` | 375 | 94 | 0 | init, plan P1, research note 1 |
| 2 | `plan template` | 856 | 214 | 0 | 13 lines |
| 3 | `plan import <10-line plan> --dry-run` | 62 | 16 | 0 | dry run, no write |
| 4 | `plan import <10-line plan>` | 19 | 5 | 0 | real write |
| 5 | `status` | 265 | 67 | 0 | 8 lines |
| 6 | `phase approve P1` | 104 | 26 | 4 | refused for agents (by design) |
| 7 | `task start P1.1 --tokens 20` | 123 | 31 | 4 | refused: P1 not approved |
| 8 | `task done P1.1 --tokens 18` | 10 | 3 | 0 | 1 line |
| 9 | `ask "..." --opt yes --opt no` | 8 | 2 | 0 | prints `Q1 open` |
| 10 | `answer Q1 yes` | 16 | 4 | 0 | |
| 11 | `inbox` | 17 | 5 | 0 | |
| 12 | `agent-guide` | 1943 | 486 | 0 | 37 lines |

**Total: 3798 bytes, about 950 tokens** (per-row rounding gives 953).

## Against the caps in docs/AGENT-INTERFACE.md

| Command | Cap | Measured | Result |
|---|---|---|---|
| `status` | ≤ 8 lines, ≤ 700 chars | 8 lines, 265 chars | within |
| `plan template` | ≤ 15 lines | 13 lines | within |
| `agent-guide` | ≤ 40 lines | 37 lines | within |
| `plan import --dry-run` | summary + ≤ 5 error lines | 2 lines | within |
| `task done` | 1 line per id | 1 line | within |

## Findings

1. The full cycle costs about 950 tokens. `agent-guide` alone is about 51% of it, so it is the first thing to trim.
2. The approval gate adds a human round trip: agents cannot run `phase approve`, so `task start` on a new phase is refused until the person approves it.
3. Every measured output is within its AGENT-INTERFACE.md cap. The two refusals are short (104 and 123 bytes).
