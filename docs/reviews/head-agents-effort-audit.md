# R7.39 audit: Agents list, effort and model per engine

Read-only audit. Scope: how `web/js/views/agents.js` shows model and effort for haiku, agy, cursor, opencode, opus (and head), and where the recording side (`roadmap/`) feeds it.

## Mismatches

1. **Hook-started jobs never record effort (Agent, agy, cursor rows).** `roadmap/services/hooks.py:1062` calls `jobs.start_job(data_dir, title, entry["model"], task, engine_model=...)` with no `effort`. So every hook job shows "default" (haiku, sonnet, opus, agy) or "not set" (cursor) in the Effort column even when a level was chosen. Only `roadmap job start --effort` (`roadmap/commands/job.py:30-31`) records it.

2. **Cursor effort is embedded in the engine name but shown as "not set".** `hooks.py:149-152` takes the real engine from `CURSOR_MODEL` (for example `grok-4.7-xhigh`) and stores it as `engine_model`. `agents.js:36` only matches the model word, so model `cursor` gives "not set" and the `xhigh` suffix is lost. The Model column shows the engine string, the Effort column does not.

3. **Agent-tool subagents default to "haiku".** `hooks.py:76` uses `tool_input.get("model") or "haiku"`. When the Agent call omits `model`, the subagent inherits the parent model (for head sessions, Opus 5.5), so the row can say "Haiku 5.5" for an Opus run. The title prefix at `hooks.py:80` uses the same guessed value.

4. **Head row shows raw text.** `agents.js:14-15` has no entry for `head` (or `opencode`), so `engineLabel` (`agents.js:28`) returns the raw word "head". The head is Opus 5.5 per the project CLAUDE.md, but `effortLabel` (`agents.js:36`) shows "not set". `roadmap/services/jobs.py:16` lists `head` as a model, and `jobs.py:312` treats `model == "head"` as a lead.

5. **Cursor label casing differs between paths.** The hook always stores `engine_model` as `auto` (`hooks.py:151`), so the exact-engine branch at `agents.js:24` shows "cursor · auto" (lowercase). The fallback at `agents.js:15` shows "cursor · Auto". The same engine gets two spellings depending on whether `engine_model` was recorded.

6. **Dead branches in engineLabel.** `agents.js:26-27` tests for a model containing "grok-4.7" or equal to "auto". `jobs.py:16` only allows the model names haiku, sonnet, opus, cursor, agy, opencode and head, so these branches are reachable only from legacy data. The Grok label therefore comes from the engine string, not the model branch.

7. **Orphaned CSS.** `web/css/components.css:816-817` defines `.ag-noeffort`, but no JS adds that class. `tests/web/test_agents.py:161-166` asserts it is absent. Either remove the rule or wire it up.

## Checked and consistent

- Recorded effort (`roadmap job start --effort`) flows through `jobs.py:90-91`, `snapshot.py:510`, `state.js:187-188` and `agents.js:33-35` for running rows. Covered by `tests/unit/test_jobs.py:46-51` and `tests/web/test_agents.py:136-146`.
- engine_model flows through `snapshot.py:511`, `state.js:189-190` and `agents.js:21-24`.
- Column tracks: live and finished rows both emit 8 cells, matching the header in `agents.js:145-148`.

## Not checked

- Whether finished-job rows (`snapshot.py:371`, raw `jobs`) carry `effort` and `engine_model` in the snapshot. Not traced end to end.
- Live browser rendering. Audit is static.

No other file was changed. Nothing committed. No roadmap service, serve, hooks install or usage sync was run. No subagents used.
