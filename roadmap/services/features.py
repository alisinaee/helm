"""Planner features (WP52): the service behind the feature ops and the feature CLI.

docs/features.json holds the features (add, set, rm, accept); tasks.json holds each task's feats (link, unlink). The
pure rules are in roadmap/core/features.py. apply_records is the one writer of features.json: tasks.apply calls it
after it has validated the F lines, and the add and set ops call it too. It never takes the directory lock, so the
caller holds it. The other writers here take the lock themselves, except link, which goes through tasks.apply.

tasks and jobs are imported inside functions: tasks.py imports this module, so a top-level import would be a cycle.
"""

import datetime
import os
import re

from roadmap.core import features as core
from roadmap.core import planfmt
from roadmap.errors import EXIT_NOT_FOUND, EXIT_USAGE, RoadmapError
from roadmap.services import records
from roadmap.store import lock, schema

KIND = "features"
FILE = core.FEATURES_FILE
TASKS_FILE = "tasks.json"
ID_MAX = 99
DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
NEXT_LIST = "roadmap feature list"
CHANGE_KEYS = ("title", "acc", "prio", "phase", "parent", "hold")


# ---------------------------------------------------------------- file

def load_doc(data_dir):
    """The features document at the current schema: {schemaVersion, updated, features}. Missing is empty."""
    doc = records.load(KIND, data_dir, FILE, "features")
    doc.setdefault("updated", "")
    return doc


def save_doc(data_dir, doc):
    """Write the features document. The caller holds the directory lock."""
    records.save(KIND, data_dir, FILE, doc)


def _phase_ids(data_dir):
    data, error = schema.read_data("tasks", os.path.join(data_dir, TASKS_FILE))
    if error is not None or data is None:
        return set()
    return {p.get("id") for p in data.get("phases", []) if isinstance(p, dict)}


def _task_doc(data_dir):
    from roadmap.services import tasks
    return tasks.load(data_dir)


def _find(items, fid):
    for item in items:
        if isinstance(item, dict) and item.get("id") == fid:
            return item
    raise RoadmapError("not_found", "no feature " + str(fid), EXIT_NOT_FOUND, next=NEXT_LIST)


def record_of(fid, title, acc="", prio=2, phase=None, parent=None, hold=False):
    """An F record in the shape planfmt.parse_plan gives, so apply_records takes it as it is."""
    return {"kind": "feature", "line": 0, "id": fid, "title": title, "acc": acc, "prio": prio, "phase": phase,
            "parent": parent, "hold": hold}


# ---------------------------------------------------------------- the one writer of features.json

def apply_records(data_dir, recs, dry_run=False):
    """Upsert the F records (kind feature; other kinds are skipped) into docs/features.json. Each record sets every
    field except accepted, which only accept sets. Returns {added, changed, wrote}. Raises usage when the result
    breaks a rule (core.validate) and not_found when a phase is unknown. Nothing is written on error.
    The caller holds the directory lock."""
    doc = load_doc(data_dir)
    items = [dict(f) for f in doc["features"] if isinstance(f, dict)]
    index = {f["id"]: f for f in items if isinstance(f.get("id"), str)}
    phases = _phase_ids(data_dir)
    added, changed = [], []
    for rec in recs:
        if not isinstance(rec, dict) or rec.get("kind") != "feature":
            continue
        fid = rec["id"]
        if rec.get("phase") is not None and rec["phase"] not in phases:
            raise RoadmapError("not_found", "phase " + str(rec["phase"]) + " does not exist (allowed: a phase id "
                               "in tasks.json)", EXIT_NOT_FOUND, next="roadmap task list")
        entry = {"id": fid, "title": rec["title"], "acc": rec.get("acc") or "", "prio": rec.get("prio", 2),
                 "parent": rec.get("parent"), "phase": rec.get("phase"), "hold": rec.get("hold") is True,
                 "accepted": index[fid].get("accepted") if fid in index else None}
        if fid in index:
            if any(index[fid].get(key) != value for key, value in entry.items()):
                changed.append(fid)
            index[fid].clear()
            index[fid].update(entry)
        else:
            items.append(entry)
            index[fid] = entry
            added.append(fid)
    problems = core.validate(items)
    if problems:
        raise RoadmapError("usage", "; ".join(problems[:3]), EXIT_USAGE, next=NEXT_LIST)
    result = {"added": added, "changed": changed, "wrote": False}
    if dry_run or not (added or changed):
        return result
    doc["features"] = items
    doc["updated"] = planfmt.today()
    save_doc(data_dir, doc)
    result["wrote"] = True
    return result


# ---------------------------------------------------------------- feature writes

def add(data_dir, title, acc="", prio=2, phase=None, parent=None):
    """Create a feature with the next free id. Returns the derived row. Refused at 60 features or past F99."""
    records.require_dir(data_dir)
    with lock.locked(data_dir):
        doc = load_doc(data_dir)
        if len(doc["features"]) >= core.MAX_FEATURES:
            raise records.conflict("features are at the most allowed (" + str(core.MAX_FEATURES) + "); remove one first",
                                   NEXT_LIST)
        fid = records.next_number("F", doc["features"])
        if int(fid[1:]) > ID_MAX:
            raise records.conflict("feature ids run out after F" + str(ID_MAX), NEXT_LIST)
        apply_records(data_dir, [record_of(fid, title, acc, prio, phase, parent)])
    return row_of(data_dir, fid)


def set_fields(data_dir, fid, changes):
    """Change some fields of a feature (keys in CHANGE_KEYS). Returns the prior values of those keys, for undo."""
    records.require_dir(data_dir)
    with lock.locked(data_dir):
        doc = load_doc(data_dir)
        current = _find(doc["features"], fid)
        prior = {key: current.get(key, _default(key)) for key in changes}
        merged = dict(current)
        merged.update(changes)
        rec = record_of(fid, merged["title"], merged.get("acc") or "", merged.get("prio", 2), merged.get("phase"),
                        merged.get("parent"), merged.get("hold") is True)
        apply_records(data_dir, [rec])
    return prior


def _default(key):
    return {"acc": "", "prio": 2, "hold": False}.get(key)


def accept(data_dir, fid, on, date=None, confirm=False, now=None):
    """Stamp (on) or clear the accepted date. Accepting a feature that is not done needs confirm. Returns the prior
    accepted value. The person sets this; the ops refuse agents and the phone before they get here."""
    records.require_dir(data_dir)
    with lock.locked(data_dir):
        doc = load_doc(data_dir)
        current = _find(doc["features"], fid)
        prior = current.get("accepted")
        if on:
            state = row_of(data_dir, fid)["state"]
            if state != "done" and not confirm:
                raise records.conflict(fid + " is " + state + ", not done; accept it anyway with --yes", NEXT_LIST)
            stamp = date or (now.date().isoformat() if now is not None else planfmt.today())
        else:
            stamp = None
        current["accepted"] = stamp
        doc["updated"] = planfmt.today()
        save_doc(data_dir, doc)
    return {"id": fid, "accepted": stamp}, prior


def remove(data_dir, fid):
    """Remove a feature with no tasks and no sub-features. Returns the removed record, for undo."""
    records.require_dir(data_dir)
    with lock.locked(data_dir):
        doc = load_doc(data_dir)
        current = _find(doc["features"], fid)
        kids = [f.get("id") for f in doc["features"] if isinstance(f, dict) and f.get("parent") == fid]
        if kids:
            raise records.conflict(fid + " has sub-features " + " ".join(kids) + "; remove them first", NEXT_LIST)
        linked = [t["id"] for t in _task_doc(data_dir)["tasks"] if fid in (t.get("feats") or [])]
        if linked:
            raise records.conflict(fid + " has " + str(len(linked)) + " task(s); unlink them first (roadmap feature "
                                   "unlink " + fid + " " + linked[0] + ")", "roadmap feature show " + fid)
        doc["features"] = [f for f in doc["features"] if f is not current]
        doc["updated"] = planfmt.today()
        save_doc(data_dir, doc)
    return dict(current)


def restore(data_dir, feature):
    """Put back a feature that rm removed (undo). The id must be free."""
    records.require_dir(data_dir)
    with lock.locked(data_dir):
        doc = load_doc(data_dir)
        if any(f.get("id") == feature["id"] for f in doc["features"]):
            raise records.conflict(feature["id"] + " already exists; not restored", NEXT_LIST)
        doc["features"].append(dict(feature))
        problems = core.validate(doc["features"])
        if problems:
            raise RoadmapError("usage", "; ".join(problems[:3]), EXIT_USAGE, next=NEXT_LIST)
        doc["updated"] = planfmt.today()
        save_doc(data_dir, doc)


# ---------------------------------------------------------------- task links

def link(data_dir, task_id, fids):
    """Add features to a task's feats (through tasks.apply, which checks the 3-per-task cap). Returns the task's feats
    and the ids that were newly added."""
    from roadmap.services import tasks
    records.require_dir(data_dir)
    before = list(tasks.get(data_dir, task_id).get("feats") or [])
    known = {f.get("id") for f in load_doc(data_dir)["features"]}
    for fid in fids:
        if fid not in known:
            raise RoadmapError("not_found", "no feature " + fid, EXIT_NOT_FOUND, next=NEXT_LIST)
    links = [{"kind": "link", "line": 0, "feature": fid, "tasks": [task_id]} for fid in fids]
    try:
        tasks.apply(data_dir, links)
    except tasks.PlanError as exc:
        raise RoadmapError("usage" if exc.usage else "invalid_plan", "; ".join(exc.errors), exc.exit,
                           next=exc.next) from exc
    after = list(tasks.get(data_dir, task_id).get("feats") or [])
    return {"task": task_id, "feats": after, "added": [f for f in fids if f not in before]}


def unlink(data_dir, task_id, fids):
    """Remove features from a task's feats. Returns the task's feats and the ids that were removed."""
    from roadmap.services import tasks
    records.require_dir(data_dir)
    with lock.locked(data_dir):
        path = tasks.tasks_path(data_dir)
        data = _task_doc(data_dir)
        task = next((t for t in data["tasks"] if isinstance(t, dict) and t.get("id") == task_id), None)
        if task is None:
            raise RoadmapError("not_found", "no task " + task_id, EXIT_NOT_FOUND,
                               next="roadmap task list --phase " + task_id.split(".")[0])
        current = list(task.get("feats") or [])
        removed = [f for f in fids if f in current]
        if removed:
            rest = [f for f in current if f not in removed]
            if rest:
                task["feats"] = rest
            else:
                task.pop("feats", None)
            data["updated"] = planfmt.today()
            schema.write_data("tasks", path, data)
    return {"task": task_id, "feats": [f for f in current if f not in removed], "removed": removed}


# ---------------------------------------------------------------- reads

def _tasks_for_view(data_dir):
    return [dict(t, state=t.get("status") if t.get("status") in ("todo", "partial", "done", "hold") else "todo")
            for t in _task_doc(data_dir)["tasks"] if isinstance(t, dict)]


def derived(data_dir):
    """The derive() view of the project (rows, uncovered, orphans, counts, taskTotals, errors). Reads only."""
    from roadmap.services import issues, jobs
    records.require_dir(data_dir)
    items, errors = core.load(data_dir)
    view = core.derive(items, _tasks_for_view(data_dir), jobs.list_jobs(data_dir), issues.list_issues(data_dir))
    view["errors"] = errors + view["errors"]
    return view


def row_of(data_dir, fid):
    """The derived row of one feature."""
    for row in derived(data_dir)["rows"]:
        if row["id"] == fid:
            return row
    raise RoadmapError("not_found", "no feature " + str(fid), EXIT_NOT_FOUND, next=NEXT_LIST)


def task_views(data_dir, fid):
    """The tasks a feature covers (its own and its sub-features'), as {id, state, estK, title}."""
    row = row_of(data_dir, fid)
    by_id = {t["id"]: t for t in _tasks_for_view(data_dir)}
    return [{"id": tid, "state": by_id[tid]["state"], "estK": by_id[tid].get("tokensK", 0),
             "title": by_id[tid].get("title", "")} for tid in row["tasks"] if tid in by_id]


def status_line(data_dir):
    """The one status line: 'features: 22 (9 done, 6 doing, 4 todo, 3 uncovered; 2 orphan tasks)'. None when the
    project has no docs/features.json, so a project without features keeps its old status."""
    if not os.path.exists(os.path.join(data_dir, FILE)):
        return None
    view = derived(data_dir)
    counts = view["counts"]
    text = "features: %d (%d done, %d doing, %d todo, %d uncovered" % (
        counts["total"], counts["done"], counts["doing"], counts["todo"], counts["uncovered"])
    orphans = len(view["orphans"])
    if orphans:
        text += "; %d orphan task%s" % (orphans, "" if orphans == 1 else "s")
    return text + ")"


def check_date(value):
    """A YYYY-MM-DD string or None."""
    if value is None:
        return None
    text = str(value)
    try:
        datetime.date.fromisoformat(text)
    except ValueError:
        raise RoadmapError("usage", "date '" + text + "' must look like 2026-10-14", EXIT_USAGE) from None
    if not DATE_RE.match(text):
        raise RoadmapError("usage", "date '" + text + "' must look like 2026-10-14", EXIT_USAGE)
    return text
