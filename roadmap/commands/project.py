"""Command group project: register projects and keep their data files healthy. Implemented in WP10."""

from roadmap.errors import stub


def register(sub, common):
    """Add the project group and its actions."""
    group = sub.add_parser("project", parents=[common], help="register and maintain projects")
    actions = group.add_subparsers(dest="action", metavar="ACTION", required=True)

    add = actions.add_parser("add", parents=[common], help="register a project folder")
    add.add_argument("path", help="project folder")
    add.add_argument("--name", help="display name (default: the folder name)")
    add.add_argument("--data-dir", default="docs", help="folder inside the project that holds the data files")
    add.set_defaults(handler=stub("project add"))

    listing = actions.add_parser("list", parents=[common], help="list registered projects")
    listing.set_defaults(handler=stub("project list"))

    show = actions.add_parser("show", parents=[common], help="show one project")
    show.add_argument("id", help="project id")
    show.set_defaults(handler=stub("project show"))

    init = actions.add_parser("init", parents=[common], help="write template data files into a project folder")
    init.add_argument("path", help="project folder")
    init.set_defaults(handler=stub("project init"))

    remove = actions.add_parser("remove", parents=[common], help="unregister a project (files are kept)")
    remove.add_argument("id", help="project id")
    remove.set_defaults(handler=stub("project remove"))

    check = actions.add_parser("check", parents=[common], help="check that a project's files parse")
    check.add_argument("id", nargs="?", help="project id (default: all)")
    check.set_defaults(handler=stub("project check"))

    migrate = actions.add_parser("migrate", parents=[common], help="upgrade a project's data files (backs up first)")
    migrate.add_argument("id", help="project id")
    migrate.set_defaults(handler=stub("project migrate"))
