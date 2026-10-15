"""Board references (R7.12): the rb:<project>/<kind>/<id> strings the Copy button puts on the clipboard, and the compact
record a ref names.

Pure: no I/O and no import from the project. parse() and format_ref() handle the text. build() reads one record from a
snapshot dict (the one roadmap.services.loader builds) plus, for the kinds the snapshot does not hold in full, the one
item the command looked up (an issue, a question, a research note). lines() and data() render the record. A record never
carries an absolute path.
"""

import re

REF_RE = re.compile(r"rb:[a-z0-9-]+(/[a-z]+/[A-Za-z0-9._-]+)?")
PROJECT = "project"
KINDS = ("phase", "task", "sub", "feature", "issue", "question", "job", "research", "section", "view", "ask",
         "commit", "branch")
LINE_MAX = 10
SUB_SEP = ".s"
ASK_OF_MAX = 5                       # asks listed per task in ask_backlinks (the newest)

# The full command a record points to, as the last line ("next: ..."). {id} is the ref's id, {task} the sub's task.
NEXT = {
    "phase": "roadmap plan view",
    "task": "roadmap task show {id}",
    "sub": "roadmap task show {task}",
    "feature": "roadmap feature show {id}",
    "issue": "roadmap issue show {id}",
    "question": "roadmap ask get {id}",
    "job": "roadmap job list",
    "research": "roadmap research list",
    "section": "roadmap status",
    "view": "roadmap status",
    "ask": "roadmap head list",
    "commit": "roadmap git show {id}",
    "branch": "roadmap git branch",
    PROJECT: "roadmap project show {id}",
}


def parse(text):
    """(project, kind, id) of a board ref. A project-only ref gives kind 'project' and id equal to the project.
    Raises ValueError for anything that is not a board ref or names an unknown kind."""
    clean = text.strip() if isinstance(text, str) else ""
    if not REF_RE.fullmatch(clean):
        raise ValueError("not a board ref (expected rb:<project>/<kind>/<id>)")
    parts = clean[len("rb:"):].split("/")
    if len(parts) == 1:
        return parts[0], PROJECT, parts[0]
    project, kind, ident = parts
    if kind not in KINDS:
        raise ValueError("kind '" + kind + "' is not one of " + "|".join(KINDS))
    return project, kind, ident


def format_ref(project, kind, ident=None):
    """The ref text for a project, kind and id. Raises ValueError for an unknown kind or text that is not a ref."""
    if kind == PROJECT:
        text = "rb:" + str(project)
    elif kind in KINDS:
        text = "rb:%s/%s/%s" % (project, kind, ident)
    else:
        raise ValueError("kind '" + str(kind) + "' is not one of " + "|".join(KINDS))
    if not REF_RE.fullmatch(text):
        raise ValueError("'" + text + "' is not a board ref")
    return text


def _tokens(value):
    return "-" if value is None else "%gk" % round(float(value), 1)


def _pair(key, value):
    return (key, "-" if value in (None, "") else value)


def _orphan_ids(snap):
    return set((snap.get("features") or {}).get("orphans") or [])


def _find(items, ident, key="id"):
    for row in items or []:
        if isinstance(row, dict) and row.get(key) == ident:
            return row
    return None


def _task_rows(snap, ident):
    task = _find(snap.get("tasks"), ident)
    if task is None:
        return None
    feats = task.get("feats") or []
    subs = task.get("subs") or []
    orphan = ident in _orphan_ids(snap)
    rows = [[_pair("title", task.get("title"))],
            [_pair("status", task.get("state")), _pair("phase", task.get("phase")),
             _pair("feature", ",".join(feats) or None), _pair("orphan", "yes" if orphan else "no")]]
    if subs:
        rows.append([_pair("subs", "%d/%d done" % (sum(1 for s in subs if s.get("d")), len(subs)))])
    return rows


def _sub_rows(snap, ident):
    task_id, _, number = ident.rpartition(SUB_SEP)
    task = _find(snap.get("tasks"), task_id)
    if not number.isdigit() or task is None:
        return None
    subs = task.get("subs") or []
    index = int(number)
    if not 1 <= index <= len(subs):
        return None
    sub = subs[index - 1]
    return [[_pair("title", sub.get("t"))],
            [_pair("status", "done" if sub.get("d") else "open"), _pair("task", task_id)]]


def _feature_rows(snap, ident):
    row = _find((snap.get("features") or {}).get("rows"), ident)
    if row is None:
        return None
    rows = [[_pair("title", row.get("title"))],
            [_pair("status", row.get("state")), _pair("tasks", "%d/%d done" % (row.get("done", 0),
                                                                             row.get("total", 0))),
             _pair("prio", row.get("prio"))]]
    if row.get("blocked"):
        rows.append([_pair("blocked", "%d task(s)" % row["blocked"])])
    return rows


def _phase_rows(snap, ident):
    phase = _find(snap.get("phases"), ident)
    if phase is None:
        return None
    return [[_pair("title", phase.get("name"))],
            [_pair("status", phase.get("state")), _pair("tasks", "%d/%d done" % (phase.get("done", 0),
                                                                               phase.get("total", 0)))]]


def _job_rows(snap, ident):
    job = _find(snap.get("jobs"), ident)
    if job is None:
        return None
    return [[_pair("title", job.get("title"))],
            [_pair("state", job.get("status")), _pair("model", job.get("model")),
             _pair("tokens", _tokens(job.get("tokensK")))],
            [_pair("task", job.get("task"))]]


def _issue_rows(item):
    rows = [[_pair("title", item.get("title"))],
            [_pair("status", item.get("status")), _pair("kind", item.get("kind")), _pair("sev", item.get("sev")),
             _pair("tasks", " ".join(item.get("tasks") or []) or None)]]
    if item.get("note"):
        rows.append([_pair("note", item["note"])])
    return rows


def _question_rows(item):
    return [[_pair("title", item.get("text"))],
            [_pair("status", item.get("status")), _pair("block", "yes" if item.get("block") else "no"),
             _pair("task", item.get("task"))]]


def _research_rows(item):
    return [[_pair("title", item.get("title"))], [_pair("file", item.get("file"))]]


def _ask_rows(item):
    rows = [[_pair("title", item.get("sum"))],
            [_pair("status", item.get("status")), _pair("kind", item.get("kind")),
             _pair("age", None if item.get("age") is None else "%dm" % item["age"])]]
    if item.get("links"):
        rows.append([_pair("bound", " ".join(item["links"]))])
    return rows


def _commit_rows(item):
    return [[_pair("title", item.get("subject"))],
            [_pair("sha", item.get("sha")), _pair("author", item.get("author")), _pair("time", item.get("time"))],
            [_pair("task", item.get("task")), _pair("job", item.get("job"))]]


def _branch_rows(item):
    return [[_pair("title", item.get("name"))],
            [_pair("current", "yes" if item.get("current") else "no"), _pair("ahead", item.get("ahead")),
             _pair("behind", item.get("behind"))],
            [_pair("upstream", item.get("upstream"))]]


def _project_rows(snap, project):
    overall = snap.get("overall") or {}
    phases = overall.get("phases") or {}
    tasks = (overall.get("project") or {})
    title = (snap.get("project") or {}).get("title") or project
    return [[_pair("title", title)],
            [_pair("phases", "%d/%d done" % (phases.get("done", 0), phases.get("total", 0)))],
            [_pair("tasks", "%d/%d done" % (tasks.get("done", 0), tasks.get("total", 0)))]]


def _view_rows(ident):
    view, _, section = ident.partition(".")
    return [[_pair("view", view), _pair("section", section or None)]]


def build(snap, project, kind, ident, item=None):
    """(rows, next_cmd) for one ref, or None when there is no such record. rows is a list of lines, each a list of
    (key, value) pairs. item is the looked-up issue, question or research note (None when the lookup found nothing).
    A section ref needs a dot (view.section)."""
    rows = None
    if kind == PROJECT:
        rows = _project_rows(snap, project)
    elif kind == "phase":
        rows = _phase_rows(snap, ident)
    elif kind == "task":
        rows = _task_rows(snap, ident)
    elif kind == "sub":
        rows = _sub_rows(snap, ident)
    elif kind == "feature":
        rows = _feature_rows(snap, ident)
    elif kind == "job":
        rows = _job_rows(snap, ident)
    elif kind == "issue" and item:
        rows = _issue_rows(item)
    elif kind == "question" and item:
        rows = _question_rows(item)
    elif kind == "research" and item:
        rows = _research_rows(item)
    elif kind == "ask" and item:
        rows = _ask_rows(item)
    elif kind == "commit" and item:
        rows = _commit_rows(item)
    elif kind == "branch" and item:
        rows = _branch_rows(item)
    elif kind == "section" and "." in ident:
        rows = _view_rows(ident)
    elif kind == "view":
        rows = [[_pair("view", ident)]]
    if rows is None:
        return None
    task_id = ident.rpartition(SUB_SEP)[0] if kind == "sub" else ident
    return rows, NEXT[kind].format(id=ident, task=task_id)


def _line(pairs):
    return "  ".join("%s: %s" % (key, " ".join(str(value).split())) for key, value in pairs)


def lines(ref, rows, next_cmd):
    """The plain text lines of a record: the ref, one line per row, then next. At most LINE_MAX lines; when the rows
    are too many the middle is cut and next stays last."""
    out = ["ref: " + ref] + [_line(row) for row in rows] + ["next: " + next_cmd]
    if len(out) > LINE_MAX:
        out = out[:LINE_MAX - 1] + out[-1:]
    return out


def data(ref, rows, next_cmd):
    """The --json object: ref, every (key, value) of the rows (a key keeps its first value), and next."""
    obj = {"ref": ref}
    for row in rows:
        for key, value in row:
            obj.setdefault(key, value)
    obj["next"] = next_cmd
    return obj


def ask_backlinks(entries):
    """{task id: [ask ids]} for the task: links of the folded head entries, in file order (HEAD-SPEC section 12, the
    Work/Planner 'ask:H12' chip). At most ASK_OF_MAX asks per task, the newest kept. A task with no ask is left out.
    Pure."""
    found = {}
    for entry in entries or []:
        eid = entry.get("id") if isinstance(entry, dict) else None
        if not isinstance(eid, str):
            continue
        for ref in entry.get("links") or []:
            if isinstance(ref, str) and ref.startswith("task:") and ref[len("task:"):]:
                found.setdefault(ref[len("task:"):], []).append(eid)
    return {tid: ids[-ASK_OF_MAX:] for tid, ids in sorted(found.items())}
