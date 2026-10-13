"""Command group job: record Claude jobs and their tokens in the project's jobs.json."""

import argparse

from roadmap.services import budget, control, jobs

DONE_WORDS = {"done": "done", "fail": "failed"}


def _project_option():
    """Parent parser that adds --project to an action."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--project", metavar="ID", default=None,
                        help="project id (default: $ROADMAP_PROJECT, then the registered project of this folder)")
    return parser


def register(sub, common):
    """Add the job group and its actions."""
    project = _project_option()
    group = sub.add_parser("job", parents=[common], help="record jobs")
    actions = group.add_subparsers(dest="action", metavar="ACTION", required=True)

    start = actions.add_parser("start", parents=[common, project], help="start a job")
    start.add_argument("title", help="what the job does")
    start.add_argument("model", help="model name, for example opus, sonnet or haiku")
    start.add_argument("task", nargs="?", help="task id from the project's tasks.json")
    start.add_argument("--parent", metavar="ID", default=None, help="job id of the lead this job works for")
    start.add_argument("--role", metavar="ROLE", default=None, help="lead or worker (needs --parent)")
    start.set_defaults(handler=_start)

    for name, text in (("done", "mark a job done"), ("fail", "mark a job failed")):
        parser = actions.add_parser(name, parents=[common, project], help=text)
        parser.add_argument("id", help="job id")
        parser.add_argument("note", nargs="?", help="short summary")
        parser.add_argument("--tokens", metavar="K", help="tokens used, in thousands")
        parser.set_defaults(handler=_finish, status=DONE_WORDS[name])

    listing = actions.add_parser("list", parents=[common, project], help="list jobs")
    listing.set_defaults(handler=_list)

    prune = actions.add_parser("prune", parents=[common, project],
                               help="remove finished jobs beyond the newest 30")
    prune.set_defaults(handler=_prune)


def _data_dir(args):
    return jobs.data_dir_of(jobs.resolve_project(args.project))


def _start(args):
    job = jobs.start_job(_data_dir(args), args.title, args.model, args.task, parent=args.parent, role=args.role)
    if not getattr(args, "json", False):
        print(job["id"])
        return None
    return job


def _finish(args):
    tokens = jobs.tokens_from_arg(args.tokens)
    project = jobs.resolve_project(args.project)
    data_dir = jobs.data_dir_of(project)
    job = jobs.finish_job(data_dir, args.id, args.status, args.note, tokens)
    if tokens is not None:
        budget.record_job_spend(data_dir, job["id"], job.get("task"), job.get("model"), tokens)
        control.after_write(project["id"])  # the spend can reach a limit row (WP27)
    if not getattr(args, "json", False):
        print(job["id"] + " " + job["status"])
        return None
    return job


def _list(args):
    rows = jobs.list_jobs(_data_dir(args))
    if not getattr(args, "json", False):
        if not rows:
            print("no jobs")
        for job in rows:
            task = " [" + job["task"] + "]" if job.get("task") else ""
            note = "  -- " + job["note"] if job.get("note") else ""
            print("%-6s %-8s %-7s%s %s%s" % (job.get("id", "?"), job.get("status", "?"), job.get("model", "?"),
                                            task, job.get("title", ""), note))
        return None
    return {"jobs": rows}


def _prune(args):
    removed, kept = jobs.prune_jobs(_data_dir(args))
    if not getattr(args, "json", False):
        print("pruned %d finished job(s); %d kept" % (removed, kept))
        return None
    return {"removed": removed, "kept": kept}
