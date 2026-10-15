# Plain Wording Proposals for UI Strings (views s-z)

| file:line | current string | proposed (max 8 words) | why |
|---|---|---|---|
| web/js/views/settings.js:37 | Preferences for this browser. Project settings live in the project files. | Browser preferences only; projects keep separate settings. | Over-long and vague about where settings live. |
| web/js/views/settings.js:43 | Read only on a phone: it can see every project and answer questions. It cannot change limits, overrides, rules, caps or approvals. | Phones can view projects and answer questions. | Over-long catalog of disallowed operations. |
| web/js/views/settings.js:50 | Global limits, the usage ledger and the global config live in the roadmap home folder. Each project keeps its rules in docs/rules.txt and its budget in budget.json. Run roadmap doctor to see the exact paths. | Run roadmap doctor to view data paths. | Over-long note leaking internal paths and jargon. |
| web/js/views/tokens.js:40 | Usage is stale, so this limit is not measured right now. | Usage data is outdated; limit unmeasured. | Over-long and uses developer jargon "stale". |
| web/js/views/tokens.js:85 | The tick at 80% is the warning line. | Marker at 80% indicates warning threshold. | Technical term "tick" replaced with clearer phrasing. |
| web/js/views/tokens.js:95 | Project stop: %s of weekly (from autonomy.json). | Project stop: %s of weekly budget. | Leaks internal filename autonomy.json into UI. |
| web/js/views/tokens.js:106 | Cap in thousands | Token limit (thousands) | Jargon "cap" lacks explicit token unit context. |
| web/js/views/tokens.js:163 | Lets this project run past its stops for a while. Logged in Activity. | Temporarily ignore limits; logged in Activity. | Informal wording ("for a while") and vague "stops". |
| web/js/views/tokens.js:170 | Project percentages are estimates (≈). Token counts are exact for reported jobs. | Percentages are estimates; reported token counts exact. | Over-long disclaimer repeated later in file. |
| web/js/views/tokens.js:173 | Usage outside these projects, such as chats or other machines, counts in global limits and makes project estimates high. | External usage skews project estimates higher. | Over-long run-on sentence. |
| web/js/views/tokens.js:175 | Tokens are counted when a job ends, so a long running job shows up late. | Tokens are counted when jobs finish. | Casual colloquial phrasing ("shows up late"). |
| web/js/views/tokens.js:176 | When the reader is off, those hours are added at the next reading, but they land on that day. | Offline usage syncs on next check. | Jargon describing background reader implementation details. |
| web/js/views/tokens.js:177 | Project % figures are estimates shown with ≈. Token figures are exact for reported jobs. | Percentages are estimates; token figures are exact. | Redundant item repeating line 170. |
| web/js/views/tokens.js:204 | The snapshot has no meters. Usage may still be loading. | Usage data still loading; limits unavailable. | Developer jargon ("snapshot has no meters"). |
| web/js/views/tokens.js:208 | This project only. Its own limits and spend, plus All projects limits that apply to it. | Project limits, spend, and applicable global limits. | Over-long and repetitive explanation. |
| web/js/views/tree.js:24 | needs you | Action needed | Conversational phrasing replaced with clear status. |
| web/js/views/usage.js:26 | Usage is old: %s | Usage data outdated: %s | Awkward phrasing ("Usage is old"). |
| web/js/views/usage.js:26 | Run Sync now, or check the usage source. | Click Sync now or check provider. | Technical term "usage source". |
| web/js/views/usage.js:30 | Stale | Outdated | Developer jargon badge label. |
| web/js/views/usage.js:30 | Usage %s min old | Updated %s min ago | Non-standard wording ("min old"). |
| web/js/views/usage.js:52 | Could not read plan usage. | Could not load account usage. | Ambiguous and technical phrasing ("read plan usage"). |
| web/js/views/work.js:113 | Tasks come from the project's task file. | Tasks load from the project plan. | Technical jargon referencing file storage structure. |
| web/js/views/work.js:127 | Work belongs to one project. | Select a project to view work. | Robotic explanation of internal data model. |
| web/js/views/work.js:130 | No project with that id. | Project not found. | Technical database jargon ("with that id"). |
| web/js/views/work.js:135 | Could not load this project. Retrying. | Failed loading project; retrying automatically. | Choppy telegraphic phrasing. |
| web/js/views/workflow.js:198 | Head | Lead agent | Architectural jargon replaced with clear role label. |
| web/js/views/workflow.js:372 | Task %s queued, waiting for a worker | Task %s queued, waiting for agent | Distributed systems jargon ("worker"). |
| web/js/views/workflow.js:377 | tokens unknown | unknown token count | Telegraphic phrase lacking clear context. |
| web/js/views/workflow.js:651 | Agents record work with roadmap job start. | No agent jobs recorded yet. | Empty state leaks internal CLI command. |
| web/js/views/workflow.js:667 | %s of %s nodes | %s of %s items | Computer science graph jargon ("nodes"). |
| web/js/views/workflow.js:673 | Done phases are collapsed to keep the diagram fast. | Completed phases collapsed for faster rendering. | Informal performance disclaimer ("keep diagram fast"). |
| web/js/views/workflow.js:674 | Show all (slow) | Show all phases | Informal UI warning label ("(slow)"). |
| web/js/views/workflow.js:676 | No nodes match these filters. | No tasks match these filters. | Graph jargon ("nodes") confusing to users. |
| web/js/views/workflow.js:681 | Focus off | Reset focus | Ambiguous action label. |
| web/js/views/workflow.js:715 | Open a project to see its diagram. Timeline and Table show every project. | Select a project to view diagram. | Over-long guidance describing other views. |
| web/js/views/workflow.js:717 | Could not load the diagram. Timeline and Table still work. | Diagram failed to load. | Over-long error banner mentioning other views. |
| web/js/views/workflow.js:746 | Tokens K | Tokens (thousands) | Jargon abbreviation without unit clarity. |
| web/js/views/workflow.js:764 | Hover or focus a bar or card to see its details here. | Select an item to view details. | Over-long and exposes technical interaction terms. |
| web/js/views/workflow.js:817 | Depends on (Map) | Depends on | Leaks view name "(Map)" into legend. |
| web/js/views/workflow.js:857 | Live. Each bar is a job from start to end, in lanes by role and model. Hover or focus a bar for its details, and press Enter to open its task. | Live job timeline by role and model. | Verbose 31-word run-on instructional paragraph. |
