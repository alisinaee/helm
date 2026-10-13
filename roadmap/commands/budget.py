"""Command budget: show the spend and the limits (budget show [--phase P], at most 8 lines).

Setting limits is a separate command group (budget set, limit set) and is not here.
"""

import argparse

from roadmap.services import budget, commands

NEXT = "roadmap budget show"
SHOWN_MAX = 8
TOP = 5


def _project_option():
    """Parent parser that adds --project to an action."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--project", metavar="ID", default=None,
                        help="project id (default: $ROADMAP_PROJECT, then the registered project of this folder)")
    return parser


def register(sub, common):
    """Add the budget group. Only the show action lives here."""
    project = _project_option()
    group = sub.add_parser("budget", parents=[common], help="show spend and limits")
    actions = group.add_subparsers(dest="action", metavar="ACTION", required=True)
    show = actions.add_parser("show", parents=[common, project], help="show spend and limits (8 lines)")
    show.add_argument("--phase", metavar="P", default=None, help="also show this phase and its top tasks")
    show.set_defaults(handler=_show)


def _top(pairs):
    """'name 20k, name 5k' for the largest first, at most TOP."""
    ranked = sorted(pairs.items(), key=lambda kv: (-kv[1], kv[0]))
    return ", ".join("%s %s" % (name, commands.k_text(value)) for name, value in ranked[:TOP])


def show_lines(data_dir, phase=None):
    """The budget view as plain lines, at most SHOWN_MAX."""
    total, by_model, by_phase, limit, limits = commands.budget_totals(data_dir)
    if limit is None:
        head = "spent %s; no project limit" % commands.k_text(total)
    else:
        head = "spent %s of %s project limit" % (commands.k_text(total), commands.k_text(limit))
    lines = [head, "models: " + (_top(by_model) if by_model else "none yet")]
    if phase is None:
        lines.append("phases: " + (_top(by_phase) if by_phase else "none yet"))
    else:
        doc = budget.get(data_dir)
        mine = {}
        for task_id, models in doc["spent"].items():
            if str(task_id).split(".")[0] == phase:
                mine[task_id] = sum(models.values())
        phase_total = sum(mine.values())
        phase_limit = limits.get("phases", {}).get(phase)
        note = "limit %s" % commands.k_text(phase_limit) if phase_limit is not None else "no limit"
        lines.append("%s: spent %s, %s" % (phase, commands.k_text(phase_total), note))
        lines.append("tasks: " + (_top(mine) if mine else "none yet"))
    set_limits = []
    for scope in ("phases", "models", "tasks"):
        for key, value in sorted((limits.get(scope) or {}).items()):
            set_limits.append("%s %s %s" % (scope[:-1], key, commands.k_text(value)))
    lines.append("limits: " + ("; ".join(set_limits) if set_limits else "none set"))
    return lines[:SHOWN_MAX]


def _show(args):
    data_dir = commands.locate(args.project, NEXT)
    lines = show_lines(data_dir, args.phase)
    if not getattr(args, "json", False):
        for line in lines:
            print(line)
        return None
    return {"lines": lines}
