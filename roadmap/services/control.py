"""Control state (WP22): stop, resume, override and the limits that stop the agents of a project.

Every write recomputes <state>/control-<project>.json: {stop, stoppedAt, stopRef, manualTasks, stopTasks, block,
taskBlocks, warn, overrideUntil}. The manual flags (stop, manualTasks, overrideUntil) are kept in the same file; the
limits (phase and task caps; the limit rows of services/limits.py: global, project, the weekly stop and the project
budget) are recomputed from the data each time, and a global row reaches every project through recompute_all.
The sentinel <state>/block-<project> exists only while something blocks: a stop, a stopped task or a limit. The
PreToolUse hook reads only these two files and fails open (services/hooks.py).

The write order of each op is: lock, validate, write, recompute, activity line. The activity line comes before the
recompute of a stop, so the stop can name its own activity id (A812).
"""

import datetime
import os

from roadmap.errors import EXIT_INVALID_DATA, EXIT_NOT_FOUND, EXIT_USAGE, RoadmapError
from roadmap.services import activity, agentguard, budget, jobs, limits, queue, questions, records, tasks
from roadmap.log import get_logger
from roadmap.store import atomic, config, lock, paths, schema

STATE_VERSION = 1
log = get_logger("services.control")
WARN_PCT = 80
BLOCK_PCT = 100
OVERRIDE_MIN_H = 1
OVERRIDE_MAX_H = 4
RECENT_ANSWER_S = 3600
LINE_MAX = 160
SCOPES = ("project", "phases", "models", "tasks")
SCOPE_WORDS = {"project": "project", "phase": "phases", "model": "models", "task": "tasks"}


# ------------------------------------------------------------------ paths and small helpers

def control_path(project_id):
    return os.path.join(paths.state_dir(), "control-" + _checked(project_id) + ".json")


def sentinel_path(project_id):
    return os.path.join(paths.state_dir(), "block-" + _checked(project_id))


def _checked(project_id):
    if not paths.valid_id(project_id):
        raise RoadmapError("invalid_input", "not a valid project id: " + repr(project_id), EXIT_USAGE)
    return project_id


def _now(now):
    return now if now is not None else datetime.datetime.now().astimezone()


def _iso(moment):
    return moment.isoformat(timespec="seconds")


def parse_time(text):
    """An ISO time as an aware datetime, or None. A naive time is read as local time."""
    if not isinstance(text, str) or not text:
        return None
    try:
        return datetime.datetime.fromisoformat(text).astimezone()
    except ValueError:
        return None


def clock_text(text):
    """HH:MM of an ISO time, or an empty string when it does not parse."""
    moment = parse_time(text)
    return moment.strftime("%H:%M") if moment is not None else ""


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value:
        return None
    return float(value)


def _pct(spent, limit):
    """Percent of a limit used. None when there is no limit. A zero limit is full as soon as anything is spent."""
    if limit is None:
        return None
    if limit <= 0:
        return 100.0 if spent > 0 else 0.0
    return spent / limit * 100.0


def _task_id(value):
    text = str(value or "").strip()
    if not records.ID_OK.match(text):
        raise RoadmapError("usage", "not a task id: " + repr(value), EXIT_USAGE)
    return text


def _project(project_id):
    project = config.get_project(project_id)
    return project, jobs.data_dir_of(project)


# ------------------------------------------------------------------ reading and saving the state

def read_state(project_id):
    """The saved control state, or None when there is none. A file that is not a JSON object is invalid_data."""
    path = control_path(project_id)
    if not os.path.exists(path):
        return None
    data = atomic.read_json(path)
    if not isinstance(data, dict):
        raise RoadmapError("invalid_data", "control file is not a JSON object; fix or remove it: " + path,
                           EXIT_INVALID_DATA)
    return data


def _manual_of(saved):
    """The manual flags of a saved state (stop, stoppedAt, stopRef, manualTasks, overrideUntil)."""
    tasks_list = saved.get("manualTasks")
    return {
        "stop": saved.get("stop") is True,
        "stoppedAt": saved.get("stoppedAt") if isinstance(saved.get("stoppedAt"), str) else None,
        "stopRef": saved.get("stopRef") if isinstance(saved.get("stopRef"), str) else None,
        "manualTasks": [t for t in tasks_list if isinstance(t, str)] if isinstance(tasks_list, list) else [],
        "manualAt": {k: v for k, v in (saved.get("manualAt") or {}).items() if isinstance(v, str)}
        if isinstance(saved.get("manualAt"), dict) else {},
        "overrideUntil": saved.get("overrideUntil") if isinstance(saved.get("overrideUntil"), str) else None,
    }


def _armed(state):
    return bool(state["stop"] or state["stopTasks"] or state["block"])


def _save(project_id, state):
    """Write the state, then the sentinel: the sentinel follows the state, so the hook never sees a stale stop."""
    atomic.write_json(control_path(project_id), state)
    sentinel = sentinel_path(project_id)
    if _armed(state):
        atomic.write_text(sentinel, _sentinel_text(state) + "\n")
    elif os.path.lexists(sentinel):
        os.remove(sentinel)


def _sentinel_text(state):
    if state["stop"]:
        return "stopped by user"
    if state["block"]:
        return state["block"]["reason"]
    return "stopped tasks: " + ", ".join(state["stopTasks"])


# ------------------------------------------------------------------ evaluation

def _spent_rows(bud):
    rows = {}
    for task_id, models in (bud.get("spent") or {}).items():
        if isinstance(models, dict):
            rows[str(task_id)] = {str(m): _number(v) or 0.0 for m, v in models.items()}
    return rows


def _load_budget(data_dir, warns):
    if not os.path.isdir(data_dir):
        return None
    try:
        return budget.get(data_dir)
    except RoadmapError as exc:
        warns.append("budget unreadable: " + exc.message)
        return None


def _load_tasks(data_dir, warns):
    if not os.path.isdir(data_dir):
        return []
    try:
        return [t for t in tasks.load(data_dir)["tasks"] if isinstance(t, dict) and isinstance(t.get("id"), str)]
    except RoadmapError as exc:
        warns.append("tasks.json unreadable: task and phase caps are not checked (" + exc.message[:60] + ")")
        return []


def _evaluate(project, manual, now):
    """The full state of a project for the given manual flags and the current data."""
    data_dir = jobs.data_dir_of(project)
    warns = []
    reasons = []
    task_blocks = {}
    bud = _load_budget(data_dir, warns)
    rows = _load_tasks(data_dir, warns)
    if bud is None:
        bud = {"spent": {}, "limits": {"project": None, "phases": {}, "models": {}, "tasks": {}}}
    spent = _spent_rows(bud)
    caps = bud["limits"]
    phase_of = {t["id"]: t.get("phase") for t in rows}
    task_total = {tid: sum(models.values()) for tid, models in spent.items()}

    for phase_id, cap in (caps.get("phases") or {}).items():
        used = sum(total for tid, total in task_total.items() if phase_of.get(tid) == phase_id)
        pct = _pct(used, _number(cap))
        if pct is None:
            continue
        if pct >= BLOCK_PCT:
            for tid, phase in phase_of.items():
                if phase == phase_id:
                    task_blocks[tid] = "phase " + phase_id + " cap reached"
        elif pct >= WARN_PCT:
            warns.append("phase " + phase_id + " at %d%%" % int(pct))

    task_caps = {t["id"]: _number(t.get("capK")) for t in rows if _number(t.get("capK")) is not None}
    task_caps.update({tid: _number(v) for tid, v in (caps.get("tasks") or {}).items() if _number(v) is not None})
    for tid, cap in task_caps.items():
        pct = _pct(task_total.get(tid, 0.0), cap)
        if pct is None:
            continue
        if pct >= BLOCK_PCT:
            task_blocks[tid] = "task " + tid + " cap reached"
        elif pct >= WARN_PCT:
            warns.append("task " + tid + " at %d%%" % int(pct))

    for model, cap in (caps.get("models") or {}).items():
        used = sum(models.get(model, 0.0) for models in spent.values())
        pct = _pct(used, _number(cap))
        if pct is not None and pct >= BLOCK_PCT:
            warns.append("model " + model + " over its cap (warning only)")

    # the account and project limit rows (services/limits.py): global rows fan out to every project this way
    applied = limits.evaluate_rows(project, now)
    for row in applied:
        if row["state"] == "block":
            reasons.append(limits.describe(row))
        elif row["state"] == "warn":
            warns.append(limits.describe(row))
    blocking_scopes = {row["scope"] for row in applied if row["state"] == "block"}

    stopped_at = manual["stoppedAt"] if manual["stop"] else None
    for tid in manual["manualTasks"]:
        stamp = clock_text(manual["manualAt"].get(tid))
        task_blocks[tid] = "stopped by user" + (" at " + stamp if stamp else "")
    override = manual["overrideUntil"]
    until = parse_time(override)
    if until is None or until <= now:
        override = None

    block = None
    if reasons:
        block = {"reason": "; ".join(reasons), "scope": "global" if blocking_scopes == {"global"} else "project",
                 "overridable": True}
    state = {
        "schemaVersion": STATE_VERSION,
        "project": project["id"],
        "stop": manual["stop"],
        "stoppedAt": stopped_at,
        "stopRef": manual["stopRef"] if manual["stop"] else None,
        "manualTasks": sorted(manual["manualTasks"]),
        "manualAt": {tid: manual["manualAt"][tid] for tid in sorted(manual["manualAt"])
                     if tid in manual["manualTasks"]},
        "stopTasks": sorted(task_blocks),
        "taskBlocks": {tid: task_blocks[tid] for tid in sorted(task_blocks)},
        "block": block,
        "warn": warns[:6],
        "overrideUntil": override,
        "day": _now(now).date().isoformat(),
        "updated": _iso(now),
    }
    return state


def _mutate(project, change, now):
    """Under the state lock: apply change(manual) to the saved manual flags, evaluate, save. Returns the state."""
    with lock.locked(paths.ensure_dir(paths.state_dir())):
        manual = _manual_of(read_state(project["id"]) or {})
        change(manual)
        state = _evaluate(project, manual, now)
        _save(project["id"], state)
    return state


def recompute(project_id, now=None):
    """Rebuild the control state and the sentinel of a project from its data. Returns the new state."""
    project = config.get_project(project_id)
    return _mutate(project, lambda manual: None, _now(now))


def recompute_all(now=None):
    """Recompute every registered project. A global limit row therefore blocks every project's sentinel at once.
    Called after a usage reading, a finished job and a limit change. Returns {project id: state or None}."""
    moment = _now(now)
    states = {}
    for entry in config.list_projects():
        try:
            states[entry["id"]] = recompute(entry["id"], moment)
        except Exception as exc:  # one broken project must not stop the others
            log.warning("control recompute failed for %s: %s", entry.get("id"), type(exc).__name__)
            states[entry["id"]] = None
    return states


def after_write(project_id, now=None):
    """Best effort recompute after a write (fan-out to every project). Never raises: a broken limit file must not
    break a write that has already been saved. Returns the state of project_id, or None."""
    try:
        return recompute_all(now).get(project_id)
    except Exception:  # the write is done; the next recompute repairs the state
        return None


def _log(data_dir, src, op, summary, moment, undo=True):
    return activity.append(data_dir, src, op, summary, undo=undo, now=moment)


# ------------------------------------------------------------------ operations (stop, resume, override)

def stop(project_id, task=None, now=None, source=None):
    """Stop the project, or one task when task is given. Stopping is never refused. Returns the state."""
    project, data_dir = _project(project_id)
    moment = _now(now)
    src = source or agentguard.source_name()
    task_id = None if task is None else _task_id(task)
    entry = _log(data_dir, src, "control.stop", "stop " + (task_id or "project"), moment)

    def change(manual):
        if task_id is not None:
            if task_id not in manual["manualTasks"]:
                manual["manualTasks"].append(task_id)
            manual["manualAt"][task_id] = _iso(moment)
            return
        manual["stop"] = True
        manual["stoppedAt"] = _iso(moment)
        manual["stopRef"] = entry["id"]

    return _mutate(project, change, moment)


def resume(project_id, now=None, source=None):
    """Clear the project stop and every stopped task. A budget or weekly block stays until its limit moves."""
    agentguard.refuse_if_agent("control.resume", source)
    project, data_dir = _project(project_id)
    moment = _now(now)
    _log(data_dir, source or agentguard.source_name(), "control.resume", "resume", moment)

    def change(manual):
        manual.update(stop=False, stoppedAt=None, stopRef=None, manualTasks=[], manualAt={})

    return _mutate(project, change, moment)


def override(project_id, hours, now=None, source=None):
    """Let work run past a budget or weekly block for 1 to 4 hours. A manual stop is not overridden."""
    agentguard.refuse_if_agent("control.override", source)
    value = _number(hours)
    if value is None or not OVERRIDE_MIN_H <= value <= OVERRIDE_MAX_H:
        raise RoadmapError("usage", "override takes 1 to %d hours (--hours N)" % OVERRIDE_MAX_H, EXIT_USAGE)
    project, data_dir = _project(project_id)
    moment = _now(now)
    until = moment + datetime.timedelta(hours=value)
    _log(data_dir, source or agentguard.source_name(), "control.override", "override %gh" % value, moment)

    def change(manual):
        manual["overrideUntil"] = _iso(until)

    return _mutate(project, change, moment)


def summary_line(project_id, now=None):
    """One line about the control state for status: running, stopped, blocked or override. Never raises."""
    try:
        state = read_state(project_id)
    except RoadmapError:
        return "control: unreadable"
    if not state:
        return "running"
    moment = _now(now)
    until = parse_time(state.get("overrideUntil"))
    overridden = until is not None and until > moment
    if state.get("stop") is True:
        return "stopped by user at " + clock_text(state.get("stoppedAt"))
    block = state.get("block")
    if isinstance(block, dict) and not (overridden and block.get("overridable")):
        return "blocked: " + str(block.get("reason", ""))
    if state.get("stopTasks"):
        return "running (stopped tasks: " + ", ".join(state["stopTasks"]) + ")"
    if overridden:
        return "running (override until " + until.strftime("%H:%M") + ")"
    return "running"


# ------------------------------------------------------------------ limits and phase approval

def set_weekly_limit(project_id, pct, now=None, source=None):
    """Set autonomy.json limit.stopAtPercent (1 to 100). Always refused from an agent."""
    agentguard.refuse_if_agent("limit.set", source)
    value = _number(pct)
    if value is None or not 1 <= value <= 100:
        raise RoadmapError("usage", "limit set takes a percent from 1 to 100", EXIT_USAGE)
    project, data_dir = _project(project_id)
    records.require_dir(data_dir)
    moment = _now(now)
    path = os.path.join(data_dir, "autonomy.json")
    with lock.locked(data_dir):
        data, error = schema.read_data("autonomy", path)
        if error is not None:
            raise RoadmapError("newer_schema", error["message"], EXIT_INVALID_DATA)
        doc = dict(data or {})
        limit = dict(doc.get("limit") or {})
        limit.update({"stopAtPercent": int(value) if value == int(value) else value, "setBy": "roadmap",
                      "setOn": moment.date().isoformat()})
        doc["limit"] = limit
        schema.write_data("autonomy", path, doc)
    _log(data_dir, source or agentguard.source_name(), "limit.set", "weekly stop at %g%%" % value, moment)
    return _mutate(project, lambda manual: None, moment)


def _current_limit(current, scope, key):
    if scope == "project":
        return _number(current.get("project"))
    return _number((current.get(scope) or {}).get(key))


def set_budget_limit(project_id, scope, key, value, now=None, source=None):
    """Set a budget limit in thousands of tokens (value None clears it). Raising or clearing a limit is refused from
    an agent; setting a limit where none was, or lowering one, is allowed."""
    if scope not in SCOPES:
        raise RoadmapError("usage", "limit scope '" + str(scope) + "' is not valid (allowed: " + "|".join(SCOPES) + ")",
                           EXIT_USAGE)
    project, data_dir = _project(project_id)
    records.require_dir(data_dir)
    before = _current_limit(budget.get(data_dir)["limits"], scope, key)
    new = None if value is None else _number(value)
    loosens = before is not None and (new is None or new > before)
    if loosens:
        agentguard.refuse_if_agent("budget.set (raising a limit)", source)
    moment = _now(now)
    budget.set_limit(data_dir, scope, key, new)
    label = scope if scope == "project" else scope[:-1] + " " + str(key)
    _log(data_dir, source or agentguard.source_name(), "budget.set",
         "limit " + label + " " + ("cleared" if new is None else "%g" % new), moment)
    return _mutate(project, lambda manual: None, moment)


def set_limit_row(project_id, scope, window, kind, value, action="block", row_id=None, now=None, source=None):
    """Set a limit row (services/limits.py): the same scope, window and kind replace the row that is there. Always
    refused from an agent. Returns {row, prior}. The weekly stop (kind acct) writes autonomy.json as limit set <pct>
    does; a project total budget writes the budget. Every project is recomputed, so a global row reaches all of them."""
    agentguard.refuse_if_agent("limit.set", source)
    spec = limits.check_spec(scope, window, kind, value, action)
    project, data_dir = _project(project_id)
    moment = _now(now)
    prior, row = limits.write_row(project, data_dir, spec, row_id=row_id, now=moment)
    _log(data_dir, source or agentguard.source_name(), "limit.set", limits.label(row) + " set", moment)
    recompute_all(moment)
    return {"row": row, "prior": prior}


def remove_limit_row(project_id, row_id, now=None, source=None):
    """Remove a limit row by id (L3, AUTO or BUD). Always refused from an agent. Returns the removed row."""
    agentguard.refuse_if_agent("limit.rm", source)
    project, data_dir = _project(project_id)
    moment = _now(now)
    removed = limits.remove_row(project, data_dir, row_id, now=moment)
    _log(data_dir, source or agentguard.source_name(), "limit.rm", limits.label(removed) + " removed", moment)
    recompute_all(moment)
    return removed


def approve_phase(project_id, phase_id, now=None, source=None):
    """Mark a phase approved in tasks.json. Always refused from an agent. Approving twice changes nothing."""
    agentguard.refuse_if_agent("phase.approve", source)
    project, data_dir = _project(project_id)
    records.require_dir(data_dir)
    moment = _now(now)
    wanted = str(phase_id or "").strip()
    with lock.locked(data_dir):
        doc = tasks.load(data_dir)
        phase = next((p for p in doc["phases"] if isinstance(p, dict) and p.get("id") == wanted), None)
        if phase is None:
            raise RoadmapError("not_found", "no phase '" + wanted + "' in tasks.json", EXIT_NOT_FOUND)
        if phase.get("approved") is True:
            return {"phase": wanted, "approved": True, "changed": False}
        phase["approved"] = True
        schema.write_data("tasks", tasks.tasks_path(data_dir), doc)
    _log(data_dir, source or agentguard.source_name(), "phase.approve", "approve " + wanted, moment)
    return {"phase": wanted, "approved": True, "changed": True}


# ------------------------------------------------------------------ inbox lines for the hooks

def pending_lines(data_dir, limit=6, now=None):
    """Up to limit short lines: queued start requests, open questions and questions answered in the last hour."""
    moment = _now(now)
    lines = []
    for entry in queue.list_queue(data_dir):
        lines.append("queued: " + str(entry.get("task")) + " (" + str(entry.get("by") or "-") + ")")
    for question in questions.list_questions(data_dir, open_only=True):
        lines.append("open question " + str(question.get("id")) + ": " + str(question.get("text")))
    for question in questions.list_questions(data_dir):
        answered = parse_time(question.get("answered"))
        if question.get("status") == "answered" and answered is not None and \
                (moment - answered).total_seconds() <= RECENT_ANSWER_S:
            lines.append("answered " + str(question.get("id")) + ": " + str(question.get("answer")))
    return [line[:LINE_MAX] for line in lines[:limit]]
