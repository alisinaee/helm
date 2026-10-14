# agy audit verification, batch 2

Checked the agy rows in n04 to n10 against the code and docs at HEAD. Each row got one verdict: KEEP (fact holds), WRONG (fact false or stale), UNVERIFIED (cannot be settled from the code alone). Line cites are the real lines; where agy's cite was off, the evidence gives the real one. Only rows checked are listed; a file with more rows than the table had at least 5 checked.

Verdict counts: n04 10 KEEP; n05 15 KEEP; n06 12 KEEP, 2 UNVERIFIED; n07 9 KEEP, 3 WRONG, 1 UNVERIFIED; n08 22 KEEP (all rows); n09 13 KEEP, 2 WRONG; n10 7 KEEP.

## agy-n04-launcher-gaps.md

| row | verdict | evidence |
|---|---|---|
| `_moment` now=None uses system time | KEEP | launcher.py:27 returns `time.time()` when None |
| `_moment` numeric string or int returns float | KEEP | launcher.py:27 `float(now)` |
| `_project_for` skips non-dict item | KEEP | launcher.py:34-35 `continue` |
| `_project_for` missing or non-string path returns None | KEEP | launcher.py:36-38 skip, returns None at :42 |
| `_project_for` empty path skipped | KEEP | launcher.py:37 `not path` is true for "" |
| `_project_for` missing dataDir defaults to "docs" | KEEP | launcher.py:39 `or "docs"` |
| `_valid_dir` control character returns False | KEEP | launcher.py:49 rejects ord < 32 or 127 (agy cited :47-49, fine) |
| `_valid_dir` None or 123 returns False | KEEP | launcher.py:47-48 `isinstance(path, str)` gate |
| `maybe_launch` now=None goes through `_moment(None)` | KEEP | launcher.py:98 `_moment(now)` |
| runner returning False still gives True | KEEP | launcher.py:103-104 ignores the runner result, returns True |
| presence/config exception returns False (fail open) | KEEP | launcher.py:105-107 `except Exception` logs and returns False |

## agy-n05-features-gaps.md

| row | verdict | evidence |
|---|---|---|
| `featops._feat_id` rejects "FX" or "123" | KEEP | featops.py:32-33; FEAT_ID_RE `^F[1-9][0-9]?$` (core/parsers.py:26) |
| `featops._opt_phase` rejects "P-1" | KEEP | featops.py:41-42; PHASE_ID_RE `^[A-Za-z0-9]+$` (core/planfmt.py:30) |
| `featops._prio` rejects 0, 4, True | KEEP | featops.py:57-58 (bool check first) |
| `featops._check_set` with no change fields raises usage | KEEP | featops.py:105-106; agy cite :94 is off by 11 lines |
| `featops._check_set` parses `hold` | KEEP | featops.py:103-104; agy cite :92-93 is off |
| `featops._feat_list` rejects empty or more than 3 | KEEP | featops.py:119-120; LINK_MAX = 3 at :23 |
| `featops._feat_list` dedupes keeping first | KEEP | featops.py:126-127 `if text not in out` |
| `featops._check_restore` non-dict raises usage | KEEP | featops.py:191-192 |
| `featops._h_restore` returns `{id, restored: True}` | KEEP | featops.py:203; agy cite :186 is off |
| `featops._h_accept` on=False clears date | KEEP, gated | summary at featops.py:173 is right, but `_refuse_accept()` (featops.py:168) runs first and refuses agent, phone and script sources; the row must say so before a test is written |
| `features.add` past ID_MAX | KEEP | features.py:145-146 raises "feature ids run out after F99"; agy cite :124 is off. The 60-feature cap (features.py:141) fires first when the list is full |
| `features.remove` refuses parent with sub-features | KEEP | features.py:197-199; agy cite :176-177 is off |
| `features.status_line` singular "1 orphan task" | KEEP | features.py:318-320 uses `"" if orphans == 1 else "s"`; agy cite :292-295 is off |
| `features.check_date` None returns None, bad calendar date raises | KEEP | features.py:326-332 (`fromisoformat` in try, usage error on ValueError) |
| `features.apply_records` dry_run returns without saving | KEEP | features.py:125-126 |

## agy-n06-rows-pz.md

Checked against `web/js/views/*.js`. `row-grid` appears in planner.js (GRID at :20), projects.js and running.js only.

| row | verdict | evidence |
|---|---|---|
| planner.js:215 uncovered callout lacks row-grid | KEEP | the `<li>` at :215 has no GRID; "Link tasks" button is inline at :216-217 |
| planner.js:229 orphan row, select inline | KEEP | `<li>` at :229 has no GRID; select inline at :231 |
| planner.js:329 project picker lacks grid | KEEP | plain `<a class="btn">` at :329, no grid |
| projects.js:93 p-row uses flex, no rg-t | UNVERIFIED | p-row class present; flex-versus-grid is a CSS question, not checked |
| projects.js:111 all-projects row lacks meter | UNVERIFIED | needs the CSS and the meter markup compared; not settled from the JS |
| recent.js:15 log row date uses `num`, not `rg-num` | KEEP | line 15 `class="log-date num"`; recent.js has 0 row-grid hits |
| research.js:67 checklist row, title/hint use `<br>` | KEEP | `<br>` at :68; research.js has 0 row-grid hits |
| research.js:76 note item lacks row-grid | KEEP | research.js has 0 row-grid hits |
| research.js:118 project link lacks grid | KEEP | plain anchor, no grid |
| roadmap.js:72 task card lacks row-grid | KEEP | roadmap.js has 0 row-grid hits |
| roadmap.js:118 lane header lacks row-grid | KEEP | `lane-head` at :118, no grid |
| roadmap.js:135 timeline row lacks row-grid | KEEP | `tl-row` at :135, no grid |
| rules.js:47 rule row lacks row-grid | KEEP | rules.js has 0 row-grid hits; `rule-row` at :47 |
| running.js:60 finished-job title lacks rg-t | KEEP | row has row-grid at :60, but `fin-title` at :62 has no rg-t class |

## agy-n07-aria-tz.md

| row | verdict | evidence |
|---|---|---|
| tasks.js:77 t-title span tabindex=0 lacks role and label | KEEP | span has tabindex="0", no role or aria-label on the line |
| toast.js:99 Undo button lacks aria-label | KEEP | no aria-label; visible text "Undo" (optional improvement) |
| toast.js:104 close button lacks aria-label | KEEP | no aria-label on the line |
| tokens.js:108 cap input needs aria-label | WRONG | input sits inside `<label class="lim-field">` (tokens.js:107-109) with text "Token limit (thousands)", so it is already named |
| tokens.js:110 spend-cap button lacks aria-label | KEEP | no aria-label on the line |
| tokens.js:166 override select needs aria-label | WRONG | select sits inside `<label class="lim-field">` with text "For" (tokens.js:165-166) |
| tokens.js:167 override button lacks aria-label | KEEP | no aria-label; visible text "Override" |
| topbar.js:22 crumb-proj lacks aria-expanded and aria-controls | KEEP | neither attribute on lines 22-23 |
| topbar.js:120 help-open lacks aria-haspopup and aria-controls | KEEP | neither attribute on the line |
| tree.js:14 subtask checkbox needs aria-label | WRONG | checkbox is wrapped in `<label class="wk-sub">` with a text span (tree.js:14-16), already named |
| tree.js:28 wk-title link contextual label | KEEP | no aria-label; optional improvement |
| work.js:104 view toggle lacks aria-controls | KEEP | has aria-pressed; aria-controls absent |
| workflow.js:436 wf-bar role=button lacks role=link or aria-controls | UNVERIFIED | element already has role="button" and tabindex="0"; agy's "role=link" would change its behaviour, so this is a design decision |
| workflow.js:608 map-op button lacks aria-controls | KEEP | has aria-label; aria-controls absent |

## agy-n08-release-cmds.md

Commands run only with `--help` under a temp ROADMAP_HOME (never run for real). Top-level `roadmap --help` lists doctor, version, service, project, job, hooks; `project`, `hooks`, `service`, `job` group help confirmed the actions. Sub-action help: `project add --name`, `hooks install --replace-legacy`, `job list --project ID` exist.

| doc row | verdict | evidence |
|---|---|---|
| RELEASE.md:17 `roadmap doctor` | KEEP | agy UNKNOWN, now resolved: exists (`doctor --help` rc 0) |
| RELEASE.md:24 `roadmap project init <split-net>` | KEEP | exists; the argument is a `path`, not a project id (`project init --help`), so the doc's name reads as a folder. Worth a doc note |
| RELEASE.md:25 `project add <split-net> --name` | KEEP | `--name NAME` present |
| RELEASE.md:26 `project check split-net` | KEEP | `[id]` optional, present |
| RELEASE.md:32 `project remove split-net` | KEEP | `id` positional, present |
| RELEASE.md:40 `hooks install split-net --replace-legacy` | KEEP | `--replace-legacy` present |
| RELEASE.md:41 `hooks status split-net` | KEEP | `project` positional, present |
| RELEASE.md:49 `hooks uninstall split-net` | KEEP | action present |
| RELEASE.md:55 `roadmap doctor` | KEEP | exists |
| RELEASE.md:72 `bin/roadmap service install` | KEEP | action present |
| RELEASE.md:73 `roadmap service status` | KEEP | action present |
| RELEASE.md:74 `roadmap doctor` | KEEP | exists |
| RELEASE.md:79 `roadmap service uninstall` | KEEP | action present |
| RELEASE.md:120 `roadmap version` | KEEP | agy UNKNOWN, now resolved: exists (`version --help` rc 0) |
| RELEASE.md:128 `roadmap service status` | KEEP | action present |
| RELEASE.md:130 `roadmap hooks status split-net` | KEEP | action present |
| RELEASE.md:131 `roadmap job list --project split-net` | KEEP | agy UNKNOWN, now resolved: `--project ID` present |
| RELEASE.md:137 `roadmap project remove split-net` | KEEP | action present |
| RELEASE.md:138 `roadmap hooks uninstall split-net` | KEEP | action present |
| RELEASE.md:140 `roadmap service uninstall` | KEEP | action present |

## agy-n09-changelog-1.0.md

| row | verdict | evidence |
|---|---|---|
| HANDOVER:8 launchd agent `com.roadmap-board.agent` on 127.0.0.1:8780 | KEEP | launchd.py:21 LABEL; serve.py:18 DEFAULT_PORT = 8780 |
| HANDOVER:29 "25 KB CSS tokens" | WRONG | web/css/*.css sum to about 63.9 KB; HANDOVER:29 itself says the CSS total cap is now 64 KB. Use the current figure |
| R7.1-SPEC:14 presence stored at `docs/presence.json` in the data dir | WRONG | presence.py:27 writes `presence-<hash>.json` in the state dir; presence.py:3 says "never in the repo". The spec is stale |
| R7.1-SPEC:15 hook touch throttled to 30 s | KEEP | presence.py:17 HOOK_THROTTLE_S = 30 |
| R7.1-SPEC:17 watching under 60 s, open under 10 min | KEEP | presence.py:18 WATCH_FRESH_S = 60; :19 HOOK_FRESH_S = 600 |
| R7.1-SPEC:23 launchOnStart runs at most once per 10 min | KEEP | launcher.py:21 RATE_S = 600; :93 launchOnStart gate |
| FACTS:585 planner features capped at 60 | KEEP | core/features.py:20 MAX_FEATURES = 60 |
| FACTS:584 max 3 feature links per task | KEEP | featops.py:23 LINK_MAX = 3 |
| FACTS:580 start queue capped at 50 | KEEP | services/queue.py:12 CAP = 50 (queue.json name not checked) |
| FACTS:599 open issues 200, open questions 50 | KEEP | services/issues.py:11 OPEN_CAP = 200; services/questions.py:13 OPEN_CAP = 50 |
| FACTS:590 activity keeps newest 500 | KEEP | services/activity.py:12 KEEP = 500, used at :30 |
| FACTS:8 `roadmap serve` default port 8780 | KEEP | commands/serve.py:18 |
| FACTS:33 service actions | KEEP | `service --help`: install, uninstall, start, stop, restart, status, logs |
| FACTS:53 project actions | KEEP | `project --help`: add, list, show, init, remove, check, migrate, new |
| FACTS:75 job actions | KEEP | `job --help`: start, done, fail, progress, list, prune |

## agy-n10-csp.md

| row | verdict | evidence |
|---|---|---|
| dom.js:42 innerHTML in `patch()` | KEEP | dom.js:42 `el.innerHTML = html` |
| dom.js:59 innerHTML in `setHtml()` | KEEP | dom.js:59 `el.innerHTML = html` |
| dom.js:28 CSSOM width via style | KEEP | dom.js:28 `el.style.width = ...`. This is CSSOM, not a style attribute; the setProperty suggestion still applies |
| workflow.js:913 indirect innerHTML via setHtml | KEEP | workflow.js:913 `setHtml(detail, detailHtml(...))` |
| app.js:208 indirect innerHTML via patch | KEEP | app.js:208 `patch(entry[0], entry[1]())` |
| app.js:213 error banner via patch | KEEP | the call is app.js:212 `patch(entry[0], errorHtml(...))`; agy cite is off by one |
| app.js:481 toasts via patch | KEEP | app.js:481 `patch("toasts", toastsHtml())` |

Summary claims, same file:
- "0 inline styles, 0 inline handlers, 0 innerHTML" for index.html, routes.js, planner.js: KEEP (grep over web/ finds no `style=`, `on*=` attributes, or innerHTML in those files).
- planner.js:468 uses textContent: KEEP.
- UI Rule 0 at workflow.js:739-755 (rg-num) and planner.js:181-202 (GRID "pl-row row-grid", rg-num): KEEP.
- Line counts for index.html (54), routes.js (39), planner.js (492), dom.js (113), workflow.js (1014), app.js (504): WRONG, each is one line less than agy's count. All files end with a newline, so `wc -l` is exact.

## Safe to apply

Only KEEP facts. Doc edits are safe as stated. Code and test changes need the usual review first.

- n04 (tests, launcher): add cases for `_project_for` skipping non-dict and empty-path entries, `_valid_dir` rejecting control characters, `maybe_launch` ignoring a False runner result (it still returns True), and the fail-open path. Note that `_moment(None)` is safe to test with a patched `time.time`.
- n05 (tests, features): add cases for `_feat_id`, `_opt_phase`, `_prio`, `_feat_list` (limit and dedupe), `_check_restore`, `features.remove` with sub-features, `features.status_line` singular, `check_date` None and bad date, `apply_records` dry_run. Document that `_h_accept` is gated by `_refuse_accept` before testing it.
- n06 (UI, row-grid): the 12 KEEP rows can be queued for a row-grid pass under UI rule 0. The 2 UNVERIFIED projects.js rows need CSS checks first. Do not apply without a design review.
- n07 (ARIA): apply only the KEEP rows: tasks.js:77, toast.js:99, toast.js:104, tokens.js:110, tokens.js:167, topbar.js:22, topbar.js:120, tree.js:28, work.js:104, workflow.js:608. Skip the WRONG rows tokens.js:108, tokens.js:166, tree.js:14, and the UNVERIFIED workflow.js:436.
- n08 (docs, RELEASE.md): no change needed for the commands. Optional doc note: `project init` takes a folder path, not a project name, at RELEASE.md:24.
- n09 (changelog): use the 13 KEEP facts. Do not use HANDOVER:29 "25 KB" (use about 64 KB CSS cap) or R7.1-SPEC:14 `docs/presence.json` (real file is `presence-<hash>.json` in the state dir); fix those two source docs before the changelog cites them.
- n10 (CSP): the 7 KEEP sink rows are safe as a refactor list. Do not use the line-count claims.
