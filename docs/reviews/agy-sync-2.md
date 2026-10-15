| file:line | cause | fix |
| --- | --- | --- |
| roadmap/core/snapshot.py:336 | Re-serializes the entire view dict via json.dumps and utf-8 encoding on every loop iteration to measure byte size while popping rows. | Estimate row byte lengths or track size incrementally rather than full re-serialization on every popped row. |
| roadmap/core/snapshot.py:413 | For each phase, filters the entire tasks list, re-filtering all tasks O(phases * tasks) times. | Group tasks by phase into a dictionary once prior to looping over phases. |
| roadmap/core/snapshot.py:429-431 | Evaluates phase_of and re-parses ended timestamps for all running and recent jobs within each phase loop. | Group running and recent jobs by phase and pre-parse job timestamps prior to iterating phases. |
| roadmap/core/snapshot.py:134-135 | Re-parses tasks_text with json.loads in _after_edges, redundantly duplicating parse_tasks performed earlier in build_snapshot. | Pass parsed task data directly into _after_edges instead of re-parsing tasks_text. |
| roadmap/core/snapshot.py:196-199 | Performs a linear scan over live_jobs for every link of every head row during link resolution. | Build a lookup dictionary mapping task and job IDs to live jobs once before resolving links. |
| roadmap/core/snapshot.py:450-464 | Iterates over open_t eight times and all tasks three times in separate list comprehensions to compute summary metrics. | Aggregate token sums, check sums, and state counts in a single pass over tasks. |
| roadmap/core/snapshot.py:154-162 | Parses started and ended timestamps in _workflow_view and parses them again in _span, while formatting all jobs before slicing. | Reuse parsed timestamps in _span and format only the newest WORKFLOW_SPANS jobs. |
| roadmap/core/snapshot.py:405-407 | Parses ended timestamp strings in ended_recently and re-parses them again when sorting recent jobs per phase. | Cache or reuse parsed datetime objects on job dictionaries instead of re-parsing repeatedly. |
