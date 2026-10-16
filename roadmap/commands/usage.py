"""Command group usage: the global plan-usage store.

show, sync (runs the source chain: OAuth endpoint, status line sidecar, transcript estimate), push (JSON on stdin)
and statusline (a Claude Code status line command that stores the rate_limits it is handed; docs/USAGE-SOURCES.md).
"""

import json
import subprocess
import sys

from roadmap.errors import EXIT_EXTERNAL, RoadmapError
from roadmap.services import usage
from roadmap.store import config as config_store


def register(sub, common):
    """Add the usage group and its actions."""
    group = sub.add_parser("usage", parents=[common], help="plan usage (weekly and five-hour limits)")
    actions = group.add_subparsers(dest="action", metavar="ACTION", required=True)
    actions.add_parser("show", parents=[common], help="show the stored usage").set_defaults(handler=handle_show)
    actions.add_parser("sync", parents=[common], help="fetch usage now").set_defaults(handler=handle_sync)
    push = actions.add_parser("push", parents=[common], help="store usage from JSON on stdin")
    push.set_defaults(handler=handle_push)
    line = actions.add_parser("statusline", parents=[common],
                              help="Claude Code status line: store its rate_limits, then print a status line")
    line.add_argument("--then", metavar="CMD", default=None,
                      help="status line command to run after storing (gets the same JSON on stdin; its output is shown)")
    line.set_defaults(handler=handle_statusline)


def _json_mode(args):
    return getattr(args, "json", False)


def _plain(value, suffix=""):
    return "n/a" if value is None else str(value) + suffix


def _text(result):
    usage_view = result["usage"]
    if usage_view.get("weeklyPercent") is None:
        line = "no usage stored yet"
    else:
        line = ("week %s (resets %s) | 5h %s (resets %s) | updated %s from %s"
                % (_plain(usage_view["weeklyPercent"], "%"), _plain(usage_view["weeklyResetsAt"]),
                   _plain(usage_view["fiveHourPercent"], "%"), _plain(usage_view["fiveHourResetsAt"]),
                   _plain(usage_view["updated"]), _plain(usage_view["source"])))
    if usage_view["stale"]:
        line += " | STALE"
    if usage_view.get("lastError"):
        line += " | last error: " + usage_view["lastError"]
    return line


def _emit_text(args, result):
    if not _json_mode(args):
        print(_text(result))


def handle_show(args):
    """Return the stored usage with its stale flag."""
    result = {"usage": usage.show()}
    _emit_text(args, result)
    return result


def handle_sync(args):
    """Read usage from the keychain and the endpoint now. A failed read exits 6 and keeps the last good values."""
    try:
        result = usage.sync_once(config_store.load())
    except usage.UsageError as exc:
        raise RoadmapError("external", "could not read usage: " + str(exc), EXIT_EXTERNAL)
    _emit_text(args, result)
    return result


def handle_push(args):
    """Store usage given as {"rateLimits": [...]} JSON on stdin."""
    result = usage.push(sys.stdin.read(), config_store.load())
    _emit_text(args, result)
    return result


STATUSLINE_MAX_BYTES = 1_000_000
THEN_TIMEOUT_S = 5


def _short_line(payload):
    limits = usage.parse_rate_limits(payload.get("rate_limits") if isinstance(payload, dict) else None)
    parts = []
    if limits.get("fiveHourPercent") is not None:
        parts.append("5h %s%%" % limits["fiveHourPercent"])
    if limits.get("weeklyPercent") is not None:
        parts.append("week %s%%" % limits["weeklyPercent"])
    return " | ".join(parts)


def handle_statusline(args):
    """Claude Code runs this as its status line with the session JSON on stdin. The rate_limits block is stored (at
    most once a minute); then the wrapped --then command gets the same stdin and its output is printed, or a short
    usage line when there is none. Never fails: a status line must always print something."""
    raw = sys.stdin.read(STATUSLINE_MAX_BYTES)
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except ValueError:
        payload = {}
    try:
        usage.auto_update(payload if isinstance(payload, dict) else {}, source=usage.SOURCE_STATUSLINE)
    except Exception:  # storing is best effort; the status line itself must still show
        pass
    if args.then:
        try:
            proc = subprocess.run(args.then, shell=True, input=raw, capture_output=True, text=True,
                                  timeout=THEN_TIMEOUT_S)
            sys.stdout.write(proc.stdout)
        except (subprocess.TimeoutExpired, OSError):
            pass
        return None
    print(_short_line(payload))
    return None
