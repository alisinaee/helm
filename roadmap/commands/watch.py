"""Command watch: block until a new Start is queued or a question is answered, then print one line.

The line is `start P2.4`, `stop P2.4` (a queued stop request), `answer Q3 yes`, or `timeout` after --max seconds (exit 0
in every case). An idle lead session can sit in this command, so a Start from the GUI reaches it at almost no token
cost. Only entries and answers that appear after the command starts count. The files are polled by their mtime every
2 seconds; the clock and the sleep are injectable so the tests need no real waiting.
"""

import argparse
import os
import time

from roadmap.errors import EXIT_USAGE, RoadmapError
from roadmap.services import commands, questions, queue, records

DEFAULT_MAX_S = 1800
MAX_LIMIT_S = 86400
POLL_S = 2
ANSWER_MAX = 60
NEXT = "roadmap status"


def _project_option():
    """Parent parser that adds --project to an action."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--project", metavar="ID", default=None,
                        help="project id (default: $ROADMAP_PROJECT, then the registered project of this folder)")
    return parser


def register(sub, common):
    """Add the watch command."""
    parser = sub.add_parser("watch", parents=[common, _project_option()],
                            help="block until a Start is queued or a question is answered")
    parser.add_argument("--max", type=int, default=DEFAULT_MAX_S, metavar="SECONDS",
                        help="give up after this many seconds (default 1800)")
    parser.set_defaults(handler=_run)


def _run(args):
    if args.max < 1 or args.max > MAX_LIMIT_S:
        raise RoadmapError("usage", "--max takes 1 to %d seconds" % MAX_LIMIT_S, EXIT_USAGE,
                           next="roadmap watch --max " + str(DEFAULT_MAX_S))
    data_dir = commands.locate(args.project, NEXT)
    event = wait(data_dir, args.max)
    if not getattr(args, "json", False):
        print(event["line"])
        return None
    return {"event": event["event"], "line": event["line"]}


def wait(data_dir, max_s, sleep=time.sleep, clock=time.monotonic, poll_s=POLL_S):
    """Block until something new appears in the queue or the questions, or max_s seconds pass. Returns a dict with
    event (start, stop, answer or timeout) and line (the one printed line)."""
    records.require_dir(data_dir)
    stamps = _stamps(data_dir)
    seen = _known(data_dir)
    start = clock()
    while True:
        now_stamps = _stamps(data_dir)
        if now_stamps != stamps:
            stamps = now_stamps
            event = _new_event(data_dir, seen)
            if event is not None:
                return event
        remaining = max_s - (clock() - start)
        if remaining <= 0:
            return {"event": "timeout", "line": "timeout"}
        sleep(min(poll_s, remaining))


def _stamps(data_dir):
    """The mtimes of queue.json and questions.json (0 when a file is missing)."""
    return tuple(_mtime(os.path.join(data_dir, name)) for name in (queue.FILE, questions.FILE))


def _mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0


def _known(data_dir):
    """The keys of every queue entry and every answer that exist now; only later keys are news."""
    keys = {_entry_key(e) for e in queue.list_queue(data_dir)}
    keys |= {_answer_key(q) for q in questions.list_questions(data_dir) if q.get("status") == "answered"}
    return keys


def _entry_key(entry):
    return "q:" + str(entry.get("task")) + "@" + str(entry.get("at"))


def _answer_key(question):
    return "a:" + str(question.get("id")) + "@" + str(question.get("answered"))


def _new_event(data_dir, seen):
    """The first unseen queue entry (as start or stop), else the first unseen answer, else None. Marks it seen."""
    for entry in queue.list_queue(data_dir):
        key = _entry_key(entry)
        if key in seen:
            continue
        seen.add(key)
        verb = "stop" if entry.get("op") == "stop" else "start"
        line = verb + " " + str(entry.get("task"))
        return {"event": verb, "line": line}
    for question in questions.list_questions(data_dir):
        key = _answer_key(question)
        if question.get("status") != "answered" or key in seen:
            continue
        seen.add(key)
        value = " ".join(str(question.get("answer") or "").split())[:ANSWER_MAX]
        return {"event": "answer", "line": ("answer " + str(question.get("id")) + " " + value).rstrip()}
    return None
