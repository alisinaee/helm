"""Build the roadmap snapshot: the dict the dashboard renders, from the texts of a project's data files.

build_snapshot(files, config, now) is pure. files maps a file name (tasks.json, jobs.json, autonomy.json
and the extras files) to its text, or to None when the file is missing. config is the parsed
roadmap.config.json. now is the moment to measure running jobs and the recent window from.
"""

from datetime import timedelta

from roadmap.core.extras import parse_extras
from roadmap.core.parsers import error_entry, parse_autonomy, parse_jobs, parse_tasks, parse_ts

SNAPSHOT_SCHEMA_VERSION = 1
PHASE_WEIGHT = {"done": 1.0, "partial": 0.5}
ACTIVE = ("todo", "partial")                        # task states counted as "left"
RECENT_WINDOW = timedelta(minutes=30)               # finished jobs shown under their task
RECENT_MAX = 2


def _missing(name):
    return error_entry(name, FileNotFoundError("file not found"))


def build_snapshot(files, config, now):
    """The snapshot dict. Same shape as the old server's build(), plus "project" and "schemaVersion".

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
    return out
