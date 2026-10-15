| file:line | cause | fix |
| --- | --- | --- |
| web/js/views/overview.js:207 | sectionView(vm) receives data via vm parameter; how vm gets fresh data is UNKNOWN | UNKNOWN |
| web/js/views/overview.js:179 | projectOverview reads vm.project.snapshot passively; snapshot refresh mechanism is UNKNOWN | UNKNOWN |
| web/js/views/overview.js:180 | scopeSnapshots(vm) reads scopes synchronously from vm without fetching fresh data | UNKNOWN |
| web/js/views/overview.js:182 | watchCountdowns() is invoked on render; whether it fetches fresh data is UNKNOWN | UNKNOWN |
| web/js/views/overview.js:106 | Placeholder notes 'Usage pending next sync', but sync mechanism is UNKNOWN | UNKNOWN |
| web/js/views/overview.js:200 | allOverview reads scopes synchronously from vm without fetching fresh data | UNKNOWN |
