"""Top-level command status: the board summary of one project in at most 8 lines and 700 characters.

Lines keep this order, and when space runs out the lowest ones go first: header, left, phase, run, ask, queue,
issues, features, budget, you, next. The ask, queue, issues and budget lines come from the command layer
(docs/AGENT-INTERFACE.md section 2; docs/PRODUCT-SPEC.md section 4).
"""

from roadmap.services import commands, features, jobs, limits, tasks

MAX_LINES = 8
MAX_CHARS = 700
HEAD = 3


def register(sub, common):
    """Add the status command to the root subparsers."""
    parser = sub.add_parser("status", parents=[common], help="brief board summary of a project")
    parser.add_argument("--project", metavar="ID", default=None,
                        help="project id (default: $ROADMAP_PROJECT, then the registered project of this folder)")
    parser.set_defaults(handler=_run)


def compose(base, extras):
    """Put the base summary lines and the four command-layer lines in priority order, then fit the budget."""
    head, rest = base[:HEAD], base[HEAD:]
    you = [line for line in rest if line.startswith("you:")]
    nxt = [line for line in rest if line.startswith("next:")]
    run = [line for line in rest if line.startswith("run:")]
    meters = [extras["limits"]] if extras.get("limits") else []
    plan = [extras["features"]] if extras.get("features") else []
    ordered = (head + run + [extras["ask"], extras["queue"], extras["issues"]] + plan + [extras["budget"]] + meters
               + you + nxt)
    return _fit(ordered)


def _fit(lines):
    """Keep lines in order while they fit: at most MAX_LINES lines and MAX_CHARS characters in all."""
    kept = []
    for line in lines:
        candidate = kept + [line]
        if len(candidate) > MAX_LINES or len("\n".join(candidate)) > MAX_CHARS:
            break
        kept.append(line)
    return kept


def _run(args):
    project, data_dir = tasks.resolve(args.project)
    base = tasks.summary(data_dir, jobs.list_jobs(data_dir), name=project["id"])
    extras = commands.status_extras(data_dir)
    extras["limits"] = limits.status_line(limits.evaluate_rows(project))
    extras["features"] = features.status_line(data_dir)
    lines = compose(base, extras)
    if not getattr(args, "json", False):
        for line in lines:
            print(line)
        return None
    return {"lines": lines}
