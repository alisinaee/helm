# Usage sources (R10.29)

The service (`roadmap serve`, usage loop every `usage.intervalS`, default 120 s) fetches the 5-hour and weekly
usage by itself. **Sync now** runs the same chain at once. The band shows the source and the age
("Updated 2 min ago, synced"). First source that gives a reading wins:

| # | Source | Label | Needs |
|---|--------|-------|-------|
| 1 | OAuth usage endpoint `GET https://api.anthropic.com/api/oauth/usage` | synced | a Claude Code CLI login |
| 2 | Claude Code `rate_limits` (status line command, hooks, token-optimizer sidecar) | from Claude Code | the status line below (CLI sessions) |
| 3 | Estimate from `~/.claude/projects/**/*.jsonl` (read only) | estimated from local transcripts, `~` | one earlier real reading |
| - | `roadmap usage push` / Enter usage by hand | by the head / entered by you | nothing |

## 1. OAuth endpoint (what CodexBar, Claude HUD, Usagebar do)
Token: keychain item `Claude Code-credentials` -> `claudeAiOauth` (macOS), else `~/.claude/.credentials.json`
(Linux, or `$CLAUDE_CONFIG_DIR`). at `https://platform.claude.com/v1/oauth/token` (fallback `console.anthropic.com`) with Claude Code's public
client id, then writes the new pair back to the same place (keychain via `security -i`, hex on stdin; file 0600).
This only happens when `usageTokenRefresh` is true (see below); otherwise an expired token is reported as expired. Tokens are never logged, printed or sent elsewhere.

On this Mac the item holds only `mcpOAuth` (desktop-app sign-in). **Do once:**

```sh
claude auth login        # or: run `claude`, then /login; pick the Claude subscription account
```

Then click **Sync now** (the background loop rechecks the keychain at most every 6 h after a miss).
If the login has expired (status `expired`), use Claude Code once (it refreshes itself), then **Sync now**.

**Token refresh is opt-in (`"usageTokenRefresh": true` in the usage config; default off).** Refresh tokens rotate:
if the service and Claude Code refresh at about the same time, one side gets a dead refresh token and the Claude
Code login breaks. With the flag off the service never refreshes and never writes the keychain or credentials file.
Turn it on only if you accept that risk.

## 2. Status line (live numbers from every CLI session)
Claude Code hands `rate_limits.five_hour/seven_day.used_percentage` to its status line command (Pro/Max, after
the first reply). `roadmap usage statusline` stores them (at most once a minute) and then runs your current status
line with the same input. **Do once** (not installed automatically), in `~/.claude/settings.json`:

```json
"statusLine": {"type": "command",
  "command": "/Users/ali/Works/roadmap-board/bin/roadmap usage statusline --then \"node '/Users/ali/.claude/plugins/marketplaces/alexgreensh-token-optimizer/skills/token-optimizer/scripts/statusline.js'\""}
```

Desktop-app sessions do not run a status line, so this only helps when you use the `claude` CLI.

## 3. Transcript estimate (last resort)
When the last real reading is older than 10 min and 1-2 found nothing, the service sums the tokens of each window
in the local transcripts (input + output + cache writes + 10% of cache reads, one count per message) and scales
them by the tokens-per-percent of the last real reading. Marked `estimate`, never written to the ledger, and any
real reading replaces it. Desktop sessions are in the transcripts too, so this follows them between readings.

## Not used
- claude.ai `sessionKey` cookie + `claude.ai/api/organizations/{id}/usage` (web menubar apps): needs browser or
  desktop-app cookie extraction; skipped.
- Scraping `claude /usage` in a PTY: needs the same CLI login as source 1.
