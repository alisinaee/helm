"""Command groups limit and phase: the limit rows that stop agents (services/limits.py, services/control.py).

limit set [PCT]                      the legacy form: stopAtPercent of the weekly usage (refused from an agent)
limit set --scope global|project --window day|week|total --pct N | --tokens K [--warn]
                                     set a row; the same scope, window and kind replace the row there (prints L3 set)
limit rm ID                          remove a row by id: L3, AUTO (the weekly stop) or BUD (the project budget)
limit show                           the rows and where they stand, at most eight lines
limit budget project <K>             a budget in thousands of tokens; `clear` removes it
limit budget phase|model|task X <K>  the same for one phase, model or task (raising or clearing is refused)
phase approve <P>                    approve a phase in tasks.json (refused from an agent)

Set, rm and the legacy form are under the agent guard (CLAUDECODE=1 is refused). Each change is an activity line and can
be undone with `undo`.
"""

from roadmap.errors import EXIT_USAGE, RoadmapError
from roadmap.services import commands, control, limits, tasks


def register(sub, common):
    """Add the limit and phase groups."""
    limit = sub.add_parser("limit", parents=[common], help="set, remove or show the limits")
    limit_actions = limit.add_subparsers(dest="action", metavar="ACTION", required=True)
    weekly = limit_actions.add_parser("set", parents=[common], help="set a limit row, or stopAtPercent with a bare PCT")
    weekly.add_argument("percent", nargs="?", type=float, default=None, metavar="PCT",
                        help="legacy: stopAtPercent of the weekly usage, 1 to 100")
    weekly.add_argument("--scope", choices=("global", "project"), default=None, help="default: project")
    weekly.add_argument("--window", choices=("day", "week", "total"), default=None)
    weekly.add_argument("--pct", type=float, default=None, metavar="N", help="a share of the weekly allowance, 0 to 100")
    weekly.add_argument("--tokens", type=float, default=None, metavar="K", help="thousands of tokens")
    weekly.add_argument("--warn", action="store_true", help="warn at 100%% instead of blocking")
    weekly.add_argument("--project", default=None, metavar="ID")
    weekly.set_defaults(handler=_limit_set)

    remove = limit_actions.add_parser("rm", parents=[common], help="remove a limit row by id, for example L3")
    remove.add_argument("row_id", metavar="ID")
    remove.add_argument("--project", default=None, metavar="ID")
    remove.set_defaults(handler=_limit_rm)

    show = limit_actions.add_parser("show", parents=[common], help="show the limit rows and where they stand")
    show.add_argument("--project", default=None, metavar="ID")
    show.set_defaults(handler=_limit_show)

    budget = limit_actions.add_parser("budget", parents=[common],
                                      help="set a budget in thousands of tokens: project | phase P | model M | "
                                           "task ID, then K (or clear)")
    budget.add_argument("parts", nargs="+", metavar="ARG")
    budget.add_argument("--project", default=None, metavar="ID")
    budget.set_defaults(handler=_limit_budget)

    phase = sub.add_parser("phase", parents=[common], help="approve a phase")
    phase_actions = phase.add_subparsers(dest="action", metavar="ACTION", required=True)
    approve = phase_actions.add_parser("approve", parents=[common], help="mark a phase approved")
    approve.add_argument("phase_id", metavar="P")
    approve.add_argument("--project", default=None, metavar="ID")
    approve.set_defaults(handler=_phase_approve)


def _number(text):
    try:
        return float(text)
    except ValueError:
        raise RoadmapError("usage", "not a number: " + text, EXIT_USAGE)


def _is_legacy(args):
    """The old `limit set <pct>` form: a bare percent and none of the row options."""
    return args.percent is not None and args.scope is None and args.window is None and args.pct is None \
        and args.tokens is None and not args.warn


def _limit_set(args):
    project, _ = tasks.resolve(args.project)
    if _is_legacy(args):
        state = control.set_weekly_limit(project["id"], args.percent)
        return _out(args, {"project": project["id"], "stopAtPercent": args.percent,
                           "summary": control.summary_line(project["id"])},
                    "weekly stop at %g%%" % args.percent, state)
    if args.percent is not None:
        raise RoadmapError("usage", "a bare PCT is the old weekly stop; for a row use --pct N", EXIT_USAGE,
                           next="roadmap limit set --scope project --window week --pct 80")
    if (args.pct is None) == (args.tokens is None):
        raise RoadmapError("usage", "give exactly one of --pct N or --tokens K", EXIT_USAGE,
                           next="roadmap limit set --scope global --window day --pct 10")
    if args.window is None:
        raise RoadmapError("usage", "give --window day, week or total", EXIT_USAGE,
                           next="roadmap limit set --scope global --window day --pct 10")
    kind, value = ("pct", args.pct) if args.pct is not None else ("tok", args.tokens)
    payload = {"scope": args.scope or "project", "window": args.window, "kind": kind, "value": value,
               "action": "warn" if args.warn else "block"}
    reply = commands.write(project["id"], "limit.set", payload, "roadmap limit show")
    data = commands.json_data(reply)
    if getattr(args, "json", False):
        return data
    print("%s set" % data["id"])
    return None


def _limit_rm(args):
    project, _ = tasks.resolve(args.project)
    reply = commands.write(project["id"], "limit.rm", {"id": args.row_id}, "roadmap limit show")
    data = commands.json_data(reply)
    if getattr(args, "json", False):
        return data
    print("%s removed" % data["id"])
    return None


def _limit_show(args):
    project, _ = tasks.resolve(args.project)
    rows = limits.evaluate_rows(project, strict=True)
    lines = limits.show_lines(rows)
    if getattr(args, "json", False):
        return {"project": project["id"], "lines": lines, "rows": rows}
    for line in lines:
        print(line)
    return None


def _limit_budget(args):
    words = list(args.parts)
    value_text = words.pop()
    if words == ["project"]:
        scope, key = "project", None
    elif len(words) == 2 and words[0] in control.SCOPE_WORDS and words[0] != "project":
        scope, key = control.SCOPE_WORDS[words[0]], words[1]
    else:
        raise RoadmapError("usage", "limit budget takes project, phase P, model M or task ID, then K (or clear)",
                           EXIT_USAGE, next="roadmap limit budget task P2.4 50")
    value = None if value_text in ("clear", "none") else _number(value_text)
    project, _ = tasks.resolve(args.project)
    state = control.set_budget_limit(project["id"], scope, key, value)
    label = "project" if key is None else words[0] + " " + key
    return _out(args, {"project": project["id"], "limit": label, "value": value, "summary": control.summary_line(
        project["id"])}, "limit " + label + " " + ("cleared" if value is None else "%g" % value), state)


def _phase_approve(args):
    project, _ = tasks.resolve(args.project)
    result = control.approve_phase(project["id"], args.phase_id)
    data = dict(result, project=project["id"])
    return data if getattr(args, "json", False) else _text(data)


def _out(args, data, line, state):
    if getattr(args, "json", False):
        return data
    print(line)
    return None


def _text(data):
    print("phase %s approved" % data["phase"] if data["changed"] else "phase %s was already approved" % data["phase"])
    return None
