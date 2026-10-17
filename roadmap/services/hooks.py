"""Hook driver: turns Claude Code hook events into job starts and closes. Ported from split-net's jobs_auto.py.

Events: PostToolUse (Agent, Task, Bash) registers jobs; SubagentStop closes the job of that agent; every event
reaps jobs whose work has finished. Detectors are a registry (DETECTORS): agent, agy and cursor. A project picks
its detectors with "hookDetectors" in its roadmap.config.json. The state of each project (active jobs and the
detector that started each) is hooks-<project>.json in the state directory. Every problem goes to hooks.log.
run_hook never raises: a hook must never fail a tool call.
"""

import datetime
import hashlib
import json
import os
import re
import shlex
import threading
import time

from roadmap import log as roadmap_log
from roadmap.core import head as head_core
from roadmap.errors import EXIT_CONFLICT, EXIT_INVALID_DATA, RoadmapError
from roadmap.services import control, git, jobs, jobtokens, presence, rules
from roadmap.services import head as head_svc
from roadmap.services import headpanel
from roadmap.services import queue as queue_service
from roadmap.store import atomic, lock, paths, schema

DEFAULT_PATTERN = r"^[A-Z]+[0-9]+(\.[0-9]+)?$"
DEFAULT_DETECTORS = ("agent", "agy", "cursor")
IDLE_S = 180          # an agent output file untouched this long counts as finished
MAX_AGE_S = 7200      # a job with no readable output after this long is closed
LOG_FILE = "hooks.log"
_AGENT_ID_RE = re.compile(r'agentId[:\s"]+([0-9a-zA-Z]{8,})')
_OUTPUT_RE = re.compile(r'output_file[:\s"]+(\S+?\.output)')
_RESULT_RE = re.compile(r"result file[^:]*:\s*(\S+\.result\.md)")
_COMPANION_RE = re.compile(r'companion\.mjs"?\s+(\w+)')
_CONTROL_RE = re.compile(r"\b(wait|observe|cancel)\b")
_CURSOR_RE = re.compile(r"cursor-review2\.sh\s+(\"[^\"]+\"|'[^']+'|[^\s&;|]+)")
_SECRET_RE = re.compile(r"sk-[A-Za-z0-9_-]{8,}|gh[pousr]_[A-Za-z0-9]{8,}|xox[abprs]-[A-Za-z0-9-]{8,}|AKIA[0-9A-Z]{12,}"
                        r"|(?i:bearer)\s+\S+|(?i:(?:api[_-]?key|token|secret|password|passwd)\s*[=:]\s*)\S+")
_QUOTED_PROMPT_RE = re.compile(r"""\s+(?:"((?:[^"\\]|\\.)*)"|'([^']*)')""")
_OPERATOR_RE = re.compile(r"\s*(?:&&|\|\||[;|&])")
HOOK_LOCK_TIMEOUT_S = 1.0  # each lock wait in one hook event: the hook must exit well inside its 10 s budget
AGENT_FALLBACK_TASK = "R7.31"  # an agent job that names no task and no head job is bound here (A5)
HEAD_JOB_WINDOW_S = 3600       # the head job an agent job falls back to started this recently
AGENTS_MAP_FILE = "agents-map.json"  # agentId -> {task, title, model} of the agent jobs (R7.89), in the data folder
AGENTS_MAP_MAX = 200                 # the newest entries kept in the agents map
FOLLOWUP_MAX_S = 1800                # a follow-up job with no SubagentStop after this long is closed as done
ORPHAN_AGE_S = 600                   # R11.144: a running job no hook owns, older than this, is surfaced at Stop
IDLE_LAUNCH_N = 3                    # task ids named in the idle alert of the Stop gate


def _response_text(tool_response):
    """The tool response as one text, with the newlines of its JSON form made real (the legacy matching rule)."""
    return json.dumps("" if tool_response is None else tool_response).replace("\\n", "\n")


def _squash(text):
    return re.sub(r"\s+", " ", text)


def _summary(text, limit=60):
    """At most limit characters of a free text (a prompt or a description), one line, with secret-looking tokens
    replaced. Only this summary may reach a job title; logs never carry free text."""
    return _SECRET_RE.sub("[redacted]", _squash(str(text or "")).strip())[:limit]


def _before_operator(text):
    """The text up to the first shell operator (&&, ||, ;, | or &). A title never shows what runs after the command."""
    return _OPERATOR_RE.split(text, maxsplit=1)[0]


class AgentDetector:
    """A subagent started with the Agent or Task tool. Closed by SubagentStop, or when its output goes quiet."""

    name = "agent"

    def on_tool(self, tool, tool_input, tool_response, session_model=None):
        if tool not in ("Agent", "Task"):
            return None
        text = _response_text(tool_response).replace("\n", " ")
        agent = _AGENT_ID_RE.search(text)
        output = _OUTPUT_RE.search(text)
        # No model in the call: the subagent runs on the session model (never a guessed default). "unknown" when the
        # hook does not know the session model either.
        model = str(tool_input.get("model") or session_model or "unknown")
        effort = str(tool_input.get("effort") or "").strip().lower()
        description = str(tool_input.get("description") or "")
        prompt = str(tool_input.get("prompt") or "")
        return {
            "title": model + ": " + _summary(description),
            "model": model,
            "effort": effort if effort in jobs.EFFORTS else "",
            "text": description + " " + prompt,
            "kind": "agent",
            "watch": output.group(1) if output else "",
            "agent": agent.group(1) if agent else "",
        }

    def reap(self, entry, now):
        age = now - float(entry.get("started") or now)
        watch = entry.get("watch") or ""
        if not watch:
            return "done" if age > MAX_AGE_S else None
        try:
            quiet = now - os.path.getmtime(watch)
        except OSError:
            return "done" if age > MAX_AGE_S else None
        return "done" if quiet > IDLE_S else None


class _FileDetector:
    """A background Bash job that writes a result file. Done when the file appears; failed when its first line
    says error."""

    name = ""

    def reap(self, entry, now):
        watch = entry.get("watch") or ""
        if watch and os.path.exists(watch):
            return "failed" if _first_line_has_error(watch) else "done"
        age = now - float(entry.get("started") or now)
        return "failed" if age > MAX_AGE_S else None


class AgyDetector(_FileDetector):
    """agy-companion jobs (not wait, observe or cancel). The result file is named in the command output."""

    name = "agy"

    def on_tool(self, tool, tool_input, tool_response, session_model=None):
        if tool != "Bash":
            return None
        cmd = str(tool_input.get("command") or "")
        if "agy-companion" not in cmd or _CONTROL_RE.search(cmd):
            return None
        found = _RESULT_RE.search(_response_text(tool_response))
        if not found:
            return None
        who = _COMPANION_RE.search(cmd)
        prompt = _summary(_before_operator(cmd.split("--prompt")[-1]).strip(" \"'"))
        title = "agy %s: %s" % (who.group(1) if who else "job", prompt)
        return {"title": title, "model": "agy", "text": cmd, "kind": "file", "watch": found.group(1),
                "agent": ""}


class CursorDetector(_FileDetector):
    """cursor-review2.sh runs. The first argument is the result file."""

    name = "cursor"

    def on_tool(self, tool, tool_input, tool_response, session_model=None):
        if tool != "Bash":
            return None
        cmd = str(tool_input.get("command") or "")
        invocation = _cursor_invocation(cmd)
        if invocation is None:
            return None
        output, prompt = invocation
        label = _summary(prompt, 70) if prompt else os.path.basename(output)
        # The real engine is named by CURSOR_MODEL in the command (grok-4.7-xhigh, auto, ...); no value means auto.
        engine = re.search(r"CURSOR_MODEL=(\S+)", cmd)
        engine_model = engine.group(1) if engine else "auto"
        return {"title": ("Cursor Auto" if engine_model == "auto" else "Cursor " + engine_model) + ": " + label, "model": "cursor", "text": cmd, "kind": "file",
                "watch": output, "agent": "", "engine_model": engine_model}


def _cursor_invocation(cmd):
    """(output file, quoted prompt or None) of the last cursor-review2.sh invocation in a command, or None.

    Chained commands around it (&&, ;, |, &) never count as the output file: the output token cannot start with an
    operator, and the last invocation is the one that runs the review.
    """
    found = None
    for match in _CURSOR_RE.finditer(cmd):
        found = match
    if found is None:
        return None
    token = found.group(1)
    if token[:1] in "&;|" or not token.strip("\"'"):
        return None
    prompt = None
    quoted = _QUOTED_PROMPT_RE.match(cmd, found.end())
    if quoted is not None:
        prompt = quoted.group(1) if quoted.group(1) is not None else quoted.group(2)
    return token.strip("\"'"), prompt


class FollowupDetector:
    """A SendMessage follow-up to a known subagent (R7.89). Not a file or output detector: it never starts from a tool
    call (the follow-up is started in _run_event). It is closed by SubagentStop (same agent id), or as done after
    FOLLOWUP_MAX_S by the stale sweep that every later event runs."""

    name = "followup"

    def on_tool(self, tool, tool_input, tool_response, session_model=None):
        return None

    def reap(self, entry, now):
        age = now - float(entry.get("started") or now)
        return "done" if age > FOLLOWUP_MAX_S else None


DETECTORS = {d.name: d for d in (AgentDetector(), AgyDetector(), CursorDetector(), FollowupDetector())}


def _first_line_has_error(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            first = fh.read(300).split("\n")[0]
    except OSError:
        return False
    return "error" in first


def task_regex(pattern):
    """Compile the project's taskIdPattern for searching inside free text (the ^ and $ anchors are dropped)."""
    body = pattern[1:] if pattern.startswith("^") else pattern
    if body.endswith("$") and not body.endswith("\\$"):
        body = body[:-1]
    try:
        return re.compile(r"(?<![A-Za-z0-9_.])(?:" + body + r")(?![A-Za-z0-9_])")
    except re.error as exc:
        raise RoadmapError("invalid_data", "taskIdPattern does not compile: " + str(exc), EXIT_INVALID_DATA)


def find_task(text, regex, known):
    """The first id in text that matches the pattern and exists in tasks.json, or None."""
    for match in regex.finditer(text or ""):
        if match.group(0) in known:
            return match.group(0)
    return None


def project_settings(data_dir):
    """Return (taskIdPattern, detector names) from the project's roadmap.config.json, with defaults."""
    data, error = schema.read_data("roadmap_config", os.path.join(data_dir, "roadmap.config.json"))
    if error is not None:
        raise RoadmapError("newer_schema", error["message"], EXIT_INVALID_DATA)
    data = data or {}
    pattern = data.get("taskIdPattern")
    if not isinstance(pattern, str) or not pattern:
        pattern = DEFAULT_PATTERN
    names = data.get("hookDetectors", list(DEFAULT_DETECTORS))
    if not isinstance(names, list):
        raise RoadmapError("invalid_data", "hookDetectors must be a list of detector names", EXIT_INVALID_DATA)
    return pattern, [n for n in names if isinstance(n, str)]


def run_hook(raw, environ=None, cwd=None, now=None, clock=None):
    """Handle one hook event given as stdin text. Returns the JSON reply for Claude Code (a dict) or None.

    Never raises. A PreToolUse event that fails, runs past PRE_TIMEOUT_S or finds no sentinel returns None, which
    lets the tool call through (fail open).
    """
    clock = time.monotonic if clock is None else clock
    started = clock()
    try:
        return _handle(raw, os.environ if environ is None else environ, cwd, time.time() if now is None else now,
                       clock, started)
    except Exception as exc:  # a hook must never fail a tool call: the problem goes to the log
        _log("error " + type(exc).__name__ + ": " + str(exc))
        return None


def _handle(raw, environ, cwd, now, clock, started):
    try:
        payload = json.loads(raw) if raw and raw.strip() else {}
    except ValueError as exc:
        _log("skip: stdin is not valid JSON (" + str(exc)[:80] + ")")
        return None
    if not isinstance(payload, dict):
        _log("skip: stdin is not a JSON object")
        return None
    event = str(payload.get("hook_event_name") or "")
    if event in USAGE_EVENTS:
        _usage_auto(payload, now)
    if event == "PreToolUse":
        return _pre_tool_use(payload, environ, cwd, now, clock, started)
    if event == "UserPromptSubmit":
        return _user_prompt(payload, environ, cwd, now, clock, started)
    tool = str(payload.get("tool_name") or "")
    _log(event + " " + tool)
    project = _project_for(payload, environ, cwd)
    if project is None:
        return None
    data_dir = jobs.data_dir_of(project)
    if not os.path.isdir(data_dir):
        _log("skip: data folder missing for " + project["id"])
        return None
    _touch_presence(project, now, clock, started)
    if event == "SessionStart":
        _head_claim(project, data_dir, payload, now, clock, started)
        panel = _panel_text(data_dir, payload, "start", now, clock, started)
        return _session_start(project, data_dir, clock, started, now, panel=panel)
    pattern, names = project_settings(data_dir)
    regex = task_regex(pattern)
    known = jobs.known_task_ids(data_dir)
    active = [DETECTORS[n] for n in names if n in DETECTORS]
    for name in names:
        if name not in DETECTORS:
            _log("skip: unknown detector '" + name + "' in " + project["id"])
    try:
        _run_event(project, data_dir, event, payload, active, regex, known, now)
    except RoadmapError as exc:
        if exc.code != "locked":
            raise
        # A busy lock: return silently, so the hook exits 0 within its time budget. The next event tries again.
    if event == "Stop":
        _head_reply_capture(payload, data_dir, now, clock, started)
        panel = "" if payload.get("stop_hook_active") else _panel_text(data_dir, payload, "stop", now, clock, started)
        reply = _stop_pickup(payload, project, data_dir, now, clock, started) or _stop_gate(payload, project, data_dir,
                                                                                          now)
        reply = _with_panel_block(reply, panel)
        orphans = "" if payload.get("stop_hook_active") or payload.get("agent_id") else _orphan_text(project, data_dir,
                                                                                                    now)
        return _with_panel_block(reply, orphans)
    if event == "PostToolUse":
        panel = _panel_text(data_dir, payload, "tool", now, clock, started)
        if panel:
            return {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": panel}}
    return None


# ------------------------------------------------------------------ panel to head (R11.2, docs/PANEL-TO-HEAD.md)

def _panel_text(data_dir, payload, via, now, clock, started):
    """The person's unseen board actions as hook text, marked seen for this session, or ''. Never for a subagent's
    own hook (agent_id in the payload) and off with head.panel false in the project config. Fail-open."""
    try:
        if payload.get("agent_id"):
            return ""
        cfg = _head_config(data_dir).get("head")
        if isinstance(cfg, dict) and cfg.get("panel") is False:
            return ""
        budget = max(0.05, (PRE_TIMEOUT_S - (clock() - started)) * 0.5)
        moment = datetime.datetime.fromtimestamp(now).astimezone()
        return headpanel.take_text(data_dir, via, sid=head_svc.session_key(payload.get("session_id")), now=moment,
                                   timeout=budget)
    except Exception as exc:
        _log("panel skipped: " + type(exc).__name__)
        return ""


def _with_panel_block(reply, panel):
    """A Stop reply that also carries the panel text: it joins an existing block, or blocks alone so the head reads
    what the person did before it ends its turn."""
    if not panel:
        return reply
    if isinstance(reply, dict) and reply.get("decision") == "block":
        return dict(reply, reason=panel + "\n" + str(reply.get("reason") or ""))
    return {"decision": "block", "reason": panel}


def _run_event(project, data_dir, event, payload, active, regex, known, now):
    """Read the state, do the job work, then save the state. The state lock is never held while a project lock is
    awaited: the state is read under its lock, the jobs are started or closed under the project lock only, and the
    result is merged into the state again under its lock. Each lock wait is HOOK_LOCK_TIMEOUT_S at most."""
    path = paths.hooks_file(project["id"])
    paths.ensure_dir(paths.state_dir())
    with lock.locked(paths.state_dir(), timeout=HOOK_LOCK_TIMEOUT_S):
        snapshot = _read_state(path)["active"]
    started = []
    closed = []
    with lock.timeout_scope(HOOK_LOCK_TIMEOUT_S):
        try:
            if event == "PostToolUse":
                tool = str(payload.get("tool_name") or "")
                tool_input = payload.get("tool_input")
                tool_input = tool_input if isinstance(tool_input, dict) else {}
                session_model = _session_model(payload) if tool in ("Agent", "Task") else None
                if tool == "Bash":
                    _commit_candidates(project, data_dir, payload, tool_input, now)
                for detector in active:
                    entry = detector.on_tool(tool, tool_input, payload.get("tool_response"),
                                             session_model=session_model)
                    if entry is not None:
                        new = _start(data_dir, detector, entry, regex, known, now,
                                     owned={e.get("job") for e in snapshot})
                        if new is not None:
                            started.append(new)
                            if detector.name == "agent" and new.get("agent"):
                                _remember_agent(data_dir, new)
                if tool == "SendMessage":
                    new = _followup_start(data_dir, tool_input, now)
                    if new is not None:
                        started.append(new)
            elif event == "SubagentStop":
                agent_id = str(payload.get("agent_id") or "")
                if agent_id:
                    stopped = _close_some(data_dir, snapshot,
                                          lambda e: "done" if e.get("agent") == agent_id else None)
                    closed += stopped
                    for job_id in stopped:  # R10.32: measured tokens from the subagent transcript, fail-open
                        jobtokens.capture_for_agent(data_dir, job_id, payload)
            left = [e for e in snapshot if e.get("job") not in set(closed)]
            closed += _close_some(data_dir, left, _verdict_of(now))
        except RoadmapError as exc:
            if exc.code != "locked":
                raise
            # keep what was done so far; the rest is retried by a later event
    if not started and not closed:
        return
    with lock.locked(paths.state_dir(), timeout=HOOK_LOCK_TIMEOUT_S):
        latest = _read_state(path)["active"]
        gone = set(closed)
        merged = [e for e in latest if e.get("job") not in gone] + started
        _write_state(path, project["id"], {"active": merged})


# ------------------------------------------------------------------ control: PreToolUse, SessionStart, Stop pickup

PRE_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit", "Bash", "Agent", "Task", "WebFetch", "WebSearch")
# while the project is blocked, these roadmap commands are the only ones a Bash call may run
ALLOWED_WHILE_BLOCKED = (("inbox",), ("status",), ("ask",), ("rules", "show"), ("watch",))
PRE_TIMEOUT_S = 0.3        # a PreToolUse that takes longer lets the tool call through
PRESENCE_MIN_BUDGET_S = 0.2  # the presence stamp is skipped when less of PRE_TIMEOUT_S is left
DENY_LOG_S = 60            # a denial is logged at most once a minute per project
PICKUP_PER_SESSION = 3
INBOX_LINES = 3
RULE_CHARS = 800      # the most text the rules and done lines add to a pickup or to the session context
_SHELL_OPERATORS = (";", "&", "|", "`", "\n", "<", ">", "$(")


def _too_slow(clock, started):
    return clock() - started > PRE_TIMEOUT_S


def _roadmap_command(command):
    """True for a Bash command that is one roadmap command: it starts with 'roadmap ' and chains nothing."""
    text = command.strip()
    return text.startswith("roadmap ") and not any(op in text for op in _SHELL_OPERATORS)


def _project_quiet(payload, cwd):
    """The registered project of the payload cwd, or None. The gate never reads ROADMAP_PROJECT: an ambient variable
    must not decide which project a tool call is denied for. Unlike _project_for, it logs nothing."""
    here = payload.get("cwd")
    here = here if isinstance(here, str) and here else cwd
    try:
        return jobs.resolve_project(None, {}, here)
    except RoadmapError:
        return None


def _allowed_while_blocked(command):
    words = command.split()[1:]
    return any(words[:len(prefix)] == list(prefix) for prefix in ALLOWED_WHILE_BLOCKED)


def _pre_tool_use(payload, environ, cwd, now, clock, started):
    """The PreToolUse decision: a deny reply when the project is stopped or blocked, otherwise None."""
    tool = str(payload.get("tool_name") or "")
    if tool not in PRE_TOOLS:
        return None
    tool_input = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
    command = str(tool_input.get("command") or "") if tool == "Bash" else ""
    roadmap_cmd = tool == "Bash" and _roadmap_command(command)
    if roadmap_cmd and _allowed_while_blocked(command):
        return None
    project = _project_quiet(payload, cwd)
    if project is None or _too_slow(clock, started):
        return None
    _touch_presence(project, now, clock, started)
    pid = project["id"]
    if not os.path.exists(control.sentinel_path(pid)):
        return None
    state = control.read_state(pid)
    if not state:
        return None
    reason = _deny_reason(state, payload, project, now)
    if roadmap_cmd:
        # a roadmap command outside the allowlist: denied while the project is stopped or blocked, or for the task
        # this agent runs; otherwise it passes
        if reason is None and not (state.get("stop") is True or isinstance(state.get("block"), dict)):
            return None
        reason = reason or _not_allowed_reason(command)
    if reason is not None and state.get("stop") is not True and isinstance(state.get("block"), dict):
        # a limit block can be stale (usage reset, override expired, budget raised): recompute before denying
        fresh = _refresh_limits(pid, now, clock, started)
        if fresh is None:
            return None
        state = fresh
        reason = _deny_reason(fresh, payload, project, now)
        if roadmap_cmd and reason is None and isinstance(fresh.get("block"), dict):
            reason = _not_allowed_reason(command)
    if reason is None or _too_slow(clock, started):
        return None
    _log_denial(pid, reason, now)
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": reason}}


def _touch_presence(project, now, clock, started):
    """Stamp that a session is open for this project (R7.1). Skipped when under PRESENCE_MIN_BUDGET_S of the hook
    budget is left; throttled inside presence; never raises or logs."""
    try:
        if PRE_TIMEOUT_S - (clock() - started) < PRESENCE_MIN_BUDGET_S:
            return
        presence.touch_hook(jobs.data_dir_of(project), now)
    except Exception:  # presence is advisory: a hook never fails because of it
        pass


def _not_allowed_reason(command):
    return "roadmap: " + " ".join(command.split()[1:2]) + " is not allowed while blocked" + TAIL


def _refresh_limits(pid, now, clock, started):
    """Recompute the control state of a project inside the rest of the 300 ms budget. Returns the fresh state, or None
    when the recompute fails or runs out of time: the call then fails open, and a stale sentinel is removed."""
    remaining = PRE_TIMEOUT_S - (clock() - started)
    moment = datetime.datetime.fromtimestamp(now).astimezone()
    try:
        if remaining <= 0:
            raise RoadmapError("locked", "no time left in the gate budget", EXIT_CONFLICT)
        with lock.timeout_scope(remaining):
            fresh = control.recompute(pid, moment, timeout=remaining)
    except Exception:
        _drop_sentinel(pid)
        return None
    return None if _too_slow(clock, started) else fresh


def _drop_sentinel(pid):
    try:
        os.remove(control.sentinel_path(pid))
    except OSError:
        pass


def _deny_reason(state, payload, project, now):
    """The one line that denies a tool call, or None when the state lets it run."""
    tail = ". Run roadmap inbox, then end your turn."
    if state.get("stop") is True:
        stamp = control.clock_text(state.get("stoppedAt"))
        ref = state.get("stopRef")
        return "roadmap: stopped by user" + (" at " + stamp if stamp else "") + (" (" + ref + ")" if ref else "") + tail
    stopped = state.get("stopTasks") or []
    if stopped:
        task = _task_of_agent(project, str(payload.get("agent_id") or ""))
        if task is not None and task in stopped:
            text = (state.get("taskBlocks") or {}).get(task) or "stopped"
            return "roadmap: task " + task + " " + str(text) + tail
    block = state.get("block")
    if isinstance(block, dict):
        until = control.parse_time(state.get("overrideUntil"))
        overridden = until is not None and until.timestamp() > now and block.get("overridable") is True
        if not overridden:
            return "roadmap: blocked: " + str(block.get("reason", "limit reached")) + tail
    return None


def _task_of_agent(project, agent_id):
    """The task of the job that runs this subagent, or None. The hook state maps agent ids to job ids."""
    if not agent_id:
        return None
    try:
        data, error = schema.read_data("hooks", paths.hooks_file(project["id"]))
        if error is not None or not data:
            return None
        wanted = {e.get("job") for e in data.get("active") or [] if isinstance(e, dict) and e.get("agent") == agent_id}
        if not wanted:
            return None
        for job in jobs.list_jobs(jobs.data_dir_of(project)):
            if job.get("id") in wanted:
                return job.get("task")
    except (RoadmapError, OSError, ValueError):
        return None
    return None


def _log_denial(pid, reason, now):
    """Log a denial, at most once a minute per project (the stamp file's mtime is the last log time)."""
    try:
        folder = paths.ensure_dir(paths.state_dir())
        stamp = os.path.join(folder, "deny-" + pid)
        last = os.path.getmtime(stamp) if os.path.exists(stamp) else 0.0
        if now - last < DENY_LOG_S:
            return
        with open(stamp, "a", encoding="utf-8"):
            pass
        os.utime(stamp, (now, now))
    except OSError:
        return
    _log("denied " + pid + ": " + reason)


def _session_start(project, data_dir, clock, started, now=None, panel=""):
    """Up to INBOX_LINES lines for the agent's context: the stop line first, then queued and answered items, then
    the head's line (HEAD-SPEC section 3) when the project captures."""
    lines = []
    try:
        state = control.read_state(project["id"])
    except RoadmapError:
        state = None
    if state and state.get("stop") is True:
        stamp = control.clock_text(state.get("stoppedAt"))
        lines.append("roadmap: stopped by user at " + stamp + ". Run roadmap inbox.")
    lines += control.pending_lines(data_dir, limit=INBOX_LINES - len(lines))
    head_lines = _head_session_lines(data_dir, now)
    panel_lines = panel.split("\n") if panel else []
    if not lines and not head_lines and not panel_lines:
        return None
    extra = _rule_lines(data_dir, _queued_task(data_dir), clock, started) if lines else []
    return {"hookSpecificOutput": {"hookEventName": "SessionStart",
                                   "additionalContext": "\n".join(lines[:INBOX_LINES] + extra + head_lines
                                                                  + panel_lines)}}


# ------------------------------------------------------------------ head capture: UserPromptSubmit (HEAD-SPEC section 3)

HEAD_MIN_WORDS = 4         # a prompt of 3 words or fewer is an ack and is not logged
HEAD_SKIP_PREFIXES = ("<task-notification", "<system-reminder", "<command-", "<bash-", "<local-command-")
HEAD_NOLOG = "//nolog"
HEAD_REPLY_CHARS = 120
HEAD_SESSION_CHARS = 120
HEAD_SESSION_ASKS = 3
_BARE_SLASH_RE = re.compile(r"/[A-Za-z0-9_:.-]+")


_MODEL_ID_RE = re.compile(r"^claude-(opus|sonnet|haiku)-(\d+)-(\d+)(?:-\d{8})?$")


def model_name(value):
    """A short model name from a hook payload 'model': a string, or an object with display_name or id. 'claude-sonnet-5-5'
    becomes 'Sonnet 5.5'. None when there is no name."""
    if isinstance(value, dict):
        value = value.get("display_name") or value.get("id")
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    match = _MODEL_ID_RE.match(text)
    if match:
        return "%s %s.%s" % (match.group(1).capitalize(), match.group(2), match.group(3))
    return text[:40]


TRANSCRIPT_TAIL_BYTES = 64 * 1024
TRANSCRIPT_TAIL_LINES = 50


def _session_model(payload):
    """The session's model as a job model word (haiku, sonnet, opus or head), or None when the hook does not know it or
    the word is not a job model."""
    name = model_name(payload.get("model")) or _transcript_model(payload.get("transcript_path"))
    word = str(name or "").split(" ")[0].lower()
    return word if word in jobs.MODELS else None


def _transcript_model(path):
    """The short name of the newest 'claude-' model in the Claude Code transcript at path, read from its last 64 KB and
    last 50 lines only. None when the path is not a file, the read fails, or no entry names a claude model. Fail-open."""
    try:
        if not isinstance(path, str) or not path.strip() or not os.path.isfile(path):
            return None
        size = os.path.getsize(path)
        with open(path, "rb") as fh:
            fh.seek(max(0, size - TRANSCRIPT_TAIL_BYTES))
            chunk = fh.read(TRANSCRIPT_TAIL_BYTES)
        lines = chunk.decode("utf-8", errors="ignore").splitlines()
        if size > TRANSCRIPT_TAIL_BYTES and lines:
            lines = lines[1:]  # the first line may start mid-entry
        for line in reversed(lines[-TRANSCRIPT_TAIL_LINES:]):
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if not isinstance(entry, dict):
                continue
            message = entry.get("message")
            names = [entry.get("model"), message.get("model") if isinstance(message, dict) else None]
            for name in names:
                if isinstance(name, str) and name.startswith("claude-"):
                    return model_name(name)
        return None
    except Exception:
        return None


def _head_claim(project, data_dir, payload, now, clock, started):
    """Record a 'claim' session record (which model works as head) when the project captures, the payload names a model,
    and the model or the session differs from the last claim of this project. Fail-open: it never raises and never
    blocks; a busy lock or a problem goes to the log."""
    try:
        model = model_name(payload.get("model")) or _transcript_model(payload.get("transcript_path"))
        if model is None or not _head_on(data_dir):
            return
        session_id = payload.get("session_id")
        key = head_svc.session_key(session_id)
        path = os.path.join(paths.state_dir(), "head-claim-%s.json" % project["id"])
        last = atomic.read_json(path, None) if os.path.exists(path) else None
        if isinstance(last, dict) and last.get("sid") == key and last.get("model") == model:
            return
        moment = datetime.datetime.fromtimestamp(now, datetime.timezone.utc)
        budget = max(0.0, (PRE_TIMEOUT_S - (clock() - started)) * 0.5)
        head_svc.session(data_dir, "claim", session_id=session_id, model=model, now=moment, timeout=budget)
        paths.ensure_dir(paths.state_dir())
        atomic.write_json(path, {"sid": key, "model": model})
    except RoadmapError as exc:
        _log("head.claim skipped: " + exc.code)
    except Exception as exc:
        _log("head.claim error " + type(exc).__name__)


def _head_config(data_dir):
    """The project's roadmap.config.json as a dict, or {} when it is missing or unreadable."""
    data, error = schema.read_data("roadmap_config", os.path.join(data_dir, "roadmap.config.json"))
    return data if error is None and isinstance(data, dict) else {}


def _head_on(data_dir):
    return _head_config(data_dir).get("headCapture") is True


# HEAD-SPEC section 13: the attachments named in a prompt (names and paths only, never read) and the reply of the turn.
_ASSET_URL_RE = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://\S+")
_ASSET_RE = re.compile(
    r"@(?P<at>[^\s@\"'`<>]+)"
    r"|(?P<path>(?:~|\.{1,2})?/[^\s\"'`<>()\[\]]+\.[A-Za-z][A-Za-z0-9]{0,7})"
    r"|(?<![\w/.@-])(?P<name>\w[\w.-]*\.(?:png|jpe?g|gif|webp|heic|bmp|svg|pdf|docx?|xlsx?|pptx?|csv|txt|md|json"
    r"|log|zip|py|js|ts|html?|css|ya?ml|toml))(?!\w)",
    re.IGNORECASE)
REPLY_TAIL_BYTES = 256 * 1024
REPLY_SLACK_S = 5   # the logged entry may be stamped a few seconds before the prompt's own transcript stamp


def prompt_assets(text):
    """The attachment names of a prompt, in order: @file references, absolute or relative paths with an extension and
    bare names of common file types. URLs are skipped. Names only; the file is never opened. Never raises."""
    try:
        if not isinstance(text, str):
            return []
        body = _ASSET_URL_RE.sub(" ", text)
        found = []
        for match in _ASSET_RE.finditer(body):
            value = match.group("at") or match.group("path") or match.group("name") or ""
            value = value.rstrip(".,;:!?)]}")
            if value:
                found.append(value)
        return head_svc.clean_assets(found)
    except Exception:
        return []


def _is_prompt(content):
    """True when a transcript user entry is a typed prompt: text, not only tool results."""
    if isinstance(content, str):
        return bool(content.strip())
    if isinstance(content, list):
        return any(isinstance(b, dict) and b.get("type") == "text" and str(b.get("text") or "").strip()
                   for b in content)
    return False


def _last_text(content):
    """The last non-empty text block of an assistant message, stripped, or None."""
    if isinstance(content, str):
        return content.strip() or None
    if not isinstance(content, list):
        return None
    texts = [b.get("text") for b in content if isinstance(b, dict) and b.get("type") == "text"]
    texts = [t.strip() for t in texts if isinstance(t, str) and t.strip()]
    return texts[-1] if texts else None


def _turn_reply(path):
    """(reply, prompt stamp) of the last turn in the transcript at path, read from its last 256 KB: the last assistant
    text after the last typed user message, and that message's timestamp text. (None, None) when either is not found
    inside the read. Fail-open: it never raises."""
    try:
        if not isinstance(path, str) or not path.strip() or not os.path.isfile(path):
            return None, None
        size = os.path.getsize(path)
        with open(path, "rb") as fh:
            fh.seek(max(0, size - REPLY_TAIL_BYTES))
            chunk = fh.read(REPLY_TAIL_BYTES)
        lines = chunk.decode("utf-8", errors="ignore").splitlines()
        if size > REPLY_TAIL_BYTES and lines:
            lines = lines[1:]  # the first line may start mid-entry
        reply = None
        for line in reversed(lines):
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if not isinstance(entry, dict):
                continue
            message = entry.get("message") if isinstance(entry.get("message"), dict) else {}
            if entry.get("type") == "user":
                if not entry.get("isMeta") and _is_prompt(message.get("content")):
                    return reply, entry.get("timestamp")
                continue
            if entry.get("type") == "assistant" and reply is None:
                reply = _last_text(message.get("content"))
        return None, None
    except Exception:
        return None, None


def _head_reply_capture(payload, data_dir, now, clock, started):
    """Store the reply of the turn on the newest entry of this session (HEAD-SPEC section 13), when that entry was
    logged at or after the turn's prompt and has no reply yet (the first Stop after the prompt wins). Off unless the
    project captures. Fail-open: a busy lock or a problem goes to
    the log and the Stop hook carries on."""
    try:
        if not _head_on(data_dir):
            return
        reply, stamp = _turn_reply(payload.get("transcript_path"))
        if reply is None or not isinstance(stamp, str):
            return
        prompt_at = head_core.parse_ts(stamp[:19] + "Z")
        entry = head_svc.latest_hook_entry(data_dir, payload.get("session_id"))
        logged_at = head_core.parse_ts(entry.get("ts")) if entry else None
        if prompt_at is None or logged_at is None or logged_at < prompt_at - datetime.timedelta(seconds=REPLY_SLACK_S):
            return
        if head_svc.details_of(data_dir, entry["id"])["reply"] is not None:
            # The person's answer is already stored: a later Stop of this session (a background turn such as a task
            # notification, which has no new prompt) must not overwrite it.
            return
        budget = max(0.0, (PRE_TIMEOUT_S - (clock() - started)) * 0.5)
        head_svc.set_reply(data_dir, entry["id"], reply, timeout=budget)
    except RoadmapError as exc:
        _log("head.reply skipped: " + exc.code)
    except Exception as exc:
        _log("head.reply error " + type(exc).__name__)


def _user_prompt(payload, environ, cwd, now, clock, started):
    """The prompt's reply: the person's unseen board actions (R11.2) first, then the triage line of the capture."""
    project = _project_for(payload, environ, cwd)
    if project is None:
        return None
    data_dir = jobs.data_dir_of(project)
    if not os.path.isdir(data_dir):
        return None
    _head_claim(project, data_dir, payload, now, clock, started)
    panel = _panel_text(data_dir, payload, "prompt", now, clock, started)
    reply = _prompt_capture(payload, data_dir, now, clock, started)
    text = "\n".join(part for part in (panel, reply) if part)
    if not text:
        return None
    return {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": text}}


def _prompt_capture(payload, data_dir, now, clock, started):
    """Log the prompt for the head and return one triage line, or None. Off unless the project sets headCapture.
    Fail-open: it never blocks the prompt, and the lock wait is a share of what is left of the 0.3 s budget (a busy
    lock spools)."""
    if not _head_on(data_dir):
        return None
    text = payload.get("prompt")
    if not isinstance(text, str):
        _log("skip: head prompt is not text")
        return None
    stripped = text.strip()
    session = payload.get("session_id")
    moment = datetime.datetime.fromtimestamp(now, datetime.timezone.utc)
    if not stripped or stripped.startswith(HEAD_NOLOG) or stripped.startswith(HEAD_SKIP_PREFIXES):
        return None
    budget = max(0.0, (PRE_TIMEOUT_S - (clock() - started)) * 0.5)
    if _BARE_SLASH_RE.fullmatch(stripped):
        try:
            head_svc.session(data_dir, "start", session_id=session, now=moment, timeout=budget)
        except RoadmapError as exc:
            _log("head.session skipped: " + exc.code)
        return None
    if len(stripped.split()) < HEAD_MIN_WORDS:
        return None
    try:
        result = head_svc.capture(data_dir, text, session_id=session, src="hook", assets=prompt_assets(text),
                                  now=moment, timeout=budget)
    except RoadmapError as exc:
        _log("head.capture skipped: " + exc.code)
        return None
    _log("head.capture %s %s len=%d" % (result["id"] or "spooled", result["kind"], result["len"]))
    hint = _head_config(data_dir).get("head")
    if isinstance(hint, dict) and hint.get("hint") is False:
        return None
    untriaged = 0 if _too_slow(clock, started) else _untriaged(data_dir, moment, result["id"])
    return _head_reply(result, untriaged)


def _untriaged(data_dir, moment, own):
    """How many other entries wait for triage (new or understood). Never raises."""
    try:
        rows = head_svc.rows(data_dir, now=moment)
    except Exception:
        return 0
    return sum(1 for r in rows if r["status"] in ("new", "understood") and r["id"] != own)


def _head_reply(result, untriaged):
    """The one reply line, at most HEAD_REPLY_CHARS: the id, the guessed kind and the triage command."""
    kind = str(result["kind"])
    eid = result["id"]
    if eid is None:
        return "head: queued (%s), logged on the next head write." % kind
    lead = "head: logged %s (%s). triage: roadmap head t %s %s " % (eid, kind, eid, kind.rstrip("?"))
    tail = " · %d untriaged" % untriaged if untriaged else ""
    room = HEAD_REPLY_CHARS - len(lead) - len(tail)
    # the summary is text from the prompt: it is shell-quoted, so a hint the agent copies can never run it
    cut = " ".join(str(result["sum"]).split())[:max(0, room)]
    while cut and len(shlex.quote(cut)) > room:
        cut = cut[:-1]
    return (lead + (shlex.quote(cut) if cut else "''") + tail)[:HEAD_REPLY_CHARS]


def _head_session_lines(data_dir, now=None):
    """At most one SessionStart line: the open asks (oldest first, with their age) and the needs-you count. Empty
    unless the project captures. Never raises."""
    try:
        if not _head_on(data_dir):
            return []
        moment = datetime.datetime.fromtimestamp(time.time() if now is None else now, datetime.timezone.utc)
        items = head_svc.rows(data_dir, now=moment)
    except Exception:
        return []
    open_rows = [r for r in items if r["status"] not in head_core.CLOSED_STATUSES]
    asks = sorted((r for r in open_rows if r["status"] != "needs-you"
                   and str(r["kind"]).rstrip("?") not in ("decision", "rule")), key=lambda r: str(r["ts"]))
    needs = [r for r in open_rows if r["status"] == "needs-you"]
    if not asks and not needs:
        return []
    segments = []
    if asks:
        names = [r["id"] + ((" " + _short_age(r["age_min"])) if r.get("age_min") is not None else "")
                 for r in asks[:HEAD_SESSION_ASKS]]
        more = " …" if len(asks) > HEAD_SESSION_ASKS else ""
        segments.append("%d open asks (%s%s)" % (len(asks), ", ".join(names), more))
    if needs:
        segments.append("%d needs-you" % len(needs))
    line = "head: " + ", ".join(segments) + ". Run roadmap head brief."
    return [line[:HEAD_SESSION_CHARS]]


def _short_age(minutes):
    minutes = max(0, int(minutes))
    if minutes < 60:
        return "%dm" % minutes
    if minutes < 1440:
        return "%dh" % (minutes // 60)
    return "%dd" % (minutes // 1440)


def _stop_pickup(payload, project, data_dir, now, clock=time.monotonic, started=None):
    """Stop hook: surface one queued start request as decision block, once per request and 3 times per session.
    The cap also counts per queued task set in the control state, so a new session id or a deleted pickup file does
    not reset it. Off with pickupOnStop false in the project config. Never while the project is stopped or blocked."""
    if payload.get("stop_hook_active"):  # any truthy value: this Stop already continues a block
        return None
    config_data, error = schema.read_data("roadmap_config", os.path.join(data_dir, "roadmap.config.json"))
    if error is not None or (config_data or {}).get("pickupOnStop") is False:
        return None
    pid = project["id"]
    state = control.read_state(pid)
    if state and (state.get("stop") is True or state.get("block")):
        return None
    moment = datetime.datetime.fromtimestamp(now).astimezone()
    entries = queue_service.list_queue(data_dir)
    if not entries:
        if control.pickup_record(pid):
            _quiet(control.clear_pickup, pid, moment, timeout=HOOK_LOCK_TIMEOUT_S)
        return None
    key = _task_set_key(entries)
    recorded = control.pickup_record(pid)
    if recorded.get("key") == key and recorded.get("blocks", 0) >= PICKUP_PER_SESSION:
        return None
    folder = paths.ensure_dir(paths.state_dir())
    path = os.path.join(folder, "pickup-" + pid + ".json")
    session = str(payload.get("session_id") or "")
    try:
        # the state folder is one lock: the file is read under it, the count is recorded (its own lock) outside it,
        # and only then is the file written
        with lock.locked(folder, timeout=HOOK_LOCK_TIMEOUT_S):
            saved = atomic.read_json(path, default={}) if os.path.exists(path) else {}
            if not isinstance(saved, dict):
                saved = {}
            surfaced = saved.get("surfaced") if isinstance(saved.get("surfaced"), dict) else {}
            sessions = saved.get("sessions") if isinstance(saved.get("sessions"), dict) else {}
            if int(sessions.get(session, 0)) >= PICKUP_PER_SESSION:
                return None
            pending = [e for e in entries if _request_key(e) not in surfaced]
            if not pending:
                return None
            entry = pending[0]
        # the count is recorded first: if it cannot be saved, nothing is blocked
        control.record_pickup(pid, key, moment, timeout=HOOK_LOCK_TIMEOUT_S)
        with lock.locked(folder, timeout=HOOK_LOCK_TIMEOUT_S):
            saved = atomic.read_json(path, default={}) if os.path.exists(path) else {}
            if not isinstance(saved, dict):
                saved = {}
            surfaced = saved.get("surfaced") if isinstance(saved.get("surfaced"), dict) else {}
            sessions = saved.get("sessions") if isinstance(saved.get("sessions"), dict) else {}
            surfaced[_request_key(entry)] = session
            sessions[session] = int(sessions.get(session, 0)) + 1
            atomic.write_json(path, {"surfaced": surfaced, "sessions": sessions})
    except (RoadmapError, ValueError, TypeError, OSError):
        return None
    _log("pickup " + str(entry.get("task")))
    task = str(entry.get("task"))
    reason = "roadmap: queued request " + task + " is waiting; run roadmap inbox and start it."
    extra = _rule_lines(data_dir, task, clock, time.monotonic() if started is None else started)
    if extra:
        reason += "\n" + "\n".join(extra)
    return {"decision": "block", "reason": reason}


GATE_GIT_S = 2  # each git read in the gate: the Stop hook stays well inside its budget


def _stop_gate(payload, project, data_dir, now):
    """Stop hook, autopilot gate (HEAD-SPEC section 11, H12): when the head tries to end its turn and the gate has
    continue items, block once with them. Off with head.gate false, while paused (head-pause file or a stop in the
    control state), at a usage stop, and at most once per head_svc.GATE_WINDOW_S. A stop_hook_active Stop is never
    blocked again. Fail-open: any error returns None."""
    try:
        if payload.get("stop_hook_active") or not _head_on(data_dir):  # the gate is part of head capture
            return None
        cfg = _head_config(data_dir).get("head")
        if isinstance(cfg, dict) and cfg.get("gate") is False:
            return None
        stamp = os.path.join(data_dir, head_svc.GATE_STAMP_FILE)
        saved = atomic.read_json(stamp, default={}) if os.path.exists(stamp) else {}
        last = saved.get("at") if isinstance(saved, dict) else None
        if isinstance(last, (int, float)) and 0 <= now - last < head_svc.GATE_WINDOW_S:
            return None
        state = control.read_state(project["id"]) or {}
        paused = (os.path.exists(os.path.join(data_dir, head_svc.GATE_PAUSE_FILE)) or state.get("stop") is True)
        if paused:
            return None
        moment = datetime.datetime.fromtimestamp(now, datetime.timezone.utc)
        rows = head_svc.rows(data_dir, now=moment)
        queue = [e.get("task") for e in queue_service.list_queue(data_dir)]
        running = [j for j in jobs.list_jobs(data_dir) if j.get("status") == "running"]
        dirty, unpushed = _git_counts(project["path"])
        data, error = schema.read_data("usage", paths.usage_file())
        usage = data if error is None and isinstance(data, dict) else None
        items = head_svc.gate(rows, queue=queue, running=running, dirty=dirty, unpushed=unpushed, usage=usage,
                              now=moment)
        idle = "" if head_svc._at_stop(usage) else _idle_text(data_dir, rows, running, moment)
        from roadmap.services import usage as usage_svc  # local, as in _usage_auto
        asked = usage_svc.refresh_requested(moment)  # a manual sync asked for a fresh usage reading
        if not items and not idle and not asked:
            return None
        atomic.write_json(stamp, {"at": now})
    except Exception as exc:  # fail open: the reason is logged by type only
        _log("gate skipped: " + type(exc).__name__)
        return None
    _log("gate block " + str(len(items)) + " items" + (" idle" if idle else ""))
    head_text = "roadmap head: continue with: " + "; ".join(items) if items else ""
    refresh = "usage refresh requested" if asked else ""
    return {"decision": "block",
            "reason": " ".join(part for part in (idle, head_text, refresh, _stops_line()) if part)}


def _stops_line():
    """The usage line of the head brief when a stop is set: 'usage: 5h 49% / stop 50% | W 20% / stop off' (R11.126)."""
    try:
        from roadmap.services import limits_v2
        if not any(info["on"] for info in limits_v2.load().values()):
            return ""
        return "usage: " + limits_v2.brief_line()
    except Exception:  # best effort: the brief must go out without it
        return ""


def _idle_text(data_dir, rows, running, moment):
    """The idle alert (R7.89): with no job running, 'idle: 0 running, N free tasks; launch now: <top 3 ids>', or ''.
    Free tasks are the todo tasks of tasks.json that no running job holds: the ones bound to an open head ask come
    first, then the todo tasks of the current phase (the phase of the newest job, else of the first todo task). Never
    raises: a problem gives ''."""
    if running:
        return ""
    try:
        tasks = [t for t in jobs.task_records(data_dir) if t.get("id")]
        jobs_list = jobs.list_jobs(data_dir)
    except (RoadmapError, OSError, ValueError):
        return ""
    todo = [t for t in tasks if t.get("status") == "todo"]
    if not todo:
        return ""
    ask_tasks = set()
    for row in rows or []:
        if row.get("status") not in head_svc.GATE_OPEN:
            continue
        for ref in row.get("links") or []:
            link = head_core.parse_link(ref)
            if link is not None and link[0] == "task":
                ask_tasks.add(link[1])
    phase = None
    for job in jobs_list:  # file order: the last job with a task names the current phase
        if job.get("task"):
            phase = next((t.get("phase") for t in tasks if t.get("id") == job["task"]), None)
    if phase is None:
        phase = todo[0].get("phase")
    ranked = [str(t["id"]) for t in todo if str(t["id"]) in ask_tasks]
    ranked += [str(t["id"]) for t in todo if t.get("phase") == phase and str(t["id"]) not in ranked]
    if not ranked:
        return ""
    return "idle: 0 running, %d free tasks; launch now: %s." % (len(ranked), ", ".join(ranked[:IDLE_LAUNCH_N]))


def _git_counts(folder):
    """(uncommitted entries, unpushed commits), None for a count git cannot give. Read-only git with a short timeout."""
    dirty = unpushed = None
    try:
        dirty = len([line for line in git.run(folder, ["status", "--porcelain"], timeout=GATE_GIT_S).splitlines()
                     if line.strip()])
    except RoadmapError:
        dirty = None
    try:
        unpushed = int(git.run(folder, ["rev-list", "--count", "@{u}..HEAD"], timeout=GATE_GIT_S).strip() or 0)
    except (RoadmapError, ValueError):
        unpushed = None
    return dirty, unpushed


def _queued_task(data_dir):
    """The task of the oldest queued start request, or None."""
    try:
        entries = queue_service.list_queue(data_dir)
    except (RoadmapError, OSError, ValueError):
        return None
    return str(entries[0].get("task")) if entries else None


def _rule_lines(data_dir, task, clock, started):
    """The `rule:` lines (rules show for the lead, at most 12) and the `done:` lines (the task's definition of done)
    for a task, with secrets redacted and at most RULE_CHARS characters in all. Fail-open: a missing task, an error
    in the rules file, or a read that runs past the 300 ms budget gives no lines, and the pickup is still surfaced.
    The read runs in a daemon thread, so a slow read cannot hold the hook past its budget."""
    if not task:
        return []
    remaining = PRE_TIMEOUT_S - (clock() - started)
    if remaining <= 0:
        return []
    box = {}

    def read_rules():
        try:
            box["lines"] = _task_rule_lines(data_dir, task)
        except Exception as exc:  # the hook fails open: the reason is logged by type only
            box["error"] = type(exc).__name__

    worker = threading.Thread(target=read_rules, daemon=True)
    worker.start()
    worker.join(remaining)
    if worker.is_alive() or "lines" not in box:
        _log("rules omitted for " + task + ": " + ("timeout" if worker.is_alive() else box.get("error", "error")))
        return []
    return _capped(box["lines"], RULE_CHARS)


def _task_rule_lines(data_dir, task):
    shown = rules.show(data_dir, task_id=task, role="lead")
    lead = [line for line in shown if line.split(" ", 3)[2:3] != ["done"]]
    _, all_rules, _ = rules.read(data_dir)
    phase = rules._phase_of(data_dir, task)
    done = [rules.format_rule(r) for r in all_rules
            if r["kind"] == "done" and rules.applies(r, task, phase, None, "lead")]
    return ["rule: " + line for line in lead] + ["done: " + line for line in done]


def _capped(lines, limit):
    """Redacted, one-line entries kept in order while they fit in limit characters (newlines included)."""
    out = []
    used = 0
    for line in lines:
        clean = _SECRET_RE.sub("[redacted]", roadmap_log.redact(_squash(line)).strip())
        if used + len(clean) + 1 > limit:
            break
        out.append(clean)
        used += len(clean) + 1
    return out


def _task_set_key(entries):
    """A short hash of the queued task ids (not their times): the key the Stop pickup count is kept under."""
    names = "\n".join(sorted(str(e.get("task")) for e in entries))
    return hashlib.sha256(names.encode("utf-8")).hexdigest()[:16]


def _quiet(func, *args, **kwargs):
    """Run a best-effort control write; a failure is logged by type only."""
    try:
        func(*args, **kwargs)
    except Exception as exc:
        _log("pickup count not cleared: " + type(exc).__name__)


def _request_key(entry):
    return str(entry.get("task")) + "@" + str(entry.get("at"))


def _verdict_of(now):
    """The function that asks each active entry's detector whether its job is finished (or failed)."""
    def verdict(entry):
        detector = DETECTORS.get(entry.get("detector"))
        return detector.reap(entry, now) if detector is not None else None
    return verdict


def _project_for(payload, environ, cwd):
    here = payload.get("cwd")
    here = here if isinstance(here, str) and here else cwd
    try:
        return jobs.resolve_project(None, environ, here)
    except RoadmapError as exc:
        _log("skip: " + exc.message)
        return None


def _parse_time(value):
    """The epoch seconds of an ISO time stamp, or None when it does not parse."""
    try:
        return datetime.datetime.fromisoformat(str(value)).timestamp()
    except (TypeError, ValueError):
        return None


def _agent_fallback_task(data_dir, known, now):
    """The task of an agent job that names none in its description or prompt (A5): the task of the newest running job
    the head started in the last hour, else AGENT_FALLBACK_TASK (logged as a warning). Returns None only when the
    fallback task is not in tasks.json; the job is then registered with no task rather than dropped."""
    try:
        records = jobs.list_jobs(data_dir)
    except RoadmapError:
        records = []
    best = None
    best_at = None
    for job in records:
        if job.get("status") != "running" or job.get("task") not in known:
            continue
        if job.get("model") != "head" and job.get("role") != "lead":
            continue
        at = _parse_time(job.get("started"))
        if at is None or not 0 <= now - at <= HEAD_JOB_WINDOW_S:
            continue
        if best_at is None or at >= best_at:  # a tie (same second) goes to the later job in the file
            best, best_at = job, at
    if best is not None:
        return best["task"]
    _log("warning: agent job names no task; bound to fallback " + AGENT_FALLBACK_TASK)
    return AGENT_FALLBACK_TASK if AGENT_FALLBACK_TASK in known else None


def _adoptable(data_dir, task, owned):
    """R11.144: the newest running job of this task that the hook does not own (a manual `job start`), or None. An
    Agent call adopts it instead of starting a duplicate, so SubagentStop closes it with measured tokens and the head
    has no second step to forget."""
    if not task:
        return None
    try:
        rows = [j for j in jobs.list_jobs(data_dir)
                if j.get("status") == "running" and j.get("task") == task and j.get("id") not in owned
                and j.get("model") != "head"]
    except (RoadmapError, OSError, ValueError):
        return None
    return rows[-1] if rows else None


def orphan_jobs(data_dir, owned, now, min_age_s=ORPHAN_AGE_S):
    """R11.144: running jobs no hook entry owns (manual `job start` with no Agent call adopting them) older than
    min_age_s: either never dispatched or never closed. [(id, task, minutes)]. Never raises."""
    out = []
    try:
        for j in jobs.list_jobs(data_dir):
            if j.get("status") != "running" or j.get("id") in owned:
                continue
            at = _parse_time(j.get("started"))
            if at is None:
                continue
            age = now - at
            if age >= min_age_s:
                out.append((j.get("id"), j.get("task") or "-", int(age // 60)))
    except Exception:
        return []
    return out


def _orphan_text(project, data_dir, now):
    """Stop-hook line naming orphan jobs, or ''."""
    try:
        with lock.locked(paths.state_dir(), timeout=HOOK_LOCK_TIMEOUT_S):
            owned = {e.get("job") for e in _read_state(paths.hooks_file(project["id"]))["active"]}
    except Exception:
        return ""
    rows = orphan_jobs(data_dir, owned, now)
    if not rows:
        return ""
    names = ", ".join("%s %s %dm" % r for r in rows[:6])
    return ("roadmap: %d job(s) running with no agent behind them: %s. Launch the Agent now (prefix its description "
            "with the task id so it adopts the job) or close it: bin/roadmap job done <id>." % (len(rows), names))


def _start(data_dir, detector, entry, regex, known, now, owned=frozenset()):
    """Register a job for a detected start when the text names a known task. An agent job that names none still gets
    a task (_agent_fallback_task). Returns the new state entry, or None. A busy project lock raises locked, so nothing
    is registered and the caller returns silently."""
    task = find_task(entry["text"], regex, known)
    title = entry["title"][:120]
    if task is None and detector.name == "agent":
        task = _agent_fallback_task(data_dir, known, now)
    if task is None and detector.name != "agent":
        _log("skip (no task id) from detector " + detector.name)
        return None
    adopted = _adoptable(data_dir, task, owned) if detector.name == "agent" else None
    try:
        job = adopted or jobs.start_job(data_dir, title, entry["model"], task, effort=entry.get("effort") or None,
                                        engine_model=entry.get("engine_model"))
    except RoadmapError as exc:
        if exc.code == "locked":
            raise
        _log("skip: " + exc.message)
        return None
    _log("%s %s %s task %s" % ("adopt" if adopted else "start", job["id"], detector.name, task))
    return {"job": job["id"], "detector": detector.name, "kind": entry["kind"], "agent": entry["agent"],
            "watch": entry["watch"], "started": now, "task": task, "title": title, "model": entry["model"]}


def _agents_map_read(data_dir):
    """The agents map (agentId -> {task, title, model}) of the data folder. {} when it is missing or not an object."""
    path = os.path.join(data_dir, AGENTS_MAP_FILE)
    if not os.path.exists(path):
        return {}
    data = atomic.read_json(path, default={})
    return data if isinstance(data, dict) else {}


def _remember_agent(data_dir, entry):
    """Store the agent job of a new Agent start under its agentId (newest AGENTS_MAP_MAX kept, insertion order). A busy
    lock or a problem goes to the log: the job itself is already registered."""
    try:
        info = {"task": entry.get("task"), "title": entry.get("title"), "model": entry.get("model")}
        with lock.locked(data_dir, timeout=HOOK_LOCK_TIMEOUT_S):
            mapping = _agents_map_read(data_dir)
            mapping.pop(entry["agent"], None)
            mapping[entry["agent"]] = info
            keep = list(mapping.items())[-AGENTS_MAP_MAX:]
            atomic.write_json(os.path.join(data_dir, AGENTS_MAP_FILE), dict(keep))
    except RoadmapError as exc:
        _log("agents map skipped: " + exc.code)
    except Exception as exc:
        _log("agents map error " + type(exc).__name__)


def _followup_start(data_dir, tool_input, now):
    """A SendMessage whose 'to' names an agent in the agents map starts a job "<model>: <task> follow-up" bound to that
    agent's task (R7.89). Returns the state entry, or None (unknown target, no task, or a failed start). A busy lock
    raises locked, so the caller's event is retried by a later one."""
    target = str(tool_input.get("to") or "").strip()
    info = _agents_map_read(data_dir).get(target) if target else None
    if not isinstance(info, dict) or not info.get("task"):
        return None
    model = str(info.get("model") or "unknown")
    task = str(info["task"])
    title = model + ": " + task + " follow-up"
    try:
        job = jobs.start_job(data_dir, title, model, task)
    except RoadmapError as exc:
        if exc.code == "locked":
            raise
        _log("skip follow-up: " + exc.message)
        return None
    _log("start %s followup task %s" % (job["id"], task))
    return {"job": job["id"], "detector": "followup", "kind": "followup", "agent": target, "watch": "", "started": now}


_GIT_COMMIT_RE = re.compile(r"\bgit\s+commit\b")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _commit_candidates(project, data_dir, payload, tool_input, now):
    """After a Bash git commit, bind HEAD to the tasks its message names (commit:<sha>) and log each done candidate.
    A failed commit re-reads the old HEAD, which binds nothing new. Returns the bound task ids."""
    command = str(tool_input.get("command") or "")
    if not _GIT_COMMIT_RE.search(command):
        return []
    here = payload.get("cwd")
    here = here if isinstance(here, str) and here else project["path"]
    try:
        out = git.run(here, ["log", "-1", "--format=%H%n%B"])
    except RoadmapError:
        return []
    sha, _, body = out.partition("\n")
    sha = sha.strip()
    if not _SHA_RE.match(sha):
        return []
    from roadmap.services import gitops  # local: gitops is the commit op and imports jobs and head too
    try:
        bound = gitops.bind_message_commit(data_dir, sha, body)
    except RoadmapError as exc:
        if exc.code == "locked":
            raise
        _log("commit detect: " + exc.message)
        return []
    for task in bound:
        _log("done candidate: " + task + " " + sha[:7])
    return bound


def _close_some(data_dir, entries, verdict):
    """Close each entry whose verdict gives a status ("done" or "failed"). Returns the job ids closed. Stops at the
    first busy project lock, so one event never waits on many locks in a row."""
    closed = []
    for entry in entries:
        status = verdict(entry)
        if status is None:
            continue
        if not _close(data_dir, entry, status):
            break
        closed.append(entry["job"])
    return closed


def _close(data_dir, entry, status):
    """Finish the job of a state entry. Returns False when the project lock is busy (the entry stays in the state),
    otherwise True: the entry may be dropped from the state."""
    try:
        jobs.finish_job(data_dir, entry["job"], status)
    except RoadmapError as exc:
        if exc.code == "locked":
            return False  # try again on the next event
        _log("drop " + str(entry.get("job")) + ": " + exc.message)
        return True  # the job is gone, or it was finished by hand
    _log(("fail " if status == "failed" else "done ") + entry["job"])
    return True


def _read_state(path):
    data, error = schema.read_data("hooks", path)
    if error is not None:
        raise RoadmapError("newer_schema", error["message"], EXIT_INVALID_DATA)
    if data is None:
        return {"active": []}
    active = data.get("active")
    if not isinstance(active, list):
        raise RoadmapError("invalid_data", "hook state has no 'active' list; fix or remove it: " + path,
                           EXIT_INVALID_DATA)
    return {"active": [e for e in active if isinstance(e, dict)]}


def _write_state(path, project_id, state):
    """Save the state atomically at the current schema. The caller holds the state directory lock."""
    schema.write_data("hooks", path, {"project": project_id, "active": state["active"]})


USAGE_EVENTS = ("UserPromptSubmit", "Stop", "PostToolUse", "SessionStart")


def _usage_auto(payload, now):
    """Keep account usage current with no manual step (R7.77): a rate_limits block in the payload, else a fresh status
    line sidecar, is stored at most once a minute (services/usage.auto_update). Never fails the hook."""
    from roadmap.services import usage as usage_svc
    try:
        moment = datetime.datetime.fromtimestamp(now).astimezone()
        source = usage_svc.auto_update(payload, moment)
        if source:
            _log("usage updated from " + source)
    except Exception as exc:  # usage is best effort; the hook's own work must go on
        _log("usage skip: " + type(exc).__name__)


def _log(message):
    """Append one line to hooks.log in the logs directory. Logging never raises."""
    try:
        folder = paths.ensure_dir(paths.logs_dir())
        line = time.strftime("%Y-%m-%dT%H:%M:%S ") + message.replace("\n", " ")[:500] + "\n"
        fd = os.open(os.path.join(folder, LOG_FILE), os.O_WRONLY | os.O_APPEND | os.O_CREAT, paths.FILE_MODE)
        try:
            os.write(fd, line.encode("utf-8"))
        finally:
            os.close(fd)
    except Exception:  # the log itself must never break a hook
        pass
