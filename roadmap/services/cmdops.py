"""Command ops that wire the control, limit, rules and budget services into the WP21 registry (commands.OPS).

Each op checks its arguments, calls the existing service and returns (data, summary, inverse). The services write
their own activity lines, so these ops are registered with logs=False and run() takes that line.

Source rules (see commands.context): gui calls skip the agent guard, because the guard is about an agent's shell
and the browser is a person. The guard reads CLAUDECODE from the process environment, so a gui call clears that
variable for the duration of the service call (under a lock). cli, agent and phone calls keep the guard. Phone
calls may not run any loosening op (resume, override, raising a limit, rules, approvals), whatever the allowlist.
"""

import contextlib
import os
import threading

from roadmap.errors import EXIT_NOT_FOUND, EXIT_USAGE, RoadmapError
from roadmap.services import commands, control, jobs, limits, rules
from roadmap.services import budget as budget_service
from roadmap.store import config as config_store
from roadmap.store import schema

LOOSENING = frozenset(["control.resume", "control.override", "budget.set", "task.cap", "limit.set", "limit.rm",
                       "phase.approve", "rules.add", "rules.rm", "rules.sync"])
_ENV_LOCK = threading.Lock()
SCOPE_WORDS = ("project", "phases", "models", "tasks")
PERCENT_MAX = 100


@contextlib.contextmanager
def _caller_env():
    """For gui calls, hide CLAUDECODE so the agent guard does not refuse a person's click in an agent's session."""
    if commands.current_source() != "gui":
        yield
        return
    with _ENV_LOCK:
        saved = os.environ.pop(agentguard_env(), None)
        try:
            yield
        finally:
            if saved is not None:
                os.environ[agentguard_env()] = saved


def agentguard_env():
    from roadmap.services import agentguard
    return agentguard.ENV


def _refuse_phone(op):
    if commands.current_source() == "phone" and op in LOOSENING:
        raise RoadmapError("forbidden", op + " is not allowed over the phone", EXIT_USAGE)


def _project_id(data_dir):
    """The project a registry call acts on: the context project, else the registered project of this data folder."""
    if commands.current_project():
        return commands.current_project()
    for entry in config_store.list_projects():
        if jobs.data_dir_of(config_store.get_project(entry["id"])) == data_dir:
            return entry["id"]
    raise RoadmapError("not_found", "no registered project has this data folder", EXIT_NOT_FOUND,
                       next="roadmap project list")


def _number_or_none(a, key):
    value = a.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise commands._usage(key + " must be a number or null")
    return value


def _text_arg(a, key):
    return commands._text(a.get(key))


def _opt_id(a, key):
    value = a.get(key)
    if value is None or str(value).strip() == "":
        return None
    return commands._id({key: value}, key, key)


# ---------------------------------------------------------------- control

def _check_none(a):
    return {}


def _check_control_stop(a):
    return {"task": _opt_id(a, "task")}


def _h_control_stop(data_dir, a, now):
    pid = _project_id(data_dir)
    before = control.read_state(pid) or {}
    was_stopped = before.get("stop") is True
    with _caller_env():
        state = control.stop(pid, task=a["task"], now=now, source=commands.current_source())
    summary_text = a["task"] or "project"
    inverse = None
    if a["task"] is None and not was_stopped:
        inverse = {"op": "control.resume", "args": {}}
    return {"stopped": state.get("stop") is True, "task": a["task"]}, "stop " + summary_text, inverse


def _h_control_resume(data_dir, a, now):
    _refuse_phone("control.resume")
    pid = _project_id(data_dir)
    before = control.read_state(pid) or {}
    was_stopped = before.get("stop") is True
    with _caller_env():
        state = control.resume(pid, now=now, source=commands.current_source())
    inverse = {"op": "control.stop", "args": {}} if was_stopped else None
    return {"stopped": state.get("stop") is True}, "resume", inverse


def _check_control_override(a):
    hours = a.get("hours")
    if isinstance(hours, bool) or not isinstance(hours, (int, float)):
        raise commands._usage("hours must be a number from 1 to 4")
    return {"hours": hours}


def _h_control_override(data_dir, a, now):
    _refuse_phone("control.override")
    pid = _project_id(data_dir)
    with _caller_env():
        control.override(pid, a["hours"], now=now, source=commands.current_source())
    return {"hours": a["hours"]}, "override %gh" % a["hours"], None


# ---------------------------------------------------------------- limits

ROW_ID_KEYS = ("scope", "window", "kind")


def _check_limit_set(a):
    """Legacy {pct} sets the weekly stop (kind acct). Otherwise {scope, window, kind, value, action, id?} sets a row."""
    if "pct" in a and not any(key in a for key in ROW_ID_KEYS):
        pct = a.get("pct")
        if isinstance(pct, bool) or not isinstance(pct, (int, float)) or not 1 <= pct <= PERCENT_MAX:
            raise commands._usage("pct must be a number from 1 to 100")
        return {"pct": pct}
    row_id = _opt_id(a, "id")
    spec = limits.check_spec(_text_arg(a, "scope") or "project", _text_arg(a, "window"), _text_arg(a, "kind"),
                             a.get("value"), _text_arg(a, "action") or "block")
    return {"row": spec, "id": row_id}


def _weekly_prior(data_dir):
    path = os.path.join(data_dir, "autonomy.json")
    data, error = schema.read_data("autonomy", path)
    if error is not None or not isinstance(data, dict):
        return None
    limit = data.get("limit") or {}
    return limit.get("stopAtPercent") if isinstance(limit, dict) else None


def _row_args(row):
    """The arguments that set a row back to this state (limit.set), with its id."""
    return {"id": row["id"], "scope": row["scope"], "window": row["window"], "kind": row["kind"],
            "value": row["value"], "action": row["action"]}


def _row_data(row):
    return {key: row[key] for key in ("id", "scope", "window", "kind", "value", "action") if key in row}


def _h_limit_set(data_dir, a, now):
    _refuse_phone("limit.set")
    pid = _project_id(data_dir)
    if "pct" in a:
        prior = _weekly_prior(data_dir)
        with _caller_env():
            control.set_weekly_limit(pid, a["pct"], now=now, source=commands.current_source())
        inverse = {"op": "limit.set", "args": {"pct": prior}} if prior is not None else None
        return {"pct": a["pct"]}, "weekly stop at %g%%" % a["pct"], inverse
    spec = a["row"]
    with _caller_env():
        result = control.set_limit_row(pid, spec["scope"], spec["window"], spec["kind"], spec["value"],
                                       spec["action"], row_id=a["id"], now=now,
                                       source=commands.current_source())
    row, prior = result["row"], result["prior"]
    inverse = {"op": "limit.set", "args": _row_args(prior)} if prior else {"op": "limit.rm",
                                                                           "args": {"id": row["id"]}}
    return _row_data(row), limits.label(row) + " set", inverse


def _check_limit_rm(a):
    row_id = _text_arg(a, "id")
    if not limits.ANY_ID.match(row_id):
        raise commands._usage("row id '" + row_id + "' looks like L3, AUTO or BUD", "roadmap limit show")
    return {"id": row_id}


def _h_limit_rm(data_dir, a, now):
    _refuse_phone("limit.rm")
    pid = _project_id(data_dir)
    with _caller_env():
        removed = control.remove_limit_row(pid, a["id"], now=now, source=commands.current_source())
    return _row_data(removed), limits.label(removed) + " removed", {"op": "limit.set", "args": _row_args(removed)}


def _check_budget_set(a):
    scope = _text_arg(a, "scope")
    if scope not in SCOPE_WORDS:
        raise commands._usage("scope '" + scope + "' is not valid (allowed: " + "|".join(SCOPE_WORDS) + ")")
    key = _text_arg(a, "key") if scope != "project" else ""
    if scope != "project" and not key:
        raise commands._usage("budget " + scope + " needs a key (the id or the model name)")
    return {"scope": scope, "key": key, "value": _number_or_none(a, "value")}


def _budget_prior(data_dir, scope, key):
    limits = budget_service.get(data_dir)["limits"]
    if scope == "project":
        return limits.get("project")
    return (limits.get(scope) or {}).get(key)


def _set_budget(data_dir, scope, key, value, now, op):
    pid = _project_id(data_dir)
    prior = _budget_prior(data_dir, scope, key)
    with _caller_env():
        control.set_budget_limit(pid, scope, key, value, now=now, source=commands.current_source())
    inverse = {"op": "budget.set", "args": {"scope": scope, "key": key, "value": prior}}
    return {"scope": scope, "key": key, "value": value}, op, inverse


def _h_budget_set(data_dir, a, now):
    _refuse_phone("budget.set")
    return _set_budget(data_dir, a["scope"], a["key"], a["value"], now, "budget " + a["scope"])


def _check_task_cap(a):
    return {"id": commands._id(a, "id", "task id"), "value": _number_or_none(a, "value")}


def _h_task_cap(data_dir, a, now):
    _refuse_phone("task.cap")
    return _set_budget(data_dir, "tasks", a["id"], a["value"], now, "cap " + a["id"])


def _check_phase_approve(a):
    return {"phase": commands._id(a, "phase", "phase id")}


def _h_phase_approve(data_dir, a, now):
    _refuse_phone("phase.approve")
    pid = _project_id(data_dir)
    with _caller_env():
        result = control.approve_phase(pid, a["phase"], now=now, source=commands.current_source())
    return result, "approve " + a["phase"], None


# ---------------------------------------------------------------- rules

def _check_rules_add(a):
    scope = _text_arg(a, "scope")
    kind = _text_arg(a, "kind")
    text = a.get("text")
    if not isinstance(text, str) or not text.strip():
        raise commands._usage("text is required")
    value = a.get("value")
    if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))):
        raise commands._usage("value must be a number or null")
    return {"scope": scope, "kind": kind, "text": text, "value": value}


def _h_rules_add(data_dir, a, now):
    _refuse_phone("rules.add")
    with _caller_env():
        rule = rules.add(data_dir, a["scope"], a["kind"], a["text"], value=a["value"],
                         source=commands.current_source())
    return rule, "rule " + rule["id"] + " added", {"op": "rules.rm", "args": {"id": rule["id"]}}


def _check_rules_rm(a):
    return {"id": _text_arg(a, "id")}


def _h_rules_rm(data_dir, a, now):
    _refuse_phone("rules.rm")
    with _caller_env():
        gone = rules.remove(data_dir, a["id"], source=commands.current_source())
    inverse = {"op": "rules.add", "args": {"scope": gone["scope"], "kind": gone["kind"], "text": gone["text"],
                                           "value": gone.get("value")}}
    return gone, "rule " + gone["id"] + " removed", inverse


def _check_rules_sync(a):
    dry = a.get("dryRun", False)
    if not isinstance(dry, bool):
        raise commands._usage("dryRun must be true or false")
    return {"dryRun": dry}


def _h_rules_sync(data_dir, a, now):
    _refuse_phone("rules.sync")
    pid = _project_id(data_dir)
    project = config_store.get_project(pid)
    with _caller_env():
        counts = rules.sync(project, data_dir, dry_run=a["dryRun"], source=commands.current_source(), now=now)
    return dict(counts) if isinstance(counts, dict) else {"result": str(counts)}, "rules sync", None


# ---------------------------------------------------------------- registration

def _register(name, check, handler):
    commands.OPS[name] = commands._Op(check, handler, public=True, logs=False)


_register("control.stop", _check_control_stop, _h_control_stop)
_register("control.resume", _check_none, _h_control_resume)
_register("control.override", _check_control_override, _h_control_override)
_register("limit.set", _check_limit_set, _h_limit_set)
_register("limit.rm", _check_limit_rm, _h_limit_rm)
_register("budget.set", _check_budget_set, _h_budget_set)
_register("task.cap", _check_task_cap, _h_task_cap)
_register("phase.approve", _check_phase_approve, _h_phase_approve)
_register("rules.add", _check_rules_add, _h_rules_add)
_register("rules.rm", _check_rules_rm, _h_rules_rm)
_register("rules.sync", _check_rules_sync, _h_rules_sync)
