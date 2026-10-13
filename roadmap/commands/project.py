"""Command group project: register projects and keep their data files healthy."""

from roadmap.errors import EXIT_INVALID_DATA, RoadmapError
from roadmap.services import projects


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
