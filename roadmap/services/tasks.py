"""Tasks service (WP16): read, query, bulk upsert of phases and tasks from parsed plan records, and the status summary.

Writes take the directory lock, validate every record before anything is written (all or nothing), and save through
schema.write_data("tasks"). Nothing is deleted except the tasks of one phase named by replace_phase. Text formats
live in roadmap.core.planfmt; this module only does the file work and the rules that need the current data.
"""

import copy
import datetime
import os
import re

from roadmap.core import parsers, planfmt
from roadmap.errors import EXIT_INVALID_DATA, EXIT_NOT_FOUND, EXIT_USAGE, RoadmapError
from roadmap.services import jobs
from roadmap.store import atomic, backup, config, lock, schema

BACKUP_OVER = 10
QUERY_LIMIT = 20
SUMMARY_MAX_LINES = 8
SUMMARY_MAX_CHARS = 700
PHASE_LINE_MAX = 160
_MISSING = object()
_NEXT_FIX = "fix the lines above, then run the same command with --dry-run"


class PlanError(RoadmapError):
    """Validation failed and nothing was written. errors holds every problem as 'line N: ... (allowed: ...)'.
    usage is True when every problem is an after-list problem, which exits with the usage code (2)."""

    def __init__(self, errors, exit_code, next_cmd, usage=False):
        super().__init__("invalid_plan", "\n".join(errors), exit_code, next=next_cmd)
        self.errors = list(errors)
        self.usage = usage


FEATURES_FILE = "features.json"
FEATURES_VERSION = 1


def tasks_path(data_dir):
    return os.path.join(data_dir, jobs.TASKS_FILE)


def features_path(data_dir):
    return os.path.join(data_dir, FEATURES_FILE)


def load_features(data_dir):
    """Feature dicts in file order (docs/features.json). A missing file gives an empty list."""
    return [dict(f) for f in _features_load(data_dir)["features"] if isinstance(f, dict)]


def resolve(project_id=None):
    """Return (project, data_dir) for the registered project a command acts on (see jobs.resolve_project)."""
    project = jobs.resolve_project(project_id)
    return project, jobs.data_dir_of(project)


def load(data_dir):
    """The tasks.json document at the current schema, with phases and tasks lists. A missing file gives an empty one.
    A file written by a newer build is newer_schema (exit 5); bad JSON is invalid_data."""
    path = tasks_path(data_dir)
    data, error = schema.read_data("tasks", path)
    if error is not None:
        raise RoadmapError("newer_schema", error["message"], EXIT_INVALID_DATA)
    if data is None:
        return _empty()
    if not isinstance(data.get("phases"), list) or not isinstance(data.get("tasks"), list):
        raise RoadmapError("invalid_data", "tasks.json needs 'phases' and 'tasks' lists; fix it, then retry: " + path,
                           EXIT_INVALID_DATA)
    return data


def get(data_dir, task_id):
    """One task as a dict. An unknown id is not_found (exit 3) with the next command that lists its phase."""
    for task in load(data_dir)["tasks"]:
        if isinstance(task, dict) and task.get("id") == task_id:
            return dict(task)
    raise RoadmapError("not_found", "no task " + str(task_id), EXIT_NOT_FOUND,
                       next="roadmap task list --phase " + str(task_id).split(".")[0])


def query(data_dir, phase=None, status=None, needs_you=False, limit=QUERY_LIMIT):
    """Tasks in file order that match the filters, at most limit of them. status is a comma text or a list."""
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise RoadmapError("usage", "--limit must be a whole number of 1 or more", EXIT_USAGE)
    wanted = _status_set(status)
    rows = []
    for task in load(data_dir)["tasks"]:
        if not isinstance(task, dict):
            continue
        if phase and _phase_of(task) != phase:
            continue
        if wanted and task.get("status") not in wanted:
            continue
        if needs_you and task.get("needsUser") is not True:
            continue
        rows.append(dict(task))
        if len(rows) >= limit:
            break
    return rows


def apply(data_dir, records, dry_run=False, replace_phase=None, project_id=None):
    """Upsert parsed records (from planfmt.parse_plan or parse_set_text) into tasks.json and return the diff.

    Feature records (F lines) go to docs/features.json and link records (L lines) add feature ids to tasks' feats.
    Validation covers the whole input before any write. A failure raises PlanError and writes nothing. With no change
    nothing is written (so updated is not bumped). A write that changes more than 10 tasks backs the file up first;
    project_id names that backup folder, and when it is None the registered project for data_dir is used."""
    _require_dir(data_dir)
    if replace_phase is not None and not planfmt.PHASE_ID_RE.match(str(replace_phase)):
        raise RoadmapError("usage", "replace phase '" + str(replace_phase) + "' is not a phase id "
                           "(allowed: letters and digits)", EXIT_USAGE)
    path = tasks_path(data_dir)
    with lock.locked(data_dir):
        before = load(data_dir)
        doc = copy.deepcopy(before)
        fbefore = _features_load(data_dir)
        fdoc = copy.deepcopy(fbefore)
        problems, input_ids = _apply_records(doc, records, replace_phase, fdoc)
        if problems:
            raise _plan_error(problems)
        diff = _diff(before, doc, input_ids, fbefore, fdoc)
        if dry_run or diff["changed"] == 0:
            diff.update(dry_run=dry_run, wrote=False, backup=None)
            return diff
        folder = None
        if diff["tasks_touched"] > BACKUP_OVER:
            folder = backup.backup_files(project_id or _registered_id(data_dir), [path])
        if diff["tasks_touched"] or diff["phases_added"] or diff["phases_changed"]:
            doc["updated"] = planfmt.today()
            schema.write_data("tasks", path, doc)
        if diff["features_added"] or diff["features_changed"]:
            fdoc["updated"] = planfmt.today()
            _features_write(data_dir, fdoc)
        diff.update(dry_run=False, wrote=True, backup=folder)
    return diff


def describe(diff):
    """One line for a diff: 'would: +P1 +T5 ~T2 =T3 (no write)', 'wrote: ...', or '0 changed'."""
    if diff["changed"] == 0:
        return "0 changed (no write)" if diff["dry_run"] else "0 changed"
    parts = []
    for count, sign in ((len(diff["phases_added"]), "+P"), (len(diff["phases_changed"]), "~P"),
                        (len(diff["features_added"]), "+F"), (len(diff["features_changed"]), "~F"),
                        (len(diff["tasks_added"]), "+T"), (len(diff["tasks_changed"]), "~T"),
                        (len(diff["tasks_removed"]), "-T"), (diff["tasks_unchanged"], "=T")):
        if count:
            parts.append(sign + str(count))
    if diff["wrote"]:
        return "wrote: " + " ".join(parts)
    return "would: " + " ".join(parts) + " (no write)"


def summary(data_dir, jobs_list=(), name=None):
    """The board summary as plain lines: at most 8 lines and 700 characters (see docs/AGENT-INTERFACE.md section 2)."""
    doc = load(data_dir)
    tasks = [t for t in doc["tasks"] if isinstance(t, dict)]
    counts = {s: 0 for s in planfmt.TASK_STATUSES}
    for task in tasks:
        if task.get("status") in counts:
            counts[task["status"]] += 1
    left = [t for t in tasks if t.get("status") in ("todo", "partial")]
    left_k = sum(_num(t.get("tokensK")) for t in left)
    you = [t for t in tasks if t.get("needsUser") is True and t.get("status") != "done"]
    running = [j for j in jobs_list if isinstance(j, dict) and j.get("status") == "running"]
    label = name or _default_name(data_dir)
    lines = [label + "  updated " + str(doc.get("updated") or "never") + "  " + str(len(tasks)) + " tasks: "
             + str(counts["done"]) + " done, " + str(counts["partial"]) + " partial, "
             + str(counts["todo"]) + " todo, " + str(counts["hold"]) + " hold",
             "left " + str(len(left)) + " (~" + _tokens_text(left_k) + ")  needs-you " + str(len(you))
             + "  running " + str(len(running)),
             _phase_line(doc, tasks)]
    upcoming = [t for t in tasks if t.get("status") == "partial" and t.get("needsUser") is not True]
    upcoming += [t for t in tasks if t.get("status") == "todo" and t.get("needsUser") is not True]
    for task in upcoming[:2]:
        lines.append("next: " + str(task.get("id")) + " " + _model_of(task) + " " + _k_text(task.get("tokensK"))
                     + " " + _short(task.get("title"), 50))
    if you:
        text = "; ".join(str(t.get("id")) + " " + _short(t.get("title"), 40) for t in you[:2])
        if len(you) > 2:
            text += " (+" + str(len(you) - 2) + ")"
        lines.append("you: " + text)
    for job in running[:2]:
        lines.append("run: " + str(job.get("id")) + " " + str(job.get("model") or "?") + " "
                     + str(job.get("task") or "-") + " " + _elapsed(job.get("started")))
    return _fit(lines)


# ---------------------------------------------------------------- apply

def _apply_records(doc, records, replace_phase, fdoc):
    """Apply records to doc (tasks) and fdoc (features) in memory. Returns (problems, input_task_ids); problems are
    (kind, text, next) tuples."""
    problems = []
    unique = []
    seen = {}
    for rec in records:
        if rec["kind"] == "link":
            unique.append(rec)
            continue
        kind = rec["kind"] if rec["kind"] in ("phase", "feature") else "task"
        key = (kind, rec["id"])
        if key in seen:
            problems.append(("invalid", _line(rec, "duplicate " + kind + " id " + rec["id"] + " (first on line "
                                              + str(seen[key]) + ") (allowed: each id once per input)"), None))
            continue
        seen[key] = rec.get("line", 0)
        unique.append(rec)
    phases = _index(doc["phases"])
    tasks = _index(doc["tasks"])
    input_ids = set()
    touched = []

    def touch(pid):
        if pid not in touched:
            touched.append(pid)

    for rec in unique:
        if rec["kind"] != "phase":
            continue
        pid = rec["id"]
        if pid in phases:
            phases[pid]["name"] = rec["name"]
            if rec["status"] is not None:
                phases[pid]["status"] = rec["status"]
        else:
            phases[pid] = {"id": pid, "name": rec["name"], "status": rec["status"] or "todo"}
            doc["phases"].append(phases[pid])
        touch(pid)

    features = _index(fdoc["features"])
    _apply_features(fdoc, features, phases, unique, problems)

    for rec in unique:
        if rec["kind"] in ("phase", "feature"):
            continue
        if rec["kind"] == "link":
            _apply_link(tasks, features, rec, problems)
            continue
        tid = rec["id"]
        input_ids.add(tid)
        if rec["kind"] == "task":
            pid = rec["phase"]
            if pid not in phases:
                problems.append(("missing", _line(rec, "phase " + pid + " does not exist (allowed: a P " + pid
                                                  + " line in this input, or an existing phase id)"),
                                 "roadmap status"))
                continue
            touch(pid)
            missing = [fid for fid in (rec.get("feats") or []) if fid not in features]
            if missing:
                problems.append(("missing", _line(rec, "feature " + missing[0] + " does not exist (allowed: an F line "
                                                  "in this input, or an existing feature id)"), None))
                continue
            if tid in tasks:
                _update_task(tasks[tid], rec)
            elif rec["model"] is None or rec["thinking"] is None:
                problems.append(("invalid", _line(rec, "a new task needs a model and a thinking level "
                                                  "(allowed: " + "|".join(planfmt.MODELS) + " / "
                                                  + "|".join(planfmt.THINKING) + ")"), None))
            else:
                tasks[tid] = _new_task(rec)
                doc["tasks"].append(tasks[tid])
        else:
            if tid not in tasks:
                pid = tid.split(".")[0]
                problems.append(("missing", _line(rec, "no task " + tid + " in tasks.json (allowed: an existing "
                                                  "task id; list them with roadmap task list --phase " + pid + ")"),
                                 "roadmap task list --phase " + pid))
                continue
            _apply_set(tasks[tid], rec["fields"])
            touch(_phase_of(tasks[tid]))

    if replace_phase is not None:
        if replace_phase not in phases:
            problems.append(("missing", "replace phase " + replace_phase + " does not exist (allowed: a phase in the "
                             "file, or a P line in this input)", "roadmap status"))
        else:
            touch(replace_phase)
            doc["tasks"] = [t for t in doc["tasks"] if not (isinstance(t, dict) and _phase_of(t) == replace_phase
                                                            and t.get("id") not in input_ids)]

    for pid in touched:
        phase = phases.get(pid)
        if phase is None or phase.get("status") == "hold":
            continue
        mine = [t for t in doc["tasks"] if isinstance(t, dict) and _phase_of(t) == pid]
        if mine:
            phase["status"] = _recompute(mine)
    problems.extend(_check_after(doc, unique))
    return problems, input_ids


def _apply_features(fdoc, features, phases, unique, problems):
    """Upsert the F records into fdoc (features index in features). Each F line sets every field except accepted,
    which only the person sets. Checks: phase exists, parent exists and is top level, and the 60-feature cap."""
    added = []
    for rec in unique:
        if rec["kind"] != "feature":
            continue
        fid = rec["id"]
        if rec["phase"] is not None and rec["phase"] not in phases:
            problems.append(("missing", _line(rec, "phase " + rec["phase"] + " does not exist (allowed: a P "
                                              + rec["phase"] + " line in this input, or an existing phase id)"),
                             "roadmap status"))
            continue
        entry = {"id": fid, "title": rec["title"], "acc": rec["acc"], "prio": rec["prio"], "parent": rec["parent"],
                 "phase": rec["phase"], "hold": rec["hold"],
                 "accepted": features[fid].get("accepted") if fid in features else None}
        if fid in features:
            features[fid].clear()
            features[fid].update(entry)
        else:
            features[fid] = entry
            fdoc["features"].append(entry)
            added.append(rec)
    for rec in unique:
        if rec["kind"] != "feature":
            continue
        parent = rec["parent"]
        if parent is None:
            continue
        if parent not in features:
            problems.append(("missing", _line(rec, "parent " + parent + " does not exist (allowed: an F line in this "
                                              "input, or an existing feature id, or -)"), None))
        elif features[parent].get("parent"):
            problems.append(("invalid", _line(rec, "parent " + parent + " is itself a sub-feature (allowed: a "
                                              "top-level feature; only one level of sub-features)"), None))
        elif any(f.get("parent") == rec["id"] for f in fdoc["features"]):
            problems.append(("invalid", _line(rec, rec["id"] + " has sub-features, so it cannot have a parent "
                                              "(allowed: one level only)"), None))
    if len(fdoc["features"]) > planfmt.FEATURES_MAX and added:
        problems.append(("invalid", _line(added[0], "the file would have " + str(len(fdoc["features"]))
                                          + " features (allowed: up to " + str(planfmt.FEATURES_MAX) + ")"), None))


def _apply_link(tasks, features, rec, problems):
    """An L line: append the feature to each named task's feats, once. Errors when the feature or a task is unknown,
    or when a task would have more than FEAT_MAX_PER_TASK features."""
    fid = rec["feature"]
    if fid not in features:
        problems.append(("missing", _line(rec, "feature " + fid + " does not exist (allowed: an F line in this input, "
                                          "or an existing feature id)"), None))
        return
    for tid in rec["tasks"]:
        task = tasks.get(tid)
        if task is None:
            pid = tid.split(".")[0]
            problems.append(("missing", _line(rec, "no task " + tid + " in tasks.json (allowed: an existing task id; "
                                              "list them with roadmap task list --phase " + pid + ")"),
                             "roadmap task list --phase " + pid))
            continue
        feats = list(task.get("feats") or [])
        if fid in feats:
            continue
        if len(feats) >= planfmt.FEAT_MAX_PER_TASK:
            problems.append(("invalid", _line(rec, tid + " already has " + str(planfmt.FEAT_MAX_PER_TASK)
                                             + " features (allowed: up to " + str(planfmt.FEAT_MAX_PER_TASK)
                                             + " per task)"), None))
            continue
        feats.append(fid)
        task["feats"] = feats


def _check_after(doc, records):
    """Problems with the after lists that this input sets: each id must be a task in the file, must not be the task
    itself, and must not close a loop (the dependency must not already lead back to the task). Checked against the
    whole file after the input is applied; kind 'usage' gives the usage exit code."""
    tasks = {t["id"]: t for t in doc["tasks"] if isinstance(t, dict) and isinstance(t.get("id"), str)}
    problems = []
    for rec in records:
        if rec["kind"] not in ("task", "set"):
            continue
        fields_after = rec.get("after") if rec["kind"] == "task" else rec["fields"].get("after")
        if fields_after is None or rec["id"] not in tasks:
            continue
        for dep in fields_after:
            if dep == rec["id"]:
                problems.append(("usage", _line(rec, rec["id"] + " cannot be after itself (allowed: other task ids "
                                                "in after)"), None))
            elif dep not in tasks:
                pid = dep.split(".")[0]
                problems.append(("usage", _line(rec, "after id " + dep + " is not a task in tasks.json (allowed: an "
                                                "existing task id; list them with roadmap task list --phase " + pid
                                                + ")"), "roadmap task list --phase " + pid))
            elif _reaches(tasks, dep, rec["id"]):
                problems.append(("usage", _line(rec, "after " + dep + " would make a loop: " + dep + " already leads "
                                                "back to " + rec["id"] + " (allowed: an after list with no loops)"),
                                 "roadmap task show " + rec["id"]))
    return problems


def _reaches(tasks, start, goal):
    """True when start is goal or follows after lists to reach goal."""
    seen = set()
    stack = [start]
    while stack:
        current = stack.pop()
        if current == goal:
            return True
        if current in seen:
            continue
        seen.add(current)
        task = tasks.get(current)
        after = task.get("after") if isinstance(task, dict) else None
        if isinstance(after, list):
            stack.extend(dep for dep in after if isinstance(dep, str))
    return False


def _update_task(task, rec):
    task["title"] = rec["title"]
    for key, value in (("status", rec["status"]), ("tokensK", rec["tokensK"]), ("thinking", rec["thinking"]),
                       ("model", rec["model"]), ("check", rec["check"]), ("checkK", rec["checkK"]),
                       ("note", rec["note"]), ("after", rec.get("after"))):
        if value is not None:
            task[key] = value
    if rec.get("feats") is not None:
        if rec["feats"]:
            task["feats"] = list(rec["feats"])
        else:
            task.pop("feats", None)
    if rec["needsUser"] is True:
        task["needsUser"] = True


def _new_task(rec):
    """A new task with the canonical field order from the skill table; note is added only when given."""
    task = {"id": rec["id"], "phase": rec["phase"], "title": rec["title"],
            "status": rec["status"] or "todo", "tokensK": 0 if rec["tokensK"] is None else rec["tokensK"],
            "thinking": rec["thinking"], "model": rec["model"], "needsUser": rec["needsUser"] is True,
            "check": rec["check"] or "none", "checkK": 0 if rec["checkK"] is None else rec["checkK"]}
    if rec["note"] is not None:
        task["note"] = rec["note"]
    if rec.get("after"):
        task["after"] = list(rec["after"])
    if rec.get("feats"):
        task["feats"] = list(rec["feats"])
    return task


def _apply_set(task, fields):
    for key, value in fields.items():
        if key == "note" and value == "":
            task.pop("note", None)
        elif key == "after" and not value:
            task.pop("after", None)
        else:
            task[key] = list(value) if key == "after" else value


def _recompute(tasks):
    """A phase's status from its tasks: all done -> done; any started (partial or done) -> partial; else todo."""
    statuses = [t.get("status") for t in tasks]
    if all(s == "done" for s in statuses):
        return "done"
    if any(s in ("partial", "done") for s in statuses):
        return "partial"
    return "todo"


def _plan_error(problems):
    missing = [p for p in problems if p[0] == "missing"]
    exit_code = EXIT_NOT_FOUND if len(missing) == len(problems) else EXIT_USAGE
    next_cmd = _NEXT_FIX
    if len(missing) == len(problems) and missing[0][2]:
        next_cmd = missing[0][2]
    usage_only = all(p[0] == "usage" for p in problems)
    if usage_only and problems[0][2]:
        next_cmd = problems[0][2]
    return PlanError([p[1] for p in problems], EXIT_USAGE if usage_only else exit_code, next_cmd, usage=usage_only)


# ---------------------------------------------------------------- diff

def _diff(before, after, input_ids, fbefore=None, fafter=None):
    field_diffs = []
    phases_added, phases_changed, _ = _compare(before["phases"], after["phases"], field_diffs)
    tasks_added, tasks_changed, tasks_removed = _compare(before["tasks"], after["tasks"], field_diffs)
    features_added, features_changed = [], []
    if fbefore is not None and fafter is not None:
        features_added, features_changed, _ = _compare(fbefore["features"], fafter["features"], field_diffs)
    changed = (len(phases_added) + len(phases_changed) + len(tasks_added) + len(tasks_changed)
               + len(tasks_removed) + len(features_added) + len(features_changed))
    return {
        "changed": changed,
        "tasks_touched": len(tasks_added) + len(tasks_changed) + len(tasks_removed),
        "phases_added": phases_added,
        "phases_changed": phases_changed,
        "features_added": features_added,
        "features_changed": features_changed,
        "tasks_added": tasks_added,
        "tasks_changed": tasks_changed,
        "tasks_removed": tasks_removed,
        "tasks_unchanged": max(0, len(input_ids) - len(tasks_added) - len(tasks_changed)),
        "field_diffs": field_diffs,
    }


def _compare(old_items, new_items, field_diffs):
    """Compare two lists of phases or tasks by id. Returns (added, changed, removed) and appends
    one 'ID field old→new' string to field_diffs for every field that changed."""
    old = _index(old_items)
    new = _index(new_items)
    added = [i for i in new if i not in old]
    removed = [i for i in old if i not in new]
    changed = []
    for key in new:
        if key not in old:
            continue
        pairs = _field_changes(old[key], new[key])
        if pairs:
            changed.append(key)
            for field, a, b in pairs:
                field_diffs.append(key + " " + field + " " + _show(a) + "→" + _show(b))
    return added, changed, removed


def _field_changes(old, new):
    keys = list(old) + [k for k in new if k not in old]
    pairs = []
    for key in keys:
        a = old.get(key, _MISSING)
        b = new.get(key, _MISSING)
        if a != b or type(a) is not type(b):
            pairs.append((key, a, b))
    return pairs


def _show(value):
    if value is _MISSING or value is None:
        return "(none)"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


# ---------------------------------------------------------------- summary helpers

def _phase_line(doc, tasks):
    segments = []
    for phase in doc["phases"]:
        if not isinstance(phase, dict) or phase.get("status") == "hold":
            continue
        mine = [t for t in tasks if _phase_of(t) == phase.get("id")]
        done = sum(1 for t in mine if t.get("status") == "done")
        partial = sum(1 for t in mine if t.get("status") == "partial")
        pct = round(100 * (done + 0.5 * partial) / len(mine)) if mine else 0
        segments.append(str(phase.get("id")) + " " + _short(phase.get("name"), 20) + " " + str(pct) + "%")
    if not segments:
        return "no phases yet"
    text = ""
    for index, segment in enumerate(segments):
        candidate = segment if not text else text + " | " + segment
        if len(candidate) > PHASE_LINE_MAX:
            return text + " | +" + str(len(segments) - index) + " more"
        text = candidate
    return text


def _fit(lines):
    lines = lines[:SUMMARY_MAX_LINES]
    while len("\n".join(lines)) > SUMMARY_MAX_CHARS and len(lines) > 1:
        lines.pop()
    return lines


def _tokens_text(k):
    if k >= 1000:
        return "{:.1f}M tok".format(k / 1000.0)
    return str(int(round(k))) + "k tok"


def _k_text(value):
    return str(int(round(_num(value)))) + "k"


def _model_of(task):
    return task.get("model") if task.get("model") in planfmt.MODELS else "?"


def _short(text, limit):
    value = " ".join(str(text or "").split())
    return value if len(value) <= limit else value[:limit - 1] + "…"


def _elapsed(started):
    try:
        start = datetime.datetime.fromisoformat(str(started))
    except (TypeError, ValueError):
        return "?"
    now = datetime.datetime.now(start.tzinfo) if start.tzinfo else datetime.datetime.now()
    minutes = max(0, int((now - start).total_seconds() // 60))
    return str(minutes) + "m" if minutes < 60 else str(minutes // 60) + "h" + "{:02d}".format(minutes % 60) + "m"


def _num(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    return float(value)


# ---------------------------------------------------------------- subtasks (WP20)

SUB_ADDR_RE = re.compile(r"^([A-Za-z0-9]+\.[0-9]+)/([0-9]+)$")


def add_subtask(data_dir, task_id, title):
    """Append a subtask to a task (at most 12, title at most 80 characters).
    Returns {"addr", "t", "d"}, where addr is like P2.4/3.
    The task's status and the updated date are not changed."""
    _require_dir(data_dir)
    text = " ".join(str(title or "").split())
    if not text:
        raise RoadmapError("usage", "a subtask needs a title (allowed: text, up to 80 characters)", EXIT_USAGE)
    if len(text) > parsers.SUB_TITLE_MAX:
        raise RoadmapError("usage", "subtask title is " + str(len(text)) + " characters; the limit is "
                           + str(parsers.SUB_TITLE_MAX), EXIT_USAGE)
    with lock.locked(data_dir):
        doc = load(data_dir)
        task = _task_in(doc, task_id)
        subs = task.get("subs") if isinstance(task.get("subs"), list) else []
        if len(subs) >= parsers.SUBS_MAX:
            raise RoadmapError("usage", task_id + " already has " + str(parsers.SUBS_MAX) + " subtasks (the most); "
                               "finish or remove one first", EXIT_USAGE)
        sub = {"t": text, "d": False}
        subs.append(sub)
        task["subs"] = subs
        schema.write_data("tasks", tasks_path(data_dir), doc)
    return {"addr": task_id + "/" + str(len(subs)), "t": text, "d": False}


def toggle_subtask(data_dir, addr):
    """Tick or untick one subtask, addressed P2.4/2 (1-based). Ticking the first subtask moves a todo task to partial.
    A task is never finished by its subtasks. Returns the result; undo_subtask(result) reverses it."""
    _require_dir(data_dir)
    task_id, index = _parse_addr(addr)
    with lock.locked(data_dir):
        doc = load(data_dir)
        task = _task_in(doc, task_id)
        sub = _sub_at(task, task_id, index, addr)
        before = {"addr": addr, "done": sub.get("d") is True, "status": task.get("status")}
        sub["d"] = not before["done"]
        if sub["d"] and task.get("status") == "todo":
            task["status"] = "partial"
        schema.write_data("tasks", tasks_path(data_dir), doc)
    return {"addr": addr, "done": sub["d"], "status_before": before["status"], "status_after": task.get("status"),
            "before": before}


def undo_subtask(data_dir, result):
    """Put back the tick and the task status that toggle_subtask changed. result is what toggle_subtask returned."""
    _require_dir(data_dir)
    before = result["before"]
    task_id, index = _parse_addr(before["addr"])
    with lock.locked(data_dir):
        doc = load(data_dir)
        task = _task_in(doc, task_id)
        sub = _sub_at(task, task_id, index, before["addr"])
        sub["d"] = before["done"]
        if before["status"] is not None:
            task["status"] = before["status"]
        schema.write_data("tasks", tasks_path(data_dir), doc)
    return {"addr": before["addr"], "done": before["done"], "status": task.get("status")}


def _parse_addr(addr):
    match = SUB_ADDR_RE.match(str(addr or "").strip())
    if not match:
        raise RoadmapError("usage", "subtask address '" + str(addr) + "' must look like P2.4/2 "
                           "(task id, slash, subtask number from 1)", EXIT_USAGE)
    return match.group(1), int(match.group(2))


def _task_in(doc, task_id):
    for task in doc["tasks"]:
        if isinstance(task, dict) and task.get("id") == task_id:
            return task
    raise RoadmapError("not_found", "no task " + str(task_id), EXIT_NOT_FOUND)


def _sub_at(task, task_id, index, addr):
    subs = task.get("subs") if isinstance(task.get("subs"), list) else []
    if index < 1 or index > len(subs):
        raise RoadmapError("not_found", "no subtask " + str(addr) + " (" + task_id + " has " + str(len(subs))
                           + " subtasks)", EXIT_NOT_FOUND)
    return subs[index - 1]


# ---------------------------------------------------------------- helpers

def _empty():
    return {"schemaVersion": schema.current_version("tasks"), "updated": "", "phases": [], "tasks": []}


def _features_load(data_dir):
    """The features document (schemaVersion 1, features list). Written by the features helper below only, so the
    feature service can replace this one place later. A missing file gives an empty document; a newer file is
    newer_schema; bad JSON is invalid_data."""
    path = features_path(data_dir)
    data = atomic.read_json(path, default=None)
    if data is None:
        return {"schemaVersion": FEATURES_VERSION, "updated": "", "features": []}
    if not isinstance(data, dict) or not isinstance(data.get("features"), list):
        raise RoadmapError("invalid_data", "features.json needs a 'features' list; fix it, then retry: " + path,
                           EXIT_INVALID_DATA)
    found = data.get("schemaVersion", FEATURES_VERSION)
    if not isinstance(found, int) or found > FEATURES_VERSION:
        raise RoadmapError("newer_schema", "features.json was written by a newer roadmap-board; left unchanged: "
                           + path, EXIT_INVALID_DATA)
    return data


def _features_write(data_dir, fdoc):
    """Save the features document at FEATURES_VERSION. The caller holds the directory lock."""
    out = dict(fdoc)
    out["schemaVersion"] = FEATURES_VERSION
    atomic.write_json(features_path(data_dir), out)


def _require_dir(data_dir):
    if not os.path.isdir(data_dir):
        raise RoadmapError("not_found", "data folder does not exist: " + str(data_dir), EXIT_NOT_FOUND)


def _index(items):
    return {item["id"]: item for item in items if isinstance(item, dict) and isinstance(item.get("id"), str)}


def _phase_of(task):
    phase = task.get("phase")
    if isinstance(phase, str) and phase:
        return phase
    return str(task.get("id", "")).split(".")[0]


def _status_set(status):
    if status is None:
        return None
    items = status.split(",") if isinstance(status, str) else list(status)
    wanted = set()
    for item in items:
        text = str(item).strip()
        if text not in planfmt.TASK_STATUSES:
            raise RoadmapError("usage", "status '" + text + "' is not valid (allowed: "
                               + "|".join(planfmt.TASK_STATUSES) + ")", EXIT_USAGE)
        wanted.add(text)
    return wanted or None


def _registered_id(data_dir):
    target = os.path.abspath(data_dir)
    for project in config.list_projects():
        if os.path.abspath(jobs.data_dir_of(project)) == target:
            return project["id"]
    raise RoadmapError("not_found", "no registered project for this data folder, so no backup id (allowed: pass "
                       "project_id)", EXIT_NOT_FOUND)


def _default_name(data_dir):
    return os.path.basename(os.path.dirname(os.path.abspath(data_dir)))


def _line(rec, text):
    return "line " + str(rec.get("line", 0)) + ": " + text
