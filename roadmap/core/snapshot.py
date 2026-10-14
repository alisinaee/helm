"""Build the roadmap snapshot: the dict the dashboard renders, from the texts of a project's data files.

build_snapshot(files, config, now) is pure. files maps a file name (tasks.json, jobs.json, autonomy.json
and the extras files) to its text, or to None when the file is missing. config is the parsed
roadmap.config.json. now is the moment to measure running jobs and the recent window from.
"""

import json
from datetime import timedelta

from roadmap.core import features as feature_rules
from roadmap.core.extras import parse_extras
from roadmap.core.parsers import (ISSUE_OPEN, error_entry, parse_activity, parse_autonomy, parse_budget,
                                  parse_comments, parse_issues, parse_jobs, parse_questions, parse_queue, parse_tasks,
                                  parse_ts)

SNAPSHOT_SCHEMA_VERSION = 1
PHASE_WEIGHT = {"done": 1.0, "partial": 0.5}
ACTIVE = ("todo", "partial")                        # task states counted as "left"
RECENT_WINDOW = timedelta(minutes=30)               # finished jobs shown under their task
RECENT_MAX = 2
ACTIVITY_SHOWN = 15                                 # log lines on the Overview
COMMENTS_SHOWN = 3                                  # newest comments per target
WORKFLOW_SPANS = 200                                # newest job spans in the workflow key
WORKFLOW_DAYS = timedelta(days=7)                   # jobs that ended (or started) longer ago are dropped
AFTER_MAX = 5                                       # most task ids in one after list


def _missing(name):
    return error_entry(name, FileNotFoundError("file not found"))


def _read_optional(files, name, parse, errors):
    """The parsed value of an optional WP20 file, or None when the file is missing (a missing file adds no error)."""
    text = files.get(name)
    if text is None:
        return None
    value, errs = parse(text, name)
    errors.extend(errs)
    return value


def _budget_view(doc, tasks, phases):
    """Limits, spend and percent of limit per total, phase, model and task. Spend is in thousands of tokens.
    Percent is None when there is no limit. Spend on '-' (no task) counts in the total and models only."""
    limits = doc["limits"]
    spent = doc["spent"]
    task_phase = {t["id"]: t["phase"] for t in tasks if t.get("id") and t.get("phase")}

    def row(amount, limit):
        pct = round(100.0 * amount / limit, 1) if limit else None
        return {"spent": round(amount, 1), "limit": limit, "pct": pct}

    task_spent = {tid: sum(models.values()) for tid, models in spent.items()}
    model_spent = {}
    phase_spent = {}
    for tid, models in spent.items():
        for model, amount in models.items():
            model_spent[model] = model_spent.get(model, 0.0) + amount
        if tid != "-":
            pid = task_phase.get(tid) or tid.split(".")[0]
            phase_spent[pid] = phase_spent.get(pid, 0.0) + task_spent[tid]
    phase_ids = [p["id"] for p in phases] + [k for k in list(limits["phases"]) + list(phase_spent)
                                              if k not in [p["id"] for p in phases]]
    model_ids = sorted(set(model_spent) | set(limits["models"]))
    task_ids = sorted(set(task_spent) | set(limits["tasks"]))
    return {
        "limits": limits,
        "total": row(sum(task_spent.values()), limits.get("project")),
        "phases": {pid: row(phase_spent.get(pid, 0.0), limits["phases"].get(pid)) for pid in phase_ids},
        "models": {m: row(model_spent.get(m, 0.0), limits["models"].get(m)) for m in model_ids},
        "tasks": {tid: row(task_spent.get(tid, 0.0), limits["tasks"].get(tid)) for tid in task_ids},
        "spent": spent,
    }


def _round_k(value):
    return round(float(value), 1) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _span(job):
    """One job as a compact list: [id, task, model, role, parent, startEpoch, endEpoch|null, status, tokensK]."""
    start = parse_ts(job.get("started"))
    end = None if job["status"] == "running" else parse_ts(job.get("ended"))
    return [job["id"], job.get("task"), job.get("model") or None, job.get("role"), job.get("parent"),
            int(start.timestamp()), int(end.timestamp()) if end else None, job["status"],
            _round_k(job.get("tokensK"))]


def _features_view(text, tasks, jobs_list, issues_open, errors):
    """The features key (WP52): rows, uncovered, orphans and counts from docs/features.json text. Absent text is an
    empty derive. Bad JSON or a bad feature goes into errors; nothing raises."""
    raw = []
    if text is not None:
        try:
            doc = json.loads(text)
            raw = doc.get("features") if isinstance(doc, dict) else None
            if not isinstance(raw, list):
                raw = []
                errors.append(error_entry("features.json", ValueError("features.json has no features array")))
        except ValueError as exc:
            errors.append(error_entry("features.json", exc))
    view = feature_rules.derive(raw, tasks, jobs_list, issues_open)
    errors.extend({"file": "features.json", "error": message} for message in view["errors"])
    return {key: view[key] for key in ("rows", "uncovered", "orphans", "counts")}


def _after_edges(tasks_text, known):
    """[from, to] pairs from each task's after list in the raw tasks.json text: from is the task waited for, to the
    waiting task. Only ids that are tasks in this file count; a bad file gives no edges."""
    try:
        raw = json.loads(tasks_text) if tasks_text else {}
    except ValueError:
        return []
    items = raw.get("tasks") if isinstance(raw, dict) else None
    edges = []
    for task in items if isinstance(items, list) else []:
        if not isinstance(task, dict) or task.get("id") not in known or not isinstance(task.get("after"), list):
            continue
        for dep in task["after"][:AFTER_MAX]:
            if isinstance(dep, str) and dep in known:
                edges.append([dep, task["id"]])
    return edges


def _workflow_view(jobs, issues_open, tasks_text, task_ids, moment):
    """The workflow key: the newest job spans (at most WORKFLOW_SPANS, in start order, jobs older than WORKFLOW_DAYS
    dropped) and the edges: after from tasks.json, and block from open blocker issues to their tasks."""
    cutoff = moment - WORKFLOW_DAYS
    spans = []
    for job in jobs:
        start = parse_ts(job.get("started"))
        if start is None:
            continue
        last = parse_ts(job.get("ended")) if job["status"] != "running" else None
        if (last or start) < cutoff:
            continue
        spans.append((start, _span(job)))
    spans.sort(key=lambda pair: pair[0])
    block = [[issue["id"], tid] for issue in issues_open if issue["kind"] == "blocker"
             for tid in issue["tasks"] if tid in task_ids]
    return {"spans": [row for _, row in spans[-WORKFLOW_SPANS:]],
            "edges": {"after": _after_edges(tasks_text, task_ids), "block": block}}


def build_snapshot(files, config, now, control=None, meters=None, rules=None):
    """The snapshot dict. Same shape as the old server's build(), plus "project" and "schemaVersion".
    meters (WP27: limits, today, week) is added only when given, so a snapshot built without it is unchanged.
    rules (WP33b: the parsed docs/rules.txt list) is added only when given, for the same reason.

    server_time is now in ISO 8601 with whole seconds. Parse problems go into errors[]; nothing raises.
    """
    config = config if isinstance(config, dict) else {}
    files = files if isinstance(files, dict) else {}
    moment = now if now.tzinfo else now.astimezone()
    errors = []

    # a missing jobs.json is normal (no job has run yet), so it adds no error; a bad one does
    jobs_text = files.get("jobs.json")
    if jobs_text is None:
        jobs = []
    else:
        jobs, errs = parse_jobs(jobs_text, moment)
        errors.extend(errs)

    out = {
        "server_time": moment.isoformat(timespec="seconds"),
        "errors": errors,
        "jobs": jobs,
        "project": {"id": str(config.get("id") or ""), "title": str(config.get("title") or "")},
        "schemaVersion": SNAPSHOT_SCHEMA_VERSION,
    }

    tasks_text = files.get("tasks.json")
    if tasks_text is None:
        tasks_updated, phases, tasks = "", [], []
        errors.append(_missing("tasks.json"))
    else:
        parsed, errs = parse_tasks(tasks_text)
        errors.extend(errs)
        tasks_updated, phases, tasks = parsed["updated"], parsed["phases"], parsed["tasks"]

    def cost(ts):
        return round(sum(t["tokensK"] + t["checkK"] for t in ts), 1)

    task_phase = {t["id"]: t["phase"] for t in tasks if t.get("id") and t.get("phase")}

    def phase_of(j):
        # A job's task id is looked up in tasks.json first (L-, S- and P-tasks);
        # the old "P2.17" prefix rule is the fallback.
        tid = j.get("task")
        if not tid:
            return None
        return task_phase.get(tid) or tid.split(".")[0]

    def ended_recently(j):
        e = parse_ts(j.get("ended"))
        return j["status"] != "running" and e is not None and moment - e <= RECENT_WINDOW

    running_jobs = [j for j in jobs if j["status"] == "running"]
    recent_jobs = [j for j in jobs if ended_recently(j)]

    for p in phases:
        ts = [t for t in tasks if t["phase"] == p["id"]]
        live = [t for t in ts if t["state"] != "deferred"]          # deferred never counts
        deferred = [t for t in ts if t["state"] == "deferred"]
        active = [t for t in live if t["state"] in ACTIVE]
        p["total"] = len(live)
        p["done"] = sum(1 for t in live if t["state"] == "done")
        p["deferred"] = len(deferred)
        p["deferred_k"] = cost(deferred)
        p["only_deferred"] = not live and bool(deferred)
        if live:
            p["progress"] = sum(PHASE_WEIGHT.get(t["state"], 0.0) for t in live) / len(live)
        elif deferred:
            p["progress"] = None                                    # shown as "deferred", no percent
        else:
            p["progress"] = 1.0 if p["state"] == "done" else 0.0
        p["remaining_k"] = cost(active)
        p["running"] = [j["id"] for j in running_jobs if phase_of(j) == p["id"]]
        recent = sorted((j for j in recent_jobs if phase_of(j) == p["id"]),
                        key=lambda j: parse_ts(j["ended"]), reverse=True)
        p["recent"] = [j["id"] for j in recent[:RECENT_MAX]]

    autonomy_text = files.get("autonomy.json")
    autonomy = None
    if autonomy_text is not None:
        autonomy, errs = parse_autonomy(autonomy_text)
        errors.extend(errs)

    extras, errs = parse_extras(config.get("extras"), files)
    errors.extend(errs)
    spikes, rh, nxt, log = extras["spikes"], extras["rh"], extras["next"], extras["log"]

    # "left" = todo + partial only: deferred tasks and other holds are parked, not left to do
    open_t = [t for t in tasks if t["state"] in ACTIVE]
    deferred_t = [t for t in tasks if t["state"] == "deferred"]
    summary = {
        "tasks_total": sum(1 for t in tasks if t["state"] != "deferred"),
        "tasks_left": len(open_t),
        "tokens_left_k": cost(open_t),
        "work_haiku_k": round(sum(t["tokensK"] for t in open_t if t["model"] == "haiku"), 1),
        "work_other_k": round(sum(t["tokensK"] for t in open_t if t["model"] not in ("haiku", "cursor", "agy")), 1),
        "work_cursor_k": round(sum(t["tokensK"] for t in open_t if t["model"] == "cursor"), 1),
        "work_agy_k": round(sum(t["tokensK"] for t in open_t if t["model"] == "agy"), 1),
        "check_sonnet_k": round(sum(t["checkK"] for t in open_t if t["check"] == "sonnet"), 1),
        "check_opus_k": round(sum(t["checkK"] for t in open_t if t["check"] == "opus"), 1),
        "need_user": sum(1 for t in open_t if t["needsUser"]),
        "deferred_count": len(deferred_t),
        "deferred_tokens_k": cost(deferred_t),
        "running_count": len(running_jobs),
        "autonomy": autonomy,
        "tokens_done_k": cost([t for t in tasks if t["state"] == "done"]),
        "tokens_partial_k": cost([t for t in tasks if t["state"] == "partial"]),
        "tokens_roadmap_k": cost([t for t in tasks if t["state"] != "deferred"]),
        "jobs_tokens_k": round(sum(j["tokensK"] or 0 for j in jobs), 1),
        "jobs_with_tokens": sum(1 for j in jobs if j["tokensK"]),
    }

    def project_progress(all_tasks):
        """Whole-project progress over every non-deferred task: done, partial, todo and the weighted percent."""
        live_all = [t for t in all_tasks if t["state"] != "deferred"]
        n = len(live_all)
        done = sum(1 for t in live_all if t["state"] == "done")
        part = sum(1 for t in live_all if t["state"] == "partial")
        prog = (sum(PHASE_WEIGHT.get(t["state"], 0.0) for t in live_all) / n) if n else 0.0
        return {"done": done, "partial": part, "todo": n - done - part, "total": n, "progress": round(prog, 4)}

    def ratio(done, total):
        return {"done": done, "total": total, "ratio": round(done / total, 4) if total else 0.0}

    out.update({
        "tasks_updated": tasks_updated,
        "summary": summary,
        "overall": {
            "project": project_progress(tasks),
            "phases": ratio(sum(1 for p in phases if p["state"] == "done"), len(phases)),
            "spikes": ratio(sum(1 for s in spikes if s["state"] == "done"), len(spikes)),
            "rh": ratio(sum(1 for r in rh if r["state"] == "done"), len(rh)),
        },
        "phases": phases,
        "tasks": tasks,
        "spikes": spikes,
        "rh": rh,
        "next": nxt,
        "log": log,
    })

    # WP20 keys. A project without the new files gets them empty (budget gets {} when budget.json is missing).
    issues_all = _read_optional(files, "issues.json", parse_issues, errors) or []
    questions_all = _read_optional(files, "questions.json", parse_questions, errors) or []
    comments_all = _read_optional(files, "comments.json", parse_comments, errors) or []
    queue_all = _read_optional(files, "queue.json", parse_queue, errors) or []
    activity_all = _read_optional(files, "activity.jsonl", parse_activity, errors) or []
    budget_doc = _read_optional(files, "budget.json", parse_budget, errors)

    issues_open = [i for i in issues_all if i["status"] in ISSUE_OPEN]
    questions_open = [q for q in questions_all if q["status"] == "open"]
    blocked = sorted({tid for i in issues_open if i["kind"] == "blocker" for tid in i["tasks"]})
    by_target = {}
    for comment in comments_all:
        by_target.setdefault(comment["on"], []).append(comment)
    needs_you = ([{"kind": "task", "id": t["id"], "title": t["title"]}
                  for t in tasks if t["needsUser"] and t["state"] in ACTIVE]
                 + [{"kind": "question", "id": q["id"], "text": q["text"]} for q in questions_open if q["block"]])
    running_ids = {j["id"] for j in running_jobs}
    running_rows = [{"id": j["id"], "title": j["title"], "model": j["model"], "task": j["task"],
                     "role": j.get("role"), "parent": j.get("parent"), "elapsed_s": j["elapsed_s"],
                     "tokensK": j["tokensK"]} for j in running_jobs]
    groups = {}
    for j in running_jobs:
        if j.get("parent") in running_ids:
            groups.setdefault(j["parent"], []).append(j["id"])
    out.update({
        "workflow": _workflow_view(jobs, issues_open, tasks_text, {t["id"] for t in tasks}, moment),
        "issues": issues_open,
        "questions": questions_open,
        "comments": {target: rows[-COMMENTS_SHOWN:] for target, rows in by_target.items()},
        "budget": {} if budget_doc is None else _budget_view(budget_doc, tasks, phases),
        "features": _features_view(files.get("features.json"), tasks, jobs, issues_open, errors),
        "blocked": blocked,
        "needsYou": needs_you,
        "agents": {"running": running_rows, "groups": groups,
                   "roots": [j["id"] for j in running_jobs if j.get("parent") not in running_ids]},
        "control": {} if control is None else control,
        "queue": queue_all,
        "activity": activity_all[-ACTIVITY_SHOWN:],
    })
    if meters is not None:
        out["meters"] = meters
    if rules is not None:
        out["rules"] = rules
    return out
