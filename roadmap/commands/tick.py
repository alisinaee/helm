"""Top-level command tick: one supervisor pass over the project store (reap, leases, retry, fold) for when serve is
down. serve runs the same pass in a thread; the lock in supervisor.tick keeps the two from overlapping."""

from roadmap.services import commands, supervisor

NEXT = "roadmap project list"


def register(sub, common):
    """Add the tick command to the root subparsers."""
    parser = sub.add_parser("tick", parents=[common], help="run one supervisor pass (use when serve is down)")
    parser.add_argument("--project", metavar="ID", default=None,
                        help="project id (default: $ROADMAP_PROJECT, then the registered project of this folder)")
    parser.set_defaults(handler=handle)


def handle(args):
    """Run one pass for the project. A pass that finds the lock held by another pass does nothing (ran false)."""
    data_dir = commands.locate(args.project, NEXT)
    report = supervisor.tick(data_dir)
    if not getattr(args, "json", False):
        if report["ran"]:
            print("roadmap: tick done (reaped %d, expired leases %d, queued %d, needs you %d, done %d, asks closed %d)"
                  % (len(report["reaped"]), len(report["expired_leases"]), len(report["queued"]),
                     len(report["needs_you"]), len(report["done_tasks"]), len(report["closed_asks"])))
        else:
            print("roadmap: tick skipped (%s)" % report["reason"])
    return report
