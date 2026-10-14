# Job staffer-mv7pmmir-239574de (staffer, done)

|file:line|now (quoted exactly)|plain|why|
|---|---|---|---|
|web/js/views/legend.js:33|"Glyphs, chips and token estimates"|Symbols, tags, and token estimates|Replaces developer frontend jargon with plain terms.|
|web/js/views/limits.js:67|" A fair day is about "| A typical day uses about |Clarifies the vague phrase "fair day" into clear language about daily usage.|
|web/js/views/limits.js:112|"Thousands"|Thousands of tokens|Explicitly states the measurement unit instead of a bare number term.|
|web/js/views/limits.js:129|"from autonomy.json (the weekly stop)"|from project settings (weekly stop)|Avoids exposing an internal configuration filename to end users.|
|web/js/views/limits.js:130|"from budget.json (the project token budget)"|from project budget|Avoids exposing an internal JSON filename to end users.|
|web/js/views/limits.js:132|"and its action is not in the snapshot yet, so it cannot be edited here"|and its action is not loaded yet, so it cannot be edited here|Replaces the internal codebase term "snapshot" with "loaded".|
|web/js/views/limits.js:181|"Warn shows a banner. Stop blocks agents from starting new work."|Warn displays an alert banner. Stop prevents agents from starting new work.|Uses clearer verbs and nouns for the user explanation.|
|web/js/views/limits.js:258|"A cap is a number of thousands above 0, or empty for no cap."|Enter a limit in thousands above 0, or leave empty for no limit.|Replaces developer shorthand "cap" with "limit" and clarifies instruction.|
|web/js/views/list.js:173|" sub</span>"| subtasks</span>|Expands clipped abbreviation "sub" into "subtasks".|
|web/js/views/list.js:174|" cmt</span>"| comments</span>|Expands clipped abbreviation "cmt" into "comments".|
|web/js/views/nav.js:43|"<span class=\"sr-only\"> need you</span></span>"|<span class="sr-only"> need your input</span></span>|Clarifies screen reader text to state what is needed from the user.|
|web/js/views/needsyou.js:11|" waiting on you"| waiting for your input|Uses standard phrasing explaining that tasks await user feedback.|
|web/js/views/needsyou.js:14|"Nothing waits on you."|No tasks are waiting for your input.|Replaces stilted colloquial phrasing with clear status text.|
|web/js/views/next.js:15|"Nothing queued."|No upcoming items scheduled.|Clarifies empty queue state in ordinary language.|
|web/js/views/overview.js:78|"Stopped. No agent starts a new job."|Stopped. Agents will not start new jobs.|Corrects awkward tense and phrasing into natural, direct English.|
|web/js/views/overview.js:82|"Blocked by a limit. Agents wait."|Blocked by a limit. Agents are paused.|Replaces terse and awkward phrasing with clear status wording.|
|web/js/views/overview.js:95|"At this pace the limit is reached about "|At this rate, the limit will be reached around |Uses conventional terminology ("rate", "will be reached around").|
|web/js/views/overview.js:105|"Usage is unknown until the next reading."|Usage data will appear after the next update.|Replaces technical telemetry phrasing with plain status text.|
|web/js/views/overview.js:107|" points of your weekly allowance"|% of your weekly allowance|Removes the ambiguous term "points" when displaying percentage allowance.|
|web/js/views/overview.js:111|"Tokens tracked today "|Tokens used today |Uses direct language ("used") instead of backend logging jargon ("tracked").|
|web/js/views/panel.js:47|"Choose a project first."|Please select a project first.|Uses standard user-interface guidance.|
|web/js/views/panel.js:102|"A cap is a number of thousands of tokens, 0 or more."|Token limits must be 0 or greater (in thousands).|Replaces developer jargon "cap" with clear validation guidance.|
|web/js/views/panel.js:133|"Type the subtask first."|Please enter a subtask title.|Uses standard form validation wording.|
|web/js/views/panel.js:148|"Type the comment first."|Please enter a comment.|Uses standard form validation wording.|
|web/js/views/panel.js:214|"Type the answer first."|Please enter an answer.|Uses standard form validation wording.|
|web/js/views/phases.js:96|"No tasks in this phase."|No tasks in this phase yet.|Adds helpful temporal context for empty phases during project planning.|
|web/js/views/phases.js:135|" items done"| tasks completed|Replaces generic "items done" with specific domain wording ("tasks completed").|
|web/js/views/planner.js:130|" (unlink its tasks first)"| (remove linked tasks first)|Replaces technical relational jargon ("unlink") with plain user action.|
|web/js/views/planner.js:162|"No acceptance line yet"|No acceptance criteria specified|Replaces internal codebase jargon ("acceptance line") with standard project management terminology.|
|web/js/views/planner.js:194|" uncovered "| without tasks |Explains what "uncovered" actually means (features that have no tasks).|
|web/js/views/planner.js:209|" orphan "| unassigned |Replaces developer software jargon ("orphan") with everyday terminology ("unassigned").|
|web/js/views/planner.js:238|"Acceptance (how the person knows it works)"|Acceptance criteria (how you verify it works)|Addresses the user directly ("you") instead of awkwardly in the third person ("the person").|
|web/js/views/planner.js:270|" tasks are orphans."| tasks are not assigned to any feature.|Clarifies technical jargon for project stakeholders.|
|web/js/views/planner.js:320|"This feature is not done yet. Accept it anyway?"|This feature has open tasks. Mark it accepted anyway?|Clarifies that unfinished tasks remain before accepting the feature.|
|web/js/views/projects.js:84|"A usage limit is blocking this project"|A usage limit has paused work on this project|Replaces the ambiguous term "blocking" with clear explanation that work is paused.|
|web/js/views/recent.js:18|"No log rows."|No recent progress recorded.|Replaces database jargon ("log rows") with plain activity summary text.|
|web/js/views/research.js:40|"The note could not be read (HTTP "|Could not load note (error |Removes technical HTTP protocol references from user-facing error messages.|
|web/js/views/roadmap.js:17|"No plan yet. Ask the lead to run plan import."|No plan yet. Import a plan to view the roadmap.|Removes CLI command references and rigid role assumptions from GUI messaging.|
|web/js/views/rules.js:113|"Rules are not in the snapshot yet."|Rules have not loaded yet.|Replaces internal codebase architecture jargon ("snapshot") with "loaded".|
|web/js/views/running.js:80|"Recently finished "|Recently completed |Uses standard professional terminology for finished work.|

DONE

[unrestricted] agy modified the working tree during this staffer run — verify the task asked for it. Delta (`git status --porcelain` entries that appeared or changed during the run):
   M web/js/views/workflow.js
  ?? web/css/graph.css
  ?? web/js/graph/render.js
ACTION FOR THE CALLING AGENT: inspect these changes (`git diff`) before trusting this staffer. Rollback: `git checkout -- <path>` for tracked files, delete the new untracked ones.
