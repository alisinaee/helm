"""Top-level command hook: the stdin entry that Claude Code hooks call.

Prints one JSON reply on stdout only when the event has one (a PreToolUse deny, a SessionStart context, a Stop
pickup). It exits 0 in every case and never raises. `hook pre` is the PreToolUse gate that hooks install adds.
"""

import json
import sys
import time

from roadmap import log as roadmap_log
from roadmap.services import hooks


def register(sub, common):
    """Add the hook command to the root subparsers."""
    parser = sub.add_parser("hook", parents=[common], help="hook entry: reads a hook event on stdin")
    parser.add_argument("gate", nargs="?", default=None, help="pre: the PreToolUse gate (set by hooks install)")
    parser.set_defaults(handler=_run)


def _run(args):
    """Hand the hook event on stdin to the driver and print its reply, if any. Returns None."""
    started = time.monotonic()
    try:
        raw = sys.stdin.read()
    except Exception:  # unreadable stdin counts as an empty event; the hook still exits 0
        raw = ""
    reply = hooks.run_hook(raw)
    if reply is not None:
        sys.stdout.write(json.dumps(reply) + "\n")
        sys.stdout.flush()
    _log_event(raw, reply, started)
    return None


def _log_event(raw, reply, started):
    """One hook.event line: the hook name, allow or deny, and the milliseconds. A deny is WARN, an allow is DEBUG.
    Fail-open, one append only, and skipped when the time budget is nearly spent (as presence is)."""
    try:
        elapsed = time.monotonic() - started
        if hooks.PRE_TIMEOUT_S - elapsed < hooks.PRESENCE_MIN_BUDGET_S:
            return
        payload = json.loads(raw) if raw and raw.strip() else {}
        name = str(payload.get("hook_event_name") or "") if isinstance(payload, dict) else ""
        output = reply.get("hookSpecificOutput") if isinstance(reply, dict) else None
        denied = isinstance(output, dict) and output.get("permissionDecision") == "deny"
        roadmap_log.debug_event("hook", "WARN" if denied else "DEBUG", "hook.event", msg=name or "hook",
                                route="hook", sid="hook",
                                data={"hook": name, "decision": "deny" if denied else "allow",
                                      "ms": int(elapsed * 1000)})
    except Exception:
        pass
