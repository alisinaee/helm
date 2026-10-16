I'll review today's commits on main and list real bugs in this chat. No plan file.

Today's commits are identified. Next I'll read the changed paths for those R10 items and check the call sites.

Reviewed today's R10 commits on main (resize, Work/Planner, Git reads, supervisor/loader/snapshot, `init`, Inbox, Stop-hook reply). Eight real bugs:

1. **P1** | `web/js/state.js:271` | A claimed job is in the snapshot (`status: "claimed"`, included in `summary.running_count`) but the client builds `running` with `status === "running"` only. `web/js/views/agents.js:94` and `web/js/views/running.js:80` then treat it as finished, and `running.js:67` labels anything not `done` as **failed**. `web/js/graph/model.js:109` skips it for "You are here", and `web/js/views/workflow.js:118` maps it to queued. **Fix:** treat `claimed` as in-flight everywhere those checks use `running` (running list, finished list, graph, workflow). Label it claimed, not failed.

2. **P1** | `roadmap/http/routes.py:729` | `git_diff` secret hiding checks only the query string (`is_secret_path` at line 726). `valid_rel_path` (`roadmap/services/git.py:91`) accepts git pathspecs (`*`, `*env*`, `:(glob)**/*`). `git show` globs those, so a same-origin caller gets `.env` and other secret blobs in one diff. **Fix:** pass `--literal-pathspecs`, reject `* ? [ ] : \` and magic pathspecs, and skip the response if any numstat path is secret or if more than one file matches.

3. **P1** | `web/js/views/work.js:34` | Planner focus arrives as `?f=F5` (legacy `#/p/<id>/planner?f=F5`, and `web/js/views/details.js:321`). `readPrefs` stores that in `prefs.f`. Leaving Planner runs `goWork` (`work.js:136`) and `persist` (`work.js:106`) writes `f=F5` as the Work tag filter, replacing the saved tags. The board then filters on the tag `F5`. **Fix:** while `view === "planner"`, keep route `f` for `applyFocus` only; load and save tag filters from the stored prefs.

4. **P1** | `roadmap/commands/init.py:47` | The printed URL is `http://localhost:<port>#<id>`. The router treats that hash as a section name, then redirects to `#/all/overview`. A folder whose id is a real section (`work`, `inbox`) opens that All-projects section. **Fix:** print `http://localhost:<port>/#/p/<id>/overview`.

5. **P2** | `roadmap/services/hooks.py:743` | `_turn_reply` keeps the newest assistant text when it walks past an `isMeta` user row. One Stop after a task notification (notification, then "Background build finished.", with no earlier Stop) stores that line on the original prompt. The "reply already set" guard at line 769 never runs. **Fix:** on an `isMeta` user row, set `reply = None` before continuing. Leave tool-result user rows alone so the final answer of the same turn is kept.

6. **P2** | `roadmap/services/hooks.py:773` | Stop calls `_head_reply_capture` only after `_run_event` (lock wait up to 1s). The reply write then uses the leftover PreToolUse budget (`PRE_TIMEOUT_S` is 0.3s), which is already 0. `set_reply(..., timeout=0)` does not wait, so a busy project lock drops the answer. **Fix:** give this write its own timeout (on the order of the Stop hook budget, not the 0.3s PreToolUse remainder), computed before the transcript read.

7. **P2** | `web/js/views/inbox.js:663` | Chips show `a`–`f` (`inbox.js:159`, `String.fromCharCode(97 + index)`). The handlers are `bindKey("1")`…`"6"`. `a` is the `g a` Agents chord, not an answer. **Fix:** bind `a`–`f` to `onDigit` on the Inbox (and ignore them when `g` is the chord prefix), or render the digits `1`–`6` in the chip.

8. **P2** | `web/js/views/git.js:26` | `sel`, `detail`, and `diffs` are one global cache. History on project B still shows project A's selected commit and its diff. **Fix:** key `detail` and `diffs` by project id, and clear `sel` when `vm.route.id` changes.

