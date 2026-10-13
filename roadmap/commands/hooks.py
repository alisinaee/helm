"""Command group hooks: install and inspect the Claude Code hooks of a project. Implemented in WP10."""

from roadmap.errors import stub


def register(sub, common):
    """Add the hooks group and its actions."""
    group = sub.add_parser("hooks", parents=[common], help="install or inspect project hooks")
    actions = group.add_subparsers(dest="action", metavar="ACTION", required=True)

    install = actions.add_parser("install", parents=[common], help="merge the hooks into the project settings")
    install.add_argument("project", help="project id")
    install.add_argument("--replace-legacy", action="store_true", help="remove old jobs_auto.py entries")
    install.set_defaults(handler=stub("hooks install"))

    uninstall = actions.add_parser("uninstall", parents=[common], help="remove the roadmap hook entries")
    uninstall.add_argument("project", help="project id")
    uninstall.set_defaults(handler=stub("hooks uninstall"))

    status = actions.add_parser("status", parents=[common], help="show which hooks are installed")
    status.add_argument("project", help="project id")
    status.set_defaults(handler=stub("hooks status"))
