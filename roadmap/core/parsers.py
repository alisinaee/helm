"""Parsers for tasks.json, jobs.json and autonomy.json.

Each parser takes the file text and returns (data, errors). A bad file never raises: it gives an
errors entry {"file", "error"} and an empty result. Pure functions, no file I/O.
"""

import json
from datetime import datetime

STATES = ("done", "partial", "todo", "hold")
MODELS = ("haiku", "sonnet", "opus", "cursor", "agy")
JOB_STATUSES = ("running", "done", "failed")


def error_entry(name, exc):
    """One errors[] entry for a file that could not be parsed."""
    return {"file": name, "error": f"{type(exc).__name__}: {exc}"}


def parse_ts(s):
    """ISO8601 -> aware datetime, or None for anything unparsable."""
    if not isinstance(s, str):
        return None
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        return None
    return d if d.tzinfo else d.astimezone()


def parse_tasks(text, name="tasks.json"):
    """Phases and tasks from tasks.json text. Returns ({"updated", "phases", "tasks"}, errors)."""
    empty = {"updated": "", "phases": [], "tasks": []}
    try:
        j = json.loads(text)
        if not isinstance(j, dict) or not isinstance(j.get("phases"), list) or not isinstance(j.get("tasks"), list):
            raise ValueError("tasks.json has no phases/tasks arrays")
        phases = []
        for p in j["phases"]:
            st = str(p.get("status", "todo"))
            phases.append({
                "id": str(p["id"]),
                "name": str(p.get("name", p["id"])),
                "state": st if st in STATES else "todo",
            })
        tasks = []
        for t in j["tasks"]:
            st = str(t.get("status", "todo"))
            model = str(t.get("model", ""))
            check = t.get("check")
            note = t.get("note") if isinstance(t.get("note"), str) else None
            state = st if st in STATES else "todo"
            # a hold whose note starts with "Deferred" is parked by project rule, not blocked
            if state == "hold" and note and note.startswith("Deferred"):
                state = "deferred"
            tasks.append({
                "id": str(t["id"]),
                "phase": str(t.get("phase", "")),
                "title": str(t.get("title", "")),
                "state": state,
                "tokensK": float(t.get("tokensK") or 0),
                "thinking": str(t.get("thinking", "")),
                "model": model if model in MODELS else model or "?",
                "needsUser": t.get("needsUser") is True,
                "check": check if check in ("sonnet", "opus") else "none",
                "checkK": float(t.get("checkK") or 0),
                "note": note,
            })
        return {"updated": str(j.get("updated", "")), "phases": phases, "tasks": tasks}, []
    except Exception as exc:  # any malformed input becomes an errors entry
        return empty, [error_entry(name, exc)]


def parse_jobs(text, now, name="jobs.json"):
    """Jobs from jobs.json text. Returns (jobs, errors). Invalid job items are skipped silently."""
    try:
        data = json.loads(text)
    except Exception as exc:
        return [], [error_entry(name, exc)]
    items = data.get("jobs") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return [], [error_entry(name, ValueError("jobs.json has no jobs array"))]
    jobs = []
    for j in items:
        if not isinstance(j, dict) or j.get("status") not in JOB_STATUSES:
            continue
        started = parse_ts(j.get("started"))
        ended = parse_ts(j.get("ended"))
        end = now if j["status"] == "running" else ended
        elapsed = round((end - started).total_seconds(), 1) if started and end else None
        jobs.append({
            "id": str(j.get("id", "")),
            "title": str(j.get("title", "")),
            "model": str(j.get("model", "")),
            "task": j["task"] if isinstance(j.get("task"), str) and j["task"] else None,
            "status": j["status"],
            "started": j.get("started") if isinstance(j.get("started"), str) else None,
            "ended": j.get("ended") if isinstance(j.get("ended"), str) else None,
            "note": j["note"] if isinstance(j.get("note"), str) and j["note"] else None,
            "elapsed_s": max(elapsed, 0.0) if elapsed is not None else None,
            "tokensK": j["tokensK"] if isinstance(j.get("tokensK"), (int, float)) else None,
        })
    return jobs, []


def parse_autonomy(text, name="autonomy.json"):
    """The autonomy object from autonomy.json text. Returns (dict or None, errors); the keys are passed through."""
    try:
        data = json.loads(text)
    except Exception as exc:
        return None, [error_entry(name, exc)]
    if not isinstance(data, dict):
        return None, [error_entry(name, ValueError("autonomy.json is not an object"))]
    return data, []
