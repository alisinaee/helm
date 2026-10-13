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

MODELS = ("haiku", "sonnet", "opus", "cursor", "agy", "head")
KEEP_FINISHED = 30
JOBS_FILE = "jobs.json"
TASKS_FILE = "tasks.json"
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


def start_job(data_dir, title, model, task=None):
    """Record a new running job and return it. The task, when given, must exist in tasks.json (not_found)."""
    _require_data_dir(data_dir)
    clean_title = _clean_title(title)
    clean_model = _clean_model(model)
    clean_task = _clean_task(task, data_dir)
    with lock.locked(data_dir):
        doc = _read_doc(data_dir)
        job = {"id": _next_id(doc["jobs"]), "title": clean_title, "model": clean_model}
        if clean_task:
            job["task"] = clean_task
        job.update({"status": "running", "started": _now_iso(), "ended": None})
        doc["jobs"].append(job)
        _write_doc(data_dir, doc)
    return dict(job)


def finish_job(data_dir, job_id, status, note=None, tokens_k=None):
    """Mark a running job done or failed, with an optional note and thousands of tokens used.
    Finishing a job that is not running is a conflict (exit 4); an unknown id is not_found (exit 3)."""
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
        job["status"] = status
        job["ended"] = _now_iso()
        if tokens_k is not None:
            job["tokensK"] = round(float(tokens_k), 1)
        if note and str(note).strip():
            job["note"] = str(note).strip()
        _write_doc(data_dir, doc)
    return dict(job)


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


def _clean_model(model):
    text = "" if model is None else str(model).strip()
    if text not in MODELS:
        raise RoadmapError("usage", "model must be one of " + ", ".join(MODELS), EXIT_USAGE)
    return text


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


