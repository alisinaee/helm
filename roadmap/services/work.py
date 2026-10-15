"""Work items (the human card) and the link from agent tasks to them (docs/WORK-MODEL.md sections 1, 2 and 6, M4).

Ops (registered in services/cmdops.py): work.add, work.set, work.link, work.accept, work.reopen. Internal inverses for
undo: work.restore (one item back, or dropped) and work.relink (links back). Each op returns (data, summary, inverse)
and commands.run writes the activity line and the undo record.

Storage: docs/work.json (items, links, events). The store v4 tables (store/work_db.py) cannot be written from here:
commands.run holds the one db transaction while an op runs, and a second connection cannot take the write lock
(database is locked). So the file is the store in both backends until commands.py mirrors it.

Status: the stored status is the person's intent only: Backlog, Won't do, or Done once accepted. Todo, Doing and Review
come from workstatus.rollup over the linked agent tasks, on every read. work.accept and work.reopen are the person's
only (agentguard.person_context): an agent, the phone and a script are refused. A reopen holds the item in Doing until
the set of done agent tasks changes.
"""

import datetime
import os
import re

from roadmap.core import workstatus
from roadmap.errors import EXIT_CONFLICT, EXIT_INVALID_DATA, EXIT_NOT_FOUND, RoadmapError
from roadmap.services import agentguard, commands, tasks
from roadmap.store import atomic, lock

FILE = "work.json"
KINDS = ("task", "issue")
TITLE_MAX = 60
OUTCOME_MAX = 240
DEFAULT_PRIO = 2
WORK_ID = re.compile(r"^W[1-9][0-9]{0,5}$")
JARGON = re.compile(r"[/\\]|\.(py|js|json|md|html|css)\b|\b(wave|W\d+|haiku|sonnet|opus)\b", re.IGNORECASE)
NEXT_LIST = "roadmap status"
CLOSED_STATES = ("Backlog", "Won't do")


# ---------------------------------------------------------------- storage

def _now(now=None):
    moment = now or datetime.datetime.now(datetime.timezone.utc)
    return moment.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _empty():
    return {"schemaVersion": 1, "items": [], "links": {}, "events": []}


def _doc(data_dir):
    doc = atomic.read_json(os.path.join(data_dir, FILE), default=None)
    if doc is None:
        return _empty()
    if not isinstance(doc, dict):
        raise RoadmapError("invalid_data", "work.json is not an object, left unchanged", EXIT_INVALID_DATA)
    for key, value in _empty().items():
        doc.setdefault(key, value)
    return doc


def _save(data_dir, doc):
    atomic.write_json(os.path.join(data_dir, FILE), doc)


def _event(doc, kind, entity_id, payload, now):
    doc["events"].append({"ts": _now(now), "kind": kind, "entity": "work_item", "entity_id": entity_id,
                          "payload": payload})


def _num(wid):
    return int(str(wid)[1:])


def _find(doc, wid):
    for item in doc["items"]:
        if item["id"] == wid:
            return item
    raise RoadmapError("not_found", "no Work item " + str(wid), EXIT_NOT_FOUND, next=NEXT_LIST)


def _next_id(doc):
    return "W%d" % (max([_num(i["id"]) for i in doc["items"]] or [0]) + 1)


# ---------------------------------------------------------------- roll-up

def _task_rows(data_dir, doc, wid):
    """The agent tasks linked to wid, with their state from tasks.json (a task that no longer exists counts as
    cancelled, so it does not hold the item open)."""
    rows = []
    for tid, linked in doc["links"].items():
        if linked != wid:
            continue
        try:
            state = str(tasks.get(data_dir, tid).get("status") or "todo")
        except RoadmapError:
            state = "cancelled"
        rows.append({"id": tid, "state": state})
    return rows


def _done_ids(rows):
    return sorted(r["id"] for r in rows if r["state"] == "done")


def _view(data_dir, doc, item):
    """The Work item as the screens read it: the derived status, badges, progress and its task ids."""
    rows = _task_rows(data_dir, doc, item["id"])
    pending = item.get("reopenDone") is not None and _done_ids(rows) == item["reopenDone"]
    state = {"Backlog": "backlog", "Won't do": "wontfix"}.get(item["status"], "")
    result = workstatus.rollup({"state": state, "reopened": pending}, rows,
                               person_accepted=item.get("accepted") is not None)
    out = {key: item[key] for key in ("id", "kind", "title", "outcome", "owner", "phase", "accepted", "reopened")}
    out.update(status=result["status"], prio="P%d" % item["prio"], badges=result["badges"],
               progress=result["progress"], tasks=[r["id"] for r in rows])
    return out


# ---------------------------------------------------------------- argument checks

def _prio(value):
    text = str(DEFAULT_PRIO if value is None else value).strip().upper()
    if text.startswith("P"):
        text = text[1:]
    if text not in ("0", "1", "2", "3"):
        raise commands._usage("prio must be P0-P3", NEXT_LIST)
    return int(text)


def _title(value):
    text = commands._text(value)
    if not text or len(text) > TITLE_MAX:
        raise commands._usage("title must be 1-%d characters" % TITLE_MAX, NEXT_LIST)
    if JARGON.search(text):
        raise commands._usage("title has a file, model or wave name; say the outcome in plain words", NEXT_LIST)
    return text


def _outcome(value):
    text = commands._text(value)
    if len(text) > OUTCOME_MAX:
        raise commands._usage("outcome must be at most %d characters" % OUTCOME_MAX, NEXT_LIST)
    return text


def _wid(a, key):
    value = commands._text(a.get(key))
    if not WORK_ID.match(value):
        raise commands._usage("Work id '" + value[:20] + "' must look like W12", NEXT_LIST)
    return value


def check_add(a):
    kind = commands._text(a.get("kind")) or "task"
    if kind not in KINDS:
        raise commands._usage("kind must be task or issue", NEXT_LIST)
    return {"title": _title(a.get("title")), "outcome": _outcome(a.get("outcome")), "kind": kind,
            "prio": _prio(a.get("prio")), "phase": commands._text(a.get("phase")) or None}


def check_set(a):
    if "status" in a:
        raise commands._usage("status comes from the roll-up; use work accept or work reopen", NEXT_LIST)
    clean = {"id": _wid(a, "id")}
    if "title" in a:
        clean["title"] = _title(a.get("title"))
    if "outcome" in a:
        clean["outcome"] = _outcome(a.get("outcome"))
    if "prio" in a:
        clean["prio"] = _prio(a.get("prio"))
    if len(clean) == 1:
        raise commands._usage("nothing to set: give title, outcome or prio", NEXT_LIST)
    return clean


def check_link(a):
    task = commands._text(a.get("task"))
    if not task:
        raise commands._usage("task is required (an agent task id such as R7.86)", NEXT_LIST)
    return {"task": task, "work": _wid(a, "work")}


def check_one(a):
    return {"id": _wid(a, "id")}


def check_restore(a):
    item = a.get("item")
    if item is not None and not isinstance(item, dict):
        raise commands._usage("item must be a Work item or null")
    return {"id": _wid(a, "id"), "item": item}


def check_relink(a):
    links = a.get("links")
    if not isinstance(links, dict):
        raise commands._usage("links must be an object of task -> Work id or null")
    return {"links": links}


# ---------------------------------------------------------------- person only

def _person_only(op):
    if not agentguard.person_context(commands.current_source()):
        raise RoadmapError("agent_refused", op + " is for the person; an agent, the phone or a script cannot run it",
                           EXIT_CONFLICT, next="ask the person")


# ---------------------------------------------------------------- handlers

def h_add(data_dir, a, now):
    with lock.locked(data_dir):
        doc = _doc(data_dir)
        wid = _next_id(doc)
        stamp = _now(now)
        item = {"id": wid, "kind": a["kind"], "title": a["title"], "outcome": a["outcome"], "status": "Todo",
                "prio": a["prio"], "owner": "you", "phase": a["phase"], "created": stamp, "updated": stamp,
                "accepted": None, "reopened": 0, "reopenDone": None}
        doc["items"].append(item)
        _event(doc, "work.add", wid, {"title": a["title"], "kind": a["kind"]}, now)
        _save(data_dir, doc)
        view = _view(data_dir, doc, item)
    return view, wid + " " + a["title"] + " added", {"op": "work.restore", "args": {"id": wid, "item": None}}


def h_set(data_dir, a, now):
    with lock.locked(data_dir):
        doc = _doc(data_dir)
        item = _find(doc, a["id"])
        prior = dict(item)
        for key in ("title", "outcome", "prio"):
            if key in a:
                item[key] = a[key]
        item["updated"] = _now(now)
        _event(doc, "work.set", a["id"], {key: a[key] for key in a if key != "id"}, now)
        _save(data_dir, doc)
        view = _view(data_dir, doc, item)
    return view, a["id"] + " changed", {"op": "work.restore", "args": {"id": a["id"], "item": prior}}


def h_link(data_dir, a, now):
    with lock.locked(data_dir):
        doc = _doc(data_dir)
        item = _find(doc, a["work"])
        tasks.get(data_dir, a["task"])
        prior = doc["links"].get(a["task"])
        doc["links"][a["task"]] = a["work"]
        _event(doc, "work.link", a["task"], {"from": prior, "to": a["work"]}, now)
        _save(data_dir, doc)
        view = _view(data_dir, doc, item)
    return view, a["task"] + " -> " + a["work"], {"op": "work.relink", "args": {"links": {a["task"]: prior}}}


def h_accept(data_dir, a, now):
    _person_only("work accept")
    with lock.locked(data_dir):
        doc = _doc(data_dir)
        item = _find(doc, a["id"])
        before = _view(data_dir, doc, item)
        if before["status"] in CLOSED_STATES or before["status"] == "Done":
            raise RoadmapError("conflict", a["id"] + " is " + before["status"] + "; nothing to accept", EXIT_CONFLICT,
                               next=NEXT_LIST)
        prior = dict(item)
        item.update(status="Done", accepted=_now(now), updated=_now(now))
        _event(doc, "work.accept", a["id"], {"from": before["status"]}, now)
        _save(data_dir, doc)
        view = _view(data_dir, doc, item)
    return view, a["id"] + " accepted", {"op": "work.restore", "args": {"id": a["id"], "item": prior}}


def h_reopen(data_dir, a, now):
    _person_only("work reopen")
    with lock.locked(data_dir):
        doc = _doc(data_dir)
        item = _find(doc, a["id"])
        before = _view(data_dir, doc, item)
        if before["status"] not in ("Done", "Review"):
            raise RoadmapError("conflict", a["id"] + " is " + before["status"] + "; only Review or Done reopens",
                               EXIT_CONFLICT, next=NEXT_LIST)
        prior = dict(item)
        item.update(status="Todo", accepted=None, reopened=item["reopened"] + 1, updated=_now(now),
                    reopenDone=_done_ids(_task_rows(data_dir, doc, a["id"])))
        _event(doc, "work.reopen", a["id"], {"from": before["status"]}, now)
        _save(data_dir, doc)
        view = _view(data_dir, doc, item)
    return view, a["id"] + " reopened", {"op": "work.restore", "args": {"id": a["id"], "item": prior}}


def h_restore(data_dir, a, now):
    """Undo: put one Work item back as it was (item None drops it and its links)."""
    with lock.locked(data_dir):
        doc = _doc(data_dir)
        doc["items"] = [i for i in doc["items"] if i["id"] != a["id"]]
        if a["item"] is not None:
            doc["items"].append(a["item"])
            doc["items"].sort(key=lambda i: _num(i["id"]))
        else:
            doc["links"] = {t: w for t, w in doc["links"].items() if w != a["id"]}
        _event(doc, "work.restore", a["id"], {}, now)
        _save(data_dir, doc)
    return {"id": a["id"]}, "undo " + a["id"], None


def h_relink(data_dir, a, now):
    """Undo of work.link: the task's prior Work item (None removes the link)."""
    with lock.locked(data_dir):
        doc = _doc(data_dir)
        for task, work in a["links"].items():
            if work is None:
                doc["links"].pop(task, None)
            else:
                doc["links"][task] = work
            _event(doc, "work.relink", task, {"to": work}, now)
        _save(data_dir, doc)
    return {"links": a["links"]}, "undo link", None


def get_view(data_dir, wid):
    """One Work item as the screens read it (derived status), or not_found."""
    doc = _doc(data_dir)
    return _view(data_dir, doc, _find(doc, wid))


def list_views(data_dir):
    """Every Work item in id order, derived status included."""
    doc = _doc(data_dir)
    return [_view(data_dir, doc, item) for item in sorted(doc["items"], key=lambda i: _num(i["id"]))]
