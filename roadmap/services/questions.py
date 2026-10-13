"""Questions (questions.json): ask, answer, expire on timeout, list. At most 50 open. Answered or defaulted questions
beyond the newest 50 move to questions-archive.jsonl. Writes run under the directory lock and save atomically."""

import datetime

from roadmap.core.parsers import OPTS_MAX, Q_TEXT_MAX, QUESTION_STATUSES
from roadmap.errors import EXIT_NOT_FOUND, EXIT_USAGE, RoadmapError
from roadmap.services import records
from roadmap.store import jsonl, lock

FILE = "questions.json"
ARCHIVE = "questions-archive.jsonl"
OPEN_CAP = 50
ANSWERED_KEEP = 50
OPT_MAX = 60


def ask(data_dir, task, text, opts=(), default=None, block=False, timeout_s=None, now=None):
    """Record a question for the user and return it. The default must be one of opts when opts are given."""
    records.require_dir(data_dir)
    clean_text = records.text_field(text, "question text", Q_TEXT_MAX)
    options = [records.text_field(o, "option", OPT_MAX) for o in (opts or ())]
    if len(options) > OPTS_MAX:
        raise RoadmapError("usage", "a question has at most " + str(OPTS_MAX) + " options", EXIT_USAGE)
    clean_default = None
    if default is not None and str(default).strip():
        clean_default = records.text_field(default, "default", OPT_MAX)
        if options and clean_default not in options:
            raise RoadmapError("usage", "the default must be one of the options (allowed: " + "|".join(options) + ")",
                               EXIT_USAGE)
    if timeout_s is not None and (isinstance(timeout_s, bool) or not isinstance(timeout_s, int) or timeout_s < 0):
        raise RoadmapError("usage", "timeout must be a whole number of seconds, 0 or more", EXIT_USAGE)
    with lock.locked(data_dir):
        doc = records.load("questions", data_dir, FILE, "questions")
        if _open_count(doc["questions"]) >= OPEN_CAP:
            raise records.conflict("questions: " + str(OPEN_CAP) + " are open, the most allowed; answer one first")
        archived = jsonl.read_objects(records.file_of(data_dir, ARCHIVE))[0]
        question = {"id": records.next_number("Q", doc["questions"], archived), "task": str(task or ""),
                    "text": clean_text, "opts": options, "def": clean_default, "block": block is True,
                    "timeoutS": timeout_s, "status": "open", "answer": None,
                    "asked": records.now_iso(now), "answered": None}
        doc["questions"].append(question)
        records.save("questions", data_dir, FILE, doc)
    return dict(question)


def answer(data_dir, question_id, value, now=None):
    """Answer an open question. With options, the value must be one of them. Returns the question."""
    records.require_dir(data_dir)
    with lock.locked(data_dir):
        doc = records.load("questions", data_dir, FILE, "questions")
        question = _find(doc["questions"], question_id)
        if question.get("status") != "open":
            raise records.conflict(question_id + " is already " + str(question.get("status")) + "; not changed")
        clean = records.text_field(value, "answer", Q_TEXT_MAX)
        if question.get("opts") and clean not in question["opts"]:
            raise RoadmapError("usage", "answer must be one of " + "|".join(question["opts"]), EXIT_USAGE)
        question.update(status="answered", answer=clean, answered=records.now_iso(now))
        moved = _archive_answered(data_dir, doc)
        records.save("questions", data_dir, FILE, doc)
    result = dict(question)
    result["archived"] = moved
    return result


def expire(data_dir, now=None):
    """Default every open question whose timeout has passed: status defaulted, answer = default. Returns the ids."""
    records.require_dir(data_dir)
    moment = now if now is not None else datetime.datetime.now().astimezone()
    with lock.locked(data_dir):
        doc = records.load("questions", data_dir, FILE, "questions")
        expired = []
        for question in doc["questions"]:
            if question.get("status") != "open" or question.get("timeoutS") is None:
                continue
            asked = _parse(question.get("asked"))
            if asked is not None and (moment - asked).total_seconds() >= question["timeoutS"]:
                question.update(status="defaulted", answer=question.get("def"), answered=records.now_iso(moment))
                expired.append(question["id"])
        if expired:
            _archive_answered(data_dir, doc)
            records.save("questions", data_dir, FILE, doc)
    return expired


def get(data_dir, question_id):
    records.require_dir(data_dir)
    return dict(_find(records.load("questions", data_dir, FILE, "questions")["questions"], question_id))


def list_questions(data_dir, open_only=False):
    records.require_dir(data_dir)
    rows = records.load("questions", data_dir, FILE, "questions")["questions"]
    return [dict(q) for q in rows if not open_only or q.get("status") == "open"]


def _open_count(items):
    return sum(1 for q in items if isinstance(q, dict) and q.get("status") == "open")


def _find(items, question_id):
    for item in items:
        if isinstance(item, dict) and item.get("id") == question_id:
            return item
    raise RoadmapError("not_found", "no question " + str(question_id), EXIT_NOT_FOUND)


def _parse(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.astimezone()


def _archive_answered(data_dir, doc):
    """Move answered or defaulted questions beyond the newest ANSWERED_KEEP to the archive. Returns the count moved."""
    done = [q for q in doc["questions"] if isinstance(q, dict) and q.get("status") in QUESTION_STATUSES[1:]]
    if len(done) <= ANSWERED_KEEP:
        return 0
    newest_first = sorted(done, key=lambda q: (q.get("answered") or q.get("asked") or ""), reverse=True)
    doomed = newest_first[ANSWERED_KEEP:]
    ids = {id(q) for q in doomed}
    for question in doomed:
        jsonl.append_line(records.file_of(data_dir, ARCHIVE), question)
    doc["questions"] = [q for q in doc["questions"] if id(q) not in ids]
    return len(doomed)
