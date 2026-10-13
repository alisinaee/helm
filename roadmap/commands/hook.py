"""Top-level command hook: the stdin entry that Claude Code hooks call. Implemented in WP4, a stub until then."""

from roadmap.errors import stub


def register(sub, common):
    """Add the hook command to the root subparsers."""
    parser = sub.add_parser("hook", parents=[common], help="hook entry: reads a hook event on stdin")
    parser.set_defaults(handler=stub("hook"))
