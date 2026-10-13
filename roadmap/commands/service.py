"""Command group service: the launchd lifecycle of the background server. Implemented in WP11."""

from roadmap.errors import stub


def register(sub, common):
    """Add the service group and its actions."""
    group = sub.add_parser("service", parents=[common], help="manage the background service")
    actions = group.add_subparsers(dest="action", metavar="ACTION", required=True)
    for name, text in (
        ("install", "install the launchd agent"),
        ("uninstall", "remove the launchd agent"),
        ("start", "start the service"),
        ("stop", "stop the service"),
        ("restart", "restart the service"),
        ("status", "show whether the service is loaded and answering"),
        ("logs", "show the service logs"),
    ):
        parser = actions.add_parser(name, parents=[common], help=text)
        if name == "logs":
            parser.add_argument("-f", "--follow", action="store_true", help="keep printing new lines")
        parser.set_defaults(handler=stub("service " + name))
