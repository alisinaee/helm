"""Command group usage: the global plan-usage store.

show, sync (runs the source chain: OAuth endpoint, status line sidecar, transcript estimate), push (JSON on stdin)
and statusline (a Claude Code status line command that stores the rate_limits it is handed; docs/USAGE-SOURCES.md).
"""

import json
import subprocess
import sys

from roadmap.commands import usage_accounts as usage_accounts_cmd
from roadmap.errors import EXIT_EXTERNAL, RoadmapError
from roadmap.services import limits_v2, usage
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
    actions.add_parser("stops", parents=[common], help="show the effective stops (5h and week)"
                       ).set_defaults(handler=handle_stops)
    stop = actions.add_parser("stop", parents=[common], help="set the 5h or week stop (budget or cap)")
    stop.add_argument("--window", required=True, choices=sorted(WINDOW_WORDS), help="5h, week or weekly")
    stop.add_argument("--mode", choices=limits_v2.MODES, default=None,
                      help="budget (use at most VALUE%% more from now) or cap (stop at VALUE%%)")
    stop.add_argument("--value", type=float, default=None, help="percent 1..100")
    stop.add_argument("--once", action="store_true", help="a budget that does not repeat on the window reset")
    stop.add_argument("--off", action="store_true", help="switch the stop off")
    stop.set_defaults(handler=handle_stop)
    usage_accounts_cmd.register(actions, common)


WINDOW_WORDS = {"5h": "five_hour", "five_hour": "five_hour", "week": "week", "weekly": "week"}


def _stops_text(info):
    lines = []
    for window in limits_v2.WINDOWS:
        row = info[window]
        pct = "n/a" if row["percent"] is None else "%g%%" % row["percent"]
        if row["stop"] is None:
            lines.append("%-9s %s, stop off" % (window, pct))
        else:
            how = ("budget +%g%% from %g%%" % (row["value"], row["base"])) if row["mode"] == "budget" else "cap"
            lines.append("%-9s %s, stop at %g%% (%s)" % (window, pct, row["stop"], how))
    return "\n".join(lines)


def handle_stops(args):
    """Print the effective stop of each window."""
    info = limits_v2.stops()
    if not _json_mode(args):
        print(_stops_text(info))
    return {"windows": info}


def handle_stop(args):
    """Set one window: --mode and --value turn it on; --off turns it off."""
    window = WINDOW_WORDS[args.window]
    patch = {"on": False} if args.off else {"on": True}
    if args.mode:
        patch["mode"] = args.mode
    if args.value is not None:
        patch["value"] = args.value
    if args.once:
        patch["once"] = True
    limits_v2.set_window(window, patch)
    return handle_stops(args)


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
        result = usage.sync_all(config_store.load())
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
    try:
        if any(info["on"] for info in limits_v2.load().values()):
            parts.append("stops: " + limits_v2.brief_line())
    except Exception:  # the status line must always print
        pass
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
