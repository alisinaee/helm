# ARIA Review: Interactive Elements Missing ARIA Attributes

| file:line | element | missing | fix |
|---|---|---|---|
| web/js/views/tasks.js:77 | `<span class="t-title" tabindex="0">` | `role="button"`, `aria-label` | Add `role="button"` and `aria-label="Edit title for " + esc(task.id)` |
| web/js/views/toast.js:99 | `<button type="button" class="btn" data-action="toast-undo">` | `aria-label` | Add `aria-label="Undo " + esc(t.text)` |
| web/js/views/toast.js:104 | `<button type="button" class="btn" data-action="toast-close">` | Contextual `aria-label` | Update to `aria-label="Dismiss notification: " + esc(t.text)` |
| web/js/views/tokens.js:108 | `<input class="lim-num" type="number">` | Specific `aria-label` | Add `aria-label="Cap in thousands for " + esc(name)` |
| web/js/views/tokens.js:110 | `<button type="button" class="btn btn-small" data-action="spend-cap">` | `aria-label` | Add `aria-label="Save cap for " + esc(name)` |
| web/js/views/tokens.js:166 | `<select class="lim-select">` | Specific `aria-label` | Add `aria-label="Override duration in hours"` |
| web/js/views/tokens.js:167 | `<button type="button" class="btn" data-action="lim-override">` | `aria-label` | Add `aria-label="Apply override for " + esc(pid)` |
| web/js/views/topbar.js:22 | `<button type="button" class="crumb-proj" data-action="panel-toggle">` | `aria-expanded`, `aria-controls` | Add `aria-expanded="false"` and `aria-controls="panel"` |
| web/js/views/topbar.js:44 | `<button type="button" class="btn" data-action="control" data-op="control.resume">` | `aria-label` | Add `aria-label="Resume project " + esc(c.id)` |
| web/js/views/topbar.js:52 | `<button type="button" class="btn" data-action="control" data-op="control.stop">` | `aria-label` | Add `aria-label="Stop project " + esc(c.id)` |
| web/js/views/topbar.js:120 | `<button type="button" class="btn" data-action="help-open">` | `aria-haspopup`, `aria-controls` | Add `aria-haspopup="dialog"` and `aria-controls="keyboard-help"` |
| web/js/views/tree.js:14 | `<input type="checkbox" data-wk="sub">` | Contextual `aria-label` | Add `aria-label="Subtask " + esc(s.addr) + ": " + esc(s.t)` |
| web/js/views/tree.js:28 | `<a class="wk-title">` | Contextual `aria-label` | Add `aria-label="Task " + esc(task.id) + ": " + esc(task.title)` |
| web/js/views/usage.js:57 | `<button type="button" class="btn" data-action="sync-usage">` | `aria-busy` | Add `aria-busy="' + (syncing ? "true" : "false") + '"` |
| web/js/views/work.js:104 | `<button type="button" data-wk="view">` | `aria-controls` | Add `aria-controls="wk-body"` |
| web/js/views/work.js:117 | `<button type="button" class="btn btn-small" data-wk="clear">` | Contextual `aria-label` | Add `aria-label="Clear active task filters"` |
| web/js/views/workflow.js:436 | `<g class="wf-bar" tabindex="0" role="button">` | `role="link"` or `aria-controls` | Set `role="link"` or add `aria-controls="panel"` for details navigation |
| web/js/views/workflow.js:600 | `<a class="wfg-chip">` | Contextual `aria-label` | Add `aria-label="Filter by " + esc(label) + ": " + esc(v)` |
| web/js/views/workflow.js:608 | `<button type="button" class="btn btn-small" data-wf-map-op="...">` | `aria-controls` | Add `aria-controls="wfg-host"` |
| web/js/views/workflow.js:652 | `<a href="...">Open Agents</a>` | Contextual `aria-label` | Add `aria-label="Open Agents view for " + esc(ctx.pid)` |
| web/js/views/workflow.js:662 | `<a href="...">Dependency / Time</a>` | Contextual `aria-label` | Add `aria-label="Order by dependency"` / `aria-label="Order by time"` |
| web/js/views/workflow.js:673 | `<a href="...">Show all (slow)</a>` | `aria-label` | Add `aria-label="Show all phases including collapsed done phases (slow)"` |
| web/js/views/workflow.js:676 | `<a href="...">Clear filters</a>` | `aria-label` | Add `aria-label="Clear map diagram filters"` |
| web/js/views/workflow.js:767 | `<a class="btn btn-small" href="...">Approve in Roadmap</a>` | `aria-label` | Add `aria-label="Approve task " + esc(it.task) + " in Roadmap"` |
| web/js/views/workflow.js:785 | `<a class="btn btn-small" href="...">Open</a>` | `aria-label` | Add `aria-label="Open task " + esc(it.task)` |
| web/js/views/workflow.js:786 | `<a class="btn btn-small" href="...">Open</a>` | `aria-label` | Add `aria-label="Open task " + esc(it.task)` |
| web/js/views/workflow.js:797 | `<a href="...">Timeline / Map / Table</a>` | Contextual `aria-label` | Add `aria-label="Switch to " + esc(v[1]) + " view"` |
| web/js/views/workflow.js:805 | `<a href="...">2 h / Today / Week / All</a>` | Contextual `aria-label` | Add `aria-label="Filter range to " + esc(r[1])` |
| web/js/views/workflow.js:867 | `<a href="...">Open Agents</a>` | Contextual `aria-label` | Add `aria-label="Open Agents view for " + esc(route.id \|\| "all projects")` |
