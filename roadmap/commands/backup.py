"""Top-level command backup: copies the data files into the state directory. Implemented in WP10."""

from roadmap.errors import stub


def register(sub, common):
    """Add the backup command to the root subparsers."""
    parser = sub.add_parser("backup", parents=[common], help="copy the data files to a timestamped backup")
    parser.add_argument("--project", help="project id (default: all projects)")
    parser.set_defaults(handler=stub("backup"))
