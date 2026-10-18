"""Panel to head (R11.2): every write the person makes on the board reaches the head agent.

The board's writes (POST /api/v1/cmd from the proven browser or the phone, the Mark button, the usage Update) append
one line to head-panel.jsonl in the data folder: {id P<n>, ts, src, op, sum, ref}. The Claude Code hooks hand the
lines nobody has seen yet to the head session as context (UserPromptSubmit, PostToolUse, SessionStart) or as a Stop
block, and `roadmap watch` wakes an idle session on a new line. Each delivered line is recorded in
head-panel-seen.json ({seen: {P3: {at, via, sid}}, acted: {P3: at}}), so the board can show every item as sent, seen
(delivered to a head session) or acted (the head acked it, or a later agent or CLI write names its ref).

Every function fails open where a hook or a write calls it: a busy lock or a broken file never fails the person's op
or the hook; the line simply waits for the next event.
"""

import datetime
import json
import os
import re
import time

from roadmap.store import atomic, jsonl, lock

FILE = "head-panel.jsonl"
SEEN_FILE = "head-panel-seen.json"
KEEP = 300                 # newest panel lines kept
SUM_MAX = 160              # one panel line's summary
FREE_MAX = 100             # the person's free text quoted in a summary
TAKE_LINES = 6             # panel lines one hook reply carries; the rest wait for the next event
STATE_N = 20               # rows the board's panel route returns
ACT_SCAN = 200             # newest activity lines scanned for the acted inference
PERSON_SOURCES = ("gui", "phone")
HEAD_SOURCES = ("cli", "agent")
FREE_KEYS = ("note", "value", "text", "title", "reason", "sum", "message")
REF_KEYS = ("id", "task", "activity", "into", "rule", "issue", "feature")
_ID_RE = re.compile(r"^P(\d+)$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
STATES = ("sent", "seen", "acted")
COALESCE_S = 5.0           # a repeated stop change of the same key within this many seconds updates its line


def _path(data_dir, name):
    return os.path.join(data_dir, name)


def _iso(now=None):
    moment = now or datetime.datetime.now().astimezone()
    if isinstance(moment, (int, float)):
        moment = datetime.datetime.fromtimestamp(moment).astimezone()
    return moment.isoformat(timespec="seconds")


def _flat(value, limit):
    return " ".join(_CONTROL.sub(" ", str(value if value is not None else "")).split())[:limit]


def _num(eid):
    match = _ID_RE.match(str(eid or ""))
    return int(match.group(1)) if match else 0


def ref_of(args):
    """The first id-like value of an op's args (id, task, ...), or ''."""
    if not isinstance(args, dict):
        return ""
    for key in REF_KEYS:
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            return _flat(value, 40)
    return ""


def summary_of(op, args, base=None):
    """One line: the activity summary (or the op), then the person's free text in quotes when the summary lacks it."""
    text = _flat(base or op, SUM_MAX)
    if isinstance(args, dict):
        for key in FREE_KEYS:
            value = args.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                value = str(value)
            if isinstance(value, str) and value.strip():
                free = _flat(value, FREE_MAX)
                if free.lower() not in text.lower():
                    text = text + ': "' + free + '"'
                break
        if "pct" in args and str(args.get("pct")) not in text:
            text += " " + str(args.get("pct")) + "%"
    return text[:SUM_MAX]


def read(data_dir):
    """The panel lines, oldest first. A missing or broken file gives []."""
    try:
        objs, _ = jsonl.read_objects(_path(data_dir, FILE))
    except Exception:
        return []
    return [o for o in objs if _num(o.get("id"))]


def _epoch(now=None):
    if isinstance(now, bool) or now is None:
        return time.time()
    if isinstance(now, (int, float)):
        return float(now)
    if isinstance(now, datetime.datetime):
        return now.timestamp()
    return time.time()


def _line_epoch(obj):
    if isinstance(obj.get("epoch"), (int, float)):
        return float(obj["epoch"])
    moment = _parse(obj.get("ts"))
    return moment.timestamp() if moment is not None else None


def _update_line(data_dir, prev, op, summary, src, moment):
    """Rewrite the panel line prev in place with the newest value; the head sees it again (its seen and acted marks
    are cleared, so the last value is what reaches it). Returns the updated line."""
    path = _path(data_dir, FILE)
    raw = jsonl.raw_lines(path)
    for index in range(len(raw) - 1, -1, -1):
        try:
            obj = json.loads(raw[index])
        except ValueError:
            continue
        if isinstance(obj, dict) and obj.get("id") == prev["id"]:
            line = dict(obj)
            line.update({"op": _flat(op, 40), "sum": _flat(summary, SUM_MAX), "ts": _iso(moment),
                         "epoch": moment, "src": src})
            raw[index] = json.dumps(line, ensure_ascii=False, separators=(",", ":"))
            atomic.write_text(path, "\n".join(raw) + "\n")
            doc = _load_seen(data_dir)
            doc["seen"].pop(prev["id"], None)
            doc["acted"].pop(prev["id"], None)
            _save_seen(data_dir, doc, read(data_dir))
            return line
    return None


def record(data_dir, op, summary, src="gui", ref="", now=None, timeout=1.0, key=None):
    """Append one panel line and return it, or None when the lock is busy or the write fails (never raises).
    With key (a stop, e.g. 'five_hour'): when the newest line with that key is at most COALESCE_S seconds old, that
    line is updated in place instead (last value wins) and no line is added."""
    try:
        if src not in PERSON_SOURCES:
            return None
        path = _path(data_dir, FILE)
        moment = _epoch(now)
        with lock.locked(data_dir, timeout):
            lines = read(data_dir)
            if key:
                keyed = [o for o in lines if o.get("key") == key and o.get("op") == op]
                if keyed:
                    prev = keyed[-1]
                    before = _line_epoch(prev)
                    if before is not None and 0 <= moment - before <= COALESCE_S:
                        updated = _update_line(data_dir, prev, op, summary, src, moment)
                        if updated is not None:
                            return updated
            last = max([_num(o.get("id")) for o in lines] or [0])
            line = {"id": "P%d" % (last + 1), "ts": _iso(now), "src": src, "op": _flat(op, 40),
                    "sum": _flat(summary, SUM_MAX), "ref": _flat(ref, 40), "epoch": moment}
            if key:
                line["key"] = _flat(key, 40)
            jsonl.append_line(path, line)
            jsonl.keep_newest(path, KEEP)
        return line
    except Exception:
        return None


def record_op(data_dir, op, args, reply, src, now=None):
    """The panel line of one cmd op run by the person. The summary is the op's activity line plus its free text."""
    if src not in PERSON_SOURCES:
        return None
    base = None
    try:
        aid = reply.get("activity") if isinstance(reply, dict) else None
        if aid:
            objs, _ = jsonl.read_objects(os.path.join(data_dir, "activity.jsonl"))
            for obj in reversed(objs[-50:]):
                if obj.get("id") == aid:
                    base = op + " " + str(obj.get("sum") or "")
                    break
    except Exception:
        base = None
    words = dict(args) if isinstance(args, dict) else {}
    data = reply.get("data") if isinstance(reply, dict) else None
    if op.startswith("rules.") and isinstance(data, dict) and isinstance(data.get("text"), str):
        words.setdefault("text", data["text"])  # an accepted proposal: the rule's own words reach the head
    return record(data_dir, op, summary_of(op, words, base), src=src, ref=ref_of(args), now=now)


def _load_seen(data_dir):
    try:
        path = _path(data_dir, SEEN_FILE)
        data = atomic.read_json(path, default={}) if os.path.exists(path) else {}
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    seen = data.get("seen") if isinstance(data.get("seen"), dict) else {}
    acted = data.get("acted") if isinstance(data.get("acted"), dict) else {}
    return {"seen": seen, "acted": acted}


def _save_seen(data_dir, doc, lines):
    keep = {o["id"] for o in lines}
    doc = {"seen": {k: v for k, v in doc["seen"].items() if k in keep},
           "acted": {k: v for k, v in doc["acted"].items() if k in keep}}
    atomic.write_json(_path(data_dir, SEEN_FILE), doc)


def unseen(data_dir):
    """The panel lines no head session has been given yet, oldest first."""
    lines = read(data_dir)
    if not lines:
        return []
    seen = _load_seen(data_dir)["seen"]
    return [o for o in lines if o["id"] not in seen]


def take(data_dir, via, sid=None, now=None, timeout=0.2, limit=TAKE_LINES):
    """Mark up to limit unseen lines seen (by via: prompt, tool, stop, start, watch, cli) and return them. [] when
    nothing is new, the lock is busy or a file is broken. Never raises."""
    try:
        if not os.path.exists(_path(data_dir, FILE)):
            return []
        with lock.locked(data_dir, timeout):
            lines = read(data_dir)
            doc = _load_seen(data_dir)
            fresh = [o for o in lines if o["id"] not in doc["seen"]][:limit]
            if not fresh:
                return []
            stamp = {"at": _iso(now), "via": via}
            if sid:
                stamp["sid"] = _flat(sid, 12)
            for line in fresh:
                doc["seen"][line["id"]] = stamp
            _save_seen(data_dir, doc, lines)
        return fresh
    except Exception:
        return []


def mark(data_dir, ids, via, now=None, timeout=1.0):
    """Mark exactly these panel lines seen by via (roadmap watch announces only the lines it prints). Returns the ids
    marked; a busy lock or a broken file gives [] and the lines stay unseen for the next hook. Never raises."""
    try:
        with lock.locked(data_dir, timeout):
            lines = read(data_dir)
            known = {o["id"] for o in lines}
            doc = _load_seen(data_dir)
            stamp = {"at": _iso(now), "via": via}
            done = [i for i in ids if i in known and i not in doc["seen"]]
            for eid in done:
                doc["seen"][eid] = stamp
            _save_seen(data_dir, doc, lines)
        return done
    except Exception:
        return []


def ack(data_dir, ids, now=None, timeout=2.0):
    """The head marks panel lines acted (and seen). Returns the ids it marked; unknown ids are skipped."""
    with lock.locked(data_dir, timeout):
        lines = read(data_dir)
        known = {o["id"] for o in lines}
        doc = _load_seen(data_dir)
        wanted = list(known) if ids == ["all"] else [i for i in ids if i in known]
        stamp = _iso(now)
        for eid in wanted:
            doc["seen"].setdefault(eid, {"at": stamp, "via": "ack"})
            doc["acted"][eid] = stamp
        _save_seen(data_dir, doc, lines)
    return sorted(wanted, key=_num)


def context_lines(items, more=0):
    """The text a hook hands the head: one header line, one line per item, and a hint for the rest."""
    if not items:
        return []
    out = ["panel: the person acted on the board (Helm) since your last look; take it into account:"]
    for o in items:
        out.append("panel %s %s %s: %s" % (o["id"], o.get("ts", "")[11:16], o.get("src", "gui"), o.get("sum", "")))
    tail = "panel: ack when handled: roadmap head panel ack " + " ".join(o["id"] for o in items)
    if more:
        tail += " · %d more: roadmap head panel" % more
    out.append(tail)
    return out


def take_text(data_dir, via, sid=None, now=None, timeout=0.2):
    """take() as the hook text ('' when nothing is new)."""
    items = take(data_dir, via, sid=sid, now=now, timeout=timeout)
    if not items:
        return ""
    more = len(unseen(data_dir))
    return "\n".join(context_lines(items, more))


def _parse(value):
    try:
        moment = datetime.datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return moment if moment.tzinfo else moment.astimezone()


def _acted_by_head(line, seen_at, activity):
    """True when a head write (cli or agent source) after the line was seen names the line's ref."""
    ref = line.get("ref") or ""
    if not ref or seen_at is None:
        return False
    pattern = re.compile(r"(?<![\w.])" + re.escape(ref) + r"(?![\w])")
    for row in activity:
        if row.get("src") not in HEAD_SOURCES:
            continue
        at = _parse(row.get("at"))
        if at is not None and at >= seen_at and pattern.search(str(row.get("sum") or "")):
            return True
    return False


def state(data_dir, n=STATE_N):
    """The newest n panel lines, newest first, each with its state (sent, seen or acted), its seen stamp and the
    totals. Never raises."""
    try:
        lines = read(data_dir)[-n:]
        doc = _load_seen(data_dir)
        try:
            activity, _ = jsonl.read_objects(os.path.join(data_dir, "activity.jsonl"))
            activity = activity[-ACT_SCAN:]
        except Exception:
            activity = []
        rows = []
        for line in reversed(lines):
            seen = doc["seen"].get(line["id"])
            if line["id"] in doc["acted"]:
                status = "acted"
            elif seen and _acted_by_head(line, _parse(seen.get("at")), activity):
                status = "acted"
            elif seen:
                status = "seen"
            else:
                status = "sent"
            row = {"id": line["id"], "ts": line.get("ts"), "src": line.get("src"), "op": line.get("op"),
                   "sum": line.get("sum"), "ref": line.get("ref") or "", "state": status}
            if seen:
                row["seenAt"] = seen.get("at")
                row["via"] = seen.get("via")
            rows.append(row)
        counts = {s: sum(1 for r in rows if r["state"] == s) for s in STATES}
        return {"rows": rows, "counts": counts}
    except Exception:
        return {"rows": [], "counts": {s: 0 for s in STATES}}
