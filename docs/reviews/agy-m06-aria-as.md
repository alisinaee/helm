| file:line | element | missing | fix |
|---|---|---|---|
| web/js/views/activity.js:15 | `<button data-action="undo-line">Undo</button>` | aria-label | Add `aria-label="' + esc("Undo " + (line.sum \|\| line.op \|\| "change")) + '"` |
| web/js/views/agents.js:52 | `<a href="...">` | aria-label | Add `aria-label="' + esc("Task " + job.task) + '"` |
| web/js/views/board.js:159 | `<button data-wk="clear">Clear filters</button>` | aria-controls | Add `aria-controls="wk-filters"` |
| web/js/views/board.js:187 | `<button data-wk="status" data-to="todo">Move to Todo</button>` | aria-label | Add `aria-label="' + esc("Move task " + task.id + " to Todo") + '"` |
| web/js/views/board.js:189 | `<button data-wk="run-start">Queue task</button>` | aria-label | Add `aria-label="' + esc("Queue task " + task.id) + '"` |
| web/js/views/board.js:190 | `<button data-wk="run-stop">Stop task</button>` | aria-label | Add `aria-label="' + esc("Stop task " + task.id) + '"` |
| web/js/views/board.js:240 | `<button class="wk-tab" data-wk="tab">` | aria-controls | Add `aria-controls="' + esc("wk-col-" + col.key) + '"` |
| web/js/views/details.js:128 | `<button data-side="status">` | aria-label | Add `aria-label="' + esc("Set status to " + s[1] + " for " + task.id) + '"` |
| web/js/views/details.js:187 | `<button data-side="start">Start</button>` | aria-label | Add `aria-label="' + esc("Start task " + task.id) + '"` |
| web/js/views/details.js:189 | `<button data-side="stop">Stop</button>` | aria-label | Add `aria-label="' + esc("Stop task " + task.id) + '"` |
| web/js/views/details.js:196 | `<button data-side="copy-launch">Copy command</button>` | aria-label | Add `aria-label="Copy launch command"` |
| web/js/views/details.js:210 | `<button type="submit" data-focus="cap-save">Save cap</button>` | aria-label | Add `aria-label="' + esc("Save token cap for " + task.id) + '"` |
| web/js/views/details.js:211 | `<button data-side="cap-clear">Clear cap</button>` | aria-label | Add `aria-label="' + esc("Clear token cap for " + task.id) + '"` |
| web/js/views/details.js:230 | `<button type="submit" data-focus="sub-add-btn">Add subtask</button>` | aria-label | Add `aria-label="' + esc("Add subtask to " + task.id) + '"` |
| web/js/views/details.js:246 | `<button type="submit" data-focus="comment-btn">Add comment</button>` | aria-label | Add `aria-label="' + esc("Add comment to " + task.id) + '"` |
| web/js/views/details.js:357 | `<button data-side="close-issue">Close issue</button>` | aria-label | Add `aria-label="' + esc("Close issue " + issue.id) + '"` |
| web/js/views/details.js:371 | `<button data-side="answer">` | aria-label | Add `aria-label="' + esc("Answer " + opt + " for " + question.id) + '"` |
| web/js/views/details.js:375 | `<div class="d-btns">` | role, aria-label | Add `role="group" aria-label="' + esc("Answers for " + question.id) + '"` |
| web/js/views/details.js:379 | `<button type="submit" data-focus="answer-btn">Send answer</button>` | aria-label | Add `aria-label="' + esc("Send answer for " + question.id) + '"` |
| web/js/views/inbox.js:108 | `<button class="btn qc-opt" data-action="inbox-answer">` | aria-label | Add `aria-label="' + esc("Choose " + opt + " for " + q.id) + '"` |
| web/js/views/inbox.js:123 | `<a class="qc-task">` | aria-label | Add `aria-label="' + esc("View task " + q.task) + '"` |
| web/js/views/inbox.js:145 | `<a href="...">` | aria-label | Add `aria-label="' + esc("View task " + entry.item.id) + '"` |
| web/js/views/inbox.js:186 | `<a href="...">` | aria-label | Add `aria-label="' + esc("View question " + e.q.id) + '"` |
| web/js/views/issues.js:38 | `<a href="...">` | aria-controls | Add `aria-controls="iss-list"` |
| web/js/views/limits.js:97 | `<input class="lim-range" type="range">` | aria-controls | Add `aria-controls="' + esc("lim-prev-" + id) + '"` |
| web/js/views/limits.js:100 | `<input class="lim-num" type="number">` | aria-controls | Add `aria-controls="' + esc("lim-prev-" + id) + '"` |
| web/js/views/limits.js:115 | `<button data-action="lim-step" data-dir="-1">−</button>` | aria-controls | Add `aria-controls="' + esc("lim-input-" + id) + '"` |
| web/js/views/limits.js:118 | `<button data-action="lim-step" data-dir="1">+</button>` | aria-controls | Add `aria-controls="' + esc("lim-input-" + id) + '"` |
| web/js/views/limits.js:124 | `<button data-action="lim-del">Delete</button>` | aria-label | Add `aria-label="' + esc("Delete limit " + id) + '"` |
| web/js/views/limits.js:135 | `<button data-action="lim-del">Delete</button>` | aria-label | Add `aria-label="' + esc("Delete limit " + row.id) + '"` |
| web/js/views/limits.js:151 | `<button data-action="lim-sheet">Edit / Done</button>` | aria-label | Add `aria-label="' + esc((sheetOpen ? "Done editing" : "Edit") + " limit " + row.id) + '"` |
| web/js/views/limits.js:171 | `<button data-action="lim-add">+ Add limit</button>` | aria-expanded, aria-controls | Add `aria-expanded="' + (addOpen ? "true" : "false") + '" aria-controls="lim-presets"` |
| web/js/views/list.js:144 | `<button data-op="start">Start</button>` | aria-label | Add `aria-label="Start selected tasks"` |
| web/js/views/list.js:145 | `<button data-op="stop">Stop</button>` | aria-label | Add `aria-label="Stop selected tasks"` |
| web/js/views/list.js:155 | `<button class="wk-sort" data-wk="sort">` | aria-label | Add `aria-label="' + esc("Sort by " + h[1] + (on ? (sort.dir === "desc" ? " descending" : " ascending") : "")) + '"` |
| web/js/views/nav.js:77 | `<button class="nav-collapse" data-action="nav-mini">` | aria-expanded, aria-controls | Add `aria-expanded="' + (mini ? "false" : "true") + '" aria-controls="nav-list"` |
