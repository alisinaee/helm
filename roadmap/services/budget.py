"""Budget (budget.json): limits in thousands of tokens and the spend per task and model.

A job's tokens are recorded once per job id (idempotent; the last 500 job ids are remembered). The task-level
`task done --tokens` path records spend only when the task has no spend yet, so one piece of work is counted once.
"""

from roadmap.errors import EXIT_USAGE, RoadmapError
from roadmap.log import get_logger
from roadmap.services import records
from roadmap.store import lock

log = get_logger("services.budget")
FILE = "budget.json"
JOBS_KEEP = 500
SCOPES = ("project", "phases", "models", "tasks")
UNATTRIBUTED = "-"


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
