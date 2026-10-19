"""Command init: set a project up in one idempotent step (register, empty board, hooks, service)."""

import os
import shutil

from roadmap.services import hooks_install, launchd, projects
from roadmap.store import atomic, config, lock, schema


def register(sub, common):
    """Add the init command."""
    parser = sub.add_parser("init", parents=[common], help="set a project up: register, hooks, service")
    parser.add_argument("path", nargs="?", default=".", help="project folder (default: the current folder)")
    parser.add_argument("--name", help="display name (default: the folder name)")
    parser.add_argument("--no-service", action="store_true", help="do not install or start the launchd service")
    parser.add_argument("--check", action="store_true", help="read-only: report what is set up, change nothing")
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


SKILL_TEMPLATE = os.path.join(projects.TEMPLATE_DIR, "skills", "helm", "SKILL.md")
SKILL_RELPATH = os.path.join(".claude", "skills", "helm", "SKILL.md")


def _install_skill(folder):
    """Copy the template skill into the project when it is missing. Never overwrites. True when copied."""
    target = os.path.join(folder, SKILL_RELPATH)
    if not os.path.isfile(SKILL_TEMPLATE) or os.path.exists(target):
        return False
    os.makedirs(os.path.dirname(target), exist_ok=True)
    shutil.copyfile(SKILL_TEMPLATE, target)
    return True


def _check(args):
    """Read-only report: registry entry, known board files, hook state and the project skill."""
    folder = os.path.abspath(os.path.expanduser(str(args.path)))
    entry = next((e for e in config.list_projects() if os.path.abspath(e["path"]) == folder), None)
    data_dir = os.path.join(folder, config.DEFAULT_DATA_DIR)
    known = [n for n, _ in projects.DATA_FILES + projects.LAZY_DATA_FILES] + ["work.json"]
    files = [n for n in known if os.path.isfile(os.path.join(data_dir, n))]
    hooks = "missing"
    if entry is not None:
        state = hooks_install.status(entry["id"])
        events = [row["state"] for row in state["events"].values()]
        hooks = "installed" if state["installed"] else "%d/%d installed" % (events.count("installed"), len(events))
    return {"registered": entry is not None, "id": entry["id"] if entry else None, "path": folder,
            "dataFiles": files, "hooks": hooks, "skill": os.path.isfile(os.path.join(folder, SKILL_RELPATH))}


def _init(args):
    if getattr(args, "check", False):
        result = _check(args)
        if getattr(args, "json", False):
            return result
        print("registered: %s (%s)" % ("yes" if result["registered"] else "no", result["id"] or "-"))
        print("data files: " + (", ".join(result["dataFiles"]) or "none"))
        print("hooks: %s; skill: %s" % (result["hooks"], "yes" if result["skill"] else "no"))
        return None
    init, entry = projects.new_project(args.path, args.name)
    _empty_board(init)
    hooks = hooks_install.install(entry["id"], False)
    skill = _install_skill(init["path"])
    service = None if args.no_service else _service()
    port = config.load().get("port", 8780)
    url = "http://localhost:%s/#/p/%s/overview" % (port, entry["id"])
    result = {"id": entry["id"], "path": entry["path"], "url": url, "port": port, "created": init["created"],
              "hooksChanged": hooks["changed"], "service": service,
              "skillInstalled": skill}
    if getattr(args, "json", False):
        return result
    if service is not None:
        print("service: " + ("running on :%s" % port if service["running"] else "not running"))
    print("ready: %s %s" % (entry["id"], url))
    return None
