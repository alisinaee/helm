"""Top-level command hook: the stdin entry that Claude Code hooks call.

Prints one JSON reply on stdout only when the event has one (a PreToolUse deny, a SessionStart context, a Stop
pickup). It exits 0 in every case and never raises. `hook pre` is the PreToolUse gate that hooks install adds.
"""

import json
import sys

from roadmap.services import hooks


def register(sub, common):
    """Add the hook command to the root subparsers."""
    parser = sub.add_parser("hook", parents=[common], help="hook entry: reads a hook event on stdin")
    parser.add_argument("gate", nargs="?", default=None, help="pre: the PreToolUse gate (set by hooks install)")
    parser.set_defaults(handler=_run)


def _run(args):
    """Hand the hook event on stdin to the driver and print its reply, if any. Returns None."""
    try:
        raw = sys.stdin.read()
    except Exception:  # unreadable stdin counts as an empty event; the hook still exits 0
        raw = ""
    reply = hooks.run_hook(raw)
    if reply is not None:
        sys.stdout.write(json.dumps(reply) + "\n")
        sys.stdout.flush()
    return None
