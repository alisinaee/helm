Here's the audit of Agents view labels with issues found:

| file:line | problem | fix |
|-----------|---------|-----|
| web/js/views/agents.js:82 | Delegation label uses `engineLabel(c.model)` without `engineModel` parameter, missing detailed model info | Use `engineLabel(c.model, c.engineModel)` |
| web/js/views/agents.js:90 | Token label "not yet" inconsistent with finished jobs "unknown" for null tokens | Use "unknown" consistently |
| web/js/views/agents.js:28 | Fallback returns raw model name if not in ENGINES dict, potentially showing unparseable model strings | Show a dash "—" instead of raw model |
| web/js/views/agents.js:21 | `model` is converted to lowercase before lookup in ENGINES dict, losing case info | Preserve original model case in lookup |
| web/js/views/agents.js:111 | `STATUS_WORDS[job.status] || job.status` uses lowercase status keys, may show lowercase vs capitalized inconsistency | Use `STATUS_WORDS[job.status.toLowerCase()] || job.status` |
