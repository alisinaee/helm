"""Project history (R11.4, docs/ACTIVITY-V2.md): one read-only feed of everything that happened in a project.

Sources, merged and never written: activity.jsonl (every write through the command layer, with its undo flag),
head.jsonl (the person's head items, the head's updates and session claims) with head-text.jsonl (full text and
reply), jobs.json (agent jobs started and finished, with model and tokens), questions.json and its archive (asked and
answered), the git log (commits) and the global usage ledger (weekly readings).

Each event is normalized to
    {id, ts, ms, kind, verb, actor, subject, summary, link, model, tokensK, src, undo, activity, detail}
kind is one of KINDS, actor one of ACTORS. subject is "<type>:<id>" (task:R11.4, head:H230, job:j1050, commit:6d4cbfd,
question:Q2) or null. link is a project-relative hash path (work/i/R11.4) or null. A write recorded both in the
activity log and in a richer source (a head update, a question) is shown once: the richer event keeps the activity
id, so its Undo still works.

page() filters by kind, actor, time range and text, and pages newest first with a cursor ("<ms>~<id>").
"""

import datetime
import os
import re
import threading
import time

from roadmap.errors import EXIT_USAGE, RoadmapError
from roadmap.store import jsonl

KINDS = ("head", "question", "job", "commit", "task", "rule", "feature", "issue", "setting", "usage", "session",
         "other")
ACTORS = ("user", "head", "agent", "system")
PAGE_DEFAULT, PAGE_MAX = 150, 500
GIT_MAX = 400
TEXT_MAX = 4000
SUMMARY_MAX = 240
Q_MAX = 200
MATCH_S = 15  # an activity line and a richer source's record within this many seconds are the same write
HIST_MAX = 240
CACHE_TTL_S = 10.0

_OP_KIND = {
    "task": "task", "queue": "task", "plan": "task", "backlog": "task", "subtask": "task", "phase": "task",
    "head": "head", "question": "question", "rules": "rule", "rule": "rule", "feature": "feature",
    "issue": "issue", "limit": "setting", "budget": "setting", "control": "setting", "usage": "setting",
    "settings": "setting", "autonomy": "setting", "job": "job", "git": "commit", "comment": "task",
}
_HEAD_BY = {"head": "head", "auto": "system", "person": "user", "user": "user", "gui": "user", "agent": "head"}
_ID_RE = re.compile(r"\b(RP\d+|R\d+(?:\.\d+)+[a-z]?|H\d+|Q\d+|F\d+|I\d+|j\d+)\b")
_ID_TYPE = (("RP", "rule"), ("R", "task"), ("H", "head"), ("Q", "question"), ("F", "feature"), ("I", "issue"),
            ("j", "job"))
_CLAUDE = re.compile(r"Co-Authored-By:\s*Claude", re.IGNORECASE)
_TASK_START = re.compile(r"^\s*(R\d+(?:\.\d+)+[a-z]?)\b")
_cache = {}
_cache_lock = threading.Lock()


# ---------------------------------------------------------------- time

def to_ms(value):
    """Epoch milliseconds of an ISO time (Z, an offset, or local when naive) or of epoch seconds; None when unknown."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value * 1000 if value < 1e11 else value)
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        moment = datetime.datetime.fromisoformat(text)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.astimezone()
    return int(moment.timestamp() * 1000)


def iso_of(ms):
    return datetime.datetime.fromtimestamp(ms / 1000).astimezone().isoformat(timespec="seconds")


# ---------------------------------------------------------------- helpers

def _cut(text, size=SUMMARY_MAX):
    text = " ".join(str(text or "").split())
    return text if len(text) <= size else text[:size - 1] + "…"


def _subject_of(text):
    found = _ID_RE.search(str(text or ""))
    if not found:
        return None
    ident = found.group(1)
    for prefix, kind in _ID_TYPE:
        if ident.startswith(prefix):
            return kind + ":" + ident
    return None


def _link_of(subject):
    if not subject:
        return None
    kind, ident = subject.split(":", 1)
    return {"task": "work/i/" + ident, "head": "head?id=" + ident, "job": "agents", "commit": "git",
            "question": "inbox", "rule": "rules", "feature": "work", "issue": "work"}.get(kind)


def _event(ms, kind, verb, actor, summary, src, key, subject=None, model=None, tokens_k=None, detail=None):
    return {"id": src + ":" + key, "ts": iso_of(ms), "ms": ms, "kind": kind, "verb": verb, "actor": actor,
            "subject": subject, "summary": _cut(summary), "link": _link_of(subject), "model": model or None,
            "tokensK": tokens_k, "src": src, "undo": False, "activity": None, "detail": detail or {}}


def _num(value):
    return round(float(value), 1) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _read_jsonl(path):
    try:
        return jsonl.read_objects(path)[0]
    except (OSError, ValueError):
        return []


def _read_json(path):
    import json
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------- sources

def from_activity(lines):
    out = []
    for line in lines:
        ms = to_ms(line.get("at"))
        if ms is None:
            continue
        op = str(line.get("op") or "")
        family = op.split(".", 1)[0]
        kind = _OP_KIND.get(family, "other")
        src = str(line.get("src") or "")
        if src == "agent":
            actor = "head" if family in ("head", "question", "rules") else "agent"
        else:
            actor = "user"
        summary = str(line.get("sum") or op or "change")
        event = _event(ms, kind, op or "change", actor, summary, "activity", str(line.get("id") or ms),
                       subject=_subject_of(summary), detail={"source": src, "op": op})
        event["undo"] = line.get("undo") is True
        event["activity"] = str(line.get("id") or "") or None
        out.append(event)
    return out


def _describe_set(changes, link):
    parts = []
    for key, value in (changes or {}).items():
        if key == "sum":
            parts.append("retitled")
        elif key == "note":
            continue
        else:
            parts.append(key + " → " + _cut(value, 40))
    for item in link or []:
        text = str(item)
        parts.append(("linked " if text.startswith("+") else "unlinked ") + text.lstrip("+-").split(":")[-1])
    return ", ".join(parts) or "updated"


def from_head(entries, texts):
    out = []
    titles = {}
    for index, entry in enumerate(entries):
        ms = to_ms(entry.get("ts"))
        if ms is None:
            continue
        kind_t = entry.get("t")
        hid = str(entry.get("id") or "")
        if kind_t == "e" and hid:
            titles[hid] = entry.get("sum") or titles.get(hid, "")
            text = texts.get(hid, {})
            detail = {"headKind": entry.get("kind"), "prio": entry.get("prio"), "source": entry.get("src"),
                      "session": entry.get("sid")}
            if text.get("text"):
                detail["text"] = str(text["text"])[:TEXT_MAX]
            if text.get("reply"):
                detail["reply"] = str(text["reply"])[:TEXT_MAX]
            out.append(_event(ms, "head", "head.new", "user" if entry.get("src") != "auto" else "system",
                              hid + " " + str(entry.get("sum") or ""), "head", hid + ".e" + str(index),
                              subject="head:" + hid, detail=detail))
        elif kind_t == "u" and hid:
            changes = entry.get("set") if isinstance(entry.get("set"), dict) else {}
            if changes.get("sum"):
                titles[hid] = changes["sum"]
            what = _describe_set(changes, entry.get("link"))
            note = entry.get("note") or ""
            summary = hid + " " + what + (" · " + str(note) if note else " · " + str(titles.get(hid, "")))
            detail = {"by": entry.get("by"), "changes": changes, "links": entry.get("link") or [],
                      "note": note or None, "title": titles.get(hid) or None}
            verb = "head.status" if "status" in changes else "head.update"
            out.append(_event(ms, "head", verb, _HEAD_BY.get(str(entry.get("by") or ""), "head"), summary, "head",
                              hid + ".u" + str(index), subject="head:" + hid, detail=detail))
        elif kind_t == "s":
            model = entry.get("model")
            ev = str(entry.get("ev") or "session")
            out.append(_event(ms, "session", "session." + ev, "agent",
                              "Head session " + ev + (" by " + str(model) if model else ""), "head",
                              "s" + str(index), model=model, detail={"session": entry.get("sid")}))
    return out


def from_jobs(jobs):
    out = []
    for job in jobs:
        jid = str(job.get("id") or "")
        if not jid:
            continue
        task = job.get("task")
        title = str(job.get("title") or jid)
        model = job.get("model")
        subject = "job:" + jid
        base = {"task": task, "job": jid, "effort": job.get("effort"), "engine": job.get("engine_model"),
                "status": job.get("status")}
        started = to_ms(job.get("started"))
        if started is not None:
            event = _event(started, "job", "job.start", "agent", "started " + title, "jobs", jid + ".s",
                           subject=subject, model=model, detail=dict(base))
            event["link"] = "agents"
            out.append(event)
        ended = to_ms(job.get("ended"))
        if ended is not None:
            status = str(job.get("status") or "done")
            detail = dict(base, note=job.get("note"), reason=job.get("reason"))
            if started is not None:
                detail["durationS"] = max(0, (ended - started) // 1000)
            event = _event(ended, "job", "job." + status, "agent", status + " " + title, "jobs", jid + ".e",
                           subject=subject, model=model, tokens_k=_num(job.get("tokensK")), detail=detail)
            event["link"] = "agents"
            out.append(event)
    return out


def from_questions(questions):
    out = []
    for q in questions:
        qid = str(q.get("id") or "")
        if not qid:
            continue
        text = str(q.get("text") or "")
        detail = {"task": q.get("task"), "options": q.get("opts") or [], "text": text[:TEXT_MAX],
                  "answer": q.get("answer"), "status": q.get("status")}
        asked = to_ms(q.get("asked"))
        if asked is not None:
            out.append(_event(asked, "question", "question.ask", "head", qid + " asked: " + text, "questions",
                              qid + ".a", subject="question:" + qid, detail=detail))
        answered = to_ms(q.get("answered"))
        if answered is not None:
            answer = q.get("answer")
            out.append(_event(answered, "question", "question.answer", "user",
                              qid + " answered “" + _cut(answer, 60) + "”: " + text, "questions", qid + ".r",
                              subject="question:" + qid, detail=detail))
    return out


def from_commits(rows):
    out = []
    for row in rows:
        at = row.get("time")
        sha = str(row.get("sha") or "")
        if not isinstance(at, int) or not sha:
            continue
        subject_text = str(row.get("subject") or "")
        if row.get("task") or row.get("job") or _TASK_START.match(subject_text):
            actor = "agent"
        else:
            actor = "head" if row.get("claude") else "user"
        detail = {"sha": sha, "author": row.get("author"), "task": row.get("task"), "job": row.get("job"),
                  "parents": row.get("parents") or []}
        event = _event(at * 1000, "commit", "git.commit", actor,
                       sha[:7] + " " + subject_text, "git", sha[:12], subject="commit:" + sha[:7], detail=detail)
        out.append(event)
    return out


def from_ledger(doc):
    out = []
    if not isinstance(doc, dict):
        return out
    seen_days = set()
    last_w = None
    for row in sorted((r for r in doc.get("recent") or [] if isinstance(r, list) and len(r) >= 2 and
                       isinstance(r[0], (int, float))), key=lambda r: r[0]):
        if row[1] == last_w:  # an unchanged reading is noise in a history
            continue
        last_w = row[1]
        ms = int(row[0] * 1000)
        seen_days.add(datetime.datetime.fromtimestamp(row[0]).date().isoformat())
        out.append(_event(ms, "usage", "usage.reading", "system", "Weekly usage " + str(_num(row[1])) + "%",
                          "ledger", "r" + str(int(row[0])), detail={"weeklyPct": _num(row[1]),
                                                                    "dayPts": _num(row[2]) if len(row) > 2 else None}))
    for day, row in (doc.get("days") or {}).items():
        if day in seen_days or not isinstance(row, dict):
            continue
        ms = to_ms(row.get("lastAt"))
        if ms is None:
            continue
        out.append(_event(ms, "usage", "usage.day", "system",
                          "Weekly usage " + str(_num(row.get("lastW"))) + "% (+" + str(_num(row.get("pts"))) +
                          " pts that day)", "ledger", "d" + day,
                          detail={"weeklyPct": _num(row.get("lastW")), "dayPts": _num(row.get("pts")),
                                  "firstAt": row.get("firstAt")}))
    return out


# ---------------------------------------------------------------- merge

def _absorb(events, activity_events, verb_prefixes):
    """Give each richer event the undo id of the activity line for the same write (same id, close in time), and
    return the activity events that were not absorbed."""
    by_subject = {}
    for line in activity_events:
        if line["subject"] and any(line["verb"].startswith(p) for p in verb_prefixes):
            by_subject.setdefault(line["subject"], []).append(line)
    used = set()
    for event in events:
        candidates = by_subject.get(event["subject"]) or []
        for line in candidates:
            if line["id"] in used or abs(line["ms"] - event["ms"]) > MATCH_S * 1000:
                continue
            used.add(line["id"])
            event["undo"] = line["undo"]
            event["activity"] = line["activity"]
            event["detail"]["op"] = line["detail"].get("op")
            event["detail"]["source"] = line["detail"].get("source") or event["detail"].get("source")
            break
    return [line for line in activity_events if line["id"] not in used]


def collect(data_dir, project_path=None, ledger_doc=None, full=True):
    """Every event of one project (unsorted). project_path enables the git log; ledger_doc adds usage readings."""
    activity = from_activity(_read_jsonl(os.path.join(data_dir, "activity.jsonl")))
    texts = {}
    if full:
        for row in _read_jsonl(os.path.join(data_dir, "head-text.jsonl")):
            if row.get("id"):
                texts.setdefault(str(row["id"]), {}).update({k: row[k] for k in ("text", "reply") if row.get(k)})
    head = from_head(_read_jsonl(os.path.join(data_dir, "head.jsonl")), texts)
    jobs_doc = _read_json(os.path.join(data_dir, "jobs.json"))
    jobs = from_jobs(jobs_doc.get("jobs") or [] if isinstance(jobs_doc, dict) else [])
    q_doc = _read_json(os.path.join(data_dir, "questions.json"))
    questions = list(q_doc.get("questions") or []) if isinstance(q_doc, dict) else []
    known = {str(q.get("id")) for q in questions}
    questions += [q for q in _read_jsonl(os.path.join(data_dir, "questions-archive.jsonl"))
                  if str(q.get("id")) not in known]
    question_events = from_questions(questions)
    activity = _absorb([e for e in head if e["src"] == "head" and e["verb"] != "head.new"], activity, ("head.",))
    activity = _absorb(question_events, activity, ("question.",))
    events = activity + head + jobs + question_events
    if project_path:
        events += from_commits(_git_rows(project_path))
    if ledger_doc is not None:
        events += from_ledger(ledger_doc)
    if not full:
        for event in events:
            event["detail"].pop("text", None)
            event["detail"].pop("reply", None)
    return events


def _git_rows(project_path):
    from roadmap.services import git as git_service
    try:
        root = git_service.repo_root(project_path)
        text = git_service.run(root, ["log", "--topo-order", "-n", str(GIT_MAX), "--format=" + git_service.LOG_FORMAT])
        rows = git_service.parse_log(text)
    except Exception:  # no repo, no git, a timeout: the feed is still shown without commits
        return []
    tokens = text.split("\0")
    claude = {tokens[i].strip() for i in range(0, len(tokens) - 5, 6) if _CLAUDE.search(tokens[i + 5])}
    for row in rows:
        row["claude"] = row["sha"] in claude
    return rows


def _stamp(paths):
    out = []
    for path in paths:
        try:
            out.append(os.stat(path).st_mtime_ns)
        except OSError:
            out.append(0)
    return tuple(out)


def cached_collect(data_dir, project_path=None, with_ledger=True, full=True):
    """collect() with a small cache keyed on the source files' mtimes; the git log and ledger refresh every 10 s."""
    names = ("activity.jsonl", "head.jsonl", "head-text.jsonl", "jobs.json", "questions.json",
             "questions-archive.jsonl")
    head_ref = os.path.join(project_path, ".git", "HEAD") if project_path else ""
    key = (data_dir, project_path, with_ledger, full)
    stamp = _stamp([os.path.join(data_dir, n) for n in names] + ([head_ref] if head_ref else [])) + (
        int(time.monotonic() // CACHE_TTL_S),)
    with _cache_lock:
        hit = _cache.get(key)
        if hit and hit[0] == stamp:
            return hit[1]
    ledger_doc = _ledger() if with_ledger else None
    events = collect(data_dir, project_path, ledger_doc, full)
    with _cache_lock:
        if len(_cache) > 32:
            _cache.clear()
        _cache[key] = (stamp, events)
    return events


def _ledger():
    try:
        from roadmap.services import ledger
        doc = ledger.read()
        return doc[0] if isinstance(doc, tuple) else doc
    except Exception:
        return None


# ---------------------------------------------------------------- query

def parse_query(query_pairs):
    """Options from the query pairs [(key, value)]: kind, actor (comma lists), from, to (ISO or epoch ms), q, before
    (cursor), limit, project. Each key at most once; anything else is invalid_input (400)."""
    allowed = ("kind", "actor", "from", "to", "q", "before", "limit", "project")
    keys = [k for k, _ in query_pairs]
    if len(keys) != len(set(keys)) or any(k not in allowed for k in keys):
        raise RoadmapError("invalid_input", "the query takes " + ", ".join(allowed) + ", once each", EXIT_USAGE)
    raw = dict(query_pairs)
    opts = {"kinds": _list(raw.get("kind"), KINDS, "kind"), "actors": _list(raw.get("actor"), ACTORS, "actor"),
            "from": _time(raw.get("from"), "from"), "to": _time(raw.get("to"), "to"),
            "q": (raw.get("q") or "").strip().lower()[:Q_MAX], "before": _cursor(raw.get("before")),
            "limit": PAGE_DEFAULT, "project": raw.get("project") or None}
    if raw.get("limit"):
        if not re.fullmatch(r"\d{1,4}", raw["limit"]) or not 1 <= int(raw["limit"]) <= PAGE_MAX:
            raise RoadmapError("invalid_input", "limit must be a whole number from 1 to " + str(PAGE_MAX), EXIT_USAGE)
        opts["limit"] = int(raw["limit"])
    return opts


def _list(text, allowed, name):
    if not text:
        return None
    items = [part.strip() for part in text.split(",") if part.strip()]
    bad = [item for item in items if item not in allowed]
    if bad:
        raise RoadmapError("invalid_input", name + " must be from " + "|".join(allowed), EXIT_USAGE)
    return set(items) or None


def _time(text, name):
    if not text:
        return None
    if re.fullmatch(r"\d{1,15}", text):
        return int(text)
    ms = to_ms(text)
    if ms is None:
        raise RoadmapError("invalid_input", name + " must be an ISO time or epoch milliseconds", EXIT_USAGE)
    return ms


def _cursor(text):
    if not text:
        return None
    match = re.fullmatch(r"(\d{1,15})~([\w.:@-]{1,120})", text)
    if not match:
        raise RoadmapError("invalid_input", "before must be a cursor from a previous page", EXIT_USAGE)
    return int(match.group(1)), match.group(2)


def cursor_of(event):
    return str(event["ms"]) + "~" + event["id"]


def _sort_key(event):
    return (event["ms"], event["id"])


def _text_match(event, q):
    if not q:
        return True
    hay = " ".join(str(v) for v in (event["summary"], event["subject"], event["model"], event["verb"],
                                    event.get("project")) if v).lower()
    return all(word in hay for word in q.split())


def page(events, opts, now_ms=None):
    """One page, newest first: {events, next, total, counts, actors, hist (first page only), first, last}."""
    q = opts.get("q") or ""
    kinds, actors = opts.get("kinds"), opts.get("actors")
    lo, hi = opts.get("from"), opts.get("to")
    base = [e for e in events if _text_match(e, q)]
    in_time = [e for e in base if (lo is None or e["ms"] >= lo) and (hi is None or e["ms"] <= hi)]
    counts = {kind: 0 for kind in KINDS}
    actor_counts = {actor: 0 for actor in ACTORS}
    for event in in_time:
        if actors is None or event["actor"] in actors:
            counts[event["kind"]] = counts.get(event["kind"], 0) + 1
        if kinds is None or event["kind"] in kinds:
            actor_counts[event["actor"]] = actor_counts.get(event["actor"], 0) + 1
    chosen = sorted((e for e in in_time if (kinds is None or e["kind"] in kinds) and
                     (actors is None or e["actor"] in actors)), key=_sort_key, reverse=True)
    start = 0
    before = opts.get("before")
    if before:
        start = len(chosen)
        for index, event in enumerate(chosen):
            if _sort_key(event) < before:
                start = index
                break
    rows = chosen[start:start + opts.get("limit", PAGE_DEFAULT)]
    more = start + len(rows) < len(chosen)
    body = {"events": rows, "next": cursor_of(rows[-1]) if rows and more else None, "total": len(chosen),
            "counts": counts, "actors": actor_counts}
    if not before:
        scoped = [e for e in base if (kinds is None or e["kind"] in kinds) and (actors is None or e["actor"] in actors)]
        body["hist"] = histogram(scoped, now_ms)
    return body


def histogram(events, now_ms=None):
    """Event counts per local hour (span up to 3 days) or per local day: {unit, start, step, counts}. The buckets run
    from the first event to now, HIST_MAX at most (the newest kept)."""
    if not events:
        return {"unit": "day", "start": None, "step": 86400000, "counts": []}
    first = min(e["ms"] for e in events)
    last = max(max(e["ms"] for e in events), now_ms or 0)
    hour = (last - first) <= 3 * 86400000
    step = 3600000 if hour else 86400000
    moment = datetime.datetime.fromtimestamp(first / 1000).astimezone()
    moment = moment.replace(minute=0, second=0, microsecond=0) if hour else \
        moment.replace(hour=0, minute=0, second=0, microsecond=0)
    start = int(moment.timestamp() * 1000)
    size = int((last - start) // step) + 1
    if size > HIST_MAX:
        start += (size - HIST_MAX) * step
        size = HIST_MAX
    counts = [0] * size
    for event in events:
        index = (event["ms"] - start) // step
        if 0 <= index < size:
            counts[int(index)] += 1
    return {"unit": "hour" if hour else "day", "start": start, "step": step, "counts": counts}


# ---------------------------------------------------------------- entry points

def project_page(project, query_pairs, full=True, now_ms=None):
    """The page for one registered project entry ({id, path, dataDir?})."""
    from roadmap.services import jobs as job_service
    opts = parse_query(query_pairs)
    data_dir = job_service.data_dir_of(project)
    events = cached_collect(data_dir, os.path.abspath(project["path"]), True, full)
    events = [dict(e, project=project["id"]) for e in events]
    return page(events, opts, now_ms or int(time.time() * 1000))


def all_page(projects, query_pairs, full=True, now_ms=None):
    """The merged page of several projects; each event carries project and pname. Usage readings appear once."""
    from roadmap.services import jobs as job_service
    opts = parse_query(query_pairs)
    wanted = opts.get("project")
    merged = []
    for index, project in enumerate(projects):
        if wanted and project["id"] != wanted:
            continue
        data_dir = job_service.data_dir_of(project)
        events = cached_collect(data_dir, os.path.abspath(project["path"]), False, full)
        name = project.get("name") or project["id"]
        merged += [dict(e, project=project["id"], pname=name) for e in events]
    ledger_doc = _ledger()
    if ledger_doc is not None:
        merged += [dict(e, project=None, pname=None) for e in from_ledger(ledger_doc)]
    return page(merged, opts, now_ms or int(time.time() * 1000))
