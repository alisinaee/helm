| file:line | prompt pattern | logged today? | should skip? |
|---|---|---|---|
| roadmap/services/hooks.py:741 | Non-string prompt payload (`not isinstance(text, str)`) | No | Yes |
| roadmap/services/hooks.py:747 | Empty or whitespace-only prompt (`not stripped`) | No | Yes |
| roadmap/services/hooks.py:747 | Explicit opt-out prefix (`//nolog`) | No | Yes |
| roadmap/services/hooks.py:747 | Task notification markup prefix (`<task-notification`) | No | Yes |
| roadmap/services/hooks.py:747 | System reminder markup prefix (`<system-reminder`) | No | Yes |
| roadmap/services/hooks.py:747 | Command markup prefix (`<command-`) | No | Yes |
| roadmap/services/hooks.py:750 | Bare slash command (`_BARE_SLASH_RE`, e.g. `/head`) | No | Yes |
| roadmap/services/hooks.py:756 | Short acknowledgement / prompt (< 4 words) | No | Yes |
| roadmap/services/hooks.py:759 | Normal user prompt (>= 4 words, no skip prefix) | Yes | No |
| roadmap/services/hooks.py:759 | Terminal bash-input echoes (>= 4 words) | Yes | Yes |
| roadmap/services/hooks.py:759 | Terminal bash-stdout (>= 4 words) | Yes | Yes |
| roadmap/services/hooks.py:759 | Command caveats (>= 4 words without skip prefix) | Yes | Yes |
