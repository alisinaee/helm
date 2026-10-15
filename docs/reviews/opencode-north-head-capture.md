# Audit: Head capture hook skip rules for missed terminal or system prompts

| file:line | problem | fix |
|-----------|---------|-----|
| roadmap/services/hooks.py:526 | HEAD_SKIP_PREFIXES only contains broad prefixes (`<bash-`, `<local-command-`) but actual terminal echo prompts use more specific tags like `<bash-input>`, `<bash-stdout>`, `<bash-stderr>`, `<local-command-caveat>` | Add specific terminal echo prompt tags to HEAD_SKIP_PREFIXES to match the actual patterns used in tests |
| roadmap/services/hooks.py:747 | Skip logic uses `startswith()` which cannot match tags like `<bash-input>` since they don't start with `<bash-` | Change skip logic to use regex pattern matching (`re.match()`) for comprehensive tag matching, or expand prefixes to cover all tag variations |
| roadmap/services/hooks.py:747 | Skip logic only checks text start position, misses terminal/system prompts embedded in larger text contexts | Implement more sophisticated skip logic that can identify tags anywhere in the text, not just at the start |
