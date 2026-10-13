"""Command group issue: open, list, show, close and link issues (issues.json). Writes go through the command layer."""

import argparse

from roadmap.errors import EXIT_USAGE, RoadmapError
from roadmap.services import commands, issues

LIST_MAX = 20
NEXT = "roadmap issue list"


def _project_option():
    """Parent parser that adds --project to an action."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--project", metavar="ID", default=None,
                        help="project id (default: $ROADMAP_PROJECT, then the registered project of this folder)")
    return parser


def register(sub, common):
    """Add the issue group and its actions."""
    project = _project_option()
    group = sub.add_parser("issue", parents=[common], help="open, list, show, close or link issues")
    actions = group.add_subparsers(dest="action", metavar="ACTION", required=True)

    new = actions.add_parser("new", parents=[common, project], help="open an issue")
    new.add_argument("title", help="what is wrong, one line")
    new.add_argument("--kind", default="bug", help="bug, risk, question or blocker (default bug)")
    new.add_argument("--sev", default="2", help="1 (most severe), 2 or 3 (default 2)")
    new.add_argument("--task", action="append", default=[], metavar="ID", help="link a task (repeatable, up to 5)")
    new.add_argument("--note", default=None, help="short note")
    new.set_defaults(handler=_new)

    listing = actions.add_parser("list", parents=[common, project], help="list open issues")
    listing.add_argument("--all", action="store_true", help="include closed and wontfix issues")
    listing.set_defaults(handler=_list)

    show = actions.add_parser("show", parents=[common, project], help="show one issue on one line")
    show.add_argument("id", help="issue id, for example I3")
    show.set_defaults(handler=_show)

    close = actions.add_parser("close", parents=[common, project], help="close an issue")
    close.add_argument("id", help="issue id, for example I3")
    close.set_defaults(handler=_close)

    link = actions.add_parser("link", parents=[common, project], help="link tasks to an issue")
    link.add_argument("id", help="issue id, for example I3")
    link.add_argument("tasks", nargs="+", metavar="task", help="task ids, for example P1.2")
    link.set_defaults(handler=_link)


def _line(issue):
    links = " " + " ".join(issue.get("tasks") or []) if issue.get("tasks") else ""
    return "%s %s %s sev%s%s %s" % (issue["id"], issue["status"], issue["kind"], issue["sev"], links,
                                    issue["title"])


def _new(args):
    try:
        sev = int(args.sev)
    except ValueError:
        raise RoadmapError("usage", "sev must be 1, 2 or 3", EXIT_USAGE, next="roadmap issue new \"<title>\"")
    reply = commands.write(args.project, "issue.new", {"title": args.title, "kind": args.kind, "sev": sev,
                                                       "tasks": args.task, "note": args.note, "by": "cli"}, NEXT)
    issue = reply["data"]
    if not getattr(args, "json", False):
        print(issue["id"] + " " + issue["status"])
        return None
    return commands.json_data(reply)


def _list(args):
    data_dir = commands.locate(args.project, NEXT)
    rows = issues.list_issues(data_dir, include_closed=args.all)
    if not getattr(args, "json", False):
        if not rows:
            print("no open issues")
        for issue in rows[:LIST_MAX]:
            print(_line(issue))
        return None
    return {"issues": rows}


def _show(args):
    data_dir = commands.locate(args.project, NEXT)
    with commands.next_on_error(NEXT):
        issue = issues.get(data_dir, args.id)
    if not getattr(args, "json", False):
        note = " -- " + issue["note"] if issue.get("note") else ""
        print(_line(issue) + note)
        return None
    return {"issue": issue}


def _close(args):
    reply = commands.write(args.project, "issue.close", {"id": args.id}, NEXT)
    if not getattr(args, "json", False):
        print(reply["data"]["id"] + " " + ("closed" if reply["data"]["changed"] else "already closed"))
        return None
    return commands.json_data(reply)


def _link(args):
    reply = commands.write(args.project, "issue.link", {"id": args.id, "tasks": args.tasks}, NEXT)
    if not getattr(args, "json", False):
        print(args.id + " links " + " ".join(reply["data"]["tasks"]))
        return None
    return commands.json_data(reply)
