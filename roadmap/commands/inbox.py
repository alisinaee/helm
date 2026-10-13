"""Command inbox: what needs the user or the next agent, in at most 6 lines (queued requests, answers, open questions)."""

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
    """Add the inbox command."""
    parser = sub.add_parser("inbox", parents=[common, _project_option()], help="queued requests, answers and open questions")
    parser.set_defaults(handler=_run)


def _run(args):
    data_dir = commands.locate(args.project, NEXT)
    lines = commands.inbox_lines(data_dir)
    if not getattr(args, "json", False):
        for line in lines:
            print(line)
        return None
    return {"lines": lines}
