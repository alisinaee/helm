"""Command init: set a project up in one idempotent step (register, empty board, hooks, service)."""

import os

from roadmap.services import hooks_install, launchd, projects
from roadmap.store import atomic, config, lock, schema


def register(sub, common):
    """Add the init command."""
    parser = sub.add_parser("init", parents=[common], help="set a project up: register, hooks, service")
    parser.add_argument("path", nargs="?", default=".", help="project folder (default: the current folder)")
    parser.add_argument("--name", help="display name (default: the folder name)")
    parser.add_argument("--no-service", action="store_true", help="do not install or start the launchd service")
    parser.set_defaults(handler=_init)


def _empty_board(init):
    """A fresh project gets no template phase; work.json is created empty when missing."""
    data_dir = init["dataDir"]
    with lock.locked(data_dir):
        if "tasks.json" in init["created"]:
            schema.write_data("tasks", os.path.join(data_dir, "tasks.json"),
                              {"schemaVersion": 1, "updated": "", "phases": [], "tasks": []})
        work = os.path.join(data_dir, "work.json")
        if not os.path.exists(work):
            atomic.write_json(work, {"schemaVersion": 1, "items": [], "links": {}, "events": []})


def _service():
    state = launchd.status()
    if not state["plistInstalled"]:
        launchd.install()
        state = launchd.status()
    if not state["loaded"]:
        launchd.start()
        state = launchd.status()
    return {"installed": state["plistInstalled"], "running": bool(state["loaded"])}


def _init(args):
    init, entry = projects.new_project(args.path, args.name)
    _empty_board(init)
    hooks = hooks_install.install(entry["id"], False)
    service = None if args.no_service else _service()
    port = config.load().get("port", 8780)
    url = "http://localhost:%s/#%s" % (port, entry["id"])
    result = {"id": entry["id"], "path": entry["path"], "url": url, "port": port, "created": init["created"],
              "hooksChanged": hooks["changed"], "service": service}
    if getattr(args, "json", False):
        return result
    if service is not None:
        print("service: " + ("running on :%s" % port if service["running"] else "not running"))
    print("ready: %s %s" % (entry["id"], url))
    return None
