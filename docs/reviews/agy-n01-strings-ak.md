# UI String Review: Wording Simplification

| file:line | current string | proposed | why |
|---|---|---|---|
| web/js/views/activity.js:44 | Newest first. Each project keeps its last 15 lines. | Recent activity across projects. | Replaces internal buffer limit details with clear user-facing scope. |
| web/js/views/activity.js:44 | Newest first, 50 at most. | Recent project activity. | Removes technical row-cap implementation detail. |
| web/js/views/activity.js:51 | Activity lines | Activity log | Replaces raw data file term with standard UI terminology. |
| web/js/views/agents.js:53 | no task | No task assigned | Uses proper sentence casing and clear status phrasing. |
| web/js/views/agents.js:55 | handed to | Delegated to | Replaces informal phrasing with standard subagent delegation terminology. |
| web/js/views/agents.js:109 | Last 10 finished | Recently finished jobs | Provides a clean section heading without hardcoded count jargon. |
| web/js/views/agents.js:118 | Live. Workers sit under the job that started them. Stop asks the project to stop that task. | Active agents and subagents. Stop halts tasks. | Condenses 16-word awkward explanation into concise summary. |
| web/js/views/board.js:188 | Move to Todo | Move to To Do | Uses standard two-word English spelling for task status. |
| web/js/views/board.js:189 | Queue run | Queue task | Clarifies action targets the task rather than ambiguous "run"; aligns actions in grid column. |
| web/js/views/board.js:191 | Stop run | Stop task | Maintains consistent task lifecycle action terminology; aligns actions in grid column. |
| web/js/views/board.js:254 | Drag a card to another column, or use its buttons. Keys: s Start, d Done, h Hold, x Reopen. Alt+Up and Alt+Down move the focused card one column. | Drag cards or use keys s/d/h/x. | Condenses 27-word keyboard manual into concise shortcut hint. |
| web/js/views/board.js:257 | Use a card's buttons to change its status. Keys: s Start, d Done, h Hold, x Reopen. | Use buttons or keys s/d/h/x. | Shortens 14-word hint for compact mobile/touch header. |
| web/js/views/details.js:11 | Partial | In progress | Replaces schema state key with standard UI status label. |
| web/js/views/details.js:90 | Choose a project to see its details. | Select a project to view details. | Uses standard concise UI directive phrasing. |
| web/js/views/details.js:98 | The card shows when its snapshot arrives. | Details load once snapshot syncs. | Eliminates colloquial "card shows" phrasing. |
| web/js/views/details.js:108 | Tasks left | Remaining tasks | Standard noun phrase; pairs with numbers aligned in fixed grid column. |
| web/js/views/details.js:109 | Tokens left | Remaining tokens | Professional terminology matching KPI metrics; keeps numbers aligned in grid columns. |
| web/js/views/details.js:112 | Open blockers | Blocking issues | More precise noun phrase; aligns numbers in grid column. |
| web/js/views/details.js:137 | Queued, a session is picking it up | Queued: agent starting now | Replaces conversational sentence with clear status indicator. |
| web/js/views/details.js:138 | Queued, picked up at the session's next stop | Queued: awaiting agent pause | Clarifies scheduler state without conversational filler. |
| web/js/views/details.js:139 | Queued, waiting for a session | Queued: waiting for terminal session | Explicitly names required CLI terminal listener. |
| web/js/views/details.js:157 | Copy failed, select the command above | Copy failed. Please copy manually. | Professional error message with clear user instruction. |
| web/js/views/details.js:207 | Cap in thousands of tokens | Token cap (thousands) | Shortens verbose input label and clarifies unit. |
| web/js/views/details.js:279 | Rules that apply | Applicable rules | Replaces conversational heading with concise terminology. |
| web/js/views/details.js:317 | Not linked to a feature. | No feature linked. | Concise empty-state description. |
| web/js/views/details.js:340 | Definition of done | Completion criteria | Replaces agile jargon acronym DOD with plain wording. |
| web/js/views/details.js:387 | This item is not open in this project. | Item not found or closed. | Direct and informative banner message. |
| web/js/views/details.js:388 | It may have been closed or answered. Go back to Projects. | Item was resolved. Return to Projects. | Shortens 10-word banner body text. |
| web/js/views/extras.js:31 | spikes | Research spikes: | Clarifies internal engineering jargon "spikes". |
| web/js/views/extras.js:32 | real hardware | Hardware checks: | Standardizes test board label; aligns numbers in grid column. |
| web/js/views/home.js:30 | Nothing is running. | No active runs. | Concise empty-state description. |
| web/js/views/home.js:48 | need you | awaiting input | Replaces informal colloquialism with clear status description. |
| web/js/views/home.js:88 | No project with that id. | Project not found. | Standard 404 error phrasing. |
| web/js/views/home.js:99 | Fix the file named above, then save it. | Fix file syntax and save. | Condenses wordy banner instruction. |
| web/js/views/inbox.js:15 | Time is up. The default applies shortly. | Time expired; applying default choice. | Replaces conversational notice with precise system action. |
| web/js/views/inbox.js:130 | This question has no options. Answer it in the terminal. | No options. Answer in terminal. | Cuts 10-word instructional sentence in half. |
| web/js/views/inbox.js:156 | All quiet. Nothing needs you. | Inbox empty. No actions pending. | Replaces folksy slang ("All quiet") with professional status. |
| web/js/views/issues.js:58 | Say what is wrong in one line. | Brief one-line summary. | Clear, concise form field helper text. |
| web/js/views/issues.js:64 | This is a blocker: its task shows Blocked until the issue is closed. A blocker with no task blocks nothing. | Blocks linked task until closed. | Cuts 19-word rambling explanation down to essential behavior. |
| web/js/views/kpi.js:25 | partly done | in progress | Replaces informal "partly done" with standard UI lifecycle status. |
