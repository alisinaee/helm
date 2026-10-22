"""Command group service: the background server (WP11). On macOS it is a launchd agent (services/launchd), on Linux a
systemd --user unit (services/systemd). backend() picks one at call time, from sys.platform.

install writes the plist (launchd) or unit (systemd) and loads it; uninstall unloads it and removes the file (logs and
config stay). start, stop, restart and status use the backend's lifecycle calls. logs prints the tail of server.log,
and -f follows it. Every command takes --json. The backend's runner is looked up at call time too.
"""

import os
import sys

from roadmap.log import SERVER_LOG
from roadmap.services import launchd, systemd
from roadmap.store import paths

LOG_TAIL_LINES = 100


def backend():
    """The service backend for this platform: launchd on macOS, systemd --user elsewhere. Read at call time."""
    return launchd if sys.platform == "darwin" else systemd


def register(sub, common):
    """Add the service group and its actions."""
    group = sub.add_parser("service", parents=[common], help="manage the background service")
    actions = group.add_subparsers(dest="action", metavar="ACTION", required=True)
    for name, text in (
        ("install", "install the background service (launchd on macOS, systemd --user on Linux)"),
        ("uninstall", "remove the background service (launchd agent or systemd unit)"),
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
    path = backend().install()
    state = backend().status()
    if not _wants_json(args):
        print("installed " + path + (" and loaded it" if state["loaded"] else ""))
    return {"plist": path, "loaded": state["loaded"]}


def _uninstall(args):
    svc = backend()
    removed = svc.uninstall()
    path = svc.plist_path()
    if not _wants_json(args):
        print(("removed " + path) if removed else "nothing to remove (no plist at " + path + ")")
    return {"plist": path, "removed": removed}


PAST = {"start": "started", "stop": "stopped", "restart": "restarted"}


def _acting(verb):
    def handler(args):
        svc = backend()
        if verb == "restart" and getattr(args, "if_stale", False):
            check = svc.stale()
            if not check["stale"]:
                state = svc.status()
                if not _wants_json(args):
                    print("skipped: no change under web/, roadmap/http/ or roadmap/services/ since the service "
                          "started (pid " + str(check["pid"]) + ")")
                return {"action": "restart", "skipped": True, "loaded": state["loaded"], "pid": state["pid"]}
        getattr(svc, verb)()
        state = svc.status()
        if not _wants_json(args):
            print("service " + PAST[verb] + (" (loaded)" if state["loaded"] else " (not loaded)"))
        return {"action": verb, "loaded": state["loaded"], "pid": state["pid"]}

    return handler


def _status(args):
    svc = backend()
    state = svc.status()
    check = svc.stale() if state["loaded"] else {"stale": False}
    state["stale"] = check["stale"]
    if not _wants_json(args):
        unit_word = "unit" if svc is systemd else "plist"
        print("label    " + state["label"])
        print(unit_word.ljust(8) + " " + state["plist"]
              + (" (installed)" if state["plistInstalled"] else " (not installed)"))
        print("loaded   " + ("yes" if state["loaded"] else "no"))
        if state["loaded"]:
            print("state    " + str(state["state"]) + ", pid " + str(state["pid"])
                  + ", last exit " + str(state["lastExitCode"]))
            if check["stale"]:
                print("RESTART NEEDED: web/, roadmap/http/ or roadmap/services/ changed since this process "
                      "started. Run: roadmap service restart")
    return state


def _logs(args):
    svc = backend()
    path = os.path.join(paths.logs_dir(), SERVER_LOG)
    if getattr(args, "follow", False):
        _follow(path)
        return None
    lines = svc.tail_lines(path, LOG_TAIL_LINES)
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
        backend().follow(path, emit, should_stop=lambda: False)
    except KeyboardInterrupt:
        return


_HANDLERS = {
    "install": _install,
    "uninstall": _uninstall,
    "start": _acting("start"),
    "stop": _acting("stop"),
    "restart": _acting("restart"),
    "status": _status,
    "logs": _logs,
}
