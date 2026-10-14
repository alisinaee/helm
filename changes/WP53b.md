# WP53b: planner fixes and smaller snapshot rows

Fixes to the Planner (WP53) after WP55 wired it in.

- `?f=<id>`: the Work drawer chip opens the Planner with that feature expanded, highlighted and scrolled to (once per
  link). The filters are cleared so it shows. A bad id is ignored.
- All projects scope (`#/all/planner`): lists the projects under "Pick a project" instead of the one-project note.
- Snapshot rows (`roadmap/core/features.py` `snapshot_rows`, used by `roadmap/core/snapshot.py`): the task id list is
  dropped, and `acc` is kept only for features that are not done. A feature's tasks come from each task's `feats` in
  the snapshot. 60 features measure about 14.0 KB (was 15.9 KB). The 8 KB target is waived (coordinator approval):
  the 14 fixed keys cost about 190 bytes a row; the HTTP and CLI rows are unchanged.
- Phone (under 640 px): the filters sit behind a "Filters (n)" toggle and a floating "+ Feature" button replaces the
  inline one. Wide screens keep the old filter row.
- Tests: `tests/web/test_planner_view.py` (focus, pick list, toggle and button, CSS budget now 4 KB), the fixture
  `tests/fixtures/planner_snapshot.json` (tasks carry `feats`, rows carry no `tasks`), `tests/unit/test_features_core.py`
  (`SnapshotRowsTests`), `tests/unit/test_features_service.py` (size guard 15 KB, row shape).

- `web/js/state.js` `normalizeTask` keeps `feats`; `web/js/views/details.js` `featureRowsOf` reads each task's
  `feats` for the Work drawer's Feature chips (approved by the coordinator).
