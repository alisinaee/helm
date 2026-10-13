"""Command undo: put back a change that reports undo, by its activity id (undo A812)."""

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
    """Add the undo command."""
    parser = sub.add_parser("undo", parents=[common, _project_option()],
                            help="reverse one change by its activity id, for example undo A812")
    parser.add_argument("activity", metavar="A812", help="activity id from the activity log")
    parser.set_defaults(handler=_run)


def _run(args):
    reply = commands.write(args.project, "undo", {"activity": args.activity}, NEXT)
    if not getattr(args, "json", False):
        print("undid %s: %s" % (reply["data"]["undone"], reply["data"]["sum"]))
        return None
    return commands.json_data(reply)
