"""Parsers for tasks.json, jobs.json and autonomy.json.

Each parser takes the file text and returns (data, errors). A bad file never raises: it gives an
errors entry {"file", "error"} and an empty result. Pure functions, no file I/O.
"""

import json
import re
from datetime import datetime

STATES = ("done", "partial", "todo", "hold")
MODELS = ("haiku", "sonnet", "opus", "cursor", "agy")
JOB_STATUSES = ("running", "done", "failed")
SUBS_MAX = 12                  # subtasks per task
SUB_TITLE_MAX = 80
ISSUE_KINDS = ("bug", "risk", "question", "blocker")
ISSUE_STATUSES = ("open", "doing", "closed", "wontfix")
ISSUE_OPEN = ("open", "doing")
QUESTION_STATUSES = ("open", "answered", "defaulted")
TITLE_MAX = 120
NOTE_MAX = 300
Q_TEXT_MAX = 200
OPTS_MAX = 5
COMMENT_MAX = 280
ACTIVITY_SUM_MAX = 60
FEAT_ID_RE = re.compile(r"^F[1-9][0-9]?$")   # planner feature ids F1..F99
FEATS_MAX = 3                  # features per task


def error_entry(name, exc):
    """One errors[] entry for a file that could not be parsed."""
    return {"file": name, "error": f"{type(exc).__name__}: {exc}"}


def _text(value, limit):
    """A one-line text cut to limit characters, or None when the value is not a string."""
    if not isinstance(value, str):
        return None
    return " ".join(value.split())[:limit]


def _num(value):
    """A finite number (not a bool), or None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if value == value and abs(value) != float("inf") else None


def parse_subs(value, name="tasks.json", task_id="?"):
    """Subtasks from a task's subs list: [{t, d}]. One level only, at most SUBS_MAX, t cut at SUB_TITLE_MAX.
    Returns (subs, errors). Bad items are skipped with an error entry; nothing raises."""
    if not isinstance(value, list):
        return [], [error_entry(name, ValueError("task " + task_id + ": subs is not a list"))]
    subs, errors = [], []
    for index, item in enumerate(value, 1):
        title = _text(item.get("t"), SUB_TITLE_MAX) if isinstance(item, dict) else None
        if not title:
            errors.append(error_entry(name, ValueError("task " + task_id + ": sub " + str(index) + " needs text t")))
            continue
        if len(subs) >= SUBS_MAX:
            errors.append(error_entry(name, ValueError("task " + task_id + ": more than " + str(SUBS_MAX)
                                                       + " subtasks, the rest are ignored")))
            break
        subs.append({"t": title, "d": item.get("d") is True})
    return subs, errors


def parse_feats(value, name="tasks.json", task_id="?"):
    """Feature ids from a task's feats list: at most FEATS_MAX valid ids (F1..F99). The first id is the primary one.
    Returns (feats, errors). Bad ids are skipped with an error entry; nothing raises."""
    if not isinstance(value, list):
        return [], [error_entry(name, ValueError("task " + task_id + ": feats is not a list"))]
    feats, errors = [], []
    for item in value:
        if not isinstance(item, str) or not FEAT_ID_RE.match(item):
            errors.append(error_entry(name, ValueError("task " + task_id + ": " + repr(item)[:40] + " is not a feature id")))
            continue
        if item in feats:
            continue
        if len(feats) >= FEATS_MAX:
            errors.append(error_entry(name, ValueError("task " + task_id + ": more than " + str(FEATS_MAX)
                                                       + " features, the rest are ignored")))
            break
        feats.append(item)
    return feats, errors


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
            phase = {
                "id": str(p["id"]),
                "name": str(p.get("name", p["id"])),
                "state": st if st in STATES else "todo",
            }
            if "approved" in p:
                phase["approved"] = p["approved"] is True
            phases.append(phase)
        tasks = []
        extra_errors = []
        for t in j["tasks"]:
            st = str(t.get("status", "todo"))
            model = str(t.get("model", ""))
            check = t.get("check")
            note = t.get("note") if isinstance(t.get("note"), str) else None
            state = st if st in STATES else "todo"
            # a hold whose note starts with "Deferred" is parked by project rule, not blocked
            if state == "hold" and note and note.startswith("Deferred"):
                state = "deferred"
            task = {
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
            }
            # optional keys (WP20) appear only when the file has them, so an old file parses exactly as before
            if "subs" in t:
                task["subs"], errs = parse_subs(t["subs"], name, task["id"])
                extra_errors.extend(errs)
            if "capK" in t:
                cap = _num(t["capK"])
                if cap is None:
                    extra_errors.append(error_entry(name, ValueError("task " + task["id"] + ": capK is not a number")))
                else:
                    task["capK"] = cap
            if "feats" in t:
                task["feats"], errs = parse_feats(t["feats"], name, task["id"])
                extra_errors.extend(errs)
            tasks.append(task)
        return {"updated": str(j.get("updated", "")), "phases": phases, "tasks": tasks}, extra_errors
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
        job = {
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
        }
        if "parent" in j:
            job["parent"] = j["parent"] if isinstance(j["parent"], str) and j["parent"] else None
        if "role" in j:
            job["role"] = j["role"] if isinstance(j["role"], str) and j["role"] else None
        jobs.append(job)
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


# -------------------------------------------- WP20 files: issues, questions, comments, budget, queue

def _items(text, name, key):
    """The list under key in a JSON object file. Returns (raw_items, errors). Never raises."""
    try:
        data = json.loads(text)
    except Exception as exc:
        return [], [error_entry(name, exc)]
    if not isinstance(data, dict) or not isinstance(data.get(key), list):
        return [], [error_entry(name, ValueError(name + " has no " + key + " array"))]
    return data[key], []


def _each(items, name, normalize):
    """Normalize each item; an item that raises ValueError is skipped with an error entry."""
    out, errors = [], []
    for index, item in enumerate(items, 1):
        try:
            out.append(normalize(item))
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            errors.append(error_entry(name, ValueError("item " + str(index) + ": " + str(exc))))
    return out, errors


def _need(value, what):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(what + " must be text")
    return value.strip()


def _norm_issue(d):
    if not isinstance(d, dict):
        raise ValueError("not an object")
    kind = d.get("kind")
    status = d.get("status")
    sev = d.get("sev")
    if kind not in ISSUE_KINDS:
        raise ValueError("kind '" + str(kind) + "' is not valid")
    if status not in ISSUE_STATUSES:
        raise ValueError("status '" + str(status) + "' is not valid")
    if isinstance(sev, bool) or sev not in (1, 2, 3):
        raise ValueError("sev must be 1, 2 or 3")
    tasks = d.get("tasks") if isinstance(d.get("tasks"), list) else []
    return {
        "id": _need(d.get("id"), "id"),
        "title": _text(d.get("title"), TITLE_MAX) or "",
        "kind": kind,
        "sev": sev,
        "status": status,
        "tasks": [str(t) for t in tasks[:5] if isinstance(t, str)],
        "by": str(d.get("by") or ""),
        "created": d.get("created") if isinstance(d.get("created"), str) else None,
        "closed": d.get("closed") if isinstance(d.get("closed"), str) else None,
        "note": _text(d.get("note"), NOTE_MAX),
    }


def parse_issues(text, name="issues.json"):
    """Issues from issues.json text: (list, errors). Bad items are skipped with an error entry."""
    items, errors = _items(text, name, "issues")
    out, errs = _each(items, name, _norm_issue)
    return out, errors + errs


def _norm_question(d):
    if not isinstance(d, dict):
        raise ValueError("not an object")
    status = d.get("status")
    if status not in QUESTION_STATUSES:
        raise ValueError("status '" + str(status) + "' is not valid")
    opts = d.get("opts") if isinstance(d.get("opts"), list) else []
    timeout = _num(d.get("timeoutS"))
    return {
        "id": _need(d.get("id"), "id"),
        "task": str(d.get("task") or ""),
        "text": _text(d.get("text"), Q_TEXT_MAX) or "",
        "opts": [_text(o, 60) for o in opts[:OPTS_MAX] if _text(o, 60)],
        "def": _text(d.get("def"), 60),
        "block": d.get("block") is True,
        "timeoutS": timeout,
        "status": status,
        "answer": _text(d.get("answer"), Q_TEXT_MAX),
        "asked": d.get("asked") if isinstance(d.get("asked"), str) else None,
        "answered": d.get("answered") if isinstance(d.get("answered"), str) else None,
    }


def parse_questions(text, name="questions.json"):
    """Questions from questions.json text: (list, errors)."""
    items, errors = _items(text, name, "questions")
    out, errs = _each(items, name, _norm_question)
    return out, errors + errs


def _norm_comment(d):
    if not isinstance(d, dict):
        raise ValueError("not an object")
    body = _text(d.get("t"), COMMENT_MAX)
    if not body:
        raise ValueError("comment needs text t")
    return {"on": _need(d.get("on"), "on"), "by": str(d.get("by") or ""),
            "at": d.get("at") if isinstance(d.get("at"), str) else None, "t": body}


def parse_comments(text, name="comments.json"):
    """Comments from comments.json text: (list in file order, errors)."""
    items, errors = _items(text, name, "comments")
    out, errs = _each(items, name, _norm_comment)
    return out, errors + errs


def _norm_queue(d):
    if not isinstance(d, dict):
        raise ValueError("not an object")
    return {"task": _need(d.get("task"), "task"), "by": str(d.get("by") or ""),
            "at": d.get("at") if isinstance(d.get("at"), str) else None}


def parse_queue(text, name="queue.json"):
    """Queue entries from queue.json text: (list, errors)."""
    items, errors = _items(text, name, "entries")
    out, errs = _each(items, name, _norm_queue)
    return out, errors + errs


def parse_budget(text, name="budget.json"):
    """Budget from budget.json text: ({"limits", "spent", "jobs"}, errors). Limits are numbers in thousands of tokens
    (None when unset). Spent is {task: {model: K}}. Bad entries are dropped with an error entry."""
    empty = {"limits": {"project": None, "phases": {}, "models": {}, "tasks": {}}, "spent": {}, "jobs": []}
    try:
        data = json.loads(text)
    except Exception as exc:
        return empty, [error_entry(name, exc)]
    if not isinstance(data, dict):
        return empty, [error_entry(name, ValueError("budget.json is not an object"))]
    errors = []
    raw_limits = data.get("limits") if isinstance(data.get("limits"), dict) else {}
    limits = {"project": _num(raw_limits.get("project"))}
    if raw_limits.get("project") is not None and limits["project"] is None:
        errors.append(error_entry(name, ValueError("limits.project is not a number")))
    for scope in ("phases", "models", "tasks"):
        block = raw_limits.get(scope) if isinstance(raw_limits.get(scope), dict) else {}
        limits[scope] = {}
        for key, value in block.items():
            number = _num(value)
            if number is None:
                errors.append(error_entry(name, ValueError(scope + "." + str(key) + " is not a number")))
            else:
                limits[scope][str(key)] = number
    spent = {}
    raw_spent = data.get("spent") if isinstance(data.get("spent"), dict) else {}
    for task, models in raw_spent.items():
        if not isinstance(models, dict):
            errors.append(error_entry(name, ValueError("spent." + str(task) + " is not an object")))
            continue
        row = {}
        for model, value in models.items():
            number = _num(value)
            if number is None:
                errors.append(error_entry(name, ValueError("spent." + str(task) + "." + str(model)
                                                           + " is not a number")))
            else:
                row[str(model)] = number
        spent[str(task)] = row
    jobs_seen = [str(j) for j in data.get("jobs", []) if isinstance(j, str)] if isinstance(data.get("jobs"), list) \
        else []
    return {"limits": limits, "spent": spent, "jobs": jobs_seen}, errors


def parse_activity(text, name="activity.jsonl"):
    """Activity lines from activity.jsonl text: (list of objects in file order, errors). A bad line adds one entry."""
    lines, bad = [], 0
    for raw in (text or "").splitlines():
        if not raw.strip():
            continue
        try:
            value = json.loads(raw)
        except ValueError:
            bad += 1
            continue
        if isinstance(value, dict):
            lines.append({"id": str(value.get("id", "")), "at": value.get("at"), "src": str(value.get("src", "")),
                          "op": str(value.get("op", "")), "sum": _text(value.get("sum"), ACTIVITY_SUM_MAX) or "",
                          "undo": value.get("undo") is True})
        else:
            bad += 1
    errors = [error_entry(name, ValueError(str(bad) + " line(s) are not JSON objects and were skipped"))] if bad else []
    return lines, errors
