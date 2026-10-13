"""Command group task: read and change tasks in the project's tasks.json (show, list, done, start, hold, set).

Reads never write. Writes go through roadmap.services.tasks.apply, which validates every record before the first
write. Output follows docs/AGENT-INTERFACE.md section 2: one line per task, and --json keeps the envelope.
"""

import argparse
import sys

from roadmap.core import planfmt
from roadmap.errors import EXIT_INVALID_DATA, EXIT_NOT_FOUND, RoadmapError
from roadmap.services import commands, tasks

STATUS_FOR = {"done": "done", "start": "partial", "hold": "hold"}
ERRORS_SHOWN = 5
DIFFS_SHOWN = 10
LIST_DEFAULT = 20


def _project_option():
    """Parent parser that adds --project to an action."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--project", metavar="ID", default=None,
                        help="project id (default: $ROADMAP_PROJECT, then the registered project of this folder)")
    return parser


def register(sub, common):
    """Add the task group and its actions."""
    project = _project_option()
    group = sub.add_parser("task", parents=[common], help="read and change tasks")
    actions = group.add_subparsers(dest="action", metavar="ACTION", required=True)

    show = actions.add_parser("show", parents=[common, project], help="show one task as one plan line")
    show.add_argument("id", help="task id, for example P2.4")
    show.set_defaults(handler=_show)

    listing = actions.add_parser("list", parents=[common, project], help="list tasks as plan lines")
    listing.add_argument("--phase", metavar="P", default=None, help="only the tasks of this phase")
    listing.add_argument("--status", metavar="S", default=None,
                         help="comma list of todo, partial, done, hold")
    listing.add_argument("--needs-you", action="store_true", help="only tasks that need the user")
    listing.add_argument("--limit", metavar="N", type=int, default=LIST_DEFAULT,
                         help="most tasks to print (default %d)" % LIST_DEFAULT)
    listing.set_defaults(handler=_list)

    for name, text in (("done", "mark tasks done"), ("start", "mark tasks started (partial)"),
                       ("hold", "put tasks on hold")):
        parser = actions.add_parser(name, parents=[common, project], help=text)
        parser.add_argument("ids", nargs="+", metavar="id", help="one or more task ids")
        parser.add_argument("--tokens", metavar="K", default=None, help="tokens used, in thousands (whole number)")
        parser.add_argument("--note", metavar="TEXT", default=None, help="short note; an empty value clears it")
        parser.set_defaults(handler=_change, status_word=name)

    bulk = actions.add_parser("set", parents=[common, project],
                              help="bulk patch from stdin, one 'ID key=value ...' line per task")
    bulk.add_argument("source", nargs="?", default="-", help="a file, or - for stdin (default -)")
    bulk.add_argument("--dry-run", action="store_true", help="show what would change, write nothing")
    bulk.set_defaults(handler=_set)


def plan_failure(errors, next_cmd, exit_code=EXIT_INVALID_DATA):
    """The error for invalid input: the first ERRORS_SHOWN problems, one per line, then a next: line.
    Nothing is written."""
    shown = list(errors[:ERRORS_SHOWN])
    if len(errors) > ERRORS_SHOWN and shown:
        shown[-1] += " (+%d more)" % (len(errors) - ERRORS_SHOWN)
    return RoadmapError("invalid_plan", "\n".join(shown) or "invalid input", exit_code, next=next_cmd)


def apply_records(data_dir, project_id, records, next_cmd, dry_run=False, replace_phase=None):
    """Run tasks.apply and turn a PlanError into the CLI error: exit 3 for unknown ids, exit 5 otherwise."""
    try:
        return tasks.apply(data_dir, records, dry_run=dry_run, replace_phase=replace_phase, project_id=project_id)
    except tasks.PlanError as exc:
        exit_code = EXIT_NOT_FOUND if exc.exit == EXIT_NOT_FOUND else EXIT_INVALID_DATA
        cmd = exc.next if exc.next and exc.next.startswith("roadmap ") else next_cmd
        raise plan_failure(exc.errors, cmd, exit_code)


def print_diff(diff, json_mode):
    """Print the summary line and, for a dry run, up to DIFFS_SHOWN field diffs. Returns the json data."""
    summary = tasks.describe(diff)
    data = {"summary": summary, "changed": diff["changed"], "wrote": diff["wrote"], "dry_run": diff["dry_run"],
            "field_diffs": diff["field_diffs"], "backup": diff["backup"]}
    if not json_mode:
        print(summary)
        if diff["dry_run"]:
            for line in diff["field_diffs"][:DIFFS_SHOWN]:
                print("~ " + line)
            for tid in diff["tasks_removed"]:
                print("- " + tid)
        return None
    return data


def _data(args):
    project, data_dir = tasks.resolve(args.project)
    return project["id"], data_dir


def _show(args):
    _, data_dir = _data(args)
    task = tasks.get(data_dir, args.id)
    if not getattr(args, "json", False):
        print(planfmt.format_task(task))
        return None
    return {"task": task}


def _list(args):
    _, data_dir = _data(args)
    rows = tasks.query(data_dir, phase=args.phase, status=args.status, needs_you=args.needs_you, limit=args.limit)
    if not getattr(args, "json", False):
        if not rows:
            print("no tasks")
        for row in rows:
            print(planfmt.format_task(row))
        return None
    return {"tasks": rows}


def _change(args):
    """task done|start|hold: each id goes through the registry op task.status, so every change is logged to the
    activity log and can be undone. --tokens feeds the budget once per task (WP20 budget service)."""
    project_id, data_dir = _data(args)
    status = STATUS_FOR[args.status_word]
    for tid in args.ids:
        tasks.get(data_dir, tid)  # unknown id: exit 3 with the exact next command
    tokens = _tokens_arg(args.tokens)
    for tid in args.ids:
        payload = {"id": tid, "status": status}
        if tokens is not None:
            payload["tokensK"] = tokens
        if args.note is not None:
            payload["note"] = args.note
        commands.write(project_id, "task.status", payload, "roadmap task list --phase " + tid.split(".")[0])
    if not getattr(args, "json", False):
        for tid in args.ids:
            print(tid + " " + status)
        return None
    return {"ids": list(args.ids), "status": status}


def _tokens_arg(value):
    """--tokens K as a whole number of thousands, or None when not given. Anything else is refused before any write
    (exit 5, the same as a bad plan line)."""
    if value is None:
        return None
    text = str(value).strip()
    if not text.isdigit():
        raise plan_failure(["tokensK '%s' is not a whole number (allowed: 0, 1, 2 ...)" % text],
                           "roadmap task done <id> --tokens 20")
    return int(text)


def _set(args):
    project_id, data_dir = _data(args)
    text = _read_source(args.source)
    records, errors = planfmt.parse_set_text(text)
    next_cmd = "roadmap task set " + args.source + " --dry-run"
    if errors:
        raise plan_failure(errors, next_cmd)
    diff = apply_records(data_dir, project_id, records, next_cmd, dry_run=args.dry_run)
    return print_diff(diff, getattr(args, "json", False))


def _read_source(source):
    if source == "-":
        return sys.stdin.read()
    try:
        with open(source, "r", encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        raise RoadmapError("not_found", "cannot read " + source, EXIT_NOT_FOUND)
