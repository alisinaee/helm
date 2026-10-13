Read-only review of the WP22 enforcement path. I’ll inspect the hook, control, rules, and command code for fail-open holes, self-lift, stop loops, races, and log leaks.

Enforcement path is in view. Next I’ll trace sentinel fail-open, agent-guard bypasses, stop pickup caps, and what gets written to the activity log.

WP22 enforcement review of the PreToolUse gate, control state, agent guard, rules sync, and the `bin/roadmap` shim. Eight findings, highest first.

## 1. High — ambient `ROADMAP_PROJECT` denies every other project

`roadmap/services/hooks.py:329` (`_project_quiet` → `jobs.resolve_project`)

The hook resolves the project as explicit id, then `ROADMAP_PROJECT`, then the payload cwd. The environment variable wins.

**Scenario.** `demo` is stopped, so `block-demo` exists. The shell has `ROADMAP_PROJECT=demo` (common in a project shell). The tool call’s cwd is another registered project that is running. PreToolUse still loads `demo` and returns `permissionDecision: deny` for Edit, Write, Bash, Agent, and the other gated tools.

**Fix.** For PreToolUse, resolve only from the payload `cwd`. Ignore `ROADMAP_PROJECT`.

## 2. High — frozen control file keeps denying after the limit is gone

`roadmap/services/hooks.py:346-377`, `roadmap/services/control.py:130-137`, `307-313`, `436-446`

The hook denies whenever the sentinel exists and the saved `block` or `stopTasks` say so. It never recomputes. `after_write` is the intended refresh and nothing in this path calls it after spend or usage changes. `set_budget_limit` writes `budget.json` first and only then calls `_mutate`.

**Scenario.** Weekly usage hits `stopAtPercent`, a recompute arms `block-<project>`, and Edit starts failing. The usage window resets to 10% in `usage.json` (usage sync does not recompute). The sentinel and `control-*.json` still say “weekly usage 100%”. The same deny returns after an override expires, because `hooks.py:374` only checks `overrideUntil` against that frozen `block`. A second case: `roadmap limit budget project 500` saves the new limit, then `_mutate` hits the state-dir lock timeout or is killed. The command errors, the sentinel stays, and every gated tool stays denied.

**Fix.** Before denying a limit block, recompute inside the 300 ms budget. If that read or recompute fails, return no decision (fail open) and remove the sentinel. Write the new limit and the control file under one lock.

## 3. High — shim never sees the sentinel when `ROADMAP_HOME` uses `~` or padding

`bin/roadmap:6-19` versus `roadmap/store/paths.py` (`_root` strips, `expanduser`, and `abspath`)

**Scenario.** `ROADMAP_HOME=~/roadmap-board` or `ROADMAP_HOME="/tmp/rb "`. Python reads `/Users/…/roadmap-board/state/block-demo` and would deny. The shim globs the literal `~/roadmap-board/state/block-*` or a path with a trailing space, finds nothing, and `exit 0` before Python. Stop and budget blocks never run.

**Fix.** Build the state directory the same way as `paths.state_dir()` before the `block-*` test.

## 4. High — a stopped agent can remove the gate; the env check is exact `1`

`roadmap/services/hooks.py:311-321` and `:340-341`, `roadmap/services/agentguard.py:17`

While a sentinel exists, Bash is allowed when the stripped command starts with `roadmap ` and does not contain `;`, `&`, `|`, backticks, newline, `<`, `>`, or `$(`. That is every subcommand, not only inbox/status/ask. `refuse_if_agent` fires only when `source == "agent"` or `CLAUDECODE` strips to exactly `1`.

**Scenario.** Project is stopped. The agent runs `roadmap hooks uninstall <id>`. The gate allows it. Uninstall does not call `refuse_if_agent` and deletes the PreToolUse entry from `.claude/settings.local.json`. The next session has no gate while `control-*.json` still says stopped. Separately, with no sentinel yet, `env -u CLAUDECODE roadmap limit budget project 99999` or `CLAUDECODE=true roadmap resume` passes `is_agent`. Passing `source="cli"` skips only the source half; clearing the variable skips the rest.

**Fix.** While blocked, allow only `roadmap inbox`, `status`, `ask`, and `rules show`. Deny `resume`, `override`, `limit`, `phase`, `rules add|rm|sync`, and `hooks uninstall` in the hook itself. Treat any non-empty `CLAUDECODE` as an agent.

## 5. High — `rules sync` deletes whatever sits between the first marker pair

`roadmap/services/rules.py:262-276` and `:288-307`

`_splice` takes the first line whose `strip()` equals `<!-- roadmap:rules -->` and the first `<!-- /roadmap:rules -->`, and replaces everything between them. It does not require that interior to be a previous generated block. The read-modify-write of `CLAUDE.md` is unlocked.

**Scenario.** `CLAUDE.md` documents the markers, one start line and one end line, with the real project instructions between them (indentation still matches after `strip()`). `roadmap rules sync` replaces that span with the generated list. A concurrent edit above the block is also lost: sync writes the whole file from the bytes it read earlier.

**Fix.** Refuse the write unless every interior line is the generated intro or a `- R…` rule line. Before `os.replace`, re-read and write only if the file is still the bytes that were spliced.

## 6. Medium — an agent can overwrite a tighter budget limit

`roadmap/services/control.py:436-442`

`loosens` is decided from `budget.get()` outside `set_limit`’s data-dir lock. The guard runs only when that stale `before` is not `None` and the new value is higher or cleared.

**Scenario.** No project limit yet. The agent calls `set_budget_limit(..., 99999)`. `before` is `None`, so `refuse_if_agent` is skipped. A person sets the limit to `10`. The agent’s `set_limit` then stores `99999`. The person’s cap is gone.

**Fix.** Under the data-dir lock, re-read the current limit, refuse a raise, and write the new value before releasing the lock.

## 7. Medium — Stop pickup can keep blocking past three times

`roadmap/services/hooks.py:436-455` and `:471-472`

The loop brake is `payload.get("stop_hook_active") is True` only. The “3 per session” counter is `sessions[session_id]` in `pickup-<project>.json`. The same queue row is suppressed only by `task@at`.

**Scenario.** Claude sends another Stop with `stop_hook_active` omitted or set to `1`, and a new `session_id` each continuation. Each id has its own counter, so the cap of 3 never hits. Each new queue timestamp (re-enqueue) is a new key, so the once-per-request record does not apply either. The hook returns `decision: block` again. Deleting `pickup-<project>.json` during the continuation turn (Write is allowed when the project is not stopped) resets both counters.

**Fix.** Treat any truthy `stop_hook_active` as already active. Key the cap to a hash stored beside the queue, not only to `session_id`. Ignore a missing or replaced pickup file by failing open after three blocks recorded in the control state.

## 8. Medium — prompts and question answers are copied into logs and session context

`roadmap/services/hooks.py:114-116` and `:508`, `roadmap/services/hooks.py:559-563`, `roadmap/services/control.py:477-484`

Activity lines in `activity.jsonl` from these writers stay structured (`stop`, `resume`, `override`, limit numbers, rule id). Free text goes elsewhere.

**Scenario.** An agy or Cursor command’s `--prompt` (or an Agent description) is copied into the job title and `hooks._log` writes 60 characters of it to `hooks.log`. `pending_lines` puts open question text and answers from the last hour into SessionStart `additionalContext` (160 characters). An answer that is a token is injected into the next session.

**Fix.** Log detector name, job id, and task id only. In inbox lines, keep question id and task id, and omit `text` and `answer`.

