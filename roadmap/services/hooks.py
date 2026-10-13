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
from roadmap.services import jobs
from roadmap.store import lock, paths, schema

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


def run_hook(raw, environ=None, cwd=None, now=None):
    """Handle one hook event given as stdin text. Returns nothing and never raises."""
    try:
        _handle(raw, os.environ if environ is None else environ, cwd, time.time() if now is None else now)
    except Exception as exc:  # a hook must never fail a tool call: the problem goes to the log
        _log("error " + type(exc).__name__ + ": " + str(exc))


def _handle(raw, environ, cwd, now):
    try:
        payload = json.loads(raw) if raw and raw.strip() else {}
    except ValueError as exc:
        _log("skip: stdin is not valid JSON (" + str(exc)[:80] + ")")
        return
    if not isinstance(payload, dict):
        _log("skip: stdin is not a JSON object")
        return
    event = str(payload.get("hook_event_name") or "")
    tool = str(payload.get("tool_name") or "")
    _log(event + " " + tool)
    project = _project_for(payload, environ, cwd)
    if project is None:
        return
    data_dir = jobs.data_dir_of(project)
    if not os.path.isdir(data_dir):
        _log("skip: data folder missing for " + project["id"])
        return
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
