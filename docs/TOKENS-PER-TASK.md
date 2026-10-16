# Token usage per task and agent (investigation H210, 2026-10-16)

## What exists today
- Account level: `roadmap usage` now reads Anthropic's usage endpoint every 2 min (5h %, weekly %). No per-task split.
- Jobs (`docs/jobs.json`): registered by hooks (PostToolUse Agent) with task id from the description, model, start/end,
  refs. NO token numbers: SubagentStop only closes the job; `job done --tokens` is manual and mostly skipped
  (Agents page shows "unknown").
- Exact data is already on disk: Claude Code writes every subagent transcript to
  `~/.claude/projects/<project-slug>/<session>/subagents/agent-<id>.jsonl` plus `agent-<id>.meta.json`
  (`description` = "R10.6 shell UX tester + fix", `model`, `toolUseId`). Every assistant message carries
  `usage` {input, output, cache_read_input, cache_creation_input}. Checked: 39 agents this session, e.g.
  R10.7 Sonnet: out 23.6k, cache read 6.4M, cache write 160k; R10.17 Haiku: out 18k, cache read 5.8M.
- The head session itself is `<session>.jsonl` in the same folder (head cost per turn).

## Plan (R10.32)
1. SubagentStop: read that agent's transcript (path from the payload or `<session>/subagents/agent-<agent_id>.jsonl`),
   sum the four usage fields + model, store on the job: `tokens: {in, out, cacheRead, cacheWrite, model}`.
   Read-only, bounded (stream the file), fail-open.
2. `roadmap tokens backfill`: match past jobs to transcripts by agent id / description task id; fill missing tokens.
3. Cost-weighted units so models compare: weight = model price ratio (Haiku 1, Sonnet 3, Opus 5) x
   (in 1 + out 5 + cacheWrite 1.25 + cacheRead 0.1). Show tokens and weighted units per job, task, phase, model.
4. % of limit (estimate): between two usage readings, split the weekly/5h % rise over the jobs active in that window
   by weighted units; label "≈". Head session counted as its own row ("head").
5. UI: Agents rows show out/total and ≈% ; Work/Task details show per-task sum; Tokens page "by task" and "by model"
   tables (aligned, right-aligned numbers).
6. agy jobs: no Claude tokens (show "agy · 0 Claude"); Cursor: none.
