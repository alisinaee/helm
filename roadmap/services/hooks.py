"""Hook driver: turns Claude Code hook events into job starts and closes. Ported from split-net's jobs_auto.py.

Events: PostToolUse (Agent, Task, Bash) registers jobs; SubagentStop closes the job of that agent; every event
reaps jobs whose work has finished. Detectors are a registry (DETECTORS): agent, agy and cursor. A project picks
its detectors with "hookDetectors" in its roadmap.config.json. The state of each project (active jobs and the
detector that started each) is hooks-<project>.json in the state directory. Every problem goes to hooks.log.
run_hook never raises: a hook must never fail a tool call.
"""

import json
import os
import re
import time

from roadmap.errors import EXIT_INVALID_DATA, RoadmapError
from roadmap.services import control, jobs
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
_QUOTED_PROMPT_RE = re.compile(r"""\s+(?:"((?:[^"\\]|\\.)*)"|'([^']*)')""")
_OPERATOR_RE = re.compile(r"\s*(?:&&|\|\||[;|&])")
HOOK_LOCK_TIMEOUT_S = 1.0  # each lock wait in one hook event: the hook must exit well inside its 10 s budget


def _response_text(tool_response):
    """The tool response as one text, with the newlines of its JSON form made real (the legacy matching rule)."""
    return json.dumps("" if tool_response is None else tool_response).replace("\\n", "\n")


def _squash(text):
    return re.sub(r"\s+", " ", text)


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
            "title": model + ": " + description,
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
        prompt = _squash(_before_operator(cmd.split("--prompt")[-1])).strip(" \"'")[:80]
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
        label = _squash(prompt)[:70] if prompt else os.path.basename(output)
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
    tool = str(payload.get("tool_name") or "")
    _log(event + " " + tool)
    project = _project_for(payload, environ, cwd)
    if project is None:
        return None
    data_dir = jobs.data_dir_of(project)
    if not os.path.isdir(data_dir):
        _log("skip: data folder missing for " + project["id"])
        return None
    if event == "SessionStart":
        return _session_start(project, data_dir)
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
        return _stop_pickup(payload, project, data_dir)
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
PRE_TIMEOUT_S = 0.3        # a PreToolUse that takes longer lets the tool call through
DENY_LOG_S = 60            # a denial is logged at most once a minute per project
PICKUP_PER_SESSION = 3
INBOX_LINES = 3
_SHELL_OPERATORS = (";", "&", "|", "`", "\n", "<", ">", "$(")


def _too_slow(clock, started):
    return clock() - started > PRE_TIMEOUT_S


def _roadmap_command(command):
    """True for a Bash command that is one roadmap command: it starts with 'roadmap ' and chains nothing."""
    text = command.strip()
    return text.startswith("roadmap ") and not any(op in text for op in _SHELL_OPERATORS)


def _project_quiet(payload, environ, cwd):
    """The registered project of the payload cwd, or None. Unlike _project_for, it logs nothing."""
    here = payload.get("cwd")
    here = here if isinstance(here, str) and here else cwd
    try:
        return jobs.resolve_project(None, environ, here)
    except RoadmapError:
        return None


def _pre_tool_use(payload, environ, cwd, now, clock, started):
    """The PreToolUse decision: a deny reply when the project is stopped or blocked, otherwise None."""
    tool = str(payload.get("tool_name") or "")
    if tool not in PRE_TOOLS:
        return None
    tool_input = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
    if tool == "Bash" and _roadmap_command(str(tool_input.get("command") or "")):
        return None
    project = _project_quiet(payload, environ, cwd)
    if project is None or _too_slow(clock, started):
        return None
    pid = project["id"]
    if not os.path.exists(control.sentinel_path(pid)):
        return None
    state = control.read_state(pid)
    if not state:
        return None
    reason = _deny_reason(state, payload, project, now)
    if reason is None or _too_slow(clock, started):
        return None
    _log_denial(pid, reason, now)
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": reason}}


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


def _session_start(project, data_dir):
    """Up to INBOX_LINES lines for the agent's context: the stop line first, then queued and answered items."""
    lines = []
    try:
        state = control.read_state(project["id"])
    except RoadmapError:
        state = None
    if state and state.get("stop") is True:
        stamp = control.clock_text(state.get("stoppedAt"))
        lines.append("roadmap: stopped by user at " + stamp + ". Run roadmap inbox.")
    lines += control.pending_lines(data_dir, limit=INBOX_LINES - len(lines))
    if not lines:
        return None
    return {"hookSpecificOutput": {"hookEventName": "SessionStart",
                                   "additionalContext": "\n".join(lines[:INBOX_LINES])}}


def _stop_pickup(payload, project, data_dir):
    """Stop hook: surface one queued start request as decision block, once per request and 3 times per session.
    Off with pickupOnStop false in the project config. Never while the project is stopped or blocked."""
    if payload.get("stop_hook_active") is True:
        return None
    config_data, error = schema.read_data("roadmap_config", os.path.join(data_dir, "roadmap.config.json"))
    if error is not None or (config_data or {}).get("pickupOnStop") is False:
        return None
    state = control.read_state(project["id"])
    if state and (state.get("stop") is True or state.get("block")):
        return None
    entries = queue_service.list_queue(data_dir)
    if not entries:
        return None
    folder = paths.ensure_dir(paths.state_dir())
    path = os.path.join(folder, "pickup-" + project["id"] + ".json")
    session = str(payload.get("session_id") or "")
    try:
        with lock.locked(folder, timeout=HOOK_LOCK_TIMEOUT_S):
            saved = atomic.read_json(path, default={}) if os.path.exists(path) else {}
            surfaced = saved.get("surfaced") if isinstance(saved.get("surfaced"), dict) else {}
            sessions = saved.get("sessions") if isinstance(saved.get("sessions"), dict) else {}
            if int(sessions.get(session, 0)) >= PICKUP_PER_SESSION:
                return None
            pending = [e for e in entries if _request_key(e) not in surfaced]
            if not pending:
                return None
            entry = pending[0]
            surfaced[_request_key(entry)] = session
            sessions[session] = int(sessions.get(session, 0)) + 1
            atomic.write_json(path, {"surfaced": surfaced, "sessions": sessions})
    except (RoadmapError, ValueError, TypeError):
        return None
    _log("pickup " + str(entry.get("task")))
    return {"decision": "block", "reason": "roadmap: queued request " + str(entry.get("task"))
            + " is waiting; run roadmap inbox and start it."}


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
        _log("skip (no task id): " + title[:60])
        return None
    try:
        job = jobs.start_job(data_dir, title, entry["model"], task)
    except RoadmapError as exc:
        if exc.code == "locked":
            raise
        _log("skip: " + exc.message)
        return None
    _log("start " + job["id"] + " " + title[:60])
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
