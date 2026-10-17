"""Command group service: the launchd lifecycle of the background server (WP11).

install writes the plist and loads it; uninstall unloads it and removes the plist (logs and config stay). start,
stop, restart and status use launchctl through services/launchd. logs prints the tail of server.log, and -f follows
it. Every command takes --json. The launchctl runner is looked up in services/launchd at call time.
"""

import os

from roadmap.log import SERVER_LOG
from roadmap.services import launchd
from roadmap.store import paths

LOG_TAIL_LINES = 100


def register(sub, common):
    """Add the service group and its actions."""
    group = sub.add_parser("service", parents=[common], help="manage the background service")
    actions = group.add_subparsers(dest="action", metavar="ACTION", required=True)
    for name, text in (
        ("install", "install the launchd agent"),
        ("uninstall", "remove the launchd agent"),
        ("start", "start the service"),
        ("stop", "stop the service"),
        ("restart", "restart the service"),
        ("status", "show whether the service is loaded and answering"),
        ("logs", "show the service logs"),
    ):
        parser = actions.add_parser(name, parents=[common], help=text)
        if name == "logs":
            parser.add_argument("-f", "--follow", action="store_true", help="keep printing new lines")
        if name == "restart":
            parser.add_argument("--if-stale", action="store_true",
                                 help="only restart when web/, roadmap/http/ or roadmap/services/ changed since "
                                      "the running process started (skip otherwise)")
        parser.set_defaults(handler=_HANDLERS[name])


def _wants_json(args):
    return getattr(args, "json", False)


def _install(args):
    path = launchd.install()
    state = launchd.status()
    if not _wants_json(args):
        print("installed " + path + (" and loaded it" if state["loaded"] else ""))
    return {"plist": path, "loaded": state["loaded"]}


def _uninstall(args):
    removed = launchd.uninstall()
    path = launchd.plist_path()
    if not _wants_json(args):
        print(("removed " + path) if removed else "nothing to remove (no plist at " + path + ")")
    return {"plist": path, "removed": removed}


PAST = {"start": "started", "stop": "stopped", "restart": "restarted"}


def _acting(verb, call):
    def handler(args):
        if verb == "restart" and getattr(args, "if_stale", False):
            check = launchd.stale()
            if not check["stale"]:
                state = launchd.status()
                if not _wants_json(args):
                    print("skipped: no change under web/, roadmap/http/ or roadmap/services/ since the service "
                          "started (pid " + str(check["pid"]) + ")")
                return {"action": "restart", "skipped": True, "loaded": state["loaded"], "pid": state["pid"]}
        call()
        state = launchd.status()
        if not _wants_json(args):
            print("service " + PAST[verb] + (" (loaded)" if state["loaded"] else " (not loaded)"))
        return {"action": verb, "loaded": state["loaded"], "pid": state["pid"]}

    return handler


def _status(args):
    state = launchd.status()
    check = launchd.stale() if state["loaded"] else {"stale": False}
    state["stale"] = check["stale"]
    if not _wants_json(args):
        print("label    " + state["label"])
        print("plist    " + state["plist"] + (" (installed)" if state["plistInstalled"] else " (not installed)"))
        print("loaded   " + ("yes" if state["loaded"] else "no"))
        if state["loaded"]:
            print("state    " + str(state["state"]) + ", pid " + str(state["pid"])
                  + ", last exit " + str(state["lastExitCode"]))
            if check["stale"]:
                print("RESTART NEEDED: web/, roadmap/http/ or roadmap/services/ changed since this process "
                      "started. Run: roadmap service restart")
    return state


def _logs(args):
    path = os.path.join(paths.logs_dir(), SERVER_LOG)
    if getattr(args, "follow", False):
        _follow(path)
        return None
    lines = launchd.tail_lines(path, LOG_TAIL_LINES)
    if not _wants_json(args):
        for line in lines:
            print(line)
        if not lines:
            print("no log lines yet (" + path + ")")
    return {"path": path, "lines": lines}


def _follow(path):
    def emit(line):
        print(line, flush=True)

    try:
        launchd.follow(path, emit, should_stop=lambda: False)
    except KeyboardInterrupt:
        return


_HANDLERS = {
    "install": _install,
    "uninstall": _uninstall,
    "start": _acting("start", launchd.start),
    "stop": _acting("stop", launchd.stop),
    "restart": _acting("restart", launchd.restart),
    "status": _status,
    "logs": _logs,
}
