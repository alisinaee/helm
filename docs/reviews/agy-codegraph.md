# Review: colbymchenry/codegraph

## What It Is
Local code intelligence tool with a Rust-powered parser and SQLite knowledge graph.
Pre-indexes codebase symbols, call paths, AST hierarchy, and blast-radius mappings.
Exposes a single consolidated MCP tool (`codegraph_explore`) for coding agents.
Integrates with Claude Code, Cursor, Codex, Gemini, Antigravity, and Copilot.
Runs a local file-watching background daemon to auto-sync the index on source edits.

## How It Saves Tokens
- Collapses multi-turn discovery loops (grep, find, reading files) into 1 `codegraph_explore` call.
- Returns verbatim, line-numbered source snippets with exact caller/callee paths and impact.
- Avoids repetitive file reads and re-parsing across multi-turn agent sessions.

## Install Steps
1. CLI: `curl -fsSL https://raw.githubusercontent.com/colbymchenry/codegraph/main/install.sh | sh` (or `npm i -g @colbymchenry/codegraph`).
2. Agent wiring: `codegraph install` (writes MCP config to `~/.claude.json` / `.mcp.json`).
3. Project init: `cd ~/Works/roadmap-board && codegraph init` (builds `.codegraph/`).

## Languages Supported
- Full support: Python (`.py`), JavaScript (`.js`, `.jsx`, `.mjs`), TypeScript, Go, Rust, Java, C#, C/C++, Swift, Kotlin, PHP, Ruby.
- Python: Full support (classes, functions, decorators, imports, call graph).
- Vanilla JS: Full support (ES modules, vanilla JS DOM/state logic without bundlers).

## License & Maintenance
- License: MIT License.
- Maintenance: Active; last commit/push 2026-10-16; 74,248 stars; 611 open issues.

## Risks
- Hooks: `codegraph install` modifies global `~/.claude.json` / `settings.json`; conflicts with worker sandboxing (`never touch ~/.claude`).
- MCP Context Cost: Registers MCP tool definitions + system prompt instructions (~500–1000 tokens overhead every turn).
- Privacy: 100% local analysis; anonymous aggregated telemetry enabled by default (disable via `codegraph telemetry off`).
- Index Staleness: Daemon watches local files with ~1s latency; parallel workers in temporary `ROADMAP_HOME` or worktrees risk DB lock contention.

## Fit Scores (1-5)
- Head planning: 3/5 (Helps explore cross-module dependencies, but codebase is compact ~41k LOC and already documented).
- Haiku workers: 1/5 (Workers receive explicit file lists from Head; adding ~800 token MCP schema to tight Haiku budget is counterproductive).
- agy workers: 1/5 (agy has unlimited quota, handles narrow audit jobs, and cannot use external MCP servers).

## Final Verdict
**Skip**
The repository is moderate in size (~25.9k lines Python, ~15.5k lines vanilla JS) and already managed by Head with strict, pre-scoped file assignments to Haiku workers. Injecting an MCP server adds mandatory base token overhead to every worker prompt turn, risks SQLite lock friction across parallel workers, and violates worker isolation rules without providing tangible token savings.
