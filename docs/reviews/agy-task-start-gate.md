| file:line | path | gate applied? | fix |
| --- | --- | --- | --- |
| roadmap/services/commands.py:108 | task.status | yes | none (gate enforced via tasks.start_refusal at roadmap/services/commands.py:109) |
| roadmap/services/commands.py:178 | task.start | no | call tasks.start_refusal(data_dir, [a["id"]]) and raise if not None before queue.enqueue at roadmap/services/commands.py:180 |
| roadmap/services/tasks.py:128 | tasks.start_refusal | yes | none (gate definition rejecting unapproved phases at roadmap/services/tasks.py:135) |
| roadmap/services/tasks.py:121 | tasks.unapproved_phases | yes | none (identifies phases where approved is False at roadmap/services/tasks.py:125) |
