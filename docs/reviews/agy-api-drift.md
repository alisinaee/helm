# Job staffer-mv9h7tds-81b4480e (staffer, done)

### Missing or Wrong Routes and Parameters in `docs/API.md`

1. `GET /api/v1/projects/{id}/head` param `n`: wrong max in [docs/API.md:158](file:///Users/ali/Works/roadmap-board/docs/API.md#L158) ("at most 100", but allows up to 200 in [roadmap/http/routes.py:542](file:///Users/ali/Works/roadmap-board/roadmap/http/routes.py#L542), [560](file:///Users/ali/Works/roadmap-board/roadmap/http/routes.py#L560)).
2. `GET /api/v1/projects/{id}/head` params `offset` and `limit`: missing in [docs/API.md:27](file:///Users/ali/Works/roadmap-board/docs/API.md#L27), [158](file:///Users/ali/Works/roadmap-board/docs/API.md#L158) (handled in [roadmap/http/routes.py:543](file:///Users/ali/Works/roadmap-board/roadmap/http/routes.py#L543), [574-583](file:///Users/ali/Works/roadmap-board/roadmap/http/routes.py#L574-L583)).
3. `GET /api/v1/projects/{pid}/git/status`: route missing in [docs/API.md:19-33](file:///Users/ali/Works/roadmap-board/docs/API.md#L19-L33) (registered in [roadmap/http/routes.py:786](file:///Users/ali/Works/roadmap-board/roadmap/http/routes.py#L786)).
4. `GET /api/v1/projects/{pid}/git/log`: route and query param `n` missing in [docs/API.md:19-33](file:///Users/ali/Works/roadmap-board/docs/API.md#L19-L33) (registered in [roadmap/http/routes.py:787](file:///Users/ali/Works/roadmap-board/roadmap/http/routes.py#L787), [709-715](file:///Users/ali/Works/roadmap-board/roadmap/http/routes.py#L709-L715)).
5. `GET /api/v1/projects/{pid}/git/branches`: route missing in [docs/API.md:19-33](file:///Users/ali/Works/roadmap-board/docs/API.md#L19-L33) (registered in [roadmap/http/routes.py:788](file:///Users/ali/Works/roadmap-board/roadmap/http/routes.py#L788)).
6. `GET /api/v1/projects/{pid}/git/show/{sha}`: route missing in [docs/API.md:19-33](file:///Users/ali/Works/roadmap-board/docs/API.md#L19-L33) (registered in [roadmap/http/routes.py:789](file:///Users/ali/Works/roadmap-board/roadmap/http/routes.py#L789)).
7. `GET /api/v1/projects/{pid}/git/diff/{sha}`: route and query param `path` missing in [docs/API.md:19-33](file:///Users/ali/Works/roadmap-board/docs/API.md#L19-L33) (registered in [roadmap/http/routes.py:790](file:///Users/ali/Works/roadmap-board/roadmap/http/routes.py#L790), [754-760](file:///Users/ali/Works/roadmap-board/roadmap/http/routes.py#L754-L760)).
8. `POST /api/v1/log`: route and body params `sid`, `events` missing in [docs/API.md:19-33](file:///Users/ali/Works/roadmap-board/docs/API.md#L19-L33) (registered in [roadmap/http/routes.py:794](file:///Users/ali/Works/roadmap-board/roadmap/http/routes.py#L794), [327-333](file:///Users/ali/Works/roadmap-board/roadmap/http/routes.py#L327-L333)).
9. `GET /api/v1/log/status`: route missing in [docs/API.md:19-33](file:///Users/ali/Works/roadmap-board/docs/API.md#L19-L33) (registered in [roadmap/http/routes.py:795](file:///Users/ali/Works/roadmap-board/roadmap/http/routes.py#L795)).
10. `GET /api/v1/log/report`: route and query param `n` missing in [docs/API.md:19-33](file:///Users/ali/Works/roadmap-board/docs/API.md#L19-L33) (registered in [roadmap/http/routes.py:796](file:///Users/ali/Works/roadmap-board/roadmap/http/routes.py#L796), [374-381](file:///Users/ali/Works/roadmap-board/roadmap/http/routes.py#L374-L381)).

[unrestricted] agy modified the working tree during this staffer run — verify the task asked for it. Delta (`git status --porcelain` entries that appeared or changed during the run):
  M docs/activity.jsonl
   M docs/head-text.jsonl
   M docs/head.jsonl
   M docs/jobs.json
   M roadmap/core/head.py
   M roadmap/core/snapshot.py
   M roadmap/services/headops.py
   M web/css/admin.css
   M web/css/flow.css
   M web/css/map.css
   M web/css/work.css
   M web/js/views/agents.js
   M web/js/views/head.js
  ?? docs/reviews/agy-readme-drift.prompt.txt
ACTION FOR THE CALLING AGENT: inspect these changes (`git diff`) before trusting this staffer. Rollback: `git checkout -- <path>` for tracked files, delete the new untracked ones.
