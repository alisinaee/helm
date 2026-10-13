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
_CURSOR_RE = re.compile(r"cursor-review2\.sh\s+(\S+)")


def _response_text(tool_response):
    """The tool response as one text, with the newlines of its JSON form made real (the legacy matching rule)."""
    return json.dumps("" if tool_response is None else tool_response).replace("\\n", "\n")


def _squash(text):
    return re.sub(r"\s+", " ", text)


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
        title = "agy %s: %s" % (who.group(1) if who else "job", _squash(cmd.split("--prompt")[-1])[:80])
        return {"title": title, "model": "agy", "text": cmd, "kind": "file", "watch": found.group(1),
                "agent": ""}


class CursorDetector(_FileDetector):
    """cursor-review2.sh runs. The first argument is the result file."""

    name = "cursor"

    def on_tool(self, tool, tool_input, tool_response):
        if tool != "Bash":
            return None
        cmd = str(tool_input.get("command") or "")
        found = _CURSOR_RE.search(cmd)
        if "cursor-review2.sh" not in cmd or not found:
            return None
        title = "Cursor Auto: " + _squash(cmd.split(found.group(1), 1)[-1])[:80]
        return {"title": title, "model": "cursor", "text": cmd, "kind": "file",
                "watch": found.group(1).strip("\"'"), "agent": ""}


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
    path = paths.hooks_file(project["id"])
    paths.ensure_dir(paths.state_dir())
    with lock.locked(paths.state_dir()):
        state = _read_state(path)
        changed = False
        if event == "PostToolUse":
            tool_input = payload.get("tool_input")
            tool_input = tool_input if isinstance(tool_input, dict) else {}
            for detector in active:
                entry = detector.on_tool(tool, tool_input, payload.get("tool_response"))
                if entry is not None:
                    changed = _start(data_dir, state, detector, entry, regex, known, now) or changed
        elif event == "SubagentStop":
            agent_id = str(payload.get("agent_id") or "")
            if agent_id:
                changed = _finish_matching(data_dir, state, agent_id) or changed
        changed = _reap(data_dir, state, now) or changed
        if changed:
            _write_state(path, project["id"], state)


def _project_for(payload, environ, cwd):
    here = payload.get("cwd")
    here = here if isinstance(here, str) and here else cwd
    try:
        return jobs.resolve_project(None, environ, here)
    except RoadmapError as exc:
        _log("skip: " + exc.message)
        return None


def _start(data_dir, state, detector, entry, regex, known, now):
    """Register a job for a detected start when the text names a known task. Returns True when state changed."""
    task = find_task(entry["text"], regex, known)
    title = entry["title"][:120]
    if task is None:
        _log("skip (no task id): " + title[:60])
        return False
    try:
        job = jobs.start_job(data_dir, title, entry["model"], task)
    except RoadmapError as exc:
        _log("skip: " + exc.message)
        return False
    state["active"].append({"job": job["id"], "detector": detector.name, "kind": entry["kind"],
                            "agent": entry["agent"], "watch": entry["watch"], "started": now})
    _log("start " + job["id"] + " " + title[:60])
    return True


def _finish_matching(data_dir, state, agent_id):
    """Close the active jobs that belong to agent_id. Returns True when state changed."""
    keep = []
    changed = False
    for entry in state["active"]:
        if entry.get("agent") != agent_id:
            keep.append(entry)
            continue
        changed = True
        if not _close(data_dir, entry, "done"):
            keep.append(entry)
    state["active"] = keep
    return changed


def _reap(data_dir, state, now):
    """Close active jobs whose detector reports them finished. Returns True when state changed."""
    keep = []
    changed = False
    for entry in state["active"]:
        detector = DETECTORS.get(entry.get("detector"))
        verdict = detector.reap(entry, now) if detector is not None else None
        if verdict is None:
            keep.append(entry)
            continue
        changed = True
        if not _close(data_dir, entry, verdict):
            keep.append(entry)
    state["active"] = keep
    return changed


def _close(data_dir, entry, status):
    """Finish the job of a state entry. Returns True when the entry may be dropped from state."""
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
