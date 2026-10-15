| file:line | problem | fix |
|---|---|---|
| web/js/views/agents.js:14 | Model label "Haiku 5.5" uses non-existent version 5.5 for Claude Haiku | UNKNOWN |
| web/js/views/agents.js:14 | Model label "Sonnet 5.5" uses non-existent version 5.5 for Claude Sonnet | UNKNOWN |
| web/js/views/agents.js:14 | Model label "Opus 5.5" uses non-existent version 5.5 for Claude Opus | UNKNOWN |
| web/js/views/agents.js:14 | Model label "agy · Gemini 3.8 Flash" uses non-existent version 3.8 for Gemini Flash | UNKNOWN |
| web/js/views/agents.js:15 | Model label for bare engine "cursor" maps to "cursor · Auto" instead of engine name | UNKNOWN |
| web/js/views/agents.js:26 | Model label "cursor · Grok 4.7" uses non-existent version 4.7 for Grok | UNKNOWN |
| web/js/views/agents.js:36 | Effort label defaults to "default" for Haiku models which do not support thinking effort | UNKNOWN |
| web/js/views/agents.js:36 | Effort label defaults to "not set" for Claude models not matching regex (e.g. claude-3-5-sonnet) | UNKNOWN |
| web/js/views/agents.js:94 | Job delegation label calls engineLabel(c.model) without c.engineModel, losing exact model name | c.role \|\| engineLabel(c.model, c.engineModel) |
| web/js/views/agents.js:130 | Model column in finished jobs includes status chip ("Done"/"Failed") under Model header | UNKNOWN |
