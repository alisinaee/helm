# Job staffer-mv7pid3j-1a086f5a (staffer, done)

|function or branch file:line|missing case|what a test should assert|
|---|---|---|
|roadmap/services/features.py:60|`_find` called with an unknown feature id|raises RoadmapError with code "not_found"|
|roadmap/services/features.py:125|`add` called when next feature id exceeds F99|raises RoadmapError conflict stating feature ids run out after F99|
|roadmap/services/features.py:161|`accept` called with an explicit date string|stamps accepted with the specified date instead of today's date|
|roadmap/services/features.py:177|`remove` called on a feature that has child features|raises RoadmapError conflict stating the feature has sub-features|
|roadmap/services/features.py:194|`restore` called with a feature id that already exists|raises RoadmapError conflict stating the feature already exists|
|roadmap/services/features.py:199|`restore` called with an invalid feature payload failing validation|raises RoadmapError with code "usage"|
|roadmap/services/features.py:234|`unlink` called with a nonexistent task id|raises RoadmapError with code "not_found"|
|roadmap/services/features.py:239|`unlink` called with feature ids not linked to the task|returns empty removed list and leaves task feats unchanged|
|roadmap/services/features.py:274|`row_of` called with a nonexistent feature id|raises RoadmapError with code "not_found"|
|roadmap/services/features.py:275|`task_views` called for a feature with tasks|returns list of dicts with id, state, estK, and title|
|roadmap/services/features.py:305|`check_date` called with an invalid calendar date string|raises RoadmapError with code "usage"|
|roadmap/services/features.py:308|`check_date` called with text failing DATE_RE regex|raises RoadmapError with code "usage"|
|roadmap/services/features.py:309|`check_date` called with a valid YYYY-MM-DD string|returns the validated date string|
|roadmap/services/featops.py:28|`_feat_id` called with an invalid feature id format|raises RoadmapError usage error stating feature id must look like F3|
|roadmap/services/featops.py:37|`_opt_phase` called with an invalid phase identifier|raises RoadmapError usage error stating phase must be a phase id or empty|
|roadmap/services/featops.py:47|`_opt_parent` called with an invalid parent feature id format|raises RoadmapError usage error stating parent must look like F3 or be empty|
|roadmap/services/featops.py:53|`_prio` called with an invalid prio value or boolean|raises RoadmapError usage error stating prio must be 1, 2 or 3|
|roadmap/services/featops.py:84|`feature.set` called with acc in changes|updates acc field and includes "acc" in changed list|
|roadmap/services/featops.py:86|`feature.set` called with prio in changes|updates prio field and includes "prio" in changed list|
|roadmap/services/featops.py:90|`feature.set` called with parent in changes|updates parent field and includes "parent" in changed list|
|roadmap/services/featops.py:92|`feature.set` called with hold in changes|updates hold field and includes "hold" in changed list|
|roadmap/services/featops.py:94|`feature.set` called with no recognized field changes|raises RoadmapError usage error stating feature set needs at least one field|
|roadmap/services/featops.py:108|`_feat_list` called with empty feats or more than 3 ids|raises RoadmapError usage error stating feats must be a list of 1 to 3 feature ids|
|roadmap/services/featops.py:113|`_feat_list` called with an invalid feature id format in list|raises RoadmapError usage error stating feature id must look like F3|
|roadmap/services/featops.py:181|`_check_restore` called with an invalid feature payload|raises RoadmapError usage error stating feature restore needs a feature record|

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
  ?? tests/web/test_planner_wire.py
ACTION FOR THE CALLING AGENT: inspect these changes (`git diff`) before trusting this staffer. Rollback: `git checkout -- <path>` for tracked files, delete the new untracked ones.
