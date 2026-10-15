"""Command logs: the debug event log (R7.16), read through roadmap.log.

roadmap logs                 the last 20 WARN and ERROR events, one line each
roadmap logs summary         counts by event, top errors, sessions, time span (at most 15 lines)
roadmap logs marks           the person's Mark events, newest first, with route and ref (at most 10)
roadmap logs status          the switch, the files and the caps; --on or --off switches logging

Filters: --since 10m|2h|1d, --src ui|core|hook, --ev NAME, --ref rb:..., --session last|<sid>, --level, --limit N
(cap 100). --json prints the {ok, data} envelope. Nothing is sent anywhere: the log stays on this machine.
"""

import collections
import datetime
import re

from roadmap import log as roadmap_log
from roadmap.errors import EXIT_ERROR, EXIT_USAGE, RoadmapError

DEFAULT_LEVEL = "WARN"
DEFAULT_LIMIT = 20
LIMIT_CAP = 100
MARKS_MAX = 10
TOP_ERRORS = 5
MSG_SHOWN = 80
SINCE = re.compile(r"^([1-9][0-9]{0,4})([mhd])$")
UNITS = {"m": 60, "h": 3600, "d": 86400}
VIEWS = ("summary", "marks", "status")
ERROR_LEVELS = ("WARN", "ERROR")


def register(sub, common):
    """Add the logs command. The view is a positional word, so one parser serves every view."""
    parser = sub.add_parser("logs", parents=[common],
                            help="debug event log: recent warnings and errors, summary, marks, status")
    parser.add_argument("view", nargs="?", choices=VIEWS, default=None,
                        help="summary | marks | status (default: the last WARN and ERROR events)")
    parser.add_argument("--since", default=None, metavar="10m|2h|1d", help="only events newer than this")
    parser.add_argument("--src", choices=roadmap_log.SOURCES, default=None, help="ui, core or hook")
    parser.add_argument("--ev", default=None, metavar="NAME", help="one event name, for example ui.error")
    parser.add_argument("--ref", default=None, metavar="rb:...", help="one project/kind/id reference")
    parser.add_argument("--session", default=None, metavar="last|SID", help="one session id, or the newest one")
    parser.add_argument("--level", choices=("DEBUG", "INFO", "WARN", "ERROR"), default=None,
                        help="the lowest level shown (default WARN)")
    parser.add_argument("--limit", type=int, default=None, metavar="N", help="newest N events (cap 100)")
    switch = parser.add_mutually_exclusive_group()
    switch.add_argument("--on", action="store_true", help="status: turn the debug log on")
    switch.add_argument("--off", action="store_true", help="status: turn the debug log off")
    parser.set_defaults(handler=_run)


def _run(args):
    """Print the view's lines, or return its data for the --json envelope."""
    views = {"summary": _summary, "marks": _marks, "status": _status}
    lines, data = views.get(args.view, _tail)(args)
    if getattr(args, "json", False):
        return data
    for line in lines:
        print(line)
    return None


def _size(count):
    if count < 1024:
        return "%d B" % count
    if count < 1024 * 1024:
        return "%.1f KB" % (count / 1024.0)
    return "%.1f MB" % (count / (1024.0 * 1024.0))


def _since(text):
    """A cutoff datetime for 10m, 2h or 1d; None when no value was given."""
    if text is None:
        return None
    match = SINCE.match(str(text).strip())
    if match is None:
        raise RoadmapError("usage", "--since takes 10m, 2h or 1d, not '" + str(text) + "'", EXIT_USAGE,
                           next="roadmap logs --since 1h")
    seconds = int(match.group(1)) * UNITS[match.group(2)]
    return datetime.datetime.now().astimezone() - datetime.timedelta(seconds=seconds)


def _limit(value, default):
    if value is None:
        return default
    if value < 1:
        raise RoadmapError("usage", "--limit takes a number from 1 to 100", EXIT_USAGE, next="roadmap logs --limit 20")
    return min(value, LIMIT_CAP)


def _query(args, level, limit, ev=None):
    """Matching events, oldest first. --session last resolves to the session of the newest event in range."""
    since = _since(args.since)
    session = args.session
    if session == "last":
        newest = roadmap_log.read_events(since=since, limit=1)
        if not newest:
            return []
        session = newest[-1].get("sid")
    return roadmap_log.read_events(since=since, src=args.src, ev=ev if ev is not None else args.ev,
                                   ref=args.ref, session=session, level_min=level, limit=limit)


def _short(text, limit=MSG_SHOWN):
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def _clock(rec):
    ts = rec.get("ts")
    return str(ts)[11:19] if isinstance(ts, str) and len(ts) >= 19 else "--:--:--"


def _line(rec):
    """One event as hh:mm:ss src ev route ref msg. Missing route or ref shows as a dash."""
    parts = [_clock(rec), str(rec.get("src") or "-"), str(rec.get("ev") or "-"), str(rec.get("route") or "-"),
             str(rec.get("ref") or "-"), _short(rec.get("msg"))]
    return " ".join(parts).rstrip()


def _empty_hint():
    """The one line for an empty result: enable and reproduce when the log is off or empty, else widen the filter."""
    info = roadmap_log.log_status()
    if not info.get("enabled", True):
        return "logs: empty and logging is off. next: roadmap logs status --on, then reproduce the bug"
    if not info.get("total_bytes"):
        return "logs: empty. next: reproduce the bug in the UI, then roadmap logs"
    return "logs: no matching events in range. next: roadmap logs summary"


def _tail(args):
    level = args.level or DEFAULT_LEVEL
    limit = _limit(args.limit, DEFAULT_LIMIT)
    events = _query(args, level, limit)
    data = {"events": events, "level": level, "count": len(events)}
    if not events:
        return [_empty_hint()], data
    last_session = events[-1].get("sid")
    lines = [_line(rec) for rec in events]
    lines.append("next: roadmap logs marks | roadmap logs --session %s" % (last_session or "last"))
    return lines, data


def _errors(events):
    """Top WARN and ERROR messages as (count, event, message, last time), most frequent first."""
    counts, last = collections.Counter(), {}
    for rec in events:
        if rec.get("lvl") not in ERROR_LEVELS:
            continue
        key = (str(rec.get("ev")), _short(rec.get("msg"), 60))
        counts[key] += 1
        last[key] = _clock(rec)
    return [(n, key[0], key[1], last[key]) for key, n in counts.most_common(TOP_ERRORS)]


def _summary(args):
    events = _query(args, None, None)
    if not events:
        return [_empty_hint()], {"count": 0}
    by_ev = collections.Counter(str(rec.get("ev")) for rec in events)
    sessions = {str(rec.get("sid")) for rec in events}
    errors = _errors(events)
    marks = sum(1 for rec in events if rec.get("ev") == "ui.mark")
    first, last = _clock(events[0]), _clock(events[-1])
    top = sorted(by_ev.items(), key=lambda item: (-item[1], item[0]))[:8]
    lines = ["logs: %d events, %s to %s" % (len(events), first, last),
             "by ev: " + ", ".join("%s %d" % (name, n) for name, n in top),
             "sessions: %d seen, last %s" % (len(sessions), events[-1].get("sid") or "-")]
    if errors:
        lines.append("top warnings and errors:")
        lines += ["  %dx %s %s (last %s)" % (n, ev, msg, when) for n, ev, msg, when in errors]
    else:
        lines.append("warnings and errors: none")
    lines.append("marks: %d (roadmap logs marks)" % marks)
    lines.append("next: roadmap logs marks | roadmap logs --session %s" % (events[-1].get("sid") or "last"))
    data = {"count": len(events), "by_ev": dict(by_ev), "sessions": len(sessions), "marks": marks,
            "first": first, "last": last,
            "errors": [{"count": n, "ev": ev, "msg": msg, "last": when} for n, ev, msg, when in errors]}
    return lines, data


def _marks(args):
    limit = min(_limit(args.limit, MARKS_MAX), MARKS_MAX)
    events = list(reversed(_query(args, None, None, ev="ui.mark")))[:limit]
    data = {"marks": events, "count": len(events)}
    if not events:
        return ["marks: none. next: press m in the UI at the moment of the bug, or roadmap logs summary"], data
    lines = ["%s %s %s %s" % (_clock(rec), rec.get("route") or "-", rec.get("ref") or "-", _short(rec.get("msg")))
             for rec in events]
    lines = [line.rstrip() for line in lines]
    lines.append("next: roadmap logs --session %s --since %s" % (events[0].get("sid") or "last", args.since or "1d"))
    return lines, data


def _status(args):
    if args.on or args.off:
        if not roadmap_log.set_enabled(bool(args.on)):
            raise RoadmapError("io", "could not save the logging switch", EXIT_ERROR, next="roadmap logs status")
    info = roadmap_log.log_status()
    if info.get("error"):
        raise RoadmapError("io", "could not read the log folder", EXIT_ERROR, next="roadmap logs summary")
    on = bool(info.get("enabled"))
    files = info.get("files") or {}
    names = ", ".join("%s %s" % (name, _size(size)) for name, size in sorted(files.items()))
    lines = ["logs: %s, level %s" % ("on" if on else "off", "DEBUG" if info.get("debug") else "INFO and up"),
             "dir: " + str(info.get("dir")),
             "files: " + (names or "none"),
             "total: %s of %s cap" % (_size(info.get("total_bytes", 0)), _size(info.get("cap_bytes", 0)))]
    if on:
        lines.append("next: roadmap logs summary | roadmap logs --off to stop")
    else:
        lines.append("next: roadmap logs status --on, then reproduce the bug")
    return lines, dict(info)
