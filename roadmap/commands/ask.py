"""Questions: ask, ask get, ask wait, ask list, and answer.

`ask wait` is the only command that waits. It checks every 5 seconds for at most 1800 seconds and then prints one line.
The sleep and the clock are injectable so tests run on a fake clock.
"""

import argparse
import datetime
import re
import time

from roadmap.errors import EXIT_USAGE, RoadmapError
from roadmap.services import commands, questions

NEXT = "roadmap ask list"
POLL_S = 5
WAIT_MAX_S = 1800
LIST_MAX = 10
_QID = re.compile(r"^Q[0-9]+$")


def _project_option():
    """Parent parser that adds --project to an action."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--project", metavar="ID", default=None,
                        help="project id (default: $ROADMAP_PROJECT, then the registered project of this folder)")
    return parser


def register(sub, common):
    """Add the ask and answer commands."""
    project = _project_option()
    parser = sub.add_parser("ask", parents=[common, project],
                            help="ask the user a question: ask \"<q>\" [--option A]... [--block]; also get, wait, list")
    parser.add_argument("words", nargs="*", metavar="TEXT",
                        help="the question, or one of: get Q3 | wait Q3 | list")
    parser.add_argument("--task", metavar="ID", default="", help="the task the question is about")
    parser.add_argument("--option", "--opt", dest="opt", action="append", default=[], metavar="A",
                        help="an answer option: \"Label\" or \"Label: description\"; add \" (recommended)\" to the "
                             "label to mark it. 2 to 6 options, or none; free text is always allowed (repeatable)")
    parser.add_argument("--default", metavar="A", default=None, help="the answer taken on timeout")
    parser.add_argument("--block", action="store_true", help="the task waits for the answer")
    parser.add_argument("--timeout", metavar="S", default=None, help="seconds until the default is taken")
    parser.set_defaults(handler=_run)

    answer = sub.add_parser("answer", parents=[common, project], help="answer an open question")
    answer.add_argument("id", metavar="Q3", help="question id")
    answer.add_argument("value", nargs="+", help="one of the options, or free text when there are none")
    answer.set_defaults(handler=_answer)


def _now():
    return datetime.datetime.now().astimezone()


def line_of(question):
    """One line: 'Q3 open', or 'Q1 answered no' (a defaulted question shows its default)."""
    if question.get("status") == "open" or question.get("answer") is None:
        return "%s %s" % (question["id"], question.get("status"))
    return "%s %s %s" % (question["id"], question.get("status"), question["answer"])


def wait_for(data_dir, question_id, timeout_s=WAIT_MAX_S, sleep=time.sleep, clock=_now):
    """Poll until the question is answered or defaulted, or timeout_s has passed. Returns (question, still_open)."""
    start = clock()
    while True:
        questions.expire(data_dir, now=clock())
        question = questions.get(data_dir, question_id)
        if question.get("status") != "open":
            return question, False
        if (clock() - start).total_seconds() >= timeout_s:
            return question, True
        sleep(POLL_S)


def _wait_seconds(value):
    if value is None:
        return WAIT_MAX_S
    try:
        seconds = int(value)
    except ValueError:
        seconds = -1
    if seconds < 0 or seconds > WAIT_MAX_S:
        raise RoadmapError("usage", "--timeout for ask wait must be 0 to %d seconds" % WAIT_MAX_S, EXIT_USAGE,
                           next="roadmap ask wait Q3 --timeout 60")
    return seconds


def _run(args):
    words = list(args.words)
    if len(words) == 1 and words[0] == "list":
        return _list(args)
    if len(words) == 2 and words[0] in ("get", "wait") and _QID.match(words[1]):
        return _get(args, words[1]) if words[0] == "get" else _wait(args, words[1])
    return _ask(args, " ".join(words))


def _ask(args, text):
    timeout = None
    if args.timeout is not None:
        try:
            timeout = int(args.timeout)
        except ValueError:
            raise RoadmapError("usage", "--timeout must be a whole number of seconds", EXIT_USAGE,
                               next="roadmap ask \"<question>\" --timeout 300")
    payload = {"text": text, "task": args.task or "", "opts": args.opt, "default": args.default,
               "block": args.block, "timeout": timeout}
    reply = commands.write(args.project, "question.ask", payload,
                           'roadmap ask "<question>" --option "Yes: ship it" --option "No: wait"')
    question = reply["data"]
    if not getattr(args, "json", False):
        print(line_of(question))
        return None
    return commands.json_data(reply)


def _get(args, question_id):
    data_dir = commands.locate(args.project, NEXT)
    with commands.next_on_error(NEXT):
        question = questions.get(data_dir, question_id)
    if not getattr(args, "json", False):
        print(line_of(question))
        return None
    return {"question": question}


def _wait(args, question_id):
    data_dir = commands.locate(args.project, NEXT)
    seconds = _wait_seconds(args.timeout)
    with commands.next_on_error(NEXT):
        question, still_open = wait_for(data_dir, question_id, timeout_s=seconds)
    if not getattr(args, "json", False):
        print(line_of(question))
        return None
    return {"question": question, "still_open": still_open}


def _list(args):
    data_dir = commands.locate(args.project, NEXT)
    rows = questions.list_questions(data_dir, open_only=True)
    if not getattr(args, "json", False):
        if not rows:
            print("no open questions")
        for question in rows[:LIST_MAX]:
            print("%s open %s" % (question["id"], question["text"]))
        return None
    return {"questions": rows}


def _answer(args):
    reply = commands.write(args.project, "question.answer", {"id": args.id, "value": " ".join(args.value)},
                           "roadmap ask list")
    if not getattr(args, "json", False):
        print(line_of(reply["data"]))
        return None
    return commands.json_data(reply)
