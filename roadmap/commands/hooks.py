"""Command group hooks: install and inspect the Claude Code hooks of a project."""

from roadmap.services import agentguard, hooks_install


def register(sub, common):
    """Add the hooks group and its actions."""
    group = sub.add_parser("hooks", parents=[common], help="install or inspect project hooks")
    actions = group.add_subparsers(dest="action", metavar="ACTION", required=True)

    install = actions.add_parser("install", parents=[common], help="merge the hooks into the project settings")
    install.add_argument("project", help="project id")
    install.add_argument("--replace-legacy", action="store_true", help="remove old jobs_auto.py entries")
    install.set_defaults(handler=_install)

    uninstall = actions.add_parser("uninstall", parents=[common], help="remove the roadmap hook entries")
    uninstall.add_argument("project", help="project id")
    uninstall.set_defaults(handler=_uninstall)

    status = actions.add_parser("status", parents=[common], help="show which hooks are installed")
    status.add_argument("project", help="project id")
    status.set_defaults(handler=_status)


def _wants_json(args):
    return getattr(args, "json", False)


def _install(args):
    result = hooks_install.install(args.project, args.replace_legacy)
    if not _wants_json(args):
        print(("changed " if result["changed"] else "already up to date ") + result["settings"])
        if result["legacyRemoved"]:
            print("removed %d legacy jobs_auto.py entr%s" % (result["legacyRemoved"],
                                                             "y" if result["legacyRemoved"] == 1 else "ies"))
        return None
    return result


def _uninstall(args):
    agentguard.refuse_if_agent("hooks uninstall")  # removing the gate loosens control: a person runs it
    result = hooks_install.uninstall(args.project)
    if not _wants_json(args):
        print("removed %d roadmap hook entr%s" % (result["removed"], "y" if result["removed"] == 1 else "ies"))
        return None
    return result


def _status(args):
    result = hooks_install.status(args.project)
    if not _wants_json(args):
        for event, row in result["events"].items():
            print("%-13s %s" % (event, row["state"]))
        return None
    return result
