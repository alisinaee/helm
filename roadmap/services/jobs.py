"""Job registry in each project's data folder (jobs.json): start, finish, list and prune.

Ported from split-net's tools/roadmap-web/jobs.py. Writes take the directory lock, re-read the file inside it,
and save atomically at the current schemaVersion. A corrupt or newer file stops the command and is never
overwritten. This module also resolves which registered project a command or hook acts on.
"""

import datetime
import math
import os
import re

from roadmap.errors import EXIT_CONFLICT, EXIT_INVALID_DATA, EXIT_NOT_FOUND, EXIT_USAGE, RoadmapError
from roadmap.store import atomic, config, lock, schema

MODELS = ("haiku", "sonnet", "opus", "cursor", "agy", "opencode", "head", "unknown")
EFFORTS = ("low", "medium", "high", "xhigh", "max")
KEEP_FINISHED = 200
PARENT_ENV = "ROADMAP_PARENT_JOB"
JOBS_FILE = "jobs.json"
TASKS_FILE = "tasks.json"
COMMIT_REF = "commit:"
TITLE_MAX = 200
_ID_RE = re.compile(r"^j(\d+)$")
_EPOCH = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)


def data_dir_of(project):
    """The absolute data folder of a registered project entry (its path joined with dataDir)."""
    return os.path.join(os.path.abspath(project["path"]), project.get("dataDir") or "docs")


def jobs_path(data_dir):
    return os.path.join(data_dir, JOBS_FILE)


def resolve_project(explicit=None, environ=None, cwd=None):
    """Return the registered project a command acts on. Order: explicit id, $ROADMAP_PROJECT, then the registered
    project whose folder contains cwd (the longest match wins). Unknown ids and no match give not_found (exit 3)."""
    environ = os.environ if environ is None else environ
    wanted = (explicit or environ.get("ROADMAP_PROJECT", "") or "").strip()
    projects = config.list_projects()
    if wanted:
        for project in projects:
            if project["id"] == wanted:
                return project
        raise RoadmapError("not_found", "no registered project with id '" + wanted + "'", EXIT_NOT_FOUND)
    here = os.path.realpath(cwd or os.getcwd())
    best = None
    best_len = -1
    for project in projects:
        root = os.path.realpath(project["path"])
        inside = here == root or here.startswith(root.rstrip(os.sep) + os.sep)
        if inside and len(root) > best_len:
            best, best_len = project, len(root)
    if best is None:
        raise RoadmapError("not_found", "no registered project contains this folder; pass --project <id> "
                           "or set ROADMAP_PROJECT", EXIT_NOT_FOUND)
    return best


def known_task_ids(data_dir):
    """The set of task ids in the project's tasks.json. A missing file gives an empty set; bad JSON is invalid_data."""
    raw = atomic.read_json(os.path.join(data_dir, TASKS_FILE), default=None)
    if raw is None:
        return set()
    tasks = raw.get("tasks") if isinstance(raw, dict) else None
    if not isinstance(tasks, list):
        raise RoadmapError("invalid_data", "tasks.json has no 'tasks' list: " + data_dir, EXIT_INVALID_DATA)
    return {t["id"] for t in tasks if isinstance(t, dict) and isinstance(t.get("id"), str)}


def start_job(data_dir, title, model, task=None, parent=None, role=None, environ=None, effort=None, engine_model=None):
    """Record a new running job and return it. The task, when given, must exist in tasks.json (not_found).
    parent is the id of an existing job (the lead); role is lead or worker and needs a parent.
    With no parent given, the parent is $ROADMAP_PARENT_JOB (environ, default os.environ). A worker with no parent
    and exactly one running lead (role lead, or model head) gets that lead as its parent."""
    _require_data_dir(data_dir)
    clean_title = _clean_title(title)
    clean_model = _clean_model(model)
    clean_task = _clean_task(task, data_dir)
    clean_effort = _clean_effort(effort)
    clean_engine = "" if engine_model is None else str(engine_model).strip()[:TITLE_MAX]
    with lock.locked(data_dir):
        doc = _read_doc(data_dir)
        clean_parent = _resolve_parent(parent, role, doc["jobs"], environ)
        clean_role = _clean_role(role, clean_parent)
        job = {"id": _next_id(doc["jobs"]), "title": clean_title, "model": clean_model}
        if clean_task:
            job["task"] = clean_task
        if clean_effort:
            job["effort"] = clean_effort
        if clean_engine:
            job["engine_model"] = clean_engine
        if clean_parent:
            job["parent"] = clean_parent
            job["role"] = clean_role
        job.update({"status": "running", "started": _now_iso(), "ended": None})
        doc["jobs"].append(job)
        _write_doc(data_dir, doc)
        if clean_task:
            _mark_partial(data_dir, clean_task)
    return dict(job)


def task_records(data_dir):
    """Every task dict in tasks.json (read only). A missing file gives an empty list; a newer or bad file raises."""
    data, error = schema.read_data("tasks", os.path.join(data_dir, TASKS_FILE))
    if error is not None:
        raise RoadmapError("newer_schema", error["message"], EXIT_INVALID_DATA)
    if data is None:
        return []
    if not isinstance(data.get("tasks"), list):
        raise RoadmapError("invalid_data", "tasks.json has no 'tasks' list", EXIT_INVALID_DATA)
    return [dict(t) for t in data["tasks"] if isinstance(t, dict)]


def bind_commit(data_dir, sha, task_ids):
    """Attach commit:<sha> to each known task named in task_ids and to the running job of that task. A commit
    never changes a task status: the person or the head marks it done. Returns the bound task ids in order.
    Adding the same commit twice changes nothing."""
    _require_data_dir(data_dir)
    known = known_task_ids(data_dir)
    wanted = [t for t in dict.fromkeys(task_ids) if t in known]
    if not wanted:
        return []
    ref = COMMIT_REF + str(sha).strip()
    with lock.locked(data_dir):
        path = os.path.join(data_dir, TASKS_FILE)
        tdoc = schema.read_data("tasks", path)[0]
        if tdoc is not None:
            for task in tdoc.get("tasks") or []:
                if isinstance(task, dict) and task.get("id") in wanted:
                    refs = task.setdefault("refs", [])
                    if ref not in refs:
                        refs.append(ref)
                        schema.write_data("tasks", path, tdoc)
        doc = _read_doc(data_dir)
        changed = False
        for job in doc["jobs"]:
            if isinstance(job, dict) and job.get("status") == "running" and job.get("task") in wanted:
                refs = job.setdefault("refs", [])
                if ref not in refs:
                    refs.append(ref)
                    changed = True
        if changed:
            _write_doc(data_dir, doc)
    return wanted


def _mark_partial(data_dir, task_id):
    """A todo task that a job starts on becomes partial (doing). Other statuses are left alone."""
    path = os.path.join(data_dir, TASKS_FILE)
    data, error = schema.read_data("tasks", path)
    if error is not None or data is None or not isinstance(data.get("tasks"), list):
        return
    for task in data["tasks"]:
        if isinstance(task, dict) and task.get("id") == task_id and task.get("status") == "todo":
            task["status"] = "partial"
            schema.write_data("tasks", path, data)
            return


def finish_job(data_dir, job_id, status, note=None, tokens_k=None):
    """Mark a running job done or failed, with an optional note and thousands of tokens used.
    Finishing a job that is not running is a conflict (exit 4); an unknown id is not_found (exit 3).
    tokens_k is the final total of the job. Progress already counted (progressK) is not counted again: the budget
    takes tokens_k minus progressK (see budget_remainder). A total below the counted progress is a usage error."""
    _require_data_dir(data_dir)
    if status not in ("done", "failed"):
        raise RoadmapError("usage", "status must be done or failed", EXIT_USAGE)
    wanted = str(job_id or "").strip()
    with lock.locked(data_dir):
        doc = _read_doc(data_dir)
        job = _find(doc["jobs"], wanted)
        if job.get("status") != "running":
            raise RoadmapError("conflict", wanted + " is already " + str(job.get("status")) + "; not changed",
                               EXIT_CONFLICT)
        counted = _counted(job)
        if tokens_k is not None and float(tokens_k) < counted:
            raise RoadmapError("usage", wanted + " already counted " + _fmt_k(counted) + " of progress; --tokens "
                               "must be the job's final total, at least that", EXIT_USAGE)
        job["status"] = status
        job["ended"] = _now_iso()
        if tokens_k is not None:
            job["tokensK"] = round(float(tokens_k), 1)
        if note and str(note).strip():
            job["note"] = str(note).strip()
        _write_doc(data_dir, doc)
    return dict(job)


def progress_job(data_dir, job_id, tokens_k):
    """Record the live tokens of a running job (thousands). Returns (job, new_k) where new_k is the amount that is
    not yet counted in the budget: tokens_k minus the progress already counted, zero when nothing moved.
    The job's tokensK shows the reading while it runs. A reading below the counted progress, or on a job that is not
    running, is refused and nothing changes (usage, conflict)."""
    _require_data_dir(data_dir)
    wanted = str(job_id or "").strip()
    value = _progress_value(tokens_k)
    with lock.locked(data_dir):
        doc = _read_doc(data_dir)
        job = _find(doc["jobs"], wanted)
        if job.get("status") != "running":
            raise RoadmapError("conflict", wanted + " is already " + str(job.get("status")) + "; progress needs a "
                               "running job", EXIT_CONFLICT)
        counted = _counted(job)
        if value < counted:
            raise RoadmapError("usage", "progress cannot go down: " + wanted + " already counted " + _fmt_k(counted),
                               EXIT_USAGE)
        new_k = round(value - counted, 1)
        if new_k > 0:
            job["progressK"] = round(value, 1)
            job["tokensK"] = round(value, 1)
            _write_doc(data_dir, doc)
    return dict(job), new_k


def list_jobs(data_dir):
    """Return every job record in file order. A corrupt file is invalid_data (exit 5)."""
    _require_data_dir(data_dir)
    return [dict(j) for j in _read_doc(data_dir)["jobs"] if isinstance(j, dict)]


def prune_jobs(data_dir):
    """Drop finished jobs beyond the newest KEEP_FINISHED. Running jobs are always kept. Returns (removed, kept)."""
    _require_data_dir(data_dir)
    with lock.locked(data_dir):
        doc = _read_doc(data_dir)
        jobs = doc["jobs"]
        running = [j for j in jobs if isinstance(j, dict) and j.get("status") == "running"]
        finished = [j for j in jobs if isinstance(j, dict) and j.get("status") != "running"]
        finished.sort(key=_finish_key, reverse=True)
        keep = {id(j) for j in running + finished[:KEEP_FINISHED]}
        kept = [j for j in jobs if not isinstance(j, dict) or id(j) in keep]
        removed = len(jobs) - len(kept)
        if removed:
            doc["jobs"] = kept
            _write_doc(data_dir, doc)
    return removed, len(kept)


# ---------------------------------------------------------------- helpers

def _require_data_dir(data_dir):
    if not os.path.isdir(data_dir):
        raise RoadmapError("not_found", "data folder does not exist: " + data_dir, EXIT_NOT_FOUND)


def _read_doc(data_dir):
    """Return the whole jobs.json document with a 'jobs' list. A missing file gives an empty list."""
    path = jobs_path(data_dir)
    data, error = schema.read_data("jobs", path)
    if error is not None:
        raise RoadmapError("newer_schema", error["message"], EXIT_INVALID_DATA)
    if data is None:
        return {"jobs": []}
    if not isinstance(data.get("jobs"), list):
        raise RoadmapError("invalid_data", "jobs.json has no 'jobs' list; fix or remove it, then retry: " + path,
                           EXIT_INVALID_DATA)
    return data


def _write_doc(data_dir, doc):
    schema.write_data("jobs", jobs_path(data_dir), doc)


def _counted(job):
    """The progress already counted for a job (thousands). A missing or odd value counts as zero."""
    value = job.get("progressK")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value or value < 0:
        return 0.0
    return float(value)


def budget_remainder(job, tokens_k):
    """The thousands of tokens a finished job adds to the budget: its final total minus the progress counted."""
    return round(max(float(tokens_k) - _counted(job), 0.0), 1)


def _progress_value(value):
    """Parse a progress reading (thousands of tokens): a finite number of zero or more."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise RoadmapError("usage", "--tokens needs a number (thousands of tokens)", EXIT_USAGE)
    if not math.isfinite(number) or number < 0:
        raise RoadmapError("usage", "--tokens must be a number of zero or more (thousands of tokens)", EXIT_USAGE)
    return number


def _fmt_k(value):
    return ("%g" % round(value, 1)) + "k"


def _next_id(jobs):
    nums = []
    for job in jobs:
        if isinstance(job, dict):
            match = _ID_RE.match(str(job.get("id", "")))
            if match:
                nums.append(int(match.group(1)))
    return "j" + str(max(nums, default=0) + 1)


def _find(jobs, job_id):
    for job in jobs:
        if isinstance(job, dict) and job.get("id") == job_id:
            return job
    raise RoadmapError("not_found", "no job with id '" + job_id + "'", EXIT_NOT_FOUND)


def _clean_title(title):
    text = "" if title is None else str(title).strip()
    if not text:
        raise RoadmapError("usage", "the job title must not be empty", EXIT_USAGE)
    return text[:TITLE_MAX]


def _clean_effort(effort):
    """The thinking effort of a job: empty (the default, nothing stored) or one of EFFORTS."""
    text = "" if effort is None else str(effort).strip()
    if text and text not in EFFORTS:
        raise RoadmapError("usage", "effort must be one of " + ", ".join(EFFORTS), EXIT_USAGE)
    return text


def _clean_model(model):
    text = "" if model is None else str(model).strip()
    if text not in MODELS:
        raise RoadmapError("usage", "model must be one of " + ", ".join(MODELS), EXIT_USAGE)
    return text


ROLES = ("lead", "worker")


def _clean_role(role, parent):
    if role is None or not str(role).strip():
        return None
    text = str(role).strip()
    if text not in ROLES:
        raise RoadmapError("usage", "role must be lead or worker", EXIT_USAGE)
    if not (parent and str(parent).strip()):
        raise RoadmapError("usage", "--role needs --parent JOB_ID", EXIT_USAGE)
    return text


def _clean_parent(parent, jobs):
    if parent is None or not str(parent).strip():
        return None
    text = str(parent).strip()
    _find(jobs, text)
    return text


def _resolve_parent(parent, role, jobs_list, environ):
    """The parent job id for a new job: an explicit parent, else $ROADMAP_PARENT_JOB, else (worker only) the one
    running lead. Returns None when there is none. An unknown id is not_found, as for --parent."""
    explicit = str(parent).strip() if parent is not None else ""
    if not explicit:
        env = os.environ if environ is None else environ
        explicit = str(env.get(PARENT_ENV, "") or "").strip()
    if not explicit and str(role or "").strip() == "worker":
        return _sole_running_lead(jobs_list)
    return _clean_parent(explicit or None, jobs_list)


def _sole_running_lead(jobs_list):
    """The id of the only running job that is a lead (role lead, or model head), or None when there are zero or
    several of them."""
    leads = [j for j in jobs_list if isinstance(j, dict) and j.get("status") == "running"
             and (j.get("role") == "lead" or j.get("model") == "head")]
    return str(leads[0].get("id")) if len(leads) == 1 else None


def _clean_task(task, data_dir):
    if task is None or not str(task).strip():
        return None
    text = str(task).strip()
    if text not in known_task_ids(data_dir):
        raise RoadmapError("not_found", "task '" + text + "' is not in tasks.json", EXIT_NOT_FOUND)
    return text


def _finish_key(job):
    return _parse_ts(job.get("ended")) or _parse_ts(job.get("started")) or _EPOCH


def _parse_ts(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.astimezone()


def _now_iso():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def tokens_from_arg(value):
    """Parse the --tokens value (thousands of tokens). Must be a finite number of zero or more."""
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise RoadmapError("usage", "--tokens needs a number (thousands of tokens)", EXIT_USAGE)
    if not math.isfinite(number) or number < 0:
        raise RoadmapError("usage", "--tokens must be a number of zero or more (thousands of tokens)", EXIT_USAGE)
    return number


