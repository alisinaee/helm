"""Command layer (WP21): the one write path for CLI calls, and the registry behind POST /api/v1/cmd.

run(op, args, source, data_dir) validates the arguments, performs the write through the WP20 services, adds one line
to docs/activity.jsonl and returns {ok, data, activity, undo}. Every reversible op also stores its inverse in
undo.jsonl (keyed by the activity id) so that `undo <activity id>` can put the change back.

Locking: the WP20 services take the directory lock themselves, and flock is not re-entrant across file descriptors,
so run() does not hold an outer lock. Each write is atomic under its own service lock, and the undo record and the
activity line each take the lock in turn.

Internal ops (public False) are the inverses that undo runs; run() refuses them from callers.
"""

import contextlib
import datetime
import re
import shlex
import threading

from roadmap.core import parsers, planfmt
from roadmap.errors import EXIT_NOT_FOUND, EXIT_USAGE, RoadmapError
from roadmap.services import activity, budget, comments, issues, jobs, questions, queue, records, tasks
from roadmap.services import agentguard
from roadmap.store import jsonl, lock, schema

UNDO_FILE = "undo.jsonl"
UNDO_KEEP = 500
ACTIVITY_ID = re.compile(r"^A[0-9]+$")
INBOX_MAX_LINES = 6
INBOX_LOOKBACK = datetime.timedelta(hours=24)
TASK_STATUSES = ("todo", "partial", "done", "hold")
TOKENS_K_MAX = 10000000        # ten billion tokens: no real task, and a bound the budget sums can take


# ---------------------------------------------------------------- validation helpers

def _usage(message, next_cmd=None):
    return RoadmapError("usage", message, EXIT_USAGE, next=next_cmd)


def _text(value):
    return "" if value is None else str(value).strip()


def _id(a, key, what):
    value = _text(a.get(key))
    if not records.ID_OK.match(value):
        raise _usage(what + " '" + value + "' is not an id such as P2.4 (allowed: letters, digits, dots)",
                     "roadmap status")
    return value


def _opt_text(a, key):
    value = a.get(key)
    return "" if value is None else str(value)


def _opt_bool(a, key, default=None):
    value = a.get(key, default)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise _usage(key + " must be true or false")
    return value


def _id_list(a, key):
    value = a.get(key) or []
    if not isinstance(value, (list, tuple)):
        raise _usage(key + " must be a list of task ids")
    return [_id({"v": item}, "v", key) for item in value]


# ---------------------------------------------------------------- task.status, task.start, task.stop

def _check_task_status(a):
    status = _text(a.get("status"))
    if status not in TASK_STATUSES:
        raise _usage("status '" + status + "' is not valid (allowed: " + "|".join(TASK_STATUSES) + ")",
                     "roadmap task list --phase " + _text(a.get("id")).split(".")[0])
    tokens = a.get("tokensK")
    if tokens is not None and (isinstance(tokens, bool) or not isinstance(tokens, int)
                               or not 0 <= tokens <= TOKENS_K_MAX):
        raise _usage("tokensK must be a whole number of thousands of tokens, from 0 to " + str(TOKENS_K_MAX))
    note = a.get("note")
    if note is not None and not isinstance(note, str):
        raise _usage("note must be text")
    return {"id": _id(a, "id", "task id"), "status": status, "tokensK": tokens, "note": note}


def _h_task_status(data_dir, a, now):
    """Set the status (and optionally the note and tokens). Undo restores the prior status and note. Tokens feed
    the budget once per task (budget.record_task_tokens); that spend is not reversed by undo. The task's at map gets
    the time of this change under its new status (newest only; the other statuses keep their old times)."""
    before = tasks.get(data_dir, a["id"])
    if a["status"] == "partial":  # a start (the CLI "task start" also writes partial): same WP62b rule as the CLI
        refusal = tasks.start_refusal(data_dir, [a["id"]])
        if refusal is not None:
            raise refusal
    prior = before.get("status") or "todo"
    parts = [a["id"], "status=" + a["status"]]
    if a["tokensK"] is not None:
        parts.append("tokensK=" + str(a["tokensK"]))
    if a["note"] is not None:
        parts.append("note=" + shlex.quote(" ".join(a["note"].split())))
    set_records = _set_records(" ".join(parts))
    stamp = before.get("at") if isinstance(before.get("at"), dict) else {}
    set_records[0]["fields"]["at"] = dict(stamp, **{a["status"]: records.now_iso(now)})
    tasks.apply(data_dir, set_records)
    fed = False
    if a["tokensK"] is not None:
        fed = budget.record_task_tokens(data_dir, a["id"], _task_model(before), float(a["tokensK"]))
    summary = a["id"] + " " + prior + "->" + a["status"]
    inverse = None
    if prior != a["status"] or a["note"] is not None:
        inverse_args = {"id": a["id"], "status": prior}
        if a["note"] is not None:
            inverse_args["note"] = before.get("note") or ""
        inverse = {"op": "task.status", "args": inverse_args}
    return ({"id": a["id"], "status": a["status"], "changed": prior != a["status"], "was": prior,
             "budgetFed": fed}, summary, inverse)


def _task_model(task):
    model = task.get("model")
    return model if isinstance(model, str) and model.strip() else "unknown"


def _set_records(text):
    records_list, errors = planfmt.parse_set_text(text)
    if errors:
        raise _usage("; ".join(errors))
    return records_list


def _check_task_id(a):
    return {"id": _id(a, "id", "task id"), "by": _opt_text(a, "by")}


def _h_task_start(data_dir, a, now):
    tasks.get(data_dir, a["id"])
    queue.enqueue(data_dir, a["id"], by=a["by"], now=now)
    return {"task": a["id"], "queued": True}, "queued " + a["id"], {"op": "queue.remove", "args": {"task": a["id"]}}


def _h_task_stop(data_dir, a, now):
    tasks.get(data_dir, a["id"])
    _enqueue_stop(data_dir, a["id"], a["by"], now)
    return {"task": a["id"], "stop": True}, "stop requested " + a["id"], {"op": "queue.remove",
                                                                           "args": {"task": a["id"]}}


def _enqueue_stop(data_dir, task_id, by, now):
    """Queue a stop request for a task: a queue entry with op stop. A task already queued is a conflict."""
    with lock.locked(data_dir):
        doc = records.load("queue", data_dir, queue.FILE, "entries")
        if any(e.get("task") == task_id for e in doc["entries"]):
            raise records.conflict(task_id + " is already queued; not changed", "roadmap status")
        if len(doc["entries"]) >= queue.CAP:
            raise records.conflict("the queue holds " + str(queue.CAP) + " entries, the most allowed; "
                                   "dequeue one first", "roadmap status")
        entry = {"task": task_id, "by": by, "at": records.now_iso(now), "op": "stop"}
        doc["entries"].append(entry)
        records.save("queue", data_dir, queue.FILE, doc)
    return entry


def _check_queue_remove(a):
    return {"task": _id(a, "task", "task id")}


def _h_queue_remove(data_dir, a, now):
    removed = queue.dequeue(data_dir, a["task"])
    return {"task": a["task"], "removed": removed}, "dequeued " + a["task"], None


# ---------------------------------------------------------------- subtasks

def _check_subtask_toggle(a):
    addr = _text(a.get("addr"))
    if not tasks.SUB_ADDR_RE.match(addr):
        raise _usage("subtask address '" + addr + "' must look like P2.4/2 (task id, slash, number from 1)",
                     "roadmap status")
    return {"addr": addr, "done": _opt_bool(a, "done")}


def _h_subtask_toggle(data_dir, a, now):
    task_id = tasks.SUB_ADDR_RE.match(a["addr"]).group(1)
    subs = tasks.get(data_dir, task_id).get("subs") or []
    index = int(a["addr"].split("/")[1])
    if index < 1 or index > len(subs):
        raise RoadmapError("not_found", "no subtask " + a["addr"] + " (" + task_id + " has " + str(len(subs))
                           + " subtasks)", EXIT_NOT_FOUND, next="roadmap status")
    current = subs[index - 1].get("d") is True
    if a["done"] is not None and a["done"] == current:
        word = "done" if current else "open"
        return {"addr": a["addr"], "done": current, "changed": False}, a["addr"] + " already " + word, None
    result = tasks.toggle_subtask(data_dir, a["addr"])
    word = "done" if result["done"] else "open"
    return ({"addr": a["addr"], "done": result["done"], "changed": True}, a["addr"] + " " + word,
            {"op": "subtask.restore", "args": {"result": result}})


def _check_subtask_add(a):
    return {"id": _id(a, "id", "task id"), "title": _opt_text(a, "title")}


def _h_subtask_add(data_dir, a, now):
    added = tasks.add_subtask(data_dir, a["id"], a["title"])
    return added, "added " + added["addr"], None


def _check_subtask_restore(a):
    result = a.get("result")
    if not isinstance(result, dict) or not isinstance(result.get("before"), dict):
        raise _usage("subtask restore needs the result of a toggle", "roadmap status")
    return {"result": result}


def _h_subtask_restore(data_dir, a, now):
    back = tasks.undo_subtask(data_dir, a["result"])
    return back, "restored " + back["addr"], None


# ---------------------------------------------------------------- plan.move

def _check_plan_move(a):
    before = _text(a.get("before"))
    after = _text(a.get("after"))
    if bool(before) == bool(after):
        raise _usage("give exactly one of --before ID or --after ID", "roadmap plan view")
    ref = before or after
    return {"id": _id(a, "id", "task id"), "ref": _id({"v": ref}, "v", "reference task id"),
            "where": "before" if before else "after"}


def _phase_of(task):
    phase = task.get("phase")
    if isinstance(phase, str) and phase:
        return phase
    return str(task.get("id", "")).split(".")[0]


def _h_plan_move(data_dir, a, now):
    path = tasks.tasks_path(data_dir)
    with lock.locked(data_dir):
        doc = tasks.load(data_dir)
        items = doc["tasks"]
        ids = [item.get("id") if isinstance(item, dict) else None for item in items]
        if a["id"] not in ids:
            raise RoadmapError("not_found", "no task " + a["id"], EXIT_NOT_FOUND,
                               next="roadmap plan view")
        if a["ref"] not in ids:
            raise RoadmapError("not_found", "no task " + a["ref"], EXIT_NOT_FOUND, next="roadmap plan view")
        if a["id"] == a["ref"]:
            raise _usage("a task cannot move next to itself", "roadmap plan view")
        mover_item = items[ids.index(a["id"])]
        if _phase_of(mover_item) != _phase_of(items[ids.index(a["ref"])]):
            raise _usage(a["id"] + " and " + a["ref"] + " are in different phases (allowed: move within one phase)",
                         "roadmap plan view")
        siblings = [i.get("id") for i in items if isinstance(i, dict) and _phase_of(i) == _phase_of(mover_item)]
        here = siblings.index(a["id"])
        if here > 0:
            inverse = {"op": "plan.move", "args": {"id": a["id"], "after": siblings[here - 1]}}
        elif len(siblings) > 1:
            inverse = {"op": "plan.move", "args": {"id": a["id"], "before": siblings[1]}}
        else:
            inverse = None
        before_ids = list(ids)
        items.pop(ids.index(a["id"]))
        target = [i.get("id") if isinstance(i, dict) else None for i in items].index(a["ref"])
        items.insert(target if a["where"] == "before" else target + 1, mover_item)
        after_ids = [i.get("id") if isinstance(i, dict) else None for i in items]
        if after_ids == before_ids:
            return {"id": a["id"], "moved": False}, a["id"] + " already in place", None
        doc["updated"] = planfmt.today()
        schema.write_data("tasks", path, doc)
    summary = "moved " + a["id"] + " " + a["where"] + " " + a["ref"]
    return {"id": a["id"], "moved": True, "ref": a["ref"], "where": a["where"]}, summary, inverse


# ---------------------------------------------------------------- questions and comments

def _check_question_ask(a):
    opts = a.get("opts") or []
    if not isinstance(opts, (list, tuple)):
        raise _usage("opts must be a list of answers")
    timeout = a.get("timeout")
    if timeout is not None and (isinstance(timeout, bool) or not isinstance(timeout, int)):
        raise _usage("timeout must be a whole number of seconds")
    task = _text(a.get("task"))
    if task and not records.ID_OK.match(task):
        raise _usage("task '" + task + "' is not a task id", "roadmap status")
    return {"text": _opt_text(a, "text"), "task": task, "opts": [str(o) for o in opts],
            "default": a.get("default"), "block": _opt_bool(a, "block", False) is True, "timeout": timeout}


def _h_question_ask(data_dir, a, now):
    question = questions.ask(data_dir, a["task"], a["text"], opts=a["opts"], default=a["default"],
                             block=a["block"], timeout_s=a["timeout"], now=now)
    return question, question["id"] + " asked: " + a["text"], None


def _check_question_answer(a):
    return {"id": _id(a, "id", "question id"), "value": _opt_text(a, "value")}


def _h_question_answer(data_dir, a, now):
    question = questions.answer(data_dir, a["id"], a["value"], now=now)
    inverse = {"op": "question.reopen", "args": {"id": question["id"]}}
    return question, question["id"] + " answered " + question["answer"], inverse


def _check_question_reopen(a):
    return {"id": _id(a, "id", "question id")}


def _h_question_reopen(data_dir, a, now):
    question = questions.reopen(data_dir, a["id"])
    return question, question["id"] + " open again", None


def _check_comment_add(a):
    return {"on": _id(a, "on", "comment target"), "text": _opt_text(a, "text"), "by": _opt_text(a, "by")}


def _h_comment_add(data_dir, a, now):
    comment = comments.add(data_dir, a["on"], a["by"], a["text"], now=now)
    return comment, "comment on " + a["on"], None


# ---------------------------------------------------------------- issues

def _check_issue_new(a):
    sev = a.get("sev", 2)
    if isinstance(sev, bool) or not isinstance(sev, int):
        raise _usage("sev must be 1, 2 or 3")
    return {"title": _opt_text(a, "title"), "kind": _text(a.get("kind")) or "bug", "sev": sev,
            "tasks": _id_list(a, "tasks"), "note": a.get("note"), "by": _opt_text(a, "by")}


def _h_issue_new(data_dir, a, now):
    _require_known_tasks(data_dir, a["tasks"])
    issue = issues.open_issue(data_dir, a["title"], a["kind"], sev=a["sev"], tasks=a["tasks"], by=a["by"],
                              note=a["note"], now=now)
    return issue, issue["id"] + " new: " + issue["title"], {"op": "issue.status",
                                                            "args": {"id": issue["id"], "status": "closed"}}


def _check_issue_id(a):
    return {"id": _id(a, "id", "issue id")}


def _h_issue_close(data_dir, a, now):
    prior = issues.get(data_dir, a["id"])
    if prior.get("status") == "closed":
        return {"id": a["id"], "status": "closed", "changed": False}, a["id"] + " already closed", None
    issue = issues.close(data_dir, a["id"], now=now)
    return ({"id": a["id"], "status": "closed", "changed": True}, a["id"] + " closed",
            {"op": "issue.status", "args": {"id": a["id"], "status": prior.get("status")}})


def _check_issue_status(a):
    status = _text(a.get("status"))
    if status not in parsers.ISSUE_STATUSES:
        raise _usage("status '" + status + "' is not valid (allowed: " + "|".join(parsers.ISSUE_STATUSES) + ")")
    return {"id": _id(a, "id", "issue id"), "status": status}


def _h_issue_status(data_dir, a, now):
    issue = issues.set_status(data_dir, a["id"], a["status"], now=now)
    return {"id": a["id"], "status": a["status"]}, a["id"] + " " + a["status"], None


def _check_issue_link(a):
    return {"id": _id(a, "id", "issue id"), "tasks": _id_list(a, "tasks")}


def _require_known_tasks(data_dir, task_ids):
    known = jobs.known_task_ids(data_dir)
    for task_id in task_ids:
        if task_id not in known:
            raise RoadmapError("not_found", "no task " + task_id + " in tasks.json", EXIT_NOT_FOUND,
                               next="roadmap status")


def _h_issue_link(data_dir, a, now):
    _require_known_tasks(data_dir, a["tasks"])
    prior = list(issues.get(data_dir, a["id"]).get("tasks") or [])
    merged = prior + [t for t in a["tasks"] if t not in prior]
    if len(merged) == len(prior):
        return {"id": a["id"], "tasks": prior, "changed": False}, a["id"] + " already links these", None
    _set_issue_tasks(data_dir, a["id"], merged)
    return ({"id": a["id"], "tasks": merged, "changed": True}, a["id"] + " links " + " ".join(merged),
            {"op": "issue.links", "args": {"id": a["id"], "tasks": prior}})


def _check_issue_links(a):
    return {"id": _id(a, "id", "issue id"), "tasks": _id_list(a, "tasks")}


def _h_issue_links(data_dir, a, now):
    _set_issue_tasks(data_dir, a["id"], a["tasks"])
    return {"id": a["id"], "tasks": a["tasks"]}, a["id"] + " links restored", None


def _set_issue_tasks(data_dir, issue_id, task_ids):
    """Replace an issue's linked task list (at most issues.TASKS_MAX, as the issue service allows)."""
    if len(task_ids) > issues.TASKS_MAX:
        raise _usage("an issue links at most " + str(issues.TASKS_MAX) + " tasks", "roadmap issue show " + issue_id)
    with lock.locked(data_dir):
        doc = records.load("issues", data_dir, issues.FILE, "issues")
        for item in doc["issues"]:
            if isinstance(item, dict) and item.get("id") == issue_id:
                item["tasks"] = list(task_ids)
                records.save("issues", data_dir, issues.FILE, doc)
                return
    raise RoadmapError("not_found", "no issue " + issue_id, EXIT_NOT_FOUND, next="roadmap issue list")


# ---------------------------------------------------------------- undo

def _check_undo(a):
    value = _text(a.get("activity"))
    if not ACTIVITY_ID.match(value):
        raise _usage("activity id '" + value + "' must look like A812", "roadmap status")
    return {"activity": value}


def _undo_state(entries, target):
    """'undid' when the change is undone, 'undoing' while an undo holds it, None when it can be undone. A claim whose
    run failed (undoFailed) is released."""
    state = None
    for e in entries:
        if e.get("undid") == target:
            state = "undid"
        elif e.get("undoing") == target:
            state = "undoing"
        elif e.get("undoFailed") == target:
            state = None
    return state


def _h_undo(data_dir, a, now):
    """Undo one change. The check and a claim ('undoing') are written under the folder lock before the inverse runs,
    so two undo calls for one change cannot both run it. The inverse takes its own locks, so it runs outside ours.
    A phone may undo only a change the phone itself made (its own origin line)."""
    path = records.file_of(data_dir, UNDO_FILE)
    target = a["activity"]
    with lock.locked(data_dir):
        entries, _ = jsonl.read_objects(path)
        if _undo_state(entries, target) is not None:
            raise records.conflict(target + " is already undone or being undone; not changed", "roadmap status")
        found = [e for e in entries if e.get("activity") == target]
        if not found:
            raise RoadmapError("not_found", "no undo for " + target + " (only changes that can be reversed)",
                               EXIT_NOT_FOUND, next="roadmap status")
        entry = found[-1]
        if current_source() == "phone" and _origin_source(data_dir, target) != "phone":
            raise RoadmapError("forbidden", "the phone may undo only its own changes", EXIT_USAGE)
        jsonl.append_line(path, {"undoing": target, "at": records.now_iso(now)})
    try:
        _execute(data_dir, entry["op"], entry.get("args") or {}, now)
    except Exception:
        with lock.locked(data_dir):
            jsonl.append_line(path, {"undoFailed": target, "at": records.now_iso(now)})
        raise
    with lock.locked(data_dir):
        jsonl.append_line(path, {"undid": target, "at": records.now_iso(now)})
        jsonl.keep_newest(path, UNDO_KEEP)
    return ({"undone": target, "op": entry["op"], "sum": entry.get("sum", "")},
            "undid " + target + ": " + str(entry.get("sum", "")), None)


def _origin_source(data_dir, activity_id):
    """The source of the activity line a change was logged under, or None when that line is gone."""
    for line in activity.recent(data_dir, 100000):
        if line.get("id") == activity_id:
            return line.get("src")
    return None


# ---------------------------------------------------------------- registry

class _Op(object):
    """One registry entry. logs False means the service already writes its own activity line (control, rules), so
    run() takes that line instead of adding one."""
    __slots__ = ("check", "handler", "public", "logs")

    def __init__(self, check, handler, public=True, logs=True):
        self.check = check
        self.handler = handler
        self.public = public
        self.logs = logs


# The caller's source and project for the op that is running on this thread (the HTTP server runs one thread per
# request, so a thread-local is per call). Handlers read them; see cmdops.
_CTX = threading.local()


@contextlib.contextmanager
def context(source, project_id=None):
    """Set the source and project for ops run inside the block, restoring the outer values after."""
    saved = (getattr(_CTX, "source", None), getattr(_CTX, "project", None))
    _CTX.source, _CTX.project = source, project_id
    try:
        yield
    finally:
        _CTX.source, _CTX.project = saved


def current_source():
    """The source of the op running on this thread: gui, cli, agent or phone. cli when no context is set."""
    return getattr(_CTX, "source", None) or "cli"


def current_project():
    """The project id of the op running on this thread, or None."""
    return getattr(_CTX, "project", None)


def _load_ops():
    from roadmap.services import cmdops  # noqa: F401  (importing registers the control, rules and budget ops)


OPS = {
    "task.status": _Op(_check_task_status, _h_task_status),
    "task.start": _Op(_check_task_id, _h_task_start),
    "task.stop": _Op(_check_task_id, _h_task_stop),
    "subtask.toggle": _Op(_check_subtask_toggle, _h_subtask_toggle),
    "subtask.add": _Op(_check_subtask_add, _h_subtask_add),
    "plan.move": _Op(_check_plan_move, _h_plan_move),
    "question.ask": _Op(_check_question_ask, _h_question_ask),
    "question.answer": _Op(_check_question_answer, _h_question_answer),
    "comment.add": _Op(_check_comment_add, _h_comment_add),
    "issue.new": _Op(_check_issue_new, _h_issue_new),
    "issue.close": _Op(_check_issue_id, _h_issue_close),
    "issue.link": _Op(_check_issue_link, _h_issue_link),
    "undo": _Op(_check_undo, _h_undo),
    # Internal inverses, used only by undo.
    "queue.remove": _Op(_check_queue_remove, _h_queue_remove, public=False),
    "issue.status": _Op(_check_issue_status, _h_issue_status, public=False),
    "issue.links": _Op(_check_issue_links, _h_issue_links, public=False),
    "subtask.restore": _Op(_check_subtask_restore, _h_subtask_restore, public=False),
    "question.reopen": _Op(_check_question_reopen, _h_question_reopen, public=False),
}


def public_ops():
    """The op names a caller may run, sorted."""
    _load_ops()
    return sorted(name for name, op in OPS.items() if op.public)


def run(op, args, source, data_dir, now=None):
    """Validate, write, log and reply. Returns {ok, data, activity, undo}. Errors raise RoadmapError with a next."""
    if source not in activity.SOURCES:
        raise _usage("source '" + str(source) + "' is not valid (allowed: " + "|".join(activity.SOURCES) + ")")
    _load_ops()
    entry = OPS.get(op)
    if entry is None or not entry.public:
        raise _usage("unknown op '" + str(op) + "' (allowed: " + "|".join(public_ops()) + ")", "roadmap status")
    if args is not None and not isinstance(args, dict):
        raise _usage("args must be an object")
    records.require_dir(data_dir)
    clean = entry.check(args or {})
    with context(source, current_project()):
        before = _newest_id(data_dir)
        data, summary, inverse = entry.handler(data_dir, clean, now)
    if entry.logs:
        line = activity.append(data_dir, source, op, summary, undo=inverse is not None, now=now)
    else:
        line = _newest_line(data_dir)
        if line is None or line["id"] == before:  # the service wrote nothing, so log the op here
            line = activity.append(data_dir, source, op, summary, undo=inverse is not None, now=now)
    if inverse is not None:
        _remember(data_dir, line["id"], summary, inverse, now)
    return {"ok": True, "data": data, "activity": line["id"], "undo": inverse is not None}


def _newest_line(data_dir):
    lines = activity.recent(data_dir, 1)
    return lines[-1] if lines else None


def _newest_id(data_dir):
    line = _newest_line(data_dir)
    return line["id"] if line else None


def _execute(data_dir, op, args, now):
    """Run an internal inverse. It writes but logs nothing itself (undo writes its own line), except services that
    always log, which keep their own line."""
    _load_ops()
    entry = OPS.get(op)
    if entry is None:
        raise RoadmapError("usage", "no inverse op " + str(op), EXIT_USAGE)
    return entry.handler(data_dir, entry.check(args or {}), now)


def _remember(data_dir, activity_id, summary, inverse, now):
    path = records.file_of(data_dir, UNDO_FILE)
    with lock.locked(data_dir):
        jsonl.append_line(path, {"activity": activity_id, "sum": summary, "op": inverse["op"],
                                 "args": inverse["args"], "at": records.now_iso(now)})
        jsonl.keep_newest(path, UNDO_KEEP)


@contextlib.contextmanager
def next_on_error(next_cmd):
    """Give a RoadmapError that has no next: line the command that comes next."""
    try:
        yield
    except RoadmapError as exc:
        if not exc.next:
            exc.next = next_cmd
        raise


def locate(project_id, next_cmd):
    """The data folder of the project a CLI call acts on (see tasks.resolve)."""
    with next_on_error(next_cmd):
        _, data_dir = tasks.resolve(project_id)
    return data_dir


def write(project_id, op, payload, next_cmd):
    """Run one op for a CLI call on the project's data folder and return the reply. The control state is recomputed
    after the write (best effort)."""
    with next_on_error(next_cmd):
        project, data_dir = tasks.resolve(project_id)
    source = agentguard.source_name()  # 'agent' inside an agent's shell, else 'cli'
    with next_on_error(next_cmd), context(source, project["id"]):
        reply = run(op, payload, source, data_dir)
    from roadmap.services import control
    control.after_write(project["id"])
    return reply


def json_data(reply):
    """The --json data of a write reply: the op's data plus activity and undo."""
    return dict(reply["data"], activity=reply["activity"], undo=reply["undo"])


# ---------------------------------------------------------------- read helpers for the CLI and the status lines

def k_text(value):
    """Thousands of tokens as text: 20k, 20.5k."""
    number = round(float(value or 0), 1)
    return str(int(number)) + "k" if number == int(number) else str(number) + "k"


def _short(text, limit):
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[:limit - 3] + "..."


def ask_line(data_dir):
    open_qs = questions.list_questions(data_dir, open_only=True)
    if not open_qs:
        return "ask: none open"
    first = open_qs[0]
    more = " (+%d)" % (len(open_qs) - 1) if len(open_qs) > 1 else ""
    return "ask: %d open: %s %s%s" % (len(open_qs), first["id"], _short(first["text"], 40), more)


def queue_line(data_dir):
    entries = queue.list_queue(data_dir)
    if not entries:
        return "queue: empty"
    names = [("stop " if e.get("op") == "stop" else "") + str(e.get("task")) for e in entries[:3]]
    more = " (+%d)" % (len(entries) - 3) if len(entries) > 3 else ""
    return "queue: %d waiting: %s%s" % (len(entries), " ".join(names), more)


def issues_line(data_dir):
    open_items = issues.list_issues(data_dir)
    if not open_items:
        return "issues: none open"
    counts = []
    for kind in parsers.ISSUE_KINDS:
        n = sum(1 for i in open_items if i.get("kind") == kind)
        if n:
            counts.append("%d %s" % (n, kind))
    return "issues: %d open (%s)" % (len(open_items), ", ".join(counts))


def budget_totals(data_dir):
    """(spent total in k, by model, by phase, project limit or None, limits block)."""
    doc = budget.get(data_dir)
    by_model, by_phase = {}, {}
    total = 0.0
    for task_id, models in doc["spent"].items():
        phase = budget.UNATTRIBUTED if task_id == budget.UNATTRIBUTED else str(task_id).split(".")[0]
        for model, amount in models.items():
            total += amount
            by_model[model] = by_model.get(model, 0.0) + amount
            by_phase[phase] = by_phase.get(phase, 0.0) + amount
    return total, by_model, by_phase, doc["limits"].get("project"), doc["limits"]


def budget_line(data_dir):
    total, _, _, limit, _ = budget_totals(data_dir)
    if limit is None:
        return "budget: %s spent, no project limit" % k_text(total)
    return "budget: %s spent of %s" % (k_text(total), k_text(limit))


def status_extras(data_dir):
    """The four status lines the command layer adds, keyed by name."""
    return {"ask": ask_line(data_dir), "queue": queue_line(data_dir), "issues": issues_line(data_dir),
            "budget": budget_line(data_dir)}


def inbox_lines(data_dir, now=None):
    """Up to INBOX_MAX_LINES lines: queued requests, questions answered in the last 24 h, open questions."""
    moment = now if now is not None else datetime.datetime.now().astimezone()
    lines = []
    for entry in queue.list_queue(data_dir)[:2]:
        verb = "stop" if entry.get("op") == "stop" else "start"
        lines.append("queued: %s %s by %s" % (verb, entry.get("task"), entry.get("by") or "-"))
    answered = []
    for q in questions.list_questions(data_dir):
        if q.get("status") in ("answered", "defaulted") and _recent(q.get("answered"), moment):
            answered.append(q)
    for q in answered[-2:]:
        lines.append("answered: %s %s" % (q["id"], q.get("answer")))
    for q in questions.list_questions(data_dir, open_only=True)[:2]:
        lines.append("open: %s %s" % (q["id"], _short(q["text"], 60)))
    if not lines:
        return ["inbox: nothing waiting"]
    if len(lines) > INBOX_MAX_LINES:
        shown = len(lines) - (INBOX_MAX_LINES - 1)
        lines = lines[:INBOX_MAX_LINES - 1] + ["(+%d more: roadmap ask list)" % shown]
    return lines


def _recent(stamp, moment):
    if not isinstance(stamp, str):
        return False
    try:
        parsed = datetime.datetime.fromisoformat(stamp)
    except ValueError:
        return False
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return moment - parsed <= INBOX_LOOKBACK
