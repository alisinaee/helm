| file:line | cause | fix |
| --- | --- | --- |
| web/js/views/agents.js:9 | Imports scopeSnapshots and pageState from inbox.js; how inbox.js fetches or refreshes data is UNKNOWN | UNKNOWN |
| web/js/views/agents.js:67 | Elapsed time calculation ticks from startedMs so elapsed figure updates locally without a new snapshot | UNKNOWN |
| web/js/views/agents.js:129 | projectBlock extracts snapshot data from entry.snap passed in from scopeSnapshots(vm) | UNKNOWN |
| web/js/views/agents.js:153 | sectionView(vm) renders views using vm; re-rendering mechanism and vm update frequency are UNKNOWN | UNKNOWN |
| web/js/views/agents.js:156 | scopeSnapshots(vm) reads snapshots from vm; agents.js contains no network fetch, polling, or event listeners for fresh data | UNKNOWN |
| web/js/views/agents.js:172 | pageAction executes run("task.stop") on stop action but does not trigger or await data reload | UNKNOWN |
| web/js/views/agents.js:179 | watchElapsed sets a 1-second setInterval that only updates DOM elapsed text without fetching fresh agent data | UNKNOWN |
| web/js/views/agents.js:190 | watchElapsed() starts the local elapsed time DOM ticker on module load without fetching fresh agent data | UNKNOWN |
