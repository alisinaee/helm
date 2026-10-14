# Job staffer-mv7pgbup-59eb3551 (staffer, done)

|function or branch file:line|missing case|what a test should assert|
|---|---|---|
|roadmap/services/commands.py:136|calling `run("task.start", {"id": "P1.1"}, ...)`|asserts return is `{"task": "P1.1", "queued": True}` and task is queued|
|roadmap/services/commands.py:142|calling `run("task.stop", {"id": "P1.1"}, ...)`|asserts return is `{"task": "P1.1", "stop": True}` and stop entry is queued|
|roadmap/services/commands.py:153|queueing a stop request when the task is already queued|asserts RoadmapError conflict "P1.1 is already queued; not changed" is raised|
|roadmap/services/commands.py:183|calling `run("subtask.toggle", {"addr": "P1.1/1"}, ...)`|asserts subtask status toggles and inverse is `subtask.restore`|
|roadmap/services/commands.py:204|calling `run("subtask.add", {"id": "P1.1", "title": "sub"}, ...)`|asserts subtask is added to the task and returns subtask metadata|
|roadmap/services/commands.py:240|calling `run("plan.move", {"id": "P1.2", "before": "P1.1"}, ...)`|asserts task order is updated and inverse is `plan.move`|
|roadmap/services/commands.py:251|calling `plan.move` with `id == ref`|asserts RoadmapError usage "a task cannot move next to itself" is raised|
|roadmap/services/commands.py:294|calling `run("question.ask", {"text": "Q", "opts": ["a", "b"]}, ...)`|asserts question record is created and returned with an id|
|roadmap/services/commands.py:304|calling `run("question.answer", {"id": "Q1", "value": "a"}, ...)`|asserts question is marked answered and inverse is `question.reopen`|
|roadmap/services/commands.py:323|calling `run("comment.add", {"on": "P1.1", "text": "c"}, ...)`|asserts comment is added to target and comment record is returned|
|roadmap/services/commands.py:338|calling `run("issue.new", {"title": "issue", "tasks": ["P1.1"]}, ...)`|asserts new issue is opened and inverse is `issue.status` closed|
|roadmap/services/commands.py:350|calling `run("issue.close", {"id": "I1"}, ...)`|asserts issue status becomes closed and changed is True|
|roadmap/services/commands.py:383|calling `run("issue.link", {"id": "I1", "tasks": ["P1.1"]}, ...)`|asserts issue links are updated and inverse is `issue.links`|
|roadmap/services/commands.py:455|undoing a non-phone activity with `current_source() == "phone"`|asserts RoadmapError forbidden "the phone may undo only its own changes" is raised|
|roadmap/services/commands.py:460|undo execution encountering an exception during inverse op execution|asserts `undoFailed` entry is appended to `undo.jsonl` and exception re-raises|
|roadmap/services/commands.py:624|calling `commands.write(project_id, op, payload, next_cmd)`|asserts op runs under context, recomputes control, and returns reply|
|roadmap/services/commands.py:655|calling `commands.ask_line(data_dir)` when open questions exist|asserts formatted string `ask: <n> open: <id> <text>` is returned|
|roadmap/services/commands.py:664|calling `commands.queue_line(data_dir)` with queued tasks|asserts formatted string `queue: <n> waiting: ...` is returned|
|roadmap/services/commands.py:673|calling `commands.issues_line(data_dir)` with open issues|asserts formatted string `issues: <n> open (...)` is returned|
|roadmap/services/commands.py:712|calling `commands.inbox_lines(data_dir)` with queue and questions|asserts list of formatted inbox summary lines is returned|
|roadmap/services/cmdops.py:81|calling `run("control.stop", {"task": "P1.1"}, ...)`|asserts return includes `{"task": "P1.1"}` and inverse is None|
|roadmap/services/cmdops.py:103|calling `run("control.override", {"hours": 2}, ...)`|asserts `control.override` is invoked and returns `{"hours": 2}`|
|roadmap/services/cmdops.py:155|calling `run("limit.set", {"scope": "project", "window": "day", "kind": "tokens", "value": 5000}, ...)`|asserts row limit is set via `control.set_limit_row` and returns row data|
|roadmap/services/cmdops.py:172|calling `run("limit.rm", {"id": "L1"}, source="gui")`|asserts limit row is removed and inverse is `limit.set` with prior row args|
|roadmap/services/cmdops.py:270|calling `run("rules.sync", {"dryRun": True}, source="gui")`|asserts `rules.sync` executes and returns sync summary dict|

DONE

[unrestricted] agy modified the working tree during this staffer run — verify the task asked for it. Delta (`git status --porcelain` entries that appeared or changed during the run):
   M roadmap/core/planfmt.py
   M roadmap/services/tasks.py
  ?? docs/facts/
  ?? tests/unit/test_gen_facts.py
  ?? tests/unit/test_plan_export_features.py
  ?? tests/unit/test_planfmt_models.py
  ?? tools/gen_facts.py
ACTION FOR THE CALLING AGENT: inspect these changes (`git diff`) before trusting this staffer. Rollback: `git checkout -- <path>` for tracked files, delete the new untracked ones.
