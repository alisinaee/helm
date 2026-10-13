"""Top-level command backup: copies the data files of one or all projects into the state directory."""

from roadmap.services import projects


def register(sub, common):
    """Add the backup command to the root subparsers."""
    parser = sub.add_parser("backup", parents=[common], help="copy the data files to a timestamped backup")
    parser.add_argument("--project", help="project id (default: all projects)")
    parser.set_defaults(handler=_run)


def _run(args):
    rows = projects.backup_projects(args.project)
    if not getattr(args, "json", False):
        if not rows:
            print("no projects to back up")
        for row in rows:
            if row["status"] == "ok":
                print("%s: %s" % (row["project"], row["folder"]))
            else:
                print("%s: skipped (%s)" % (row["project"], row["reason"]))
        return None
    return {"backups": rows}
