"""Planner features (docs/features.json): derive feature rows, coverage and orphan tasks.

derive(features, tasks, jobs, issues=None) is pure: it takes the raw feature list (read by
roadmap.services.features.load), the parsed tasks (parse_tasks), the parsed jobs (parse_jobs) and the parsed issues.
It never raises. A feature that fails a rule is left out of rows and named in errors. validate(features) returns the
same error strings.

Rules (spec section 2): ids F1..F99, at most 60 features, title <= 80, acc <= 160, prio 1..3, one parent level only.
A task lists up to 3 features in feats; it counts once in taskTotals and in each of its features' figures.
"""

import datetime
import re

from roadmap.core.parsers import FEAT_ID_RE, ISSUE_OPEN
from roadmap.core.planfmt import PHASE_ID_RE

FEATURES_FILE = "features.json"
DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
MAX_FEATURES = 60
TITLE_MAX = 80
ACC_MAX = 160
PRIO_DEFAULT = 2
PRIOS = (1, 2, 3)
STATES = ("hold", "uncovered", "done", "doing", "todo")


def validate(features):
    """Error strings for a raw feature list. An empty list means every feature is valid."""
    return _check(features)[1]


def derive(features, tasks, jobs, issues=None):
    """The planner view: rows, uncovered and orphans, counts, taskTotals and errors. Never raises."""
    kept, errors = _check(features)
    task_list = ([t for t in tasks if isinstance(t, dict) and isinstance(t.get("id"), str)]
                 if isinstance(tasks, list) else [])
    job_list = [j for j in jobs if isinstance(j, dict)] if isinstance(jobs, list) else []
    kept_ids = {f["id"] for f in kept}
    children = {f["id"]: [] for f in kept}
    for f in kept:
        if f["parent"] is not None:
            children[f["parent"]].append(f["id"])

    own = {f["id"]: set() for f in kept}          # feature id -> task ids linked directly
    orphans = []
    for t in task_list:
        linked = [x for x in _list(t.get("feats")) if isinstance(x, str) and x in kept_ids]
        for fid in linked:
            own[fid].add(t["id"])
        if not linked:
            orphans.append(t["id"])

    spent = {}
    running = {}
    for j in job_list:
        task_id = j.get("task")
        if not isinstance(task_id, str):
            continue
        if isinstance(j.get("tokensK"), (int, float)) and not isinstance(j.get("tokensK"), bool):
            spent[task_id] = spent.get(task_id, 0.0) + float(j["tokensK"])
        if j.get("status") == "running":
            running[task_id] = running.get(task_id, 0) + 1
    blocked_ids = _blocked_tasks(issues)
    tasks_by_id = {t["id"]: t for t in task_list}

    rows = []
    for f in kept:
        group = [f["id"]] + children[f["id"]]
        member_ids = set()
        for fid in group:
            member_ids |= own[fid]
        ordered = [t["id"] for t in task_list if t["id"] in member_ids]
        rows.append(_row(f, ordered, tasks_by_id, spent, running, blocked_ids))

    uncovered = [r["id"] for r in rows if r["state"] == "uncovered"]
    # total is the features that are not on hold, so done + doing + todo + uncovered == total; hold is its own count.
    counts = {"total": sum(1 for r in rows if r["state"] != "hold")}
    for state in ("done", "doing", "todo"):
        counts[state] = sum(1 for r in rows if r["state"] == state)
    counts["uncovered"] = len(uncovered)
    counts["hold"] = sum(1 for r in rows if r["state"] == "hold")
    return {
        "rows": rows,
        "uncovered": uncovered,
        "orphans": orphans,
        "counts": counts,
        "taskTotals": _task_totals(task_list, spent),
        "errors": errors,
    }


# ---------------------------------------------------------------- checks

def _check(raw_list):
    """(kept normalized features in file order, error strings). A feature with an error is left out."""
    if not isinstance(raw_list, list):
        return [], ["features must be a list"]
    errors, candidates, seen = [], [], set()
    for index, raw in enumerate(raw_list, 1):
        if index > MAX_FEATURES:
            errors.append("features beyond the first " + str(MAX_FEATURES) + " are ignored")
            break
        feat, errs = _field_errors(raw, index)
        if errs:
            errors.extend(errs)
            continue
        if feat["id"] in seen:
            errors.append(feat["id"] + ": id is used more than once, the later one is ignored")
            continue
        seen.add(feat["id"])
        candidates.append(feat)
    by_id = {f["id"]: f for f in candidates}
    kept = []
    for f in candidates:
        parent = f["parent"]
        if parent is None:
            kept.append(f)
        elif parent == f["id"]:
            errors.append(f["id"] + ": a feature cannot be its own parent")
        elif parent not in by_id:
            errors.append(f["id"] + ": parent " + parent + " is not a valid feature")
        elif by_id[parent]["parent"] is not None:
            errors.append(f["id"] + ": parent " + parent + " has a parent (one level only)")
        else:
            kept.append(f)
    return kept, errors


def _field_errors(raw, index):
    """(normalized feature, errors) for one raw feature. The feature is None when it has errors. Never raises."""
    if not isinstance(raw, dict):
        return None, ["feature " + str(index) + ": not an object"]
    fid = raw.get("id")
    label = fid if isinstance(fid, str) else "feature " + str(index)
    errs = []
    if not isinstance(fid, str) or not FEAT_ID_RE.match(fid):
        errs.append(label + ": id must be F1 to F99")
    title = raw.get("title")
    if not isinstance(title, str) or not title.strip():
        errs.append(label + ": title is required")
    elif len(title.strip()) > TITLE_MAX:
        errs.append(label + ": title is longer than " + str(TITLE_MAX) + " characters")
    acc = raw.get("acc", "")
    if acc is None:
        acc = ""
    if not isinstance(acc, str):
        errs.append(label + ": acc must be text")
    elif len(acc.strip()) > ACC_MAX:
        errs.append(label + ": acc is longer than " + str(ACC_MAX) + " characters")
    prio = raw.get("prio", PRIO_DEFAULT)
    if isinstance(prio, bool) or prio not in PRIOS:
        errs.append(label + ": prio must be 1, 2 or 3")
    parent = raw.get("parent")
    if parent is not None and (not isinstance(parent, str) or not FEAT_ID_RE.match(parent)):
        errs.append(label + ": parent must be a feature id or null")
    phase = raw.get("phase")
    if phase not in (None, "") and (not isinstance(phase, str) or not PHASE_ID_RE.match(phase)):
        errs.append(label + ": phase must be a phase id or null")
    accepted = raw.get("accepted")
    if accepted not in (None, "") and not _is_date(accepted):
        errs.append(label + ": accepted must look like 2026-10-14")
    if errs:
        return None, errs
    return {
        "id": fid,
        "title": " ".join(title.split()),
        "acc": " ".join(acc.split()),
        "prio": prio,
        "parent": parent,
        "phase": phase or None,
        "hold": raw.get("hold") is True,
        "accepted": accepted or None,
    }, []


def _is_date(value):
    """True for a YYYY-MM-DD string that is a real calendar date."""
    if not isinstance(value, str) or not DATE_RE.match(value):
        return False
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        return False
    return True


# ---------------------------------------------------------------- derived figures

def _row(f, ordered, tasks_by_id, spent, running, blocked_ids):
    members = [tasks_by_id[tid] for tid in ordered]
    total = len(members)
    done = sum(1 for t in members if t.get("state") == "done")
    touched = any(t.get("state") in ("done", "partial") for t in members)
    run = sum(running.get(tid, 0) for tid in ordered)
    if f["hold"]:
        state = "hold"
    elif total == 0:
        state = "uncovered"
    elif done == total:
        state = "done"
    elif touched or run > 0:
        state = "doing"
    else:
        state = "todo"
    return {
        "id": f["id"], "title": f["title"], "acc": f["acc"], "prio": f["prio"], "parent": f["parent"],
        "phase": f["phase"], "hold": f["hold"], "accepted": f["accepted"],
        "tasks": list(ordered), "done": done, "total": total,
        "estK": round(sum(_num(t.get("tokensK")) for t in members), 1),
        "spentK": round(sum(spent.get(tid, 0.0) for tid in ordered), 1),
        "blocked": sum(1 for tid in ordered if tid in blocked_ids),
        "running": run,
        "state": state,
    }


# The snapshot row (WP53b, R7.10): the derived row without the task id list. hold is state "hold" and running is not
# shown, so neither is carried. acc is carried only while the feature is not done.
SNAPSHOT_ROW_KEYS = ("id", "title", "prio", "parent", "phase", "accepted", "done", "total", "estK", "spentK",
                     "blocked", "state")


def snapshot_rows(rows):
    """The rows the snapshot carries: SNAPSHOT_ROW_KEYS, plus acc for a feature that is not done. The Planner reads a
    feature's tasks from each task's feats in the snapshot, so the id list is left out. Never raises."""
    out = []
    for row in rows if isinstance(rows, list) else []:
        slim = {key: row[key] for key in SNAPSHOT_ROW_KEYS if key in row}
        if row.get("state") != "done" and row.get("acc"):
            slim["acc"] = row["acc"]
        out.append(slim)
    return out


def _task_totals(task_list, spent):
    """Each task once: the global figures."""
    return {
        "total": len(task_list),
        "done": sum(1 for t in task_list if t.get("state") == "done"),
        "estK": round(sum(_num(t.get("tokensK")) for t in task_list), 1),
        "spentK": round(sum(spent.get(t["id"], 0.0) for t in task_list), 1),
    }


def _blocked_tasks(issues):
    """Task ids named by open blocker issues."""
    out = set()
    for issue in _list(issues):
        if not isinstance(issue, dict) or issue.get("kind") != "blocker" or issue.get("status") not in ISSUE_OPEN:
            continue
        for tid in _list(issue.get("tasks")):
            if isinstance(tid, str):
                out.add(tid)
    return out


def _list(value):
    return value if isinstance(value, list) else []


def _num(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    return float(value)
