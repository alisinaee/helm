# agy batch 3 verification

Checked against the current code (after 62e359d, 6956e7a and 29e6e58). Rows are cited by the agy doc line or the agy
file:line. Where agy's cite is stale, the current location is given in the evidence. Verdicts: KEEP = the claim holds
at the current code (a stale cite alone does not change the verdict); WRONG = the claim, the expected result or the
fix does not hold. No row is UNVERIFIED.

## m01-api (11 rows: KEEP 10, WRONG 1)

| row | verdict | evidence |
|---|---|---|
| 138 GET feature route | KEEP | ROUTES (routes.py:384-395) has no feature path; API.md:138 still claims a GET route |
| 216-217 task.rename title limit | WRONG | Claim "UNKNOWN" is false: parsers.py:20 TITLE_MAX = 120 and commands.py:130 uses it; API.md already says 1 to 120, so the fix is a no-op |
| 217 task.start args | KEEP | commands.py:163-164 _check_task_id takes id and optional by; API.md lists no args |
| 217 task.stop args | KEEP | same check as task.start (commands.py:558, 163-164) |
| 218 subtask.add omitted | KEEP | public op commands.py:560; not in the API.md ops list |
| 218 subtask.toggle done optional | KEEP | commands.py:211 _opt_bool; with done omitted the subtask toggles (commands.py:225-229) |
| 218 question.ask omitted | KEEP | public op commands.py:562; not in the API.md ops list |
| 219 issue.new args | KEEP | _check_issue_new (commands.py:361-366) takes title, tasks, kind, sev, note, by; title is _opt_text, so not enforced here |
| 219 issue.link omitted | KEEP | public op commands.py:567; not in the API.md ops list |
| 227 feature.unlink feats size | KEEP | featops.py:119-120 _feat_list enforces 1 to LINK_MAX=3; API.md states the limit only for feature.link |
| 231-232 error order | KEEP | API.md lists 413 before 415 and 404 before 422; code: 415 in _write_guard (routes.py:145-155), 422 JSON check before 404 unknown_op in cmd (routes.py:221-240) |

## m02-security-cites (24 rows: KEEP 19, WRONG 5)

| row | verdict | evidence |
|---|---|---|
| 175 host_allowed security.py:48 | KEEP | def at security.py:48 |
| 176 phone_host_allowed security.py:55 | KEEP | def at security.py:55 |
| 177 "if folder is None" routes.py:362 | WRONG | routes.py:362 is `if folder is not None:`; `if folder is None:` is routes.py:376 in notes() |
| 179 write_request_allowed security.py:70 | KEEP | def at security.py:70 |
| 179 out = scrub(snap) routes.py:110 | WRONG | routes.py:110 is `def scrub_text`; `out = scrub(snap)` is routes.py:124 in _phone_public() |
| 180 new_token security.py:34 | KEEP | def at security.py:34 |
| 180 write_request_allowed security.py:70 | KEEP | def at security.py:70 |
| 181 safe_equal security.py:39 | KEEP | def at security.py:39 |
| 181 CSRF safe_equal security.py:84 | KEEP | security.py:84 is the return safe_equal(headers.get(CSRF_HEADER), token) line |
| 182 _snapshot_reply routes.py:115-118 | WRONG | def is at routes.py:130 (body 130-139) |
| 183 MAX_BODY_BYTES security.py:17 | KEEP | security.py:17 = 4096 |
| 183 need_user routes.py:171 | WRONG | routes.py:171 is poll_intervals; need_user is routes.py:185 in _summary (178-) |
| 183 _write_guard in usage_sync routes.py:191 | WRONG | routes.py:191 is `def projects`; usage_sync is at 204 and calls _write_guard at 205 |
| 189 cookie_value security.py:107 | KEEP | def at security.py:107 |
| 189 phone_cookie_header security.py:113 | KEEP | def at security.py:113 |
| 190 phone_cookie_header security.py:113 | KEEP | same |
| 192 safe_equal security.py:39 | KEEP | same as 181 |
| 193 FailureLimiter security.py:133 | KEEP | class at security.py:133 |
| 194 plain_redirect_path security.py:128 | KEEP | def at security.py:128 |
| 197 CSP security.py:18 | KEEP | security.py:18 |
| 197 security_headers security.py:206 | KEEP | def at security.py:206 |
| 198 CSP security.py:18 | KEEP | security.py:18 |
| 198 CSP_LEGACY security.py:22 | KEEP | security.py:22 |
| 199 security_headers security.py:206 | KEEP | def at security.py:206 |

## m03-guard-gaps (36 rows: KEEP 33, WRONG 3)

agentguard.py rows (file line of the agy row):

| row | verdict | evidence |
|---|---|---|
| L3 agent_marked(None) reads os.environ | KEEP | agentguard.py:68 defaults to os.environ; no test passes None |
| L4 CLAUDECODE whitespace only | KEEP | agentguard.py:70-71 skips blank values; returns False |
| L5 empty dict | KEEP | returns False (agentguard.py:74) |
| L6 benign env only | KEEP | returns False |
| L7 AGY_ prefix only | KEEP | "AGY_" startswith AGY_ matches (agentguard.py:23, 73) |
| L8 CURSOR without underscore | KEEP | "CURSOR" does not start with CURSOR_; returns False |
| L9 CLAUDECODE = 123 | KEEP | str(123) is non-blank and key == ENV: True |
| L10 cli, stdin Pipe, stdout Tty | KEEP | _isatty(stdin) False (agentguard.py:94) |
| L11 stream isatty raises ValueError | KEEP | _isatty catches ValueError and OSError (agentguard.py:80-81) |
| L12 stream without isatty | KEEP | AttributeError is caught (agentguard.py:80-81) |
| L13 stdin/stdout None default to sys streams | KEEP | agentguard.py:92-93 default to sys.stdin/sys.stdout |
| L14 gui proven with CLAUDECODE set | KEEP | person_context returns gui_proven() (agentguard.py:88-89); tests use env {} only |
| L15 gui after browser_proven block | KEEP | finally restores the saved flag (agentguard.py:34-35) |
| L16 gui with browser_proven(False) | KEEP | gui_proven() is False |
| L17 source None with TTY streams | KEEP | source != "cli" returns False (agentguard.py:90-91) |
| L18 source "custom" | KEEP | returns False |
| L19 cli, CLAUDECODE whitespace, TTY | KEEP | agent_marked is False and both streams are TTY: True |
| L20 cli, environ None, CLAUDECODE in os.environ | KEEP | agent_marked(None) reads os.environ and is True: False |

featops.py rows:

| row | verdict | evidence |
|---|---|---|
| L21 accept, source agent, direct | KEEP | _h_accept calls _refuse_accept (featops.py:167-168); person_context("agent") False; agent_refused, EXIT_CONFLICT (featops.py:162-164) |
| L22 accept, source phone, direct | KEEP | same path |
| L23 accept on=False from bare non-TTY cli | KEEP | _refuse_accept runs whatever the value of on (featops.py:168) |
| L24 accept on=False from agent | KEEP | same |
| L25 agent undo of a clearance | KEEP | _h_undo blocks only the phone (commands.py:486); inverse feature.accept on=True runs and is refused by _refuse_accept |
| L26 phone undo of an accept | WRONG | _h_undo raises forbidden "the phone may undo only its own changes" (commands.py:486-487) before any inverse runs; an accept never has phone origin, so agent_refused is not the result |
| L27 TTY with CLAUDECODE or CODEX_HOME | KEEP | agent_marked True (agentguard.py:72-74) so refused; the test covers only CURSOR_TRACE_ID and AGY_SESSION |
| L28 accept with bad date | KEEP | _check_accept calls features.check_date (featops.py:156-157), usage error (features.py:332) |
| L29 accept with id FX or F100 | KEEP | FEAT_ID_RE ^F[1-9][0-9]?$ rejects both (parsers.py:26; featops.py:30-34) |
| L30 phone restore of accepted feature | WRONG | _h_undo raises forbidden first: origin of the feature.rm is not phone, and PHONE_OPS (security.py:175) has no feature ops; not agent_refused |
| L31 bare non-TTY cli restore of accepted | KEEP | _h_restore refuses (featops.py:199-201) since person_context("cli") is False without a TTY |
| L32 TTY with AGY_SESSION restore | KEEP | agent_marked True, refused |
| L33 unproven gui restore | KEEP | gui_proven() False, refused |
| L34 proven browser click restore | KEEP | person_context True; restore runs (featops.py:199-203); tests cover TTY only |
| L35 phone restore of unaccepted feature | WRONG | _h_undo blocks the phone first (commands.py:486-487) because the origin is not phone, so it does not succeed |
| L36 restore with feature not a dict | KEEP | _check_restore raises usage "feature restore needs a feature record" (featops.py:190-192) |
| L37 restore with id "123" | KEEP | FEAT_ID_RE rejects it (featops.py:191) |
| L38 restore with accepted None | KEEP | returns the record with accepted None (featops.py:193-194) |

## m04-queue-gaps (22 rows: KEEP 16, WRONG 6)

queue.py and loader.py have changed since agy ran; cites below are current locations.

| row | verdict | evidence |
|---|---|---|
| queue L3 WATCHING session | KEEP | idle is False (queue.py:49); body is the open-session text (queue.py:54); no spawn (queue.py:59-60). Agy cite now queue.py:46-62 |
| queue L4 presence.state raises | KEEP | except pass (queue.py:61-62); enqueue still returns the entry (queue.py:29-30) |
| queue L5 path with spaces, shlex.quote | WRONG | queue.py has no shlex and no path in the notification; body names the project id only (queue.py:52-56) |
| queue L6 notify_dir title and kind | KEEP | queue.py:58 notify.notify_dir(data_dir, "start", "Start queued", body) |
| queue L7 _project_path registry lookup | WRONG | queue.py has no _project_path; the helper now is loader.py:61 with a different signature |
| queue L8 list_projects raises | WRONG | same: function not in queue.py |
| queue L9 custom dataDir match | WRONG | same |
| queue L10 empty path | WRONG | same |
| queue L11 maybe_launch returns True | KEEP | _launch_quietly returns with no error (queue.py:33-38) |
| queue L12 maybe_launch raises | KEEP | except pass (queue.py:37-38) |
| queue L13 real _spawn daemon thread | KEEP | _spawn (queue.py:41-43) uses Thread(target, args=(arg,), daemon=True); called with _launch_quietly, data_dir (queue.py:60) |
| queue L14 notify outside lock | KEEP | lock block ends at queue.py:27; _notify_start at queue.py:29 |
| loader L15 session=_session_view(folder) | KEEP | loader.py:47 |
| loader L16 folder=_project_path(entry) | KEEP | loader.py:47 |
| loader L17 session key in snapshot | KEEP | loader.py:47 passes session; snapshot.py:347-348 adds the key when not None |
| loader L18 presence.state raises gives session None | KEEP | _session_view returns None (loader.py:57-58) |
| loader L19 entry with no path | WRONG | load_snapshot calls project_folder(entry) first (loader.py:34); loader.py:28 reads entry["path"] and raises KeyError, so build_snapshot never gets folder=None. The isolated _project_path returning None is true |
| loader L20 _session_view with OPEN | KEEP | returns presence.state directly (loader.py:56) |
| loader L21 OSError from state | KEEP | except returns None (loader.py:57-58) |
| loader L22 path "" | KEEP | falsy, returns None (loader.py:65) |
| loader L23 non-string truthy path | KEEP | str(path) (loader.py:65) |
| loader L24 entry 123 | KEEP | .get raises AttributeError, caught, returns None (loader.py:66-67) |

## m05-rename-gaps (32 rows: KEEP 30, WRONG 2)

| row | verdict | evidence |
|---|---|---|
| L3 120 chars with spaces | KEEP | commands.py:126 strips, then 120 limit (commands.py:130; parsers.py:20) |
| L4 121 chars | KEEP | commands.py:130-131 message "title is 121 characters (allowed: up to 120)" |
| L5 single char "x" | KEEP | valid |
| L6 activity summary for a 120-char title | WRONG | activity.py:24 truncates the summary to ACTIVITY_SUM_MAX = 60 (parsers.py:25) after collapsing whitespace; the stored sum never exceeds 60 |
| L7 undo pruned to 500 | KEEP | _remember calls keep_newest(UNDO_KEEP) (commands.py:635); UNDO_KEEP = 500 (commands.py:28) |
| L8 NUL | KEEP | category Cc, rejected (commands.py:132-133) |
| L9 CR | KEEP | Cc, rejected |
| L10 VT and FF | KEEP | Cc, rejected |
| L11 C1 U+0085 and U+009F | KEEP | Cc, rejected |
| L12 U+200B (Cf) | KEEP | Cf is not Cc, so it passes |
| L13 ESC | KEEP | Cc, rejected |
| L14 second undo of same activity | KEEP | conflict "is already undone or being undone; not changed" (commands.py:479-480) |
| L15 undo record shape | KEEP | _remember writes {activity, sum, op, args, at} (commands.py:633-634) |
| L16 undo return shape | KEEP | {undone, op, sum} (commands.py:498-499) |
| L17 phone undo of a GUI rename | KEEP | forbidden, EXIT_USAGE (commands.py:486-487) |
| L18 phone undo of its own rename | KEEP | allowed when origin is phone; the phone listener does not accept task.rename (security.py:175), so only commands.run reaches it |
| L19 undo after identical title | KEEP | inverse None, nothing remembered, undo gives not_found (commands.py:482-484) |
| L20 undo after task deleted | KEEP | _execute raises, undoFailed is appended and the error re-raised (commands.py:491-494) |
| L21 agent rename | KEEP | run() has no agent refusal (commands.py:584-606); the handler notes no guard |
| L22 write() under CLAUDECODE | KEEP | source_name gives agent (commands.py:661) |
| L23 cli source | KEEP | valid source |
| L24 invalid source | KEEP | "source 'invalid' is not valid (allowed: ...)" (commands.py:586-587) |
| L25 missing id | KEEP | empty id fails ID_OK, usage with next "roadmap status" (commands.py:46-50) |
| L26 id P1/2 or P..1 | KEEP | fails ID_OK (commands.py:44-50) |
| L27 unknown id with empty title | KEEP | title check runs first with next "roadmap task list --phase P99" (commands.py:127-129) |
| L28 activity unchanged on unknown id | KEEP | tasks.get raises in the handler before activity.append (commands.py:598-601) |
| L29 non-dict args | KEEP | "args must be an object" (commands.py:592-593) |
| L30 activity fields | KEEP | activity.append with undo = inverse is not None (commands.py:600) |
| L31 internal double quotes in summary | WRONG | shlex.quote('Task "beta"') gives 'Task "beta"' (no single quote inside, so one pair of single quotes); the agy expected \'...\' form is wrong |
| L32 identical title undo=False | KEEP | inverse None gives undo False (commands.py:600-601) |
| L33 empty or control title, no activity | KEEP | entry.check fails before the handler and append (commands.py:595) |
| L34 injected now in at | KEEP | now passed to run and activity.append (commands.py:584, 600) |

## m06-aria-as (36 rows: KEEP 28, WRONG 8)

Current file locations differ from agy's cites. Markup checked by text. "Missing" means the attribute is absent on the
element at its current location.

| agy cite | verdict | evidence |
|---|---|---|
| activity.js:15 Undo | KEEP | button at activity.js:15-16 has no aria-label |
| agents.js:52 job link | KEEP | now agents.js:53; no aria-label |
| board.js:159 Clear filters, aria-controls wk-filters | WRONG | now board.js:173; "wk-filters" is a class (board.js:175), not an id, so the target does not exist |
| board.js:187 Move to Todo aria-label | KEEP | now board.js:202; no aria-label (the summary has one) |
| board.js:189 Queue task | KEEP | now board.js:203; no aria-label |
| board.js:190 Stop task | KEEP | now board.js:204; no aria-label |
| board.js:240 wk-tab aria-controls wk-col-key | KEEP | id wk-col-<key> exists (board.js:238) so the target is valid |
| details.js:128 status button | KEEP | now details.js:129; has aria-pressed, no aria-label |
| details.js:187 Start aria-label | KEEP | now details.js:189; markup uses data-focus="start" (agy wrote data-side), no aria-label |
| details.js:189 Stop aria-label | KEEP | details.js:190; no aria-label |
| details.js:196 Copy command | KEEP | details.js:197-198; no aria-label |
| details.js:210 Save cap | KEEP | details.js:211; no aria-label |
| details.js:211 Clear cap | KEEP | details.js:212-213; no aria-label |
| details.js:230 Add subtask | KEEP | details.js:231; no aria-label |
| details.js:246 Add comment | KEEP | details.js:247; no aria-label |
| details.js:357 Close issue | KEEP | details.js:361-362; no aria-label |
| details.js:371 answer button | KEEP | details.js:375; no aria-label |
| details.js:375 d-btns group | KEEP | details.js:379 div has no role and no aria-label |
| details.js:379 Send answer | KEEP | details.js:383; no aria-label |
| inbox.js:108 qc-opt | KEEP | inbox.js:109-112; no aria-label |
| inbox.js:123 qc-task link | KEEP | inbox.js:124; no aria-label |
| inbox.js:145 link | KEEP | inbox.js:147; no aria-label |
| inbox.js:186 link | KEEP | inbox.js:188; no aria-label |
| issues.js:38 aria-controls iss-list | WRONG | iss-list is a class on the ul (issues.js:105); no id, target does not exist |
| limits.js:97 range aria-controls lim-prev-id | WRONG | now limits.js:98; no lim-prev- id exists anywhere in web/js |
| limits.js:100 number aria-controls lim-prev-id | WRONG | now limits.js:101; same missing target |
| limits.js:115 minus step aria-controls lim-input-id | WRONG | now limits.js:116; no lim-input- id exists |
| limits.js:118 plus step aria-controls lim-input-id | WRONG | now limits.js:119; same missing target |
| limits.js:124 Delete | KEEP | limits.js:125; no aria-label |
| limits.js:135 Delete | KEEP | limits.js:136; no aria-label |
| limits.js:151 Edit / Done | KEEP | limits.js:152; no aria-label |
| limits.js:171 Add limit aria-expanded, aria-controls lim-presets | WRONG | aria-expanded is missing (valid), but lim-presets is a class (limits.js:159), not an id; the target does not exist |
| list.js:144 Start | KEEP | list.js:143-144; no aria-label |
| list.js:145 Stop | KEEP | list.js:145; no aria-label |
| list.js:155 sort button aria-label | KEEP | list.js:156; the th has aria-sort, the button has no aria-label |
| nav.js:77 collapse aria-expanded, aria-controls | WRONG | aria-label is already present; aria-expanded is missing, but the aria-controls target nav-list is a class (nav.js:75), not an id |

## safe to apply

- m01: API.md:138 remove the GET feature route claim. API.md task.start and task.stop: add (id, by?). Add subtask.add (id, title?), question.ask (text, task?, opts?, default?, block?, timeout?), issue.link (id, tasks). Document subtask.toggle done as optional. Document issue.new args. feature.unlink: add the 1 to 3 feats limit. API.md:231-232: reorder to 403, 415, 413, 422, 404. Do not apply the task.rename row (no-op).
- m02: correct the five cites: routes.py:376 (not 362), routes.py:124 (not 110), routes.py:130-139 (not 115-118), routes.py:185 (not 171), routes.py:205 (not 191). The other 19 cites are correct.
- m03: correct the three expected results: L26 (forbidden, EXIT_USAGE, not agent_refused), L30 (forbidden, not agent_refused), L35 (forbidden, does not succeed). The other 33 rows are safe as test cases.
- m04: the 16 KEEP rows are safe as test cases, with cites updated to the current lines. Drop L5, L7, L8, L9, L10 and L19.
- m05: the 30 KEEP rows are safe as test cases. Fix L6 (summary truncated to 60) and L31 (expected 'Task "beta"').
- m06: the 28 KEEP attributes are safe to apply. Do not apply the 8 WRONG rows (board.js:159, issues.js:38, limits.js:97, 100, 115, 118, 171, nav.js:77) as written, because their aria-controls targets (wk-filters, iss-list, lim-prev-, lim-input-, lim-presets, nav-list) are classes, not ids. Add real ids first if those rows are wanted.
