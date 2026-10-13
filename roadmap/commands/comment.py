"""Commands comment and comments: add a comment on a task or issue, and read the newest ones."""

import argparse

from roadmap.services import commands, comments

NEXT = "roadmap status"
DEFAULT_LAST = 5


def _project_option():
    """Parent parser that adds --project to an action."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--project", metavar="ID", default=None,
                        help="project id (default: $ROADMAP_PROJECT, then the registered project of this folder)")
    return parser


def register(sub, common):
    """Add the comment and comments commands."""
    project = _project_option()
    add = sub.add_parser("comment", parents=[common, project], help="add a comment on a task or issue")
    add.add_argument("target", metavar="ID", help="task or issue id, for example P2.4 or I3")
    add.add_argument("text", nargs="+", help="comment text, up to 280 characters")
    add.set_defaults(handler=_add)

    listing = sub.add_parser("comments", parents=[common, project], help="show the newest comments on a task or issue")
    listing.add_argument("target", metavar="ID", help="task or issue id")
    listing.add_argument("--last", metavar="N", type=int, default=DEFAULT_LAST,
                         help="how many of the newest comments (default %d)" % DEFAULT_LAST)
    listing.set_defaults(handler=_list)


def _add(args):
    reply = commands.write(args.project, "comment.add",
                           {"on": args.target, "text": " ".join(args.text), "by": "cli"}, NEXT)
    if not getattr(args, "json", False):
        print("commented " + args.target)
        return None
    return commands.json_data(reply)


def _list(args):
    data_dir = commands.locate(args.project, NEXT)
    last = args.last if args.last > 0 else DEFAULT_LAST
    rows = comments.list_comments(data_dir, on=args.target, limit=last)
    if not getattr(args, "json", False):
        if not rows:
            print("no comments on " + args.target)
        for row in rows:
            print("%s %s: %s" % (str(row.get("at", ""))[:16], row.get("by") or "-", row.get("t", "")))
        return None
    return {"comments": rows}
