| file:line | cause | fix |
| --- | --- | --- |
| roadmap/services/jobs.py:99 | start_job writes job data via _write_doc without notifying snapshot consumers | UNKNOWN |
| roadmap/services/jobs.py:128 | finish_job writes job data via _write_doc without notifying snapshot consumers | UNKNOWN |
| roadmap/services/jobs.py:154 | progress_job writes job data via _write_doc without notifying snapshot consumers | UNKNOWN |
| roadmap/services/jobs.py:178 | prune_jobs writes job data via _write_doc without notifying snapshot consumers | UNKNOWN |
| roadmap/services/jobs.py:204 | _write_doc only calls schema.write_data and does not notify snapshot consumers | UNKNOWN |
