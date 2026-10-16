"""Work items from the CLI: work list, show, add, set, link, accept, reopen (docs/WORK-MODEL.md section 6, M5).

Reads come from services/work.py (the status is derived on every read, never stored). Writes go through the registry
ops work.add, work.set, work.link, work.accept and work.reopen, so each one is logged and can be undone. accept and
reopen are the person's only: the service refuses an agent, the phone or a script. Output is at most 15 lines.
"""

import argparse

from roadmap.errors import RoadmapError
from roadmap.services import commands, tasks, work

OUT_LINES = 15
LIST_NEXT = "roadmap work list"


def _project_option():
    """Parent parser that adds --project to an action."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--project", metavar="ID", default=None,
                        help="project id (default: $ROADMAP_PROJECT, then the registered project of this folder)")
    return parser


def register(sub, common):
    """Add the work group and its actions."""
    project = _project_option()
    group = sub.add_parser("work", parents=[common],
                           help="Work items (the human cards): work list|show|add|set|link|accept|reopen")
    actions = group.add_subparsers(dest="action", metavar="ACTION", required=True)

    def add(name, help_text):
        return actions.add_parser(name, parents=[common, project], help=help_text)

    add("list", "one line per Work item: id, status, prio, n/m done, title").set_defaults(handler=_list)

    show = add("show", "one Work item: outcome and its agent tasks (at most 15 lines)")
    show.add_argument("id", metavar="W12")
    show.set_defaults(handler=_show)

    new = add("add", "add a Work item: work add \"<title>\" [--outcome ..] [--kind task|issue] [--prio P0-P3]")
    new.add_argument("title", metavar="TITLE", help="plain words, at most 60 characters")
    new.add_argument("--outcome", default="", metavar="TEXT", help="one line: what done looks like")
    new.add_argument("--kind", default=None, choices=work.KINDS, help="task (default) or issue")
    new.add_argument("--prio", default=None, metavar="P0-P3", help="priority (default P2)")
    new.add_argument("--phase", default=None, metavar="R8", help="the phase milestone")
    new.set_defaults(handler=_add)

    setter = add("set", "change a Work item: work set W12 [--title ..] [--outcome ..] [--prio P0-P3]")
    setter.add_argument("id", metavar="W12")
    setter.add_argument("--title", default=None, metavar="TEXT")
    setter.add_argument("--outcome", default=None, metavar="TEXT")
    setter.add_argument("--prio", default=None, metavar="P0-P3")
    setter.set_defaults(handler=_set)

    link = add("link", "bind an agent task to a Work item: work link R7.86 W12")
    link.add_argument("task", metavar="R7.86", help="an agent task id")
    link.add_argument("work", metavar="W12", help="the Work item id")
    link.set_defaults(handler=_link)

    accept = add("accept", "accept a Work item into Done (the person only)")
    accept.add_argument("id", metavar="W12")
    accept.set_defaults(handler=_accept)

    reopen = add("reopen", "reopen a Review or Done Work item (the person only)")
    reopen.add_argument("id", metavar="W12")
    reopen.set_defaults(handler=_reopen)


# ---------------------------------------------------------------- helpers

def _data(args):
    project, data_dir = tasks.resolve(args.project)
    return project["id"], data_dir


def _json(args):
    return getattr(args, "json", False)


def _fit(lines, reserve=1):
    """The lines that fit under OUT_LINES less reserve (room for the next: line); past that, one '+N more' line."""
    room = OUT_LINES - reserve
    if len(lines) <= room:
        return lines
    return lines[:room - 1] + ["+%d more (roadmap work list)" % (len(lines) - room + 1)]


def _progress(view):
    return "%d/%d" % (view["progress"]["done"], view["progress"]["total"])


def _row(view):
    return "%-5s %-8s %-3s %5s %s" % (view["id"], view["status"], view["prio"], _progress(view), view["title"])


def _task_state(data_dir, tid):
    try:
        return str(tasks.get(data_dir, tid).get("status") or "todo")
    except RoadmapError:
        return "cancelled"


def _write(args, op, payload, next_cmd):
    project_id, _ = _data(args)
    return commands.write(project_id, op, payload, next_cmd)


# ---------------------------------------------------------------- handlers

def _list(args):
    _, data_dir = _data(args)
    views = work.list_views(data_dir)
    if _json(args):
        return {"items": views}
    if not views:
        print("ok no Work items. next: roadmap work add \"<title>\"")
        return None
    for line in _fit([_row(v) for v in views]):
        print(line)
    print("next: roadmap work show %s" % views[0]["id"])
    return None


def _show(args):
    _, data_dir = _data(args)
    view = work.get_view(data_dir, args.id)
    if _json(args):
        return {"item": view}
    lines = [_row(view)]
    if view["outcome"]:
        lines.append("  outcome: " + view["outcome"])
    for tid in view["tasks"]:
        lines.append("  %s %s" % (tid, _task_state(data_dir, tid)))
    if not view["tasks"]:
        lines.append("  no agent tasks yet")
    for line in _fit(lines):
        print(line)
    print("next: roadmap work list")
    return None


def _add(args):
    reply = _write(args, "work.add", {"title": args.title, "outcome": args.outcome, "kind": args.kind,
                                      "prio": args.prio, "phase": args.phase}, LIST_NEXT)
    if _json(args):
        return commands.json_data(reply)
    print("ok %s added. next: roadmap work show %s" % (reply["data"]["id"], reply["data"]["id"]))
    return None


def _set(args):
    payload = {"id": args.id}
    for key in ("title", "outcome", "prio"):
        if getattr(args, key) is not None:
            payload[key] = getattr(args, key)
    nxt = "roadmap work show " + args.id
    reply = _write(args, "work.set", payload, nxt)
    if _json(args):
        return commands.json_data(reply)
    print("ok %s changed. next: %s" % (args.id, nxt))
    return None


def _link(args):
    reply = _write(args, "work.link", {"task": args.task, "work": args.work},
                   "roadmap work show " + args.work)
    if _json(args):
        return commands.json_data(reply)
    print("ok %s -> %s linked. next: roadmap work show %s" % (args.task, args.work, args.work))
    return None


def _accept(args):
    reply = _write(args, "work.accept", {"id": args.id}, LIST_NEXT)
    if _json(args):
        return commands.json_data(reply)
    print("ok %s %s. next: roadmap work list" % (args.id, reply["data"]["status"]))
    return None


def _reopen(args):
    reply = _write(args, "work.reopen", {"id": args.id}, "roadmap work show " + args.id)
    if _json(args):
        return commands.json_data(reply)
    print("ok %s reopened. next: roadmap work show %s" % (args.id, args.id))
    return None
