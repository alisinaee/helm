| file:line | cause | fix |
|---|---|---|
| web/js/state.js:313 | Head data is ingested passively from raw.head during snapshot normalization; how the page refreshes Head data is not defined here and is UNKNOWN | UNKNOWN |
| web/js/state.js:27-39 | createStore sets up snapshots storage without any refresh loop, polling interval, or timer; refresh frequency is UNKNOWN | UNKNOWN |
| web/js/state.js:501-507 | buildViewModel binds snapshot data to vm.project.snapshot.head on render without triggering network refreshes; refresh interval is UNKNOWN | UNKNOWN |
| web/js/state.js:458-460 | Refresh/staleness thresholds STALE_AFTER_S and OLD_AFTER_S (web/js/state.js:23-24) apply only to usage data; Head data refresh interval is UNKNOWN | UNKNOWN |
| docs/facts/FACTS.md:546 | Snapshot route GET /api/v1/projects/{pid}/snapshot serves project snapshot data containing head, but client polling frequency is UNKNOWN | UNKNOWN |
