"""Top-level command status: the board summary of one project in at most 8 lines (docs/AGENT-INTERFACE.md section 2)."""

from roadmap.services import jobs, tasks


def register(sub, common):
    """Add the status command to the root subparsers."""
    parser = sub.add_parser("status", parents=[common], help="brief board summary of a project")
    parser.add_argument("--project", metavar="ID", default=None,
                        help="project id (default: $ROADMAP_PROJECT, then the registered project of this folder)")
    parser.set_defaults(handler=_run)


def _run(args):
    project, data_dir = tasks.resolve(args.project)
    lines = tasks.summary(data_dir, jobs.list_jobs(data_dir), name=project["id"])
    if not getattr(args, "json", False):
        for line in lines:
            print(line)
        return None
    return {"lines": lines}
