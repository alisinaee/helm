"""Top-level command doctor: checks the install and prints the fix for each problem. Implemented in WP11."""

from roadmap.errors import stub


def register(sub, common):
    """Add the doctor command to the root subparsers."""
    parser = sub.add_parser("doctor", parents=[common], help="check the install and print a fix for each problem")
    parser.set_defaults(handler=stub("doctor"))
