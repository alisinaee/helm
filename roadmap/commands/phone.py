"""Command group phone: the read-only phone listener and its tunnel. Implemented in WP13."""

from roadmap.errors import stub


def register(sub, common):
    """Add the phone group and its actions."""
    group = sub.add_parser("phone", parents=[common], help="read-only access from a phone")
    actions = group.add_subparsers(dest="action", metavar="ACTION", required=True)
    for name, text in (
        ("start", "rotate the phone token and start the tunnel"),
        ("stop", "stop the tunnel and delete the token"),
        ("link", "print the phone link"),
        ("status", "show whether the tunnel is running"),
    ):
        parser = actions.add_parser(name, parents=[common], help=text)
        parser.set_defaults(handler=stub("phone " + name))
