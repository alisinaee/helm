"""Top-level command hook: the stdin entry that Claude Code hooks call. Exits 0, prints nothing, never raises."""

import sys

from roadmap.services import hooks


def register(sub, common):
    """Add the hook command to the root subparsers."""
    parser = sub.add_parser("hook", parents=[common], help="hook entry: reads a hook event on stdin")
    parser.set_defaults(handler=_run)


def _run(args):
    """Hand the hook event on stdin to the driver. Returns None, so the CLI exits 0 with no output."""
    try:
        raw = sys.stdin.read()
    except Exception:  # unreadable stdin counts as an empty event; the hook still exits 0
        raw = ""
    hooks.run_hook(raw)
    return None
