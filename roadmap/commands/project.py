"""Command group project: register projects and keep their data files healthy."""

import argparse
import json
import os

from roadmap.commands import research
from roadmap.errors import EXIT_INVALID_DATA, RoadmapError
from roadmap.services import projects
from roadmap.store import config, lock, schema

PLAN_TEMPLATE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates",
                             "plan_template.json")
FIRST_NOTE = ("scope", "Project scope and first questions")


def register(sub, common):
    """Add the project group and its actions."""
    group = sub.add_parser("project", parents=[common], help="register and maintain projects")
    actions = group.add_subparsers(dest="action", metavar="ACTION", required=True)

    add = actions.add_parser("add", parents=[common], help="register a project folder")
    add.add_argument("path", help="project folder")
    add.add_argument("--name", help="display name (default: the folder name)")
    add.add_argument("--data-dir", default="docs", help="folder inside the project that holds the data files")
    add.set_defaults(handler=_add)

    listing = actions.add_parser("list", parents=[common], help="list registered projects")
    listing.set_defaults(handler=_list)

    show = actions.add_parser("show", parents=[common], help="show one project")
    show.add_argument("id", help="project id")
    show.set_defaults(handler=_show)

    init = actions.add_parser("init", parents=[common], help="write template data files into a project folder")
    init.add_argument("path", help="project folder")
    init.set_defaults(handler=_init)

    remove = actions.add_parser("remove", parents=[common], help="unregister a project (files are kept)")
    remove.add_argument("id", help="project id")
    remove.set_defaults(handler=_remove)

    check = actions.add_parser("check", parents=[common], help="check that a project's files parse")
    check.add_argument("id", nargs="?", help="project id (default: all)")
    check.set_defaults(handler=_check)

    migrate = actions.add_parser("migrate", parents=[common], help="upgrade a project's data files (backs up first)")
    migrate.add_argument("id", help="project id")
    migrate.set_defaults(handler=_migrate)

    new = actions.add_parser("new", parents=[common],
                             help="start a project: init, plan with phase P1 not approved, optional research note 1")
    new.add_argument("path", help="project folder (must exist)")
    new.add_argument("--name", help="display name (default: the folder name)")
    new.add_argument("--research", action="store_true", help="also create research note 01 from the template")
    new.set_defaults(handler=_new)


def _wants_json(args):
    return getattr(args, "json", False)


def _add(args):
    entry = projects.add_project(args.path, args.name, args.data_dir)
    if not _wants_json(args):
        print("added " + entry["id"] + " -> " + entry["path"])
        return None
    return {"project": entry}


def _list(args):
    rows = projects.list_projects()
    if not _wants_json(args):
        if not rows:
            print("no projects")
        for row in rows:
            print("%-16s %s %s" % (row["id"], row["name"], row["path"]))
        return None
    return {"projects": rows}


def _show(args):
    row = projects.show_project(args.id)
    if not _wants_json(args):
        for key in ("id", "name", "path", "dataPath", "pathExists", "addedAt"):
            print("%s: %s" % (key, row.get(key)))
        return None
    return {"project": row}


def _init(args):
    result = projects.init_project(args.path)
    if not _wants_json(args):
        print("created: " + (", ".join(result["created"]) or "nothing"))
        print("kept: " + (", ".join(result["kept"]) or "nothing"))
        return None
    return result


def _remove(args):
    entry = projects.remove_project(args.id)
    if not _wants_json(args):
        print("removed " + entry["id"] + "; its files were kept")
        return None
    return {"removed": entry}


def _check(args):
    reports = projects.check_projects(args.id)
    bad = [r for r in reports if not r["ok"]]
    if not _wants_json(args):
        for report in reports:
            print("%s (%s)" % (report["id"], report["dataPath"]))
            for row in report["files"]:
                detail = row["error"] or (("schema " + str(row["schemaVersion"])) if row["schemaVersion"] else "")
                print("  %-22s %-8s %s" % (row["file"], row["status"], detail))
    if bad:
        raise RoadmapError("invalid_data", _summary(bad), EXIT_INVALID_DATA)
    return {"projects": reports, "ok": True}


def _summary(bad):
    parts = []
    for report in bad:
        for row in report["files"]:
            if row["status"] == "error":
                parts.append(report["id"] + "/" + row["file"] + ": " + row["error"])
    return "; ".join(parts) + ". Fix the file, then run: roadmap project check"


def _migrate(args):
    result = projects.migrate_project(args.id)
    if not _wants_json(args):
        if not result["migrated"]:
            print("nothing to migrate; no backup made")
        for row in result["migrated"]:
            print("migrated %s: schema %s -> %s" % (row["file"], row["from"], row["to"]))
        if result["backup"]:
            print("backup: " + result["backup"])
        return None
    return result


def _new(args):
    """Init the folder, register it, write the plan template (phase P1, approved false) into a tasks.json that has no
    phases or tasks yet, and with --research create note 01. Safe to run again: existing files, notes and the
    registration are kept."""
    init, entry = projects.new_project(args.path, args.name)
    plan = _write_plan_template(init["dataDir"])
    note = _first_note(entry["id"], init["dataDir"]) if args.research else None
    if not _wants_json(args):
        print("registered " + entry["id"] + " -> " + entry["path"])
        print("created: " + (", ".join(init["created"]) or "nothing"))
        print("plan: " + ("phase P1 written, not approved" if plan["written"] else "kept (tasks.json has phases)"))
        if args.research:
            print("research: " + (note["file"] if note else "kept (a note exists)"))
        print("next: read the research, then approve phase P1 with: roadmap phase approve P1")
        return None
    return {"project": entry, "created": init["created"], "kept": init["kept"], "plan": plan, "research": note}


def _write_plan_template(data_dir):
    """Write the plan template when tasks.json holds no phases and no tasks yet. Returns {phase, approved, written}."""
    path = os.path.join(data_dir, "tasks.json")
    with lock.locked(data_dir):
        current, error = schema.read_data("tasks", path)
        if error is not None:
            raise RoadmapError("newer_schema", error["message"], EXIT_INVALID_DATA)
        if current and (current.get("phases") or current.get("tasks")):
            return {"phase": None, "approved": None, "written": False}
        with open(PLAN_TEMPLATE, "r", encoding="utf-8") as fh:
            body = json.load(fh)
        schema.write_data("tasks", path, body)
    return {"phase": "P1", "approved": False, "written": True}


def _first_note(project_id, data_dir):
    """Create research note 01 unless a note exists. Returns the note's data, or None when one exists."""
    folder = os.path.join(data_dir, research.RESEARCH_DIR)
    if research._notes(folder):
        return None
    slug, title = FIRST_NOTE
    return research._new(argparse.Namespace(project=project_id, slug=slug, title=title, json=True))
