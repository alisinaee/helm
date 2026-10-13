"""Command groups limit and phase: the limits that stop agents (services/control.py).

limit set <pct>                      stopAtPercent of the weekly usage (refused from an agent)
limit budget project <K>             a budget in thousands of tokens; `clear` removes it
limit budget phase|model|task X <K>  the same for one phase, model or task (raising or clearing is refused)
phase approve <P>                    approve a phase in tasks.json (refused from an agent)
"""

from roadmap.errors import EXIT_USAGE, RoadmapError
from roadmap.services import control, tasks


def register(sub, common):
    """Add the limit and phase groups."""
    limit = sub.add_parser("limit", parents=[common], help="set the weekly stop percent or a budget limit")
    limit_actions = limit.add_subparsers(dest="action", metavar="ACTION", required=True)
    weekly = limit_actions.add_parser("set", parents=[common], help="set stopAtPercent (weekly usage, 1 to 100)")
    weekly.add_argument("percent", type=float, metavar="PCT")
    weekly.add_argument("--project", default=None, metavar="ID")
    weekly.set_defaults(handler=_limit_set)
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


def _limit_set(args):
    project, _ = tasks.resolve(args.project)
    state = control.set_weekly_limit(project["id"], args.percent)
    return _out(args, {"project": project["id"], "stopAtPercent": args.percent, "summary": control.summary_line(
        project["id"])}, "weekly stop at %g%%" % args.percent, state)


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
