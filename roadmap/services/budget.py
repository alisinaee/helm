"""Budget (budget.json): limits in thousands of tokens and the spend per task and model.

A job's tokens are recorded once per job id (idempotent; the last 500 job ids are remembered). The task-level
`task done --tokens` path records spend only when the task has no spend yet, so one piece of work is counted once.
"""

import datetime
import json
import os

from roadmap.errors import EXIT_USAGE, RoadmapError
from roadmap.log import get_logger
from roadmap.services import records
from roadmap.store import lock

log = get_logger("services.budget")
FILE = "budget.json"
JOBS_KEEP = 500
SCOPES = ("project", "phases", "models", "tasks")
UNATTRIBUTED = "-"
AUTONOMY_FILE = "autonomy.json"
MAX_USAGE_AGE_MIN = 90


LEGACY_STOP_KEYS = ("stopAtPercent", "fiveHourStopAtPercent")
MOVED_NOTE = "moved to Tokens > Limits (R11.164)"
WINDOW_NAMES = {"five_hour": "5-hour", "week": "weekly"}


def drop_legacy_stops(data_dir, locked=False):
    """One-time cleanup (R11.164): Tokens > Limits is the only source of usage stops, so the two legacy stop keys in
    docs/autonomy.json limit are dropped (and a note kept). Returns True when something was dropped. Best effort: an
    unreadable file or a failed write leaves it alone. locked=True when the caller already holds the folder lock."""
    path = os.path.join(data_dir, AUTONOMY_FILE)
    if not os.path.exists(path):
        return False
    try:
        if locked:
            return _drop_legacy(path)
        with lock.locked(data_dir):
            return _drop_legacy(path)
    except Exception as exc:  # the cleanup is optional; the guard must still answer
        log.warning("legacy stop keys not dropped: %s", type(exc).__name__)
        return False


def _drop_legacy(path):
    from roadmap.store import schema
    data, error = schema.read_data("autonomy", path)
    if error is not None or not isinstance(data, dict) or not isinstance(data.get("limit"), dict):
        return False
    if not any(key in data["limit"] for key in LEGACY_STOP_KEYS):
        return False
    doc = dict(data)
    limit = dict(doc["limit"])
    for key in LEGACY_STOP_KEYS:
        limit.pop(key, None)
    limit["note"] = MOVED_NOTE
    doc["limit"] = limit
    schema.write_data("autonomy", path, doc)
    return True


def guard(data_dir, now=None):
    """Check the usage stops. The stops come only from Tokens > Limits (limits_v2; R11.164): each window that is on
    with a stop blocks when its fresh reading is at or past it ("stop: weekly 86% >= 80%"); a stale or missing reading
    on an on stop blocks with the stale hint. Off windows never block. The reading is the one in docs/autonomy.json
    usage when it is fresh, else the global usage. Returns (stop, warn): stop is one line or None; warn is a note when
    the usage reading is older than maxUsageAgeMin (default 90) or autonomy.json cannot be read, else None."""
    from roadmap.services import limits_v2
    drop_legacy_stops(data_dir)
    doc, warn = {}, None
    path = os.path.join(data_dir, AUTONOMY_FILE)
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                doc = json.load(fh)
        except (OSError, ValueError):
            doc, warn = {}, "autonomy.json unreadable: limits not checked"
        if not isinstance(doc, dict):
            doc, warn = {}, "autonomy.json is not an object: limits not checked"
    usage = doc.get("usage") if isinstance(doc.get("usage"), dict) else {}
    local_fresh = bool(usage) and _stale_warning(doc, usage, now) is None
    try:
        windows = limits_v2.stops(now, persist=False)
    except Exception as exc:  # a broken config must not block work by itself
        log.warning("limits not read: %s", type(exc).__name__)
        return None, warn
    stop = _stop_reason(windows, usage, local_fresh)
    if stop:
        return stop, None
    if warn or not os.path.exists(path):
        return None, warn
    return None, _stale_warning(doc, usage, now)


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


_LOCAL_KEYS = {"week": "weeklyPercent", "five_hour": "fiveHourPercent"}


def _stop_reason(windows, usage, local_fresh):
    """The first stop reached (weekly, then 5-hour), as the refusal line, or None."""
    for window in ("week", "five_hour"):
        info = windows[window]
        stop_at = info.get("stop")
        if not info.get("on") or not _is_number(stop_at):
            continue
        reading = usage.get(_LOCAL_KEYS[window]) if local_fresh else None
        if not _is_number(reading) and info.get("fresh"):
            reading = info.get("percent")
        name = WINDOW_NAMES[window]
        if not _is_number(reading):
            from roadmap.services import limits
            return "stop: %s stop at %g%%: usage is stale (%s): sync usage before starting new work" % (
                name, stop_at, limits._stale_age_text())
        if reading >= stop_at:
            return "stop: %s %g%% >= %g%%" % (name, reading, stop_at)
    return None


def _stale_warning(doc, usage, now):
    """A note when the usage reading is older than maxUsageAgeMin, or has no readable time. None when fresh."""
    max_age = doc.get("maxUsageAgeMin", MAX_USAGE_AGE_MIN)
    if not _is_number(max_age):
        max_age = MAX_USAGE_AGE_MIN
    stamp = _parse_time(usage.get("updated"))
    if stamp is None:
        return "usage has no readable time: run usage push"
    current = now or datetime.datetime.now(datetime.timezone.utc)
    age_min = (current - stamp).total_seconds() / 60
    if age_min <= max_age:
        return None
    age = "%d min" % age_min if age_min < 180 else "%dh" % (age_min // 60)
    return "usage " + age + " old: run usage push"


def _parse_time(text):
    """An ISO 8601 time as an aware datetime (no offset means UTC), or None when it is not a time."""
    if not isinstance(text, str):
        return None
    try:
        stamp = datetime.datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return stamp.replace(tzinfo=datetime.timezone.utc) if stamp.tzinfo is None else stamp


def get(data_dir):
    """The whole budget document: limits, spent and the recorded job ids. A missing file gives the empty shape."""
    records.require_dir(data_dir)
    return _load_doc(data_dir)


def set_limit(data_dir, scope, key, value):
    """Set one limit in thousands of tokens. scope is project, phases, models or tasks. value None clears it."""
    records.require_dir(data_dir)
    with lock.locked(data_dir):
        return set_limit_locked(data_dir, scope, key, value)


def set_limit_locked(data_dir, scope, key, value):
    """set_limit for a caller that already holds the folder lock (the control ops hold it across the write and the
    recompute, so the limit and the control file change together)."""
    records.require_dir(data_dir)
    if scope not in SCOPES:
        raise RoadmapError("usage", "limit scope '" + str(scope) + "' is not valid (allowed: " + "|".join(SCOPES) + ")",
                           EXIT_USAGE)
    if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0):
        raise RoadmapError("usage", "a limit is a number of thousands of tokens, 0 or more, or empty to clear",
                           EXIT_USAGE)
    doc = _load_doc(data_dir)
    limits = doc["limits"]
    if scope == "project":
        limits["project"] = None if value is None else round(float(value), 1)
    else:
        if not records.ID_OK.match(str(key or "")):
            raise RoadmapError("usage", "limit key '" + str(key) + "' is not an id", EXIT_USAGE)
        block = limits.setdefault(scope, {})
        if value is None:
            block.pop(str(key), None)
        else:
            block[str(key)] = round(float(value), 1)
    records.save("budget", data_dir, FILE, doc)
    return doc["limits"]


def update(data_dir, mutate):
    """Run mutate(doc) on the budget document under the folder lock, then save it. Returns mutate's result."""
    records.require_dir(data_dir)
    with lock.locked(data_dir):
        doc = _load_doc(data_dir)
        result = mutate(doc)
        records.save("budget", data_dir, FILE, doc)
    return result


def set_project_limit(data_dir, value, action="block"):
    """Set the project budget in thousands of tokens (None clears it). action warn makes it warn instead of block.
    Returns (prior value, prior action)."""
    if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0):
        raise RoadmapError("usage", "a limit is a number of thousands of tokens, 0 or more, or empty to clear",
                           EXIT_USAGE)

    def mutate(doc):
        prior = (doc["limits"]["project"], doc.get("limitAction"))
        doc["limits"]["project"] = None if value is None else round(float(value), 1)
        if action == "warn" and value is not None:
            doc["limitAction"] = "warn"
        else:
            doc.pop("limitAction", None)
        return prior

    return update(data_dir, mutate)


def record_job_spend(data_dir, job_id, task, model, tokens_k):
    """Add a finished job's tokens to its task and model, and to the usage ledger for its project. Returns True when
    recorded, False when this job id was already counted (nothing changes)."""
    records.require_dir(data_dir)
    wanted = str(job_id or "").strip()
    name = str(model or "").strip()
    amount = _amount(tokens_k)
    if not wanted or not name:
        raise RoadmapError("usage", "a job spend needs a job id and a model", EXIT_USAGE)
    with lock.locked(data_dir):
        doc = _load_doc(data_dir)
        if wanted in doc["jobs"]:
            return False
        row = doc["spent"].setdefault(str(task or UNATTRIBUTED), {})
        row[name] = round(row.get(name, 0.0) + amount, 1)
        doc["jobs"] = (doc["jobs"] + [wanted])[-JOBS_KEEP:]
        records.save("budget", data_dir, FILE, doc)
    _ledger_spend(data_dir, amount)
    return True


def _ledger_spend(data_dir, amount):
    """Add the tokens to the usage ledger under the project that owns this folder. Best effort: the budget is saved."""
    try:
        from roadmap.services import ledger
        project_id = ledger.project_id_for_dir(data_dir)
        if project_id is not None:
            ledger.record_spend(project_id, amount)
    except Exception as exc:  # the spend is recorded in budget.json already; the ledger is derived
        log.warning("usage ledger not updated for a job spend: %s", type(exc).__name__)


def record_task_tokens(data_dir, task_id, model, tokens_k):
    """`task done --tokens` path: record the tokens only when the task has no spend yet. Returns True when recorded."""
    records.require_dir(data_dir)
    name = str(model or "").strip()
    amount = _amount(tokens_k)
    if not str(task_id or "").strip() or not name:
        raise RoadmapError("usage", "a task spend needs a task id and a model", EXIT_USAGE)
    with lock.locked(data_dir):
        doc = _load_doc(data_dir)
        if doc["spent"].get(task_id):
            return False
        doc["spent"][task_id] = {name: round(amount, 1)}
        records.save("budget", data_dir, FILE, doc)
    return True


def _load_doc(data_dir):
    doc = records.load("budget", data_dir, FILE)
    doc.setdefault("spent", {})
    doc.setdefault("jobs", [])
    doc["limits"] = dict(doc.get("limits") or {})
    doc["limits"].setdefault("phases", {})
    doc["limits"].setdefault("models", {})
    doc["limits"].setdefault("tasks", {})
    doc["limits"].setdefault("project", None)
    rows = doc.get("limitRows")
    doc["limitRows"] = list(rows) if isinstance(rows, list) else []  # WP27 limit rows (services/limits.py)
    return doc


def _amount(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value or value < 0:
        raise RoadmapError("usage", "tokens must be a number of thousands, 0 or more", EXIT_USAGE)
    return float(value)
