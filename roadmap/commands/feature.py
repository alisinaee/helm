"""Command group feature (WP52): the planner's features. add, list, tree, show, set, move, link, unlink, accept, rm.

Reads never write. Writes go through commands.write, so they log one activity line each and can be undone. accept is
refused from an agent shell (the op says "ask the person"). Output: one line per feature or task; --json keeps the
envelope. A feature's line: F3 doing 4/5 380K/410K blk0 Roadmap visual (done/total, estimate/spent, blocked).
"""

import argparse

from roadmap.errors import EXIT_NOT_FOUND, EXIT_USAGE, RoadmapError
from roadmap.services import commands, features, tasks

NEXT_LIST = "roadmap feature list"
TREE_MAX = 99                       # outline lines printed before the "+N more" line (R7.13 H4)


def _project_option():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--project", metavar="ID", default=None,
                        help="project id (default: $ROADMAP_PROJECT, then the registered project of this folder)")
    return parser


def register(sub, common):
    """Add the feature group and its actions."""
    project = _project_option()
    group = sub.add_parser(
        "feature", parents=[common],
        help="planner features: add, list, tree, show, set, move, link, unlink, accept, rm")
    actions = group.add_subparsers(dest="action", metavar="ACTION", required=True)

    add = actions.add_parser("add", parents=[common, project], help="add a feature")
    add.add_argument("title", help="what you are building, at most 80 characters")
    add.add_argument("--acc", default="", metavar="TEXT", help="acceptance, at most 160 characters")
    add.add_argument("--prio", type=int, choices=(1, 2, 3), default=2)
    add.add_argument("--phase", default=None, metavar="R6", help="phase id")
    add.add_argument("--parent", default=None, metavar="F2", help="parent feature (3 levels at most)")
    _ask_flags(add, "mark the feature as asked for by the person")
    add.set_defaults(handler=_add)

    listing = actions.add_parser("list", parents=[common, project], help="one line per feature")
    listing.set_defaults(handler=_list)

    tree = actions.add_parser("tree", parents=[common, project],
                              help="the plan outline: one line per item (at most 99 lines)")
    tree.set_defaults(handler=_tree)

    update = actions.add_parser("set", parents=[common, project], help="change a feature's ask flag")
    update.add_argument("id", metavar="F3")
    _ask_flags(update, "the person asked for this (or not)", required=True)
    update.set_defaults(handler=_set)

    move = actions.add_parser("move", parents=[common, project], help="move a feature up or down, or under a parent")
    move.add_argument("id", metavar="F3")
    where = move.add_mutually_exclusive_group(required=True)
    where.add_argument("--up", action="store_true", help="swap with the sibling above")
    where.add_argument("--down", action="store_true", help="swap with the sibling below")
    where.add_argument("--parent", metavar="F2|-", default=None, help="move under this feature, or - for the top level")
    move.set_defaults(handler=_move)

    show = actions.add_parser("show", parents=[common, project], help="one feature and its tasks")
    show.add_argument("id", metavar="F3")
    show.set_defaults(handler=_show)

    link = actions.add_parser("link", parents=[common, project], help="link a feature to tasks")
    link.add_argument("id", metavar="F3")
    link.add_argument("tasks", nargs="+", metavar="TASK", help="task ids, for example R6.6")
    link.set_defaults(handler=_link)

    unlink = actions.add_parser("unlink", parents=[common, project], help="unlink a feature from tasks")
    unlink.add_argument("id", metavar="F3")
    unlink.add_argument("tasks", nargs="+", metavar="TASK")
    unlink.set_defaults(handler=_unlink)

    accept = actions.add_parser("accept", parents=[common, project], help="mark a feature accepted (the person only)")
    accept.add_argument("id", metavar="F3")
    accept.add_argument("--off", action="store_true", help="clear the accepted date instead")
    accept.add_argument("--yes", action="store_true", help="accept even when the feature is not done")
    accept.set_defaults(handler=_accept)

    remove = actions.add_parser("rm", parents=[common, project], help="remove a feature with no tasks")
    remove.add_argument("id", metavar="F3")
    remove.set_defaults(handler=_rm)


def _ask_flags(parser, help_text, required=False):
    """--ask and --no-ask, one of them (set requires one)."""
    group = parser.add_mutually_exclusive_group(required=required)
    group.add_argument("--ask", dest="ask", action="store_const", const=True, default=None,
                       help=help_text)
    group.add_argument("--no-ask", dest="ask", action="store_const", const=False, default=None,
                       help="clear the ask flag")


def _json(args):
    return getattr(args, "json", False)


def _k(value):
    return str(int(round(float(value or 0)))) + "K"


def _line(row):
    return "%s %s %d/%d %s/%s blk%d %s" % (row["id"], row["state"], row["done"], row["total"], _k(row["estK"]),
                                          _k(row["spentK"]), row["blocked"], row["title"])


def _emit(lines):
    for line in lines:
        print(line)


def _check_id(value):
    if not value or not value.startswith("F") or not value[1:].isdigit():
        raise RoadmapError("usage", "feature id '" + value + "' must look like F3 (allowed: F1 to F99)", EXIT_USAGE,
                           next=NEXT_LIST)
    return value


def _find(data_dir, fid):
    for row in features.derived(data_dir)["rows"]:
        if row["id"] == fid:
            return row
    raise RoadmapError("not_found", "no feature " + fid, EXIT_NOT_FOUND, next=NEXT_LIST)


def _add(args):
    project, _ = tasks.resolve(args.project)
    reply = commands.write(project["id"], "feature.add", {"title": args.title, "acc": args.acc, "prio": args.prio,
                                                         "phase": args.phase, "parent": args.parent,
                                                         "ask": args.ask is True}, NEXT_LIST)
    row = reply["data"]
    if _json(args):
        return commands.json_data(reply)
    print(row["id"] + " added: " + row["title"])
    return None


def _list(args):
    _, data_dir = tasks.resolve(args.project)
    rows = features.derived(data_dir)["rows"]
    if _json(args):
        return {"features": rows}
    if not rows:
        print("no features yet")
        return None
    _emit(_line(row) for row in rows)
    return None


def _outline_key(row):
    """Sort key that puts the rows in preorder: P0, P0.0, P0.0.1, P0.1, P1."""
    label = row.get("label")
    if not isinstance(label, str) or not label[1:].replace(".", "").isdigit():
        return (1, ())
    return (0, tuple(int(part) for part in label[1:].split(".")))


def tree_line(row):
    """One outline line: indent by depth, then P1.2 F7 doing 3/5 gaps:1 [ask] title."""
    depth = str(row.get("label") or "").count(".")
    gaps = " gaps:%d" % row["gaps"] if row.get("gaps") else ""
    ask = " [ask]" if row.get("ask") else ""
    return "%s%s %s %s %d/%d%s%s %s" % ("  " * depth, row.get("label") or "-", row["id"], row["state"], row["done"],
                                       row["total"], gaps, ask, row["title"])


def tree_next(rows):
    """The next: hint for the outline: link the first uncovered item, else show the first item not done."""
    for row in rows:
        if row["state"] == "uncovered":
            return "roadmap feature link " + row["id"] + " <TASK>"
    for row in rows:
        if row["state"] != "done" and row["state"] != "hold":
            return "roadmap feature show " + row["id"]
    return "roadmap plan view"


def _tree(args):
    _, data_dir = tasks.resolve(args.project)
    rows = sorted(features.derived(data_dir)["rows"], key=_outline_key)
    keep = TREE_MAX - 1 if len(rows) > TREE_MAX else TREE_MAX     # the "+N more" line takes the last slot
    lines = [tree_line(row) for row in rows[:keep]]
    if len(rows) > TREE_MAX:
        lines.append("+%d more" % (len(rows) - keep))
    if not rows:
        lines = ["no plan yet"]
    nxt = "roadmap plan template --tree" if not rows else tree_next(rows)
    if _json(args):
        return {"lines": lines, "total": len(rows), "next": nxt}
    _emit(lines)
    print("next: " + nxt)
    return None


def _set(args):
    fid = _check_id(args.id)
    project, _ = tasks.resolve(args.project)
    reply = commands.write(project["id"], "feature.set", {"id": fid, "ask": args.ask}, NEXT_LIST)
    if _json(args):
        return commands.json_data(reply)
    print("%s %s" % (fid, "asked for" if args.ask else "not asked for"))
    return None


def _move(args):
    fid = _check_id(args.id)
    project, _ = tasks.resolve(args.project)
    if args.parent is not None:
        payload = {"id": fid, "parent": "" if args.parent == "-" else args.parent}
    else:
        payload = {"id": fid, "dir": "up" if args.up else "down"}
    reply = commands.write(project["id"], "feature.move", payload, NEXT_LIST)
    if _json(args):
        return commands.json_data(reply)
    print("%s now %s" % (fid, reply["data"].get("label") or "at the top level"))
    return None


def _show(args):
    fid = _check_id(args.id)
    _, data_dir = tasks.resolve(args.project)
    row = _find(data_dir, fid)
    covered = features.task_views(data_dir, fid)
    if _json(args):
        return {"feature": row, "tasks": covered}
    print(_line(row))
    if row["acc"]:
        print("acc: " + row["acc"])
    for task in covered:
        print("  %s %s %s | %s" % (task["id"], task["state"], _k(task["estK"]), task["title"]))
    return None


def _links(args, op):
    fid = _check_id(args.id)
    project, _ = tasks.resolve(args.project)
    replies = []
    for task_id in args.tasks:
        replies.append(commands.write(project["id"], op, {"task": task_id, "feats": [fid]}, NEXT_LIST))
    return fid, replies


def _link(args):
    fid, replies = _links(args, "feature.link")
    data = [reply["data"] for reply in replies]
    if _json(args):
        return {"id": fid, "links": data}
    for reply in replies:
        print("%s linked to %s" % (fid, reply["data"]["task"]) if reply["data"]["added"] else
              "%s already linked to %s" % (fid, reply["data"]["task"]))
    return None


def _unlink(args):
    fid, replies = _links(args, "feature.unlink")
    data = [reply["data"] for reply in replies]
    if _json(args):
        return {"id": fid, "links": data}
    for reply in replies:
        print("%s unlinked from %s" % (fid, reply["data"]["task"]) if reply["data"]["removed"] else
              "%s was not linked to %s" % (fid, reply["data"]["task"]))
    return None


def _accept(args):
    fid = _check_id(args.id)
    project, _ = tasks.resolve(args.project)
    reply = commands.write(project["id"], "feature.accept", {"id": fid, "on": not args.off, "confirm": args.yes},
                           NEXT_LIST)
    data = reply["data"]
    if _json(args):
        return commands.json_data(reply)
    print(fid + (" accepted " + data["accepted"] if data["accepted"] else " not accepted"))
    return None


def _rm(args):
    fid = _check_id(args.id)
    project, _ = tasks.resolve(args.project)
    reply = commands.write(project["id"], "feature.rm", {"id": fid}, NEXT_LIST)
    if _json(args):
        return commands.json_data(reply)
    print("removed " + fid)
    return None
