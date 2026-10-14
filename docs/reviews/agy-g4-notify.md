# Job staffer-mv7pi5i1-f2727ddf (staffer, done)

|function or branch file:line|missing case|what a test should assert|
|/Users/ali/Works/roadmap-board/roadmap/services/notify.py:52-53|`_macos()` called directly without mocking|returns `sys.platform == "darwin"`|
|/Users/ali/Works/roadmap-board/roadmap/services/notify.py:61-65|`_run_osascript()` invoked directly or without runner injection|returns True when subprocess exits 0, False otherwise|
|/Users/ali/Works/roadmap-board/roadmap/services/notify.py:71-72|`_log_once()` called a second time within RATE_S (60 seconds)|returns early without logging a duplicate warning|
|/Users/ali/Works/roadmap-board/roadmap/services/notify.py:80-81|`config.load()` raises an exception inside `_enabled()`|catches exception and returns False|
|/Users/ali/Works/roadmap-board/roadmap/services/notify.py:122|`notify()` called with empty or None `title`|uses fallback TITLE "roadmap-board" in osascript payload|
|/Users/ali/Works/roadmap-board/roadmap/services/notify.py:136|`project_of()` called with path not matching any registered project|returns None|
|/Users/ali/Works/roadmap-board/roadmap/services/notify.py:143-144|`notify_dir()` called without runner under unit tests or off macOS|returns False immediately without resolving project|
|/Users/ali/Works/roadmap-board/roadmap/services/notify.py:146-147|`notify_dir()` called with an unregistered folder where `project_of()` is None|returns False without attempting notification|
|/Users/ali/Works/roadmap-board/roadmap/services/notify.py:149-151|`body_for()` callback raises an exception in `notify_dir()`|logs warning and returns False without raising|
|/Users/ali/Works/roadmap-board/roadmap/commands/watch.py:41|`watch` command invoked with `--max` exceeding MAX_LIMIT_S (86400)|raises RoadmapError with EXIT_USAGE (code 2)|
|/Users/ali/Works/roadmap-board/roadmap/commands/watch.py:64|file mtime changes but `_new_event()` returns None (no new entries or answers)|wait loop continues polling rather than exiting|
|/Users/ali/Works/roadmap-board/roadmap/commands/watch.py:114|question answer text exceeds ANSWER_MAX (60 characters)|`event["line"]` truncates answer text to 60 characters|
|/Users/ali/Works/roadmap-board/roadmap/commands/skills.py:45|`TEMPLATE_DIR` does not exist or is not a directory|`templates()` returns an empty list|
|/Users/ali/Works/roadmap-board/roadmap/commands/skills.py:82|plain-text `skills list` for a project where skills are not installed|formats state as "not installed"|
|/Users/ali/Works/roadmap-board/roadmap/commands/skills.py:127-128|`skills install` invoked when `templates()` is empty|raises RoadmapError with EXIT_NOT_FOUND (code 3)|
|/Users/ali/Works/roadmap-board/roadmap/commands/skills.py:145-147|plain-text `skills install --dry-run` encountering an existing conflict|prints `conflict: <dest> exists (not written; add --yes)`|
|/Users/ali/Works/roadmap-board/roadmap/commands/skills.py:148-149|plain-text `skills install --yes` replacing and backing up a skill|prints `backup: <dest> -> <backup>` to stdout|
|/Users/ali/Works/roadmap-board/roadmap/commands/skills.py:150|plain-text `skills install` without `--dry-run` and without `--json`|prints `create: <dest>` without `would ` prefix|
|/Users/ali/Works/roadmap-board/roadmap/commands/skills.py:161-162|conflict error when `skills install` is called with `--project`|next suggestion contains `--project <id>`|

DONE

[unrestricted] agy modified the working tree during this staffer run — verify the task asked for it. Delta (`git status --porcelain` entries that appeared or changed during the run):
   M roadmap/commands/job.py
   M roadmap/commands/project.py
   M roadmap/services/jobs.py
   M tools/ui_smoke.py
   M web/icons.svg
   M web/js/app.js
   M web/js/routes.js
   M web/js/state.js
   M web/js/views/details.js
  ?? roadmap/templates/plan_template.json
  ?? tests/unit/test_job_progress.py
  ?? tests/unit/test_project_new.py
ACTION FOR THE CALLING AGENT: inspect these changes (`git diff`) before trusting this staffer. Rollback: `git checkout -- <path>` for tracked files, delete the new untracked ones.
