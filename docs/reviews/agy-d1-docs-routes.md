# Job staffer-mv7pv54l-7570e246 (staffer, done)

|route or op|in code?|in API.md?|note|
|---|---|---|---|
|`feature.restore`|Yes (`roadmap/services/featops.py:203`)|No|Internal op registered with `public=False` (`roadmap/services/featops.py:3`); not documented in `docs/API.md:222`|
|`task.status`|UNKNOWN|Yes (`docs/API.md:214`)|Documented in `docs/API.md:214`; not defined in `roadmap/services/cmdops.py:1-295` or `roadmap/services/featops.py:1-204`|
|`task.start`|UNKNOWN|Yes (`docs/API.md:214`)|Documented in `docs/API.md:214`; not defined in `roadmap/services/cmdops.py:1-295` or `roadmap/services/featops.py:1-204`|
|`task.stop`|UNKNOWN|Yes (`docs/API.md:214`)|Documented in `docs/API.md:214`; not defined in `roadmap/services/cmdops.py:1-295` or `roadmap/services/featops.py:1-204`|
|`subtask.toggle`|UNKNOWN|Yes (`docs/API.md:215`)|Documented in `docs/API.md:215`; not defined in `roadmap/services/cmdops.py:1-295` or `roadmap/services/featops.py:1-204`|
|`plan.move`|UNKNOWN|Yes (`docs/API.md:215`)|Documented in `docs/API.md:215`; not defined in `roadmap/services/cmdops.py:1-295` or `roadmap/services/featops.py:1-204`|
|`question.answer`|UNKNOWN|Yes (`docs/API.md:216`)|Documented in `docs/API.md:216`; not defined in `roadmap/services/cmdops.py:1-295` or `roadmap/services/featops.py:1-204`|
|`comment.add`|UNKNOWN|Yes (`docs/API.md:216`)|Documented in `docs/API.md:216`; not defined in `roadmap/services/cmdops.py:1-295` or `roadmap/services/featops.py:1-204`|
|`issue.new`|UNKNOWN|Yes (`docs/API.md:216`)|Documented in `docs/API.md:216`; not defined in `roadmap/services/cmdops.py:1-295` or `roadmap/services/featops.py:1-204`|
|`issue.close`|UNKNOWN|Yes (`docs/API.md:216`)|Documented in `docs/API.md:216`; not defined in `roadmap/services/cmdops.py:1-295` or `roadmap/services/featops.py:1-204`|
|`undo`|UNKNOWN|Yes (`docs/API.md:220`)|Documented in `docs/API.md:220`; not defined in `roadmap/services/cmdops.py:1-295` or `roadmap/services/featops.py:1-204`|
|`GET /`|UNKNOWN|Yes (`docs/API.md:31`)|Documented in `docs/API.md:31`; not in `roadmap/http/routes.py:349-359` `ROUTES` table (handled via static file fallback per `roadmap/http/routes.py:363`)|
|`GET /<file>`|UNKNOWN|Yes (`docs/API.md:31`)|Documented in `docs/API.md:31`; not in `roadmap/http/routes.py:349-359` `ROUTES` table (handled via static file fallback per `roadmap/http/routes.py:363`)|

DONE

[unrestricted] agy modified the working tree during this staffer run — verify the task asked for it. Delta (`git status --porcelain` entries that appeared or changed during the run):
   M roadmap/commands/status.py
   M roadmap/commands/task.py
   M roadmap/core/features.py
   M roadmap/core/snapshot.py
   M roadmap/services/tasks.py
  ?? docs/features.json
  ?? tests/unit/test_phase_gate.py
ACTION FOR THE CALLING AGENT: inspect these changes (`git diff`) before trusting this staffer. Rollback: `git checkout -- <path>` for tracked files, delete the new untracked ones.
