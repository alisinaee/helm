"""Command group skills: list the Haiku-sized skill templates and install them into <project>/.claude/skills.

Templates live in roadmap/templates/skills/<name>/. Install never overwrites silently: an existing skill folder is
renamed to <name>.bak-<timestamp> and only replaced with --yes. Without --yes a conflict exits 4 and writes nothing.
"""

import datetime
import os
import shutil

from roadmap.errors import EXIT_CONFLICT, EXIT_NOT_FOUND, EXIT_USAGE, RoadmapError
from roadmap.services import jobs

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates", "skills")
SKILL_SUBDIR = os.path.join(".claude", "skills")
MAX_BYTES = 3200
ENTRY = "SKILL.md"


def register(sub, common):
    """Add the skills group and its actions."""
    group = sub.add_parser("skills", parents=[common], help="list or install the agent skill templates")
    actions = group.add_subparsers(dest="action", metavar="ACTION", required=True)

    listing = actions.add_parser("list", parents=[common], help="list the skill templates, sizes and install state")
    listing.add_argument("--project", metavar="ID", default=None,
                         help="project id (default: $ROADMAP_PROJECT, then the registered project of this folder)")
    listing.set_defaults(handler=_list)

    install = actions.add_parser("install", parents=[common],
                                 help="copy the skills into <project>/.claude/skills")
    install.add_argument("--project", metavar="ID", default=None,
                         help="project id (default: $ROADMAP_PROJECT, then the registered project of this folder)")
    install.add_argument("--target", metavar="DIR", default=None,
                         help="install into this project folder instead of a registered project")
    install.add_argument("--yes", action="store_true",
                         help="back up existing skill folders as <name>.bak-<timestamp> and replace them")
    install.add_argument("--dry-run", action="store_true", help="show what would change, write nothing")
    install.set_defaults(handler=_install)


def templates():
    """(name, folder) for every template folder that holds a SKILL.md, sorted by name."""
    rows = []
    if os.path.isdir(TEMPLATE_DIR):
        for name in sorted(os.listdir(TEMPLATE_DIR)):
            folder = os.path.join(TEMPLATE_DIR, name)
            if os.path.isfile(os.path.join(folder, ENTRY)):
                rows.append((name, folder))
    return rows


def _root(args):
    """(project id or None, project folder or None) for the call. Without a project, list still works."""
    if getattr(args, "target", None) and getattr(args, "project", None):
        raise RoadmapError("usage", "use --project or --target, not both", EXIT_USAGE)
    if getattr(args, "target", None):
        root = os.path.realpath(os.path.expanduser(args.target))
        if not os.path.isdir(root):
            raise RoadmapError("not_found", "no folder at " + root, EXIT_NOT_FOUND)
        return None, root
    entry = jobs.resolve_project(getattr(args, "project", None))
    return entry["id"], os.path.realpath(entry["path"])


def _root_or_none(args):
    try:
        return _root(args)
    except RoadmapError:
        return None, None


def _list(args):
    project_id, root = _root_or_none(args)
    rows = []
    for name, folder in templates():
        row = {"name": name, "bytes": os.path.getsize(os.path.join(folder, ENTRY)), "max_bytes": MAX_BYTES}
        row["installed"] = None if root is None else os.path.isdir(os.path.join(root, SKILL_SUBDIR, name))
        rows.append(row)
    if not getattr(args, "json", False):
        for row in rows:
            state = {None: "no project", True: "installed", False: "not installed"}[row["installed"]]
            print("%-16s %5d bytes  %s" % (row["name"], row["bytes"], state))
        return None
    return {"project": project_id, "skills": rows}


def _backup_name(dest, stamp, taken):
    """A backup path next to dest that is not taken yet: <dest>.bak-<stamp>, then -2, -3 and so on."""
    candidate = dest + ".bak-" + stamp
    number = 2
    while os.path.lexists(candidate) or candidate in taken:
        candidate = dest + ".bak-" + stamp + "-" + str(number)
        number += 1
    return candidate


def _plan(root, stamp, yes):
    """One row per template: where it goes, and whether it is created, replaced or a conflict."""
    rows = []
    taken = set()
    for name, folder in templates():
        dest = os.path.join(root, SKILL_SUBDIR, name)
        row = {"name": name, "src": folder, "dest": dest, "backup": None}
        if not os.path.lexists(dest):
            row["action"] = "create"
        elif yes:
            row["action"] = "replace"
            row["backup"] = _backup_name(dest, stamp, taken)
            taken.add(row["backup"])
        else:
            row["action"] = "conflict"
        rows.append(row)
    return rows


def _copy(src, dest):
    os.makedirs(dest, exist_ok=True)
    for fname in sorted(os.listdir(src)):
        path = os.path.join(src, fname)
        if os.path.isfile(path):
            shutil.copyfile(path, os.path.join(dest, fname))


def _install(args):
    project_id, root = _root(args)
    if not templates():
        raise RoadmapError("not_found", "no skill templates are packaged in " + TEMPLATE_DIR, EXIT_NOT_FOUND)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    rows = _plan(root, stamp, args.yes)
    conflicts = [row["name"] for row in rows if row["action"] == "conflict"]
    if conflicts and not args.dry_run and not args.yes:
        raise RoadmapError("conflict", "already installed, nothing written: " + ", ".join(conflicts)
                           + " (add --yes to back them up and replace)", EXIT_CONFLICT,
                           next="roadmap skills install --yes" + _target_flag(args, root))
    if not args.dry_run:
        for row in rows:
            if row["action"] == "replace":
                os.rename(row["dest"], row["backup"])
            if row["action"] in ("create", "replace"):
                _copy(row["src"], row["dest"])
    if not getattr(args, "json", False):
        prefix = "would " if args.dry_run else ""
        for row in rows:
            if row["action"] == "conflict":
                print("conflict: %s exists (not written; add --yes)" % row["dest"])
                continue
            if row["backup"]:
                print("%sbackup: %s -> %s" % (prefix, row["dest"], row["backup"]))
            print("%s%s: %s" % (prefix, row["action"], row["dest"]))
        if args.dry_run:
            print("dry run: nothing written")
        return None
    return {"project": project_id, "root": root, "dry_run": bool(args.dry_run), "skills": [
        {"name": row["name"], "dest": row["dest"], "action": row["action"], "backup": row["backup"]} for row in rows]}


def _target_flag(args, root):
    if getattr(args, "target", None):
        return " --target " + root
    if getattr(args, "project", None):
        return " --project " + args.project
    return ""
