"""Command group usage: the global plan-usage store. Implemented in WP6."""

from roadmap.errors import stub


def register(sub, common):
    """Add the usage group and its actions."""
    group = sub.add_parser("usage", parents=[common], help="plan usage (weekly and five-hour limits)")
    actions = group.add_subparsers(dest="action", metavar="ACTION", required=True)
    for name, text in (
        ("show", "show the stored usage"),
        ("sync", "fetch usage now"),
        ("push", "store usage from JSON on stdin"),
    ):
        parser = actions.add_parser(name, parents=[common], help=text)
        parser.set_defaults(handler=stub("usage " + name))
