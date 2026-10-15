| file:line | current string | proposed | why |
|---|---|---|---|
| web/js/views/legend.js:8 | built, not fully proven yet | Built; verification pending | Jargon; "proven" is colloquial developer phrasing. |
| web/js/views/legend.js:11 | parked; not counted in tasks left | Deferred; excluded from task count | Jargon; "parked" is slang, replaces with standard status term. |
| web/js/views/legend.js:13 | estimated tokens for the work; – means no value | Estimated tokens; dash indicates unestimated | Over-long (9 words); simplifies verbose explanation of dash symbol. |
| web/js/views/legend.js:14 | the check after the work, with its own model and estimate | Verification step, model, and estimate | Over-long (10 words); replaces verbose sentence with concise label. |
| web/js/views/legend.js:15 | this task waits for the person | Task waiting for your input | Awkward phrasing ("the person"); directly addresses user. |
| web/js/views/legend.js:26 | Models that do the work | Execution models | Conversational filler; replaces with concise technical label. |
| web/js/views/legend.js:33 | Glyphs, chips and token estimates | Icons, badges, and token estimates | UI implementation jargon ("glyphs", "chips") replaced by plain terms. |
| web/js/views/limits.js:54 |  of weekly |  of weekly quota | Fragmented jargon missing referent noun; clarifies unit. |
| web/js/views/limits.js:64 |  tokens. Exact for jobs that report their tokens. |  tokens; exact if reported | Over-long and redundant ("tokens... their tokens"); aligns concise metrics. |
| web/js/views/limits.js:66 | of weekly, per day | of weekly limit per day | Clipped jargon; clarifies daily pacing against weekly limit. |
| web/js/views/limits.js:67 |  A fair day is about  |  Daily average is about  | "Fair day" is colloquial jargon; "daily average" is standard. |
| web/js/views/limits.js:103 | % of weekly | % of weekly limit | Clipped jargon; clarifies unit for select dropdown. |
| web/js/views/limits.js:112 | Thousands | Tokens (k) | Ambiguous label without unit context; specifies thousand tokens. |
| web/js/views/limits.js:129 | from autonomy.json (the weekly stop) | From weekly stop policy | Implementation jargon exposing internal config filename autonomy.json. |
| web/js/views/limits.js:130 | from budget.json (the project token budget) | From project token budget | Implementation jargon exposing internal config filename budget.json. |
| web/js/views/limits.js:132 | and its action is not in the snapshot yet, so it cannot be edited here | Pending snapshot sync; read-only | Over-long (14 words) and contains architecture jargon ("snapshot"). |
| web/js/views/limits.js:174 | No limits. Agents may use your whole weekly allowance. | No limits; full weekly allowance available | Over-long (9 words); provides concise empty-state message. |
| web/js/views/limits.js:181 | Warn shows a banner. Stop blocks agents from starting new work. | Warn alerts; Stop pauses new work | Over-long (10 words); shortens explanatory footer text. |
| web/js/views/limits.js:258 | A cap is a number of thousands above 0, or empty for no cap. | Enter thousands above 0, or clear | Over-long (13 words) and awkward phrasing ("number of thousands"). |
| web/js/views/list.js:106 | No model | Unassigned model | Ambiguous status sounds like missing data; clarifies configuration state. |
| web/js/views/list.js:160 | Select all shown tasks | Select all visible tasks | Informal phrasing ("shown"); "visible" is standard UI convention. |
| web/js/views/list.js:173 |  sub |  subtasks | Developer shorthand jargon; clarifies unit in fixed-width table column. |
| web/js/views/list.js:174 |  cmt |  notes | Developer abbreviation jargon; clarifies badge in fixed-width column. |
| web/js/views/nav.js:43 |  need you |  awaiting your action | Screen reader text uses informal anthropomorphic phrasing. |
| web/js/views/nav.js:47 |  tasks need you |  tasks awaiting your action | Screen reader text uses informal phrasing; clarifies required action. |
| web/js/views/nav.js:78 | Collapse navigation | Collapse menu | Standard UI terminology; keeps aria-label concise. |
| web/js/views/needsyou.js:11 |  waiting on you |  awaiting action | Conversational phrasing replaced with concise action status. |
| web/js/views/needsyou.js:14 | Nothing waits on you. | No actions pending | Conversational phrasing replaced with standard empty-state text. |
| web/js/views/needsyou.js:15 | Needs you | Needs Action | Informal and anthropomorphic section title; standardizes action label. |
| web/js/views/next.js:15 | Nothing queued. | Queue is empty. | Standardizes empty queue messaging. |
| web/js/views/next.js:18 | Next up | Upcoming Queue | Informal conversational phrasing; clarifies roadmap queue section. |
| web/js/views/overview.js:59 | Usage across all projects is at  | All projects usage:  | Over-long conversational banner prefix; condenses header. |
| web/js/views/overview.js:62 |  Work is stopped by this limit. |  Work stopped by limit. | Removes passive conversational filler words. |
| web/js/views/overview.js:62 |  Work keeps running. |  Work continues. | Conversational slang ("keeps running") replaced by concise status. |
| web/js/views/overview.js:78 | Stopped. No agent starts a new job. | Stopped. No new jobs will run. | Awkward phrasing replaced with clear system behavior statement. |
| web/js/views/overview.js:82 | Blocked by a limit. Agents wait. | Limit reached; execution paused. | Anthropomorphic jargon ("Agents wait"); clarifies operational state. |
| web/js/views/overview.js:95 | At this pace the limit is reached about  | Projected limit reached at  | Conversational and wordy (8 words); clarifies projection. |
| web/js/views/overview.js:105 | Usage is unknown until the next reading. | Usage pending next sync. | "Reading" is hardware/sensor jargon; clarifies software sync event. |
| web/js/views/overview.js:115 | No limits set. Agents may use your whole weekly allowance. | No limits set; full allowance available. | Over-long (10 words); shortens explanatory placeholder. |
| web/js/views/palette.js:189 | Search tasks, issues, questions or type > for commands | Search items or type > for commands | Over-long (9 words); replaces exhaustive list with concise category. |
