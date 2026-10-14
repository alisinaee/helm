"""Command group subtask: add a subtask to a task, and tick or untick one (P2.4/2).
Writes go through the command layer."""

import argparse

from roadmap.services import commands

NEXT = "roadmap status"


def _project_option():
    """Parent parser that adds --project to an action."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--project", metavar="ID", default=None,
                        help="project id (default: $ROADMAP_PROJECT, then the registered project of this folder)")
    return parser


def register(sub, common):
    """Add the subtask group and its actions."""
    project = _project_option()
    group = sub.add_parser("subtask", parents=[common], help="add subtasks, mark them done")
    actions = group.add_subparsers(dest="action", metavar="ACTION", required=True)

    add = actions.add_parser("add", parents=[common, project], help="add a subtask to a task")
    add.add_argument("id", help="task id, for example P2.4")
    add.add_argument("title", nargs="+", help="subtask text, up to 80 characters")
    add.set_defaults(handler=_add)

    done = actions.add_parser("done", parents=[common, project], help="mark a subtask done")
    done.add_argument("addr", help="subtask address, for example P2.4/2")
    done.set_defaults(handler=_done)


def _add(args):
    reply = commands.write(args.project, "subtask.add", {"id": args.id, "title": " ".join(args.title)}, NEXT)
    if not getattr(args, "json", False):
        print(reply["data"]["addr"] + " added")
        return None
    return commands.json_data(reply)


def _done(args):
    reply = commands.write(args.project, "subtask.toggle", {"addr": args.addr, "done": True}, NEXT)
    if not getattr(args, "json", False):
        suffix = "" if reply["data"]["changed"] else " (no change)"
        print(args.addr + " done" + suffix)
        return None
    return commands.json_data(reply)
