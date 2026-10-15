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
import threading
import time

from roadmap import log as roadmap_log
from roadmap.core import head as head_core
from roadmap.errors import EXIT_CONFLICT, EXIT_INVALID_DATA, RoadmapError
from roadmap.services import control, git, jobs, presence, rules
from roadmap.services import head as head_svc
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

    def on_tool(self, tool, tool_input, tool_response):
        if tool not in ("Agent", "Task"):
            return None
        text = _response_text(tool_response).replace("\n", " ")
        agent = _AGENT_ID_RE.search(text)
        output = _OUTPUT_RE.search(text)
        model = str(tool_input.get("model") or "haiku")
        description = str(tool_input.get("description") or "")
        prompt = str(tool_input.get("prompt") or "")
        return {
            "title": model + ": " + _summary(description),
            "model": model,
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

    def on_tool(self, tool, tool_input, tool_response):
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

    def on_tool(self, tool, tool_input, tool_response):
        if tool != "Bash":
            return None
        cmd = str(tool_input.get("command") or "")
        invocation = _cursor_invocation(cmd)
        if invocation is None:
            return None
        output, prompt = invocation
        label = _summary(prompt, 70) if prompt else os.path.basename(output)
        return {"title": "Cursor Auto: " + label, "model": "cursor", "text": cmd, "kind": "file",
                "watch": output, "agent": ""}


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


DETECTORS = {d.name: d for d in (AgentDetector(), AgyDetector(), CursorDetector())}


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
        return _session_start(project, data_dir, clock, started, now)
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
        return _stop_pickup(payload, project, data_dir, now, clock, started) or _stop_gate(payload, project, data_dir,
                                                                                         now)
    return None


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
                for detector in active:
                    entry = detector.on_tool(tool, tool_input, payload.get("tool_response"))
                    if entry is not None:
                        new = _start(data_dir, detector, entry, regex, known, now)
                        if new is not None:
                            started.append(new)
            elif event == "SubagentStop":
                agent_id = str(payload.get("agent_id") or "")
                if agent_id:
                    closed += _close_some(data_dir, snapshot,
                                          lambda e: "done" if e.get("agent") == agent_id else None)
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


def _session_start(project, data_dir, clock, started, now=None):
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
    if not lines and not head_lines:
        return None
    extra = _rule_lines(data_dir, _queued_task(data_dir), clock, started) if lines else []
    return {"hookSpecificOutput": {"hookEventName": "SessionStart",
                                   "additionalContext": "\n".join(lines[:INBOX_LINES] + extra + head_lines)}}


# ------------------------------------------------------------------ head capture: UserPromptSubmit (HEAD-SPEC section 3)

HEAD_MIN_WORDS = 4         # a prompt of 3 words or fewer is an ack and is not logged
HEAD_SKIP_PREFIXES = ("<task-notification", "<system-reminder", "<command-")
HEAD_NOLOG = "//nolog"
HEAD_REPLY_CHARS = 120
HEAD_SESSION_CHARS = 120
HEAD_SESSION_ASKS = 3
_BARE_SLASH_RE = re.compile(r"/[A-Za-z0-9_:.-]+")


def _head_config(data_dir):
    """The project's roadmap.config.json as a dict, or {} when it is missing or unreadable."""
    data, error = schema.read_data("roadmap_config", os.path.join(data_dir, "roadmap.config.json"))
    return data if error is None and isinstance(data, dict) else {}


def _head_on(data_dir):
    return _head_config(data_dir).get("headCapture") is True


def _user_prompt(payload, environ, cwd, now, clock, started):
    """Log the prompt for the head and reply with one triage line. Off unless the project sets headCapture. Fail-open:
    it never blocks the prompt, and the lock wait is a share of what is left of the 0.3 s budget (a busy lock spools)."""
    project = _project_for(payload, environ, cwd)
    if project is None:
        return None
    data_dir = jobs.data_dir_of(project)
    if not os.path.isdir(data_dir) or not _head_on(data_dir):
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
        result = head_svc.capture(data_dir, text, session_id=session, src="hook", now=moment, timeout=budget)
    except RoadmapError as exc:
        _log("head.capture skipped: " + exc.code)
        return None
    _log("head.capture %s %s len=%d" % (result["id"] or "spooled", result["kind"], result["len"]))
    hint = _head_config(data_dir).get("head")
    if isinstance(hint, dict) and hint.get("hint") is False:
        return None
    untriaged = 0 if _too_slow(clock, started) else _untriaged(data_dir, moment, result["id"])
    reply = _head_reply(result, untriaged)
    return {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": reply}}


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
    lead = 'head: logged %s (%s). triage: roadmap head t %s %s "' % (eid, kind, eid, kind.rstrip("?"))
    tail = '"' + (" · %d untriaged" % untriaged if untriaged else "")
    room = HEAD_REPLY_CHARS - len(lead) - len(tail)
    return (lead + str(result["sum"])[:max(0, room)] + tail)[:HEAD_REPLY_CHARS]


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
        if not items:
            return None
        atomic.write_json(stamp, {"at": now})
    except Exception as exc:  # fail open: the reason is logged by type only
        _log("gate skipped: " + type(exc).__name__)
        return None
    _log("gate block " + str(len(items)) + " items")
    return {"decision": "block", "reason": "roadmap head: continue with: " + "; ".join(items)}


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


def _start(data_dir, detector, entry, regex, known, now):
    """Register a job for a detected start when the text names a known task. Returns the new state entry, or None.
    A busy project lock raises locked, so nothing is registered and the caller returns silently."""
    task = find_task(entry["text"], regex, known)
    title = entry["title"][:120]
    if task is None:
        _log("skip (no task id) from detector " + detector.name)
        return None
    try:
        job = jobs.start_job(data_dir, title, entry["model"], task)
    except RoadmapError as exc:
        if exc.code == "locked":
            raise
        _log("skip: " + exc.message)
        return None
    _log("start %s %s task %s" % (job["id"], detector.name, task))
    return {"job": job["id"], "detector": detector.name, "kind": entry["kind"], "agent": entry["agent"],
            "watch": entry["watch"], "started": now}


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
