"""Command group git: status, log, branches, branch, show, commit and push for the project folder (GIT-SPEC step 5).

Reads go through roadmap/services/git.py. Writes go through the commands.py ops git.commit, git.push, git.branch and
git.switch, so the policy, the protected branches and the agent rules in roadmap/services/gitops.py apply here too.
"""

import argparse
import time

from roadmap.errors import EXIT_USAGE, RoadmapError
from roadmap.services import commands, git, jobs, tasks

NEXT_STATUS = "roadmap git status"
NEXT_LOG = "roadmap git log"
NEXT_BRANCH = "roadmap git branches"
STATUS_FILES = 5
LOG_DEFAULT = 10
OUT_LINES = 15  # most lines a human output prints without --full (a next: line counts)


def _full(args):
    return getattr(args, "full", False)


def _fit(lines, full, reserve=0):
    """The lines that fit under OUT_LINES less reserve; past that, one '+N more' line."""
    room = OUT_LINES - reserve
    if full or len(lines) <= room:
        return lines
    return lines[:room - 1] + ["+%d more (--full)" % (len(lines) - room + 1)]


def _project_option():
    """Parent parser that adds --project to an action."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--project", metavar="ID", default=None,
                        help="project id (default: $ROADMAP_PROJECT, then the registered project of this folder)")
    return parser


def register(sub, common):
    """Add the git group and its actions."""
    project = _project_option()
    group = sub.add_parser("git", parents=[common], help="git status, log, branches, commit and push")
    actions = group.add_subparsers(dest="action", metavar="ACTION", required=True)

    status = actions.add_parser("status", parents=[common, project], help="branch, counts and top changed files")
    status.set_defaults(handler=_status)

    log = actions.add_parser("log", parents=[common, project], help="the newest commits")
    log.add_argument("--task", metavar="ID", default=None, help="only commits linked to this task")
    log.add_argument("--job", metavar="ID", default=None, help="only commits linked to this job")
    log.add_argument("-n", metavar="N", type=int, default=LOG_DEFAULT, help="how many (default %d)" % LOG_DEFAULT)
    log.add_argument("--full", action="store_true", help="print past the 15-line cap")
    log.set_defaults(handler=_log)

    branches = actions.add_parser("branches", parents=[common, project], help="local branches")
    branches.add_argument("--full", action="store_true", help="print past the 15-line cap")
    branches.set_defaults(handler=_branches)

    branch = actions.add_parser("branch", parents=[common, project],
                                help="create or switch a branch (no argument: list them)")
    branch.add_argument("op", nargs="?", choices=("new", "switch"), help="new or switch")
    branch.add_argument("name", nargs="?", metavar="NAME", help="branch name")
    branch.set_defaults(handler=_branch)

    show = actions.add_parser("show", parents=[common, project], help="one commit: header and file list")
    show.add_argument("sha", metavar="SHA", help="commit id, 7 to 40 hex characters")
    show.add_argument("--stat", action="store_true", help="show the diffstat instead of the file status letters")
    show.add_argument("--full", action="store_true", help="print past the 15-line cap")
    show.set_defaults(handler=_show)

    commit = actions.add_parser("commit", parents=[common, project],
                                help="commit exactly the named paths (never everything)")
    commit.add_argument("paths", nargs="+", metavar="PATH", help="paths relative to the project")
    commit.add_argument("-m", "--message", required=True, metavar="TEXT", help="commit message")
    commit.add_argument("--task", metavar="ID", default=None, help="task id to write as a Task: trailer")
    commit.add_argument("--job", metavar="ID", default=None, help="job id to write as a Job: trailer")
    commit.set_defaults(handler=_commit)

    push = actions.add_parser("push", parents=[common, project],
                              help="push the current branch (policy in docs/git.json; never forced)")
    push.add_argument("--remote", metavar="NAME", default=None, help="remote name (default: the branch's remote)")
    push.add_argument("--checked", action="store_true",
                      help="say that a green make check ran (needed by the after-check policy)")
    push.set_defaults(handler=_push)


def _project(project_id, next_cmd):
    """(project path, data folder) of the registered project a command acts on."""
    with commands.next_on_error(next_cmd):
        project, data_dir = tasks.resolve(project_id)
    return project["path"], data_dir


def _ago(when):
    """A unix time as a short age, for example 5m, 3h or 2d."""
    if not isinstance(when, int):
        return "-"
    secs = max(0, int(time.time()) - when)
    if secs < 3600:
        return "%dm" % (secs // 60)
    if secs < 86400:
        return "%dh" % (secs // 3600)
    return "%dd" % (secs // 86400)


def _owner_map(data_dir):
    """Path -> id of the running job that owns it (its files list in jobs.json)."""
    owners = {}
    for job in jobs.list_jobs(data_dir):
        if job.get("status") != "running":
            continue
        for name in job.get("files") or []:
            if isinstance(name, str):
                owners.setdefault(name, job.get("id"))
    return owners


def _changed_rows(st, owners):
    """Unique changed paths, staged and changed first, then untracked and conflicts: (path, letters, owner)."""
    rows, seen = [], set()
    for entry in st["staged"] + st["changed"]:
        if entry["path"] not in seen:
            seen.add(entry["path"])
            rows.append((entry["path"], entry["code"], owners.get(entry["path"]) or "unattributed"))
    for path in st["untracked"]:
        if path not in seen:
            seen.add(path)
            rows.append((path, "??", "unattributed" if path not in owners else owners[path]))
    for path in st["conflicts"]:
        if path not in seen:
            seen.add(path)
            rows.append((path, "UU", "unattributed"))
    return rows


def _status(args):
    path, data_dir = _project(args.project, NEXT_STATUS)
    st = git.read_status(path)
    owners = _owner_map(data_dir)
    rows = _changed_rows(st, owners)
    if not getattr(args, "json", False):
        if st["detached"]:
            head = "(detached)"
        else:
            head = st["branch"] or "-"
        line = head
        if st["upstream"]:
            line += " -> " + st["upstream"] + "  +%d -%d" % (st["ahead"], st["behind"])
        print(line)
        if st["in_progress"]:
            print(st["in_progress"] + " in progress: finish it in a terminal")
        elif st["detached"]:
            print("detached HEAD: commit and push are refused; check out a branch first")
        print("staged %d  changed %d  untracked %d  conflicts %d" % (
            len(st["staged"]), len(st["changed"]), len(st["untracked"]), len(st["conflicts"])))
        for name, code, owner in rows[:STATUS_FILES]:
            print("  %-2s %s  [%s]" % (code, name, owner))
        return None
    return {"branch": st["branch"], "detached": st["detached"], "upstream": st["upstream"],
            "ahead": st["ahead"], "behind": st["behind"], "in_progress": st["in_progress"],
            "staged": len(st["staged"]), "changed": len(st["changed"]), "untracked": len(st["untracked"]),
            "conflicts": len(st["conflicts"]),
            "files": [{"path": name, "code": code, "owner": owner} for name, code, owner in rows]}


def _log(args):
    path, _ = _project(args.project, NEXT_LOG)
    if args.n < 1:
        raise RoadmapError("usage", "-n must be at least 1", EXIT_USAGE, next=NEXT_LOG)
    rows = git.read_log(path, limit=git.LOG_MAX)
    if args.task:
        rows = [row for row in rows if row.get("task") == args.task]
    if args.job:
        rows = [row for row in rows if row.get("job") == args.job]
    rows = rows[:args.n]
    if not getattr(args, "json", False):
        lines = []
        for row in rows:
            links = " ".join(part for part in (row.get("task"), row.get("job")) if part)
            tags = " [" + links + "]" if links else ""
            lines.append("%s  %-12.12s %4s  %s%s" % (row["sha"][:7], row["author"], _ago(row["time"]), row["subject"],
                                                    tags))
        for line in _fit(lines or ["no commits"], _full(args)):
            print(line)
        return None
    return {"commits": rows}


def _branches(args):
    path, _ = _project(args.project, NEXT_BRANCH)
    rows = git.read_branches(path)
    if not getattr(args, "json", False):
        lines = []
        for row in rows:
            mark = "*" if row["current"] else " "
            track = ""
            if row["upstream"]:
                track = " -> %s +%d -%d" % (row["upstream"], row["ahead"], row["behind"])
                if row["gone"]:
                    track += " (gone)"
            lines.append("%s %s%s  %s" % (mark, row["name"], track, _ago(row["time"])))
        for line in _fit(lines or ["no branches"], _full(args)):
            print(line)
        return None
    return {"branches": rows}


def _branch(args):
    if args.op is None:
        return _branches(args)
    if not args.name:
        raise RoadmapError("usage", "branch " + args.op + " needs a branch name", EXIT_USAGE, next=NEXT_BRANCH)
    if args.op == "new":
        reply = commands.write(args.project, "git.branch", {"name": args.name}, NEXT_BRANCH)
        text = "created branch " + args.name
    else:
        reply = commands.write(args.project, "git.switch", {"name": args.name}, NEXT_BRANCH)
        text = "switched to " + args.name
    if not getattr(args, "json", False):
        print(text)
        return None
    return commands.json_data(reply)


def _show(args):
    sha = git.valid_sha(args.sha)
    path, _ = _project(args.project, NEXT_LOG)
    root = git.repo_root(path)
    mode = "--stat" if args.stat else "--name-status"
    text = git.redact(git.run(root, ["show", "--no-color", "--format=%H  %an  %ar%n%s", mode, sha]))
    if not getattr(args, "json", False):
        for line in _fit(text.rstrip("\n").split("\n"), _full(args)):
            print(line)
        return None
    return {"sha": sha, "text": text.rstrip("\n")}


def _commit(args):
    payload = {"paths": list(args.paths), "message": args.message, "task": args.task, "job": args.job}
    reply = commands.write(args.project, "git.commit", payload, NEXT_STATUS)
    if not getattr(args, "json", False):
        data = reply["data"]
        print("committed %s (%d file(s))" % (data["sha"][:7], data["files"]))
        return None
    return commands.json_data(reply)


def _push(args):
    payload = {"remote": args.remote, "checked": bool(args.checked)}
    reply = commands.write(args.project, "git.push", payload, NEXT_STATUS)
    if not getattr(args, "json", False):
        data = reply["data"]
        print("pushed %s to %s" % (data["branch"], data["remote"]))
        return None
    return commands.json_data(reply)
