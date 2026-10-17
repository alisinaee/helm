### 1) References to roadmap-board
| file:line | what it is (id, label, path, display string) | visible to the person? |
|---|---|---|
| [`roadmap/log.py:149`](file:///Users/ali/Works/helm/roadmap/log.py#L149) | path (fallback state dir) | No (internal fallback) |
| [`roadmap/commands/tokens.py:8`](file:///Users/ali/Works/helm/roadmap/commands/tokens.py#L8) | path (transcripts default) | Yes (CLI `--help` default) |
| [`roadmap/commands/ref.py:22`](file:///Users/ali/Works/helm/roadmap/commands/ref.py#L22) | display string (ref example) | Yes (CLI `--help` text) |
| [`roadmap/services/tasks.py:864`](file:///Users/ali/Works/helm/roadmap/services/tasks.py#L864) | display string (schema error) | Yes (CLI/API error message) |
| [`roadmap/services/launchd.py:21`](file:///Users/ali/Works/helm/roadmap/services/launchd.py#L21) | label/id (`com.roadmap-board.agent`) | Yes (plist, launchctl, CLI status) |
| [`roadmap/services/projects.py:170,234`](file:///Users/ali/Works/helm/roadmap/services/projects.py#L170) | display string (schema errors) | Yes (CLI check/migrate error) |
| [`roadmap/store/paths.py:39,47,55`](file:///Users/ali/Works/helm/roadmap/store/paths.py#L39) | path (config, state, logs defaults) | Yes (CLI info/show, paths) |
| [`roadmap/store/schema.py:73`](file:///Users/ali/Works/helm/roadmap/store/schema.py#L73) | display string (schema error) | Yes (CLI/API error message) |
| [`web/js/state.js:27`](file:///Users/ali/Works/helm/web/js/state.js#L27) | id (localStorage key prefix) | No (browser storage key) |
| [`tools/cursor-job.sh:6`](file:///Users/ali/Works/helm/tools/cursor-job.sh#L6) | path (fallback repo dir) | Yes (script failure if missing) |
| [`bin/roadmap:14`](file:///Users/ali/Works/helm/bin/roadmap#L14) | path (fast-path state dir) | No (hook pre check) |
| [`tools/oc-job.sh:6`](file:///Users/ali/Works/helm/tools/oc-job.sh#L6) | path (fallback repo dir) | Yes (script failure if missing) |
| [`tools/gen_facts.py:2,260`](file:///Users/ali/Works/helm/tools/gen_facts.py#L2) | display string (docstring, header) | Yes (generated FACTS.md header) |
| [`tools/cursor-review2.sh:6`](file:///Users/ali/Works/helm/tools/cursor-review2.sh#L6) | path (hardcoded repo dir) | Yes (script failure if missing) |

### 2) Safe Migration Plan to Project ID "helm"
- **Where ID is stored**:
  - Registry: [`~/.config/roadmap-board/config.json`](file:///Users/ali/.config/roadmap-board/config.json) (`projects[].id = "roadmap-board"`).
  - State dir: `~/Library/Application Support/roadmap-board/` (`hooks-`, `control-`, `head-claim-`, `deny-`, `backups/`).
  - launchd label: `com.roadmap-board.agent` in [`roadmap/services/launchd.py:21`](file:///Users/ali/Works/helm/roadmap/services/launchd.py#L21) and `~/Library/LaunchAgents/`.
  - Hooks: [`.claude/settings.local.json`](file:///Users/ali/Works/helm/.claude/settings.local.json) calls `bin/roadmap hook`; resolves project dynamically via cwd matching `path`.
- **Redirect `#/p/roadmap-board` -> `#/p/helm`**: In [`web/js/router.js`](file:///Users/ali/Works/helm/web/js/router.js) (`parseRoute`), if `id === "roadmap-board"`, rewrite `id = "helm"` and set `route.redirect = buildHash(route)`; [`web/js/app.js:272`](file:///Users/ali/Works/helm/web/js/app.js#L272) automatically executes `window.location.replace()`.
- **Data move without loss**: Stop daemon. Rename state files (`hooks-roadmap-board.json` -> `hooks-helm.json`, `control-`, `head-claim-`, `deny-`, `backups/roadmap-board/`). Update `config.json` `projects[0].id` to `"helm"`. Repo data (`docs/`) stays in place.
- **Service restart**: `bin/roadmap service restart` required after `config.json` & state file edits. Full launchctl reload (`bootout` old label + `bootstrap` new) required only if changing launchd `LABEL`.

### 3) Display-Only Changes (Safe Without Migration)
- Browser tab title in [`web/js/state.js:541`](file:///Users/ali/Works/helm/web/js/state.js#L541) (fix `"roadmap-board · Helm"` fallback and avoid `"Helm · Helm"`).
- Help texts & examples: [`roadmap/commands/ref.py:22`](file:///Users/ali/Works/helm/roadmap/commands/ref.py#L22) (`rb:helm/...`), [`roadmap/commands/tokens.py:8`](file:///Users/ali/Works/helm/roadmap/commands/tokens.py#L8).
- Schema mismatch messages in [`roadmap/store/schema.py:73`](file:///Users/ali/Works/helm/roadmap/store/schema.py#L73), [`roadmap/services/projects.py:170,234`](file:///Users/ali/Works/helm/roadmap/services/projects.py#L170), [`roadmap/services/tasks.py:864`](file:///Users/ali/Works/helm/roadmap/services/tasks.py#L864).
- Header & docstrings in [`tools/gen_facts.py:2,260`](file:///Users/ali/Works/helm/tools/gen_facts.py#L2) and script fallback paths in `tools/cursor-*.sh`, `tools/oc-job.sh`.

[unrestricted] agy modified the working tree during this staffer run — verify the task asked for it. Delta (`git status --porcelain` entries that appeared or changed during the run):
   M tests/web/test_tokens_simple.py
   M tests/web/test_tokens_truth.py
   M web/css/tokens.css
   M web/js/views/tokens.js
  ?? tests/api/test_limits_v2_api.py
  ?? tests/unit/test_limits_v2.py
  ?? tests/web/render_limits_v2.mjs
  ?? tests/web/test_limits_v2_web.py
  ?? web/js/views/limits_v2.js
ACTION FOR THE CALLING AGENT: inspect these changes (`git diff`) before trusting this staffer. Rollback: `git checkout -- <path>` for tracked files, delete the new untracked ones.
