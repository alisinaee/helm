"""Command group job: record Claude jobs and their tokens. Implemented in WP4."""

from roadmap.errors import stub


def register(sub, common):
    """Add the job group and its actions."""
    group = sub.add_parser("job", parents=[common], help="record jobs")
    actions = group.add_subparsers(dest="action", metavar="ACTION", required=True)

    start = actions.add_parser("start", parents=[common], help="start a job")
    start.add_argument("title", help="what the job does")
    start.add_argument("model", help="model name, for example opus, sonnet or haiku")
    start.add_argument("task", nargs="?", help="task id from the project's tasks.json")
    start.set_defaults(handler=stub("job start"))

    for name, text in (("done", "mark a job done"), ("fail", "mark a job failed")):
        parser = actions.add_parser(name, parents=[common], help=text)
        parser.add_argument("id", help="job id")
        parser.add_argument("note", nargs="?", help="short summary")
        parser.add_argument("--tokens", type=int, metavar="K", help="tokens used, in thousands")
        parser.set_defaults(handler=stub("job " + name))

    listing = actions.add_parser("list", parents=[common], help="list jobs")
    listing.set_defaults(handler=stub("job list"))

    prune = actions.add_parser("prune", parents=[common], help="remove finished jobs older than the retention limit")
    prune.set_defaults(handler=stub("job prune"))
