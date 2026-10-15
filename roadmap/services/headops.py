"""Head ops (HEAD-SPEC sections 4 and 10): the registry entries behind `roadmap head ...`, run through commands.run like the
feature ops. Each op returns (data, summary, inverse), so commands.run logs one activity line and undo can replay the
inverse.

Public: head.log, head.triage, head.set, head.bind, head.unbind, head.split, head.merge, head.convert, head.review,
head.accept, head.forget. Internal: head.restore, the inverse that undo replays (a snapshot of the fields an op changed).

Person only (agentguard.person_context, the rule feature.accept uses): head.review, head.accept and head.forget. An
agent, the phone and a bare non-TTY shell are refused with "ask the person". The head may set done (head.set
status=done); the person confirms it or reopens it with head.review.

head.convert creates through the services' own calls: issues.open_issue for an issue, tasks.apply for a task or a
backlog item (the same records as `roadmap backlog add`). Undo restores the head entry only; the created item stays.
head.accept marks the entry done with the note "accepted": the head record has no date field (HEAD-SPEC section 2).
"""

import os
import re
from datetime import datetime, timezone

from roadmap.core import head, planfmt
from roadmap.core.parsers import ISSUE_KINDS, TITLE_MAX
from roadmap.errors import EXIT_CONFLICT, EXIT_NOT_FOUND, EXIT_USAGE, RoadmapError
from roadmap.services import agentguard, commands, issues, notify, tasks
from roadmap.services import head as store
from roadmap.store import config, jsonl, lock

NEXT_LIST = "roadmap head list"
ID_RE = re.compile(r"^H[1-9][0-9]{0,3}$")
BACKLOG_PHASE = "BL"            # the reserved Backlog phase (commands/backlog.py RESERVED_PHASE)
BACKLOG_NAME = "Backlog"
BACKLOG_MODEL = "haiku"         # placeholders, as in `roadmap backlog add`
BACKLOG_THINKING = "low"
CONVERT_TARGETS = ("task", "issue", "backlog", "rule")
REVIEW_ACTIONS = ("confirm", "reopen")
ISSUE_SEV = 2
RULE_NOTE = "add to rules.txt?"
ACCEPT_NOTE = "accepted"
FORGET_NOTE = "verbatim forgotten"


# ---------------------------------------------------------------- argument checks

def _hid(a, key="id"):
    value = commands._text(a.get(key))
    if not ID_RE.match(value):
        raise commands._usage("head id '" + value + "' must look like H15", NEXT_LIST)
    return value


def _ref_list(value, key="refs"):
    """Canonical link refs ('task:R7.31'), no repeats, at most MAX_LINKS. None or empty gives []."""
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        raise commands._usage(key + " must be a list of link refs such as task:R7.31", NEXT_LIST)
    refs = []
    for item in value:
        parsed = head.parse_link(commands._text(item))
        if parsed is None:
            raise commands._usage("link '" + commands._text(item) + "' must look like task:R7.31 (kinds: "
                                  + ", ".join(head.LINK_KINDS) + ")", NEXT_LIST)
        ref = parsed[0] + ":" + parsed[1]
        if ref not in refs:
            refs.append(ref)
    if len(refs) > head.MAX_LINKS:
        raise commands._usage("at most " + str(head.MAX_LINKS) + " link refs per call", NEXT_LIST)
    return refs


def _kind_arg(a, key="kind"):
    value = commands._text(a.get(key))
    if value == "":
        return None
    if value not in store.KINDS:
        raise commands._usage(key + " must be one of " + "|".join(store.KINDS), NEXT_LIST)
    return value


def _sum_arg(a, key="sum", required=False):
    text = commands._text(a.get(key))
    if text == "":
        if required:
            raise commands._usage(key + " must not be empty", NEXT_LIST)
        return None
    return store.make_summary("", text)


def _status_arg(a, key="status"):
    value = commands._text(a.get(key))
    if value == "":
        return None
    if value not in head.MANUAL_STATUSES:
        raise commands._usage(key + " must be one of " + "|".join(head.MANUAL_STATUSES), NEXT_LIST)
    return value


def _need_refs(a):
    refs = _ref_list(a.get("refs"))
    if not refs:
        raise commands._usage("give at least one link ref such as task:R7.31", NEXT_LIST)
    return refs


# ---------------------------------------------------------------- shared helpers

def _row(data_dir, eid):
    for row in store.rows(data_dir):
        if row["id"] == eid:
            return row
    raise RoadmapError("not_found", "no head entry " + eid, EXIT_NOT_FOUND, next=NEXT_LIST)


def _by():
    """'person' for the person's own call (agentguard.person_context), else 'head'."""
    return "person" if agentguard.person_context(commands.current_source()) else "head"


def _src():
    return "gui" if commands.current_source() == "gui" else "cli"


def _person_only(op):
    if not agentguard.person_context(commands.current_source()):
        raise RoadmapError("agent_refused", op + " is for the person; an agent, the phone or a script cannot run it",
                           EXIT_CONFLICT, next="ask the person")


def _person_closed(data_dir, eid):
    """True when the person's own last status mark on eid is done (a confirmed or accepted entry). Only the person
    may then change its status."""
    last = None
    for rec in store._records(data_dir):
        if rec.get("t") == "u" and rec.get("id") == eid and isinstance(rec.get("set"), dict) \
                and "status" in rec["set"]:
            last = rec
    return bool(last) and last.get("by") == "person" and last["set"]["status"] == "done"


def _guard_status(data_dir, eid, status):
    """Refuse an agent's status change that would reopen (open) or override a person's done mark. Other statuses
    on an entry the person has not closed stay with the head."""
    if status is None:
        return
    if status == "open" or _person_closed(data_dir, eid):
        _person_only("head status=" + status + " on " + eid)


def _umbrella_only(links):
    """True when links is not empty and every ref is an umbrella task (task:R7.31, HEAD-SPEC section 12)."""
    return bool(links) and all(ref.startswith("task:") and planfmt.is_umbrella_task(ref[len("task:"):])
                               for ref in links)


def _check_real_bind(status, links, eid):
    """HEAD-SPEC section 12: an open ask must not be bound only to an umbrella task. Closed asks may keep them."""
    if status not in head.CLOSED_STATUSES and _umbrella_only(links):
        raise commands._usage(eid + " is open and would be bound only to the umbrella task R7.31; bind a real task "
                              "(head convert " + eid + " creates one)", "roadmap head convert " + eid)


def umbrella_only_asks(data_dir, now=None):
    """Ids of open asks bound only to umbrella tasks: the gate's list of asks that still need a real task."""
    return [row["id"] for row in store.rows(data_dir, now=now)
            if row["status"] not in head.CLOSED_STATUSES and _umbrella_only(row["links"])]


def _prior(row, keys):
    """The current values of the fields an op is about to change, as set fields. status reads as 'open' when no
    manual status is set (update() accepts it), and a guessed kind loses its '?' mark."""
    values = {}
    for key in keys:
        if key == "status":
            values[key] = row["manual"] or "open"
        elif key == "kind":
            kind = str(row["kind"] or "").rstrip("?")
            if kind in store.KINDS:
                values[key] = kind
        elif key == "sum":
            values[key] = row["sum"] or ""
        elif key == "into":
            values[key] = row["into"]
    return values


def _step(eid, sets=None, link=None):
    step = {"id": eid}
    if sets:
        step["set"] = sets
    if link:
        step["link"] = link
    return step


def _undo(steps):
    return {"op": "head.restore", "args": {"steps": steps}}


def _link_update(data_dir, eid, add=(), remove=(), now=None):
    """Add and remove refs on one entry in one update record. Returns (added, removed): only the refs it changed."""
    row = _row(data_dir, eid)
    have = row["links"]
    added = [ref for ref in add if ref not in have]
    removed = [ref for ref in remove if ref in have]
    if len(have) - len(removed) + len(added) > head.MAX_LINKS:
        raise commands._usage(eid + " would hold more than " + str(head.MAX_LINKS) + " links", NEXT_LIST)
    _check_real_bind(row["status"], [ref for ref in have if ref not in removed] + added, eid)
    links = ["+" + ref for ref in added] + ["-" + ref for ref in removed]
    if links:
        store.update(data_dir, eid, by=_by(), links=links, now=now)
    return added, removed


def _next_number(doc, phase):
    numbers = [0]
    for task in doc["tasks"]:
        tid = task.get("id") if isinstance(task, dict) else None
        if isinstance(tid, str) and tid.startswith(phase + ".") and tid[len(phase) + 1:].isdigit():
            numbers.append(int(tid[len(phase) + 1:]))
    return max(numbers) + 1


def _new_task(data_dir, phase, title, status):
    """Add one task to a phase (the Backlog phase is created on first use), with the records of `roadmap backlog add`."""
    doc = tasks.load(data_dir)
    phase_ids = [p.get("id") for p in doc["phases"] if isinstance(p, dict)]
    records = []
    if phase not in phase_ids:
        if phase != BACKLOG_PHASE:
            raise commands._usage("phase " + phase + " does not exist", "roadmap task list")
        records.append({"kind": "phase", "line": 1, "id": phase, "name": BACKLOG_NAME, "status": None})
    tid = phase + "." + str(_next_number(doc, phase))
    records.append({"kind": "task", "line": 2, "id": tid, "phase": phase, "title": title, "status": status,
                    "tokensK": 0, "thinking": BACKLOG_THINKING, "model": BACKLOG_MODEL, "needsUser": None,
                    "check": None, "checkK": None, "note": None, "after": None, "feats": None})
    try:
        tasks.apply(data_dir, records)
    except tasks.PlanError as exc:
        raise RoadmapError("usage", "; ".join(exc.errors)[:300], EXIT_USAGE, next="roadmap status")
    return tid


def _title_of(row):
    text = " ".join(str(row["sum"] or "").split()) or row["id"]
    return text[:TITLE_MAX].rstrip()


# ---------------------------------------------------------------- log, triage, set, bind, unbind

def _check_log(a):
    text = commands._text(a.get("text"))
    if not text:
        raise commands._usage("text is empty (allowed: the message to log)", NEXT_LIST)
    return {"text": text, "kind": _kind_arg(a), "sum": _sum_arg(a), "refs": _ref_list(a.get("refs"))}


def _h_log(data_dir, a, now):
    got = store.capture(data_dir, a["text"], src=_src(), kind=a["kind"], sum_text=a["sum"], now=now)
    eid = got["id"]
    if eid is None:
        return dict(got, bound=[]), "logged, numbered after the next head write (spooled)", None
    added, _ = _link_update(data_dir, eid, add=a["refs"], now=now)
    inverse = _undo([_step(eid, {"status": "declined"}, ["-" + ref for ref in added])])
    return {"id": eid, "kind": got["kind"], "sum": got["sum"], "bound": added}, \
        eid + " " + got["kind"] + " logged", inverse


def _check_triage(a):
    kind = _kind_arg(a)
    if kind is None:
        raise commands._usage("triage needs a kind (allowed: " + "|".join(store.KINDS) + ")", NEXT_LIST)
    return {"id": _hid(a), "kind": kind, "sum": _sum_arg(a, required=True), "refs": _ref_list(a.get("refs")),
            "status": _status_arg(a)}


def _h_triage(data_dir, a, now):
    row = _row(data_dir, a["id"])
    _guard_status(data_dir, a["id"], a["status"])
    sets = {"kind": a["kind"], "sum": a["sum"]}
    if a["status"]:
        sets["status"] = a["status"]
    added = [ref for ref in a["refs"] if ref not in row["links"]]
    if len(row["links"]) + len(added) > head.MAX_LINKS:
        raise commands._usage(a["id"] + " would hold more than " + str(head.MAX_LINKS) + " links", NEXT_LIST)
    if added:
        _check_real_bind(a["status"] or row["status"], row["links"] + added, a["id"])
    prior = _prior(row, sets)
    # by head: the update with kind and sum marks the entry triaged (store/core rule)
    store.update(data_dir, a["id"], by="head", sets=sets, links=["+" + ref for ref in added], now=now)
    inverse = _undo([_step(a["id"], prior, ["-" + ref for ref in added])])
    summary = a["id"] + " triaged as " + a["kind"]
    return {"id": a["id"], "kind": a["kind"], "sum": a["sum"], "linked": added}, summary, inverse


def _check_set(a):
    clean = {"id": _hid(a), "status": _status_arg(a), "kind": _kind_arg(a), "sum": _sum_arg(a),
             "note": commands._text(a.get("note")) or None}
    if clean["status"] is None and clean["kind"] is None and clean["sum"] is None and clean["note"] is None:
        raise commands._usage("head set needs at least one of status, kind, sum, note", NEXT_LIST)
    return clean


def _h_set(data_dir, a, now):
    row = _row(data_dir, a["id"])
    _guard_status(data_dir, a["id"], a["status"])
    if a["status"] is not None:
        _check_real_bind(a["status"], row["links"], a["id"])
    sets = {key: a[key] for key in ("status", "kind", "sum") if a[key] is not None}
    store.update(data_dir, a["id"], by=_by(), sets=sets or None, note=a["note"], now=now)
    inverse = _undo([_step(a["id"], _prior(row, sets))]) if sets else None
    changed = sorted(sets) + (["note"] if a["note"] else [])
    return {"id": a["id"], "changed": changed}, a["id"] + " set " + ", ".join(changed), inverse


def _check_bind(a):
    return {"id": _hid(a), "refs": _need_refs(a)}


def _h_bind(data_dir, a, now):
    added, _ = _link_update(data_dir, a["id"], add=a["refs"], now=now)
    inverse = _undo([_step(a["id"], None, ["-" + ref for ref in added])]) if added else None
    return {"id": a["id"], "bound": added}, a["id"] + " bound " + (", ".join(added) or "nothing new"), inverse


def _check_unbind(a):
    return {"id": _hid(a), "refs": _need_refs(a)}


def _h_unbind(data_dir, a, now):
    _, removed = _link_update(data_dir, a["id"], remove=a["refs"], now=now)
    inverse = _undo([_step(a["id"], None, ["+" + ref for ref in removed])]) if removed else None
    return {"id": a["id"], "unbound": removed}, a["id"] + " unbound " + (", ".join(removed) or "nothing"), inverse


# ---------------------------------------------------------------- split, merge

def _check_split(a):
    sums = a.get("sums")
    if not isinstance(sums, list) or len(sums) != 2:
        raise commands._usage("split needs exactly two summaries", NEXT_LIST)
    clean = [store.make_summary("", commands._text(text)) for text in sums]
    if not all(clean):
        raise commands._usage("each split summary must not be empty", NEXT_LIST)
    return {"id": _hid(a), "sums": clean}


def _h_split(data_dir, a, now):
    row = _row(data_dir, a["id"])
    if row["manual"] == "merged":
        raise commands._usage(a["id"] + " is already merged", NEXT_LIST)
    text = store.text_of(data_dir, a["id"]) or row["sum"] or a["id"]
    kind = _prior(row, ["kind"]).get("kind")
    new = []
    for summary in a["sums"]:
        got = store.capture(data_dir, text, src=_src(), kind=kind, sum_text=summary, from_id=a["id"], now=now)
        new.append(got["id"])
    _guard_status(data_dir, a["id"], "merged")
    prior = _prior(row, ["status"])
    store.update(data_dir, a["id"], by=_by(), sets={"status": "merged"}, now=now)
    steps = [_step(eid, {"status": "declined"}) for eid in new if eid]
    steps.append(_step(a["id"], prior))
    numbered = [eid for eid in new if eid]
    summary = a["id"] + " split into " + (", ".join(numbered) or "spooled entries")
    return {"id": a["id"], "into": numbered}, summary, _undo(steps)


def _check_merge(a):
    eid, into = _hid(a), _hid(a, "into")
    if eid == into:
        raise commands._usage("an entry cannot merge into itself", NEXT_LIST)
    return {"id": eid, "into": into}


def _h_merge(data_dir, a, now):
    row = _row(data_dir, a["id"])
    _row(data_dir, a["into"])
    _guard_status(data_dir, a["id"], "merged")
    prior = _prior(row, ["status"])
    prior["into"] = row["into"]
    store.update(data_dir, a["id"], by=_by(), sets={"status": "merged", "into": a["into"]}, now=now)
    return {"id": a["id"], "into": a["into"]}, a["id"] + " merged into " + a["into"], _undo([_step(a["id"], prior)])


# ---------------------------------------------------------------- convert

def _check_convert(a):
    target = commands._text(a.get("target"))
    if target not in CONVERT_TARGETS:
        raise commands._usage("convert target must be task, issue, backlog or rule", NEXT_LIST)
    phase = commands._text(a.get("phase")) or BACKLOG_PHASE
    if not planfmt.PHASE_ID_RE.match(phase):
        raise commands._usage("phase '" + phase + "' must be a phase id (allowed: letters and digits)", NEXT_LIST)
    kind = commands._text(a.get("kind")) or "bug"
    if kind not in ISSUE_KINDS:
        raise commands._usage("issue kind must be one of " + "|".join(ISSUE_KINDS), NEXT_LIST)
    return {"id": _hid(a), "target": target, "phase": phase, "kind": kind}


def _h_convert(data_dir, a, now):
    row = _row(data_dir, a["id"])
    prior = _prior(row, ["status"])
    if a["target"] == "rule":
        _guard_status(data_dir, a["id"], "needs-you")
        store.update(data_dir, a["id"], by=_by(), sets={"status": "needs-you"}, note=RULE_NOTE, now=now)
        return {"id": a["id"], "status": "needs-you"}, a["id"] + " needs you: " + RULE_NOTE, \
            _undo([_step(a["id"], prior)])
    if len(row["links"]) >= head.MAX_LINKS:
        raise commands._usage(a["id"] + " already holds " + str(head.MAX_LINKS) + " links", NEXT_LIST)
    title = _title_of(row)
    if a["target"] == "issue":
        item = issues.open_issue(data_dir, title, a["kind"], sev=ISSUE_SEV, by="head", now=now)
        ref = "issue:" + item["id"]
    elif a["target"] == "task":
        ref = "task:" + _new_task(data_dir, a["phase"], title, "todo")
    else:
        ref = "backlog:" + _new_task(data_dir, BACKLOG_PHASE, title, "backlog")
    _link_update(data_dir, a["id"], add=[ref], now=now)
    return {"id": a["id"], "ref": ref}, a["id"] + " -> " + ref, _undo([_step(a["id"], None, ["-" + ref])])


# ---------------------------------------------------------------- review, accept, forget (person only)

def _check_review(a):
    action = commands._text(a.get("action"))
    if action not in REVIEW_ACTIONS:
        raise commands._usage("review action must be confirm or reopen", NEXT_LIST)
    return {"id": _hid(a), "action": action}


def _h_review(data_dir, a, now):
    _person_only("head review")
    row = _row(data_dir, a["id"])
    status = "done" if a["action"] == "confirm" else "open"
    _check_real_bind(status, row["links"], a["id"])
    store.update(data_dir, a["id"], by="person", sets={"status": status}, now=now)
    summary = a["id"] + (" confirmed done" if status == "done" else " reopened")
    return {"id": a["id"], "status": status}, summary, _undo([_step(a["id"], _prior(row, ["status"]))])


def _check_id(a):
    return {"id": _hid(a)}


def _h_accept(data_dir, a, now):
    _person_only("head accept")
    row = _row(data_dir, a["id"])
    store.update(data_dir, a["id"], by="person", sets={"status": "done"}, note=ACCEPT_NOTE, now=now)
    return {"id": a["id"], "status": "done"}, a["id"] + " accepted", _undo([_step(a["id"], _prior(row, ["status"]))])


def _h_forget(data_dir, a, now):
    _person_only("head forget")
    _row(data_dir, a["id"])
    with lock.locked(data_dir):
        store.forget_text(data_dir, a["id"])
    store.update(data_dir, a["id"], by="person", note=FORGET_NOTE, now=now)
    return {"id": a["id"], "forgotten": True}, a["id"] + " verbatim forgotten", None


# ---------------------------------------------------------------- undo replay (internal)

def _check_restore(a):
    steps = a.get("steps")
    if not isinstance(steps, list) or not steps:
        raise commands._usage("restore needs a list of steps", NEXT_LIST)
    clean = []
    for step in steps:
        if not isinstance(step, dict):
            raise commands._usage("each restore step must be an object", NEXT_LIST)
        sets = step.get("set") or {}
        links = step.get("link") or []
        if not isinstance(sets, dict) or set(sets) - set(store.SET_KEYS):
            raise commands._usage("restore may set only " + ", ".join(store.SET_KEYS), NEXT_LIST)
        if not isinstance(links, list) or any(
                not isinstance(ref, str) or ref[:1] not in ("+", "-") or head.parse_link(ref[1:]) is None
                for ref in links):
            raise commands._usage("restore links must be +kind:value or -kind:value", NEXT_LIST)
        clean.append({"id": _hid(step), "set": sets, "link": links})
    return {"steps": clean}


def _h_restore(data_dir, a, now):
    for step in a["steps"]:
        store.update(data_dir, step["id"], by="auto", sets=step["set"] or None, links=step["link"], now=now)
    return {"steps": len(a["steps"])}, "undone: " + ", ".join(step["id"] for step in a["steps"]), None


# ---------------------------------------------------------------- registration

# ---------------------------------------------------------------- notices (services/notify, the existing osascript path)

STALE_MIN_DEFAULT = 120         # config head.staleMin (HEAD-SPEC section 3): the done-not-accepted wait before a notice
NEEDS_YOU_KIND = "head-needs-you"
REVIEW_KIND = "head-review"


def _stale_min():
    """head.staleMin from the global config, 120 when it is missing or not a positive whole number."""
    try:
        value = (config.load().get("head") or {}).get("staleMin")
    except Exception:  # an unreadable config means the default, never an error in the op
        return STALE_MIN_DEFAULT
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return STALE_MIN_DEFAULT
    return value


def _statuses(data_dir, now):
    return {row["id"]: row["status"] for row in store.rows(data_dir, now=now)}


def _awaiting_review(data_dir, now, stale_min):
    """Ids whose latest status change is a done set by the head (by=head), made more than stale_min minutes ago.
    The person's confirm, accept or reopen is a later record, so it clears the id."""
    objs, _ = jsonl.read_objects(os.path.join(data_dir, store.FILE))
    moment = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    last = {}
    for rec in objs:
        sets = rec.get("set") if isinstance(rec.get("set"), dict) else {}
        if rec.get("t") == "u" and sets.get("status") in head.MANUAL_STATUSES:
            last[rec.get("id")] = (sets["status"], rec.get("by"), head.parse_ts(rec.get("ts")))
    out = []
    for eid, (status, by, ts) in last.items():
        if status == "done" and by == "head" and ts is not None and \
                (moment - ts).total_seconds() / 60.0 > stale_min:
            out.append(eid)
    return sorted(out)


def _raise_notices(data_dir, before, now):
    """After a write: one notice when an entry became needs-you, and one when a head-done entry waits for the
    person's Review past head.staleMin. notify_dir rate-limits each kind to one notification a minute."""
    after = _statuses(data_dir, now)
    new_needs = sorted(eid for eid, status in after.items() if status == "needs-you" and before.get(eid) != "needs-you")
    if new_needs:
        text = ", ".join(new_needs[:3]) + " needs you"
        notify.notify_dir(data_dir, NEEDS_YOU_KIND, "Head needs you",
                          lambda project: text + " in " + project + ". Run: roadmap head list")
    waiting = _awaiting_review(data_dir, now, _stale_min())
    if waiting:
        text = str(len(waiting)) + " done, not accepted"
        notify.notify_dir(data_dir, REVIEW_KIND, "Head review waiting",
                          lambda project: text + " in " + project + ". Review them: roadmap head list")


def _noticed(handler):
    """Wrap a public head op: run it, then raise notices. A failed notice never fails the op, which is already saved."""
    def run_op(data_dir, a, now):
        try:
            before = _statuses(data_dir, now)
        except Exception:
            before = {}
        result = handler(data_dir, a, now)
        try:
            _raise_notices(data_dir, before, now)
        except Exception:
            pass
        return result
    return run_op


def _register(name, check, handler, public=True):
    if public:
        handler = _noticed(handler)
    commands.OPS[name] = commands._Op(check, handler, public=public)


_register("head.log", _check_log, _h_log)
_register("head.triage", _check_triage, _h_triage)
_register("head.set", _check_set, _h_set)
_register("head.bind", _check_bind, _h_bind)
_register("head.unbind", _check_unbind, _h_unbind)
_register("head.split", _check_split, _h_split)
_register("head.merge", _check_merge, _h_merge)
_register("head.convert", _check_convert, _h_convert)
_register("head.review", _check_review, _h_review)
_register("head.accept", _check_id, _h_accept)
_register("head.forget", _check_id, _h_forget)
_register("head.restore", _check_restore, _h_restore, public=False)
