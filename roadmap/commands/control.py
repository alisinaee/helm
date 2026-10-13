"""Command group control: stop (always allowed), resume and override (refused from an agent shell).

Each call writes an activity line and recomputes the control state (services/control.py).
"""

from roadmap.services import control, tasks


def register(sub, common):
    """Add the stop, resume and override commands."""
    stop = sub.add_parser("stop", parents=[common], help="stop the project, or one task with --task")
    stop.add_argument("--task", default=None, metavar="ID", help="stop only this task")
    stop.add_argument("--project", default=None, metavar="ID")
    stop.set_defaults(handler=_stop)

    resume = sub.add_parser("resume", parents=[common], help="clear the stop and every stopped task")
    resume.add_argument("--project", default=None, metavar="ID")
    resume.set_defaults(handler=_resume)

    over = sub.add_parser("override", parents=[common], help="work past a budget or weekly block for 1 to 4 hours")
    over.add_argument("--hours", type=float, required=True, metavar="N")
    over.add_argument("--project", default=None, metavar="ID")
    over.set_defaults(handler=_override)


def _emit(args, state, project_id):
    summary = control.summary_line(project_id)
    data = {"project": project_id, "summary": summary, "stop": state["stop"], "stopTasks": state["stopTasks"],
            "block": state["block"], "overrideUntil": state["overrideUntil"], "warn": state["warn"]}
    if getattr(args, "json", False):
        return data
    print(summary)
    return None


def _stop(args):
    project, _ = tasks.resolve(args.project)
    state = control.stop(project["id"], task=args.task)
    return _emit(args, state, project["id"])


def _resume(args):
    project, _ = tasks.resolve(args.project)
    state = control.resume(project["id"])
    return _emit(args, state, project["id"])


def _override(args):
    project, _ = tasks.resolve(args.project)
    state = control.override(project["id"], args.hours)
    return _emit(args, state, project["id"])
