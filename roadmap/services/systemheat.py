"""System map A2: heat per component, from the last 30 days of git history, the running jobs, the open Work items and
the open bug issues.

One read-only `git log --since=30.days --name-only` call (argv list, no shell) gives the commits. Each commit's files
are mapped to components with system.assign_files (the same globs the map uses), so a commit counts once for every
component it touches. A commit subject with task ids (R7.108) links the component to those tasks; a running job, an
open Work item or an open bug issue counts for a component when its task id is one of those tasks.

The parsed history is cached by (project root, HEAD sha); no sha, no cache. Nothing here writes, and a missing git
history never raises: it gives zero heat plus a warning.

Heat per component: {commits30, lastAt (UTC ISO text or null), openWork, runningJobs, bugs}.
"""

import collections
import datetime
import re
import threading

from roadmap.core import workstatus
from roadmap.errors import RoadmapError
from roadmap.services import git, system

DAYS = 30
MAX_COMMITS = 2000
CACHE_MAX = 16
TASK_RE = re.compile(r"\bR\d+(?:\.\d+)*\b")
CLOSED = frozenset({workstatus.DONE, workstatus.WONT_DO})
RECORD = "\x1e"
FIELD = "\x1f"

_CACHE = collections.OrderedDict()
_LOCK = threading.Lock()


def history(project_root, sha=None, use_cache=True):
    """The commits of the last 30 days: {"commits": [{sha, at, subject, tasks, files}], "warnings": [...]}.
    Cached by (project root, sha) when there is a sha. Raises RoadmapError only for a path that is not a folder."""
    root = system._root(project_root)
    if sha is None:
        sha = system._head_sha(root)
    key = (root, sha)
    if use_cache and sha:
        with _LOCK:
            if key in _CACHE:
                _CACHE.move_to_end(key)
                return _CACHE[key]
    commits, warnings = _read_log(root)
    result = {"commits": commits, "warnings": warnings, "sha": sha}
    if use_cache and sha:
        with _LOCK:
            _CACHE[key] = result
            while len(_CACHE) > CACHE_MAX:
                _CACHE.popitem(last=False)
    return result


def _read_log(root):
    fmt = "--format=" + RECORD + "%H" + FIELD + "%at" + FIELD + "%s"
    try:
        text = git.run(root, ["log", "--since=%d.days" % DAYS, "-n", str(MAX_COMMITS), "--name-only", fmt])
    except RoadmapError as err:
        return [], ["git history unavailable: " + str(err)]
    commits = []
    for chunk in text.split(RECORD):
        lines = chunk.split("\n")
        head = lines[0].split(FIELD)
        if not chunk.strip() or len(head) != 3 or not head[1].isdigit():
            continue
        subject = head[2].strip()
        commits.append({"sha": head[0], "at": int(head[1]), "subject": subject,
                        "tasks": sorted(set(TASK_RE.findall(subject))),
                        "files": sorted({line.strip() for line in lines[1:] if line.strip()})})
    warnings = ["history capped at %d commits" % MAX_COMMITS] if len(commits) >= MAX_COMMITS else []
    return commits, warnings


def collect(data_dir):
    """(running jobs, open Work items, open issues) read from one project's data folder. Read only."""
    from roadmap.services import issues as issues_svc
    from roadmap.services import jobs as jobs_svc
    from roadmap.services import work as work_svc
    running = [j for j in jobs_svc.list_jobs(data_dir) if j.get("status") == "running"]
    open_work = [w for w in work_svc.list_views(data_dir) if w.get("status") not in CLOSED]
    open_issues = issues_svc.list_issues(data_dir)
    return running, open_work, open_issues


def build(project_root, components, sha=None, jobs=(), work=(), issues=()):
    """Heat for every component. components are system.load() dicts (id, files globs); jobs, work and issues are
    lists of dicts as collect() returns them (running jobs with "task", Work items with "tasks" and "kind", issues
    with "tasks" and "kind"). Returns {"heat": {id: {...}}, "summary": {...}, "warnings": [...], "sha": sha}."""
    hist = history(project_root, sha)
    commits = hist["commits"]
    specs = [{"id": c["id"], "files": list(c.get("files", []))} for c in components]
    heat = {c["id"]: {"commits30": 0, "lastAt": None, "openWork": 0, "runningJobs": 0, "bugs": 0, "_tasks": set()}
            for c in components}
    owner = {}
    all_files = sorted({f for c in commits for f in c["files"]})
    assigned, unmatched = system.assign_files(all_files, specs)
    for cid, paths in assigned.items():
        for path in paths:
            owner[path] = cid
    untagged = 0
    unmatched_hits = 0
    for commit in commits:
        if not commit["tasks"]:
            untagged += 1
        touched = {owner[f] for f in commit["files"] if f in owner}
        unmatched_hits += sum(1 for f in commit["files"] if f not in owner)
        for cid in touched:
            row = heat[cid]
            row["commits30"] += 1
            row["lastAt"] = max(row["lastAt"] or 0, commit["at"])
            row["_tasks"].update(commit["tasks"])
    for job in jobs:
        if job.get("status") == "running" and job.get("task"):
            for row in heat.values():
                if job["task"] in row["_tasks"]:
                    row["runningJobs"] += 1
    for item in work:
        if item.get("status") in CLOSED:
            continue
        for row in heat.values():
            if row["_tasks"] & set(item.get("tasks") or []):
                row["openWork"] += 1
                if item.get("kind") == "bug":
                    row["bugs"] += 1
    for issue in issues:
        if issue.get("status") not in ("open", "doing") or issue.get("kind") != "bug":
            continue
        for row in heat.values():
            if row["_tasks"] & set(issue.get("tasks") or []):
                row["bugs"] += 1
    out = {}
    for cid, row in heat.items():
        last = row["lastAt"]
        out[cid] = {"commits30": row["commits30"],
                    "lastAt": datetime.datetime.fromtimestamp(last, datetime.timezone.utc).strftime(
                        "%Y-%m-%dT%H:%M:%SZ") if last else None,
                    "openWork": row["openWork"], "runningJobs": row["runningJobs"], "bugs": row["bugs"]}
    summary = {"days": DAYS, "commits": len(commits), "untagged": untagged,
               "unmatchedFiles": unmatched_hits, "unmatchedPaths": len(unmatched)}
    return {"heat": out, "summary": summary, "warnings": list(hist["warnings"]), "sha": hist["sha"]}
