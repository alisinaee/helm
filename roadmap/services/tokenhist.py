"""Token history for the Tokens page (R11.6): daily sums by model, totals, per-task sums and the remaining estimate.

Read only. Input is a list of (project id, name, jobs list, tasks doc) so the maths is testable without files;
collect() reads them from the registered projects. Tokens come from jobs that carry measured tokens (R10.32);
units are the cost-weighted units of core/parsers.weighted_units. Days are local calendar days of the job start.

Remaining estimate (an estimate, never a measurement): for every open task (not done, deferred, backlog) the
task's tokensK minus the thousands already spent on it (the job's reported tokensK, else in + out + cacheWrite
of the measured tokens), never below 0. Summed per (project, phase) and overall. Fail-open: collect() never raises.
"""

import time
from datetime import datetime, timedelta

from roadmap.core.parsers import parse_ts, weighted_units

MODELS = ("haiku", "sonnet", "opus", "other")
CLOSED = ("done", "deferred", "backlog")
TOP_TASKS = 60
FIELDS = ("jobs", "in", "out", "cacheRead", "cacheWrite", "units")


def _num(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value == value


def _model(job):
    tokens = job.get("tokens") if isinstance(job.get("tokens"), dict) else {}
    text = str(tokens.get("model") or job.get("model") or "").lower()
    return next((m for m in MODELS[:3] if m in text), "other")


def _blank():
    return {k: 0 for k in FIELDS}


def _add(into, job, tokens):
    into["jobs"] += 1
    if tokens:
        for key in ("in", "out", "cacheRead", "cacheWrite"):
            into[key] += int(tokens[key]) if _num(tokens.get(key)) and tokens[key] > 0 else 0
        into["units"] = round(into["units"] + weighted_units(tokens), 1)


def _spent_k(jobs):
    total = 0.0
    for job in jobs:
        tokens = job.get("tokens") if isinstance(job.get("tokens"), dict) else None
        if _num(job.get("tokensK")) and job["tokensK"] > 0:
            total += job["tokensK"]
        elif tokens:
            total += sum(tokens[k] for k in ("in", "out", "cacheWrite") if _num(tokens.get(k)) and tokens[k] > 0) / 1000
    return total


def build(projects, samples=(), now=None):
    """The history document for [(pid, name, jobs, tasks_doc)]."""
    now = now if now is not None else time.time()
    today = datetime.fromtimestamp(now).astimezone().date()
    week_from = today - timedelta(days=6)
    days = {}
    totals = {"today": _blank(), "d7": _blank(), "all": _blank()}
    by_project = []
    by_task = {}
    by_phase = {}
    phases = []
    first_day = None
    for pid, name, jobs, doc in projects:
        mine = {"id": pid, "name": name, "today": _blank(), "d7": _blank(), "all": _blank()}
        per_task_jobs = {}
        for job in jobs:
            if not isinstance(job, dict):
                continue
            tokens = job.get("tokens") if isinstance(job.get("tokens"), dict) else None
            started = parse_ts(job.get("started"))
            model = _model(job)
            if started is not None:
                day = started.astimezone().date()
                key = day.isoformat()
                cell = days.setdefault(key, {}).setdefault(model, _blank())
                _add(cell, job, tokens)
                if first_day is None or key < first_day:
                    first_day = key
                scopes = ["all"] + (["d7"] if day >= week_from else []) + (["today"] if day == today else [])
            else:
                scopes = ["all"]
            for scope in scopes:
                _add(mine[scope], job, tokens)
                _add(totals[scope], job, tokens)
            task = job.get("task")
            if task:
                per_task_jobs.setdefault(task, []).append(job)
        by_project.append(mine)
        tasks = doc.get("tasks", []) if isinstance(doc, dict) else []
        phase_of = {t.get("id"): t.get("phase") for t in tasks if isinstance(t, dict)}
        for task, rows in per_task_jobs.items():
            agg = by_task.setdefault((pid, task), dict(_blank(), id=task, project=pid, phase=phase_of.get(task) or ""))
            for job in rows:
                _add(agg, job, job.get("tokens") if isinstance(job.get("tokens"), dict) else None)
                if agg["phase"]:
                    row = by_phase.setdefault((pid, agg["phase"]), dict(_blank(), id=agg["phase"], project=pid))
                    _add(row, job, job.get("tokens") if isinstance(job.get("tokens"), dict) else None)
        phases.extend(_remaining(pid, name, doc, per_task_jobs))
    ranked = sorted(by_task.values(), key=lambda r: (-r["units"], -r["jobs"], r["id"]))
    remaining_k = round(sum(p["remainingK"] for p in phases), 1)
    return {
        "generatedAt": datetime.fromtimestamp(now).astimezone().isoformat(timespec="seconds"),
        "today": today.isoformat(),
        "firstDay": first_day,
        "models": list(MODELS),
        "days": [{"d": d, "m": days[d]} for d in sorted(days)],
        "totals": totals,
        "projects": by_project,
        "tasks": ranked[:TOP_TASKS],
        "taskCount": len(ranked),
        "phaseUse": sorted(by_phase.values(), key=lambda r: (-r["units"], r["id"])),
        "phases": phases,
        "remainingK": remaining_k,
        "estimatedK": round(sum(p["estK"] for p in phases), 1),
        "samples": [{"t": int(s["t"]), "wk": s["wk"]} for s in samples if _num(s.get("t")) and _num(s.get("wk"))],
    }


def _remaining(pid, pname, doc, jobs_by_task):
    tasks = [t for t in (doc.get("tasks", []) if isinstance(doc, dict) else []) if isinstance(t, dict)]
    names = {p.get("id"): p.get("name") or p.get("id") for p in (doc.get("phases", []) if isinstance(doc, dict) else [])
             if isinstance(p, dict)}
    rows = {}
    for task in tasks:
        status = str(task.get("status") or "todo")
        phase = task.get("phase") or ""
        if status == "hold" and str(task.get("note") or "").startswith("Deferred"):
            status = "deferred"  # parked by project rule, as core/parsers.py
        if status in CLOSED or not phase:
            continue
        est = float(task["tokensK"]) if _num(task.get("tokensK")) and task["tokensK"] > 0 else 0.0
        spent = _spent_k(jobs_by_task.get(task.get("id"), []))
        row = rows.setdefault(phase, {"project": pid, "projectName": pname, "id": phase,
                                      "name": names.get(phase) or phase, "open": 0, "estK": 0.0, "spentK": 0.0,
                                      "remainingK": 0.0})
        row["open"] += 1
        row["estK"] += est
        row["spentK"] += min(spent, est)
        row["remainingK"] += max(est - spent, 0.0)
    out = []
    for row in rows.values():
        for key in ("estK", "spentK", "remainingK"):
            row[key] = round(row[key], 1)
        out.append(row)
    return out


def collect(entries, project=None, now=None):
    """Read the registered projects ({id, name, data_dir}) and build the document. Never raises."""
    from roadmap.services import jobs as job_service
    from roadmap.services import tasks as task_service
    from roadmap.services import tokenshare
    rows = []
    for entry in entries:
        if project and entry["id"] != project:
            continue
        try:
            data_dir = entry["data_dir"]
            rows.append((entry["id"], entry.get("name") or entry["id"], job_service.list_jobs(data_dir),
                         task_service.load(data_dir)))
        except Exception:
            continue
    try:
        samples = tokenshare.read_samples()
    except Exception:
        samples = []
    return build(rows, samples, now)
