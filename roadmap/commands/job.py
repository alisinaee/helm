"""Command group job: record Claude jobs and their tokens in the project's jobs.json."""

import argparse
import sys

from roadmap.errors import EXIT_NOT_FOUND, RoadmapError
from roadmap.services import budget, control, git, jobs

DONE_WORDS = {"done": "done", "fail": "failed"}
OUT_LINES = 15  # most lines a human output prints without --full (a next: line counts)


def _full(args):
    return getattr(args, "full", False)


def _pick(rows, room):
    """Compact view: every running job first (never hidden), then the newest finished jobs that fit in room.
    Returns (jobs to show, how many finished jobs are hidden)."""
    running = [job for job in rows if job.get("status") == "running"]
    finished = [job for job in reversed(rows) if job.get("status") != "running"]
    if len(running) + len(finished) <= room:
        return running + finished, 0
    take = max(room - len(running) - 1, 0)
    return running + finished[:take], len(finished) - take


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
    start.add_argument("--effort", metavar="LEVEL", default=None,
                       help="thinking effort: low, medium, high, xhigh or max (default: not recorded)")
    start.add_argument("--engine-model", metavar="NAME", default=None,
                       help="the real model of the engine, for example laguna-s-2.1 (default: not recorded)")
    start.set_defaults(handler=_start)

    for name, text in (("done", "mark a job done"), ("fail", "mark a job failed")):
        parser = actions.add_parser(name, parents=[common, project], help=text)
        parser.add_argument("id", help="job id")
        parser.add_argument("note", nargs="?", help="short summary")
        parser.add_argument("--tokens", metavar="K", help="tokens used, in thousands")
        if name == "fail":
            parser.add_argument("--reason", metavar="TEXT", default=None,
                                help="first error line, kept to 80 characters")
        parser.set_defaults(handler=_finish, status=DONE_WORDS[name])

    progress = actions.add_parser("progress", parents=[common, project],
                                  help="record the live tokens of a running job (optional)")
    progress.add_argument("id", help="job id")
    progress.add_argument("--tokens", metavar="K", required=True,
                          help="tokens used so far, in thousands (the job's running total)")
    progress.set_defaults(handler=_progress)

    listing = actions.add_parser("list", parents=[common, project], help="list jobs")
    listing.add_argument("--full", action="store_true", help="print past the 15-line cap")
    listing.set_defaults(handler=_list)

    prune = actions.add_parser("prune", parents=[common, project],
                               help="remove finished jobs beyond the newest 30")
    prune.set_defaults(handler=_prune)


def _data_dir(args):
    return jobs.data_dir_of(jobs.resolve_project(args.project))


def _start(args):
    data_dir = _data_dir(args)
    stop, warn = budget.guard(data_dir)
    if stop:
        raise RoadmapError("stop", stop, EXIT_NOT_FOUND)  # exit 3: usage is at a stop in docs/autonomy.json
    if warn:
        print("warn: " + warn, file=sys.stderr)
    job = jobs.start_job(data_dir, args.title, args.model, args.task, parent=args.parent, role=args.role,
                          effort=args.effort, engine_model=args.engine_model)
    if not getattr(args, "json", False):
        print(job["id"])
        return None
    return job


def _finish(args):
    tokens = jobs.tokens_from_arg(args.tokens)
    project = jobs.resolve_project(args.project)
    data_dir = jobs.data_dir_of(project)
    job = jobs.finish_job(data_dir, args.id, args.status, args.note, tokens,
                          reason=getattr(args, "reason", None))
    if tokens is not None:
        # progress already counted in the budget (job progress) is not counted again
        remainder = jobs.budget_remainder(job, tokens)
        budget.record_job_spend(data_dir, job["id"], job.get("task"), job.get("model"), remainder)
        control.after_write(project["id"])  # the spend can reach a limit row (WP27)
    commits = _linked_commits(project, job["id"]) if job["status"] == "done" else []
    job["commits"] = commits
    if not getattr(args, "json", False):
        print(job["id"] + " " + job["status"])
        if commits:
            print("commits: " + " ".join(sha[:7] for sha in commits))
        return None
    return job


def _linked_commits(project, job_id):
    """Commit ids whose Job: trailer names job_id (newest first). Not a git repo or no commits gives []. Nothing is
    stored: the link is read from git each time."""
    try:
        rows = git.read_log(project["path"], limit=git.LOG_MAX)
    except RoadmapError:
        return []
    return [row["sha"] for row in rows if row.get("job") == job_id]


def _progress(args):
    """Record a running job's live tokens. Only the part not yet counted goes to the budget, under a key that is
    unique to this reading, so the job's final spend (job done --tokens) adds just the rest."""
    value = jobs.tokens_from_arg(args.tokens)
    project = jobs.resolve_project(args.project)
    data_dir = jobs.data_dir_of(project)
    job, new_k = jobs.progress_job(data_dir, args.id, value)
    if new_k > 0:
        key = job["id"] + "@" + repr(job["progressK"])
        budget.record_job_spend(data_dir, key, job.get("task"), job.get("model"), new_k)
        control.after_write(project["id"])
    if not getattr(args, "json", False):
        print("%s progress %sk" % (job["id"], repr(job["progressK"])))
        return None
    return job


def _list(args):
    data_dir = _data_dir(args)
    rows = jobs.list_jobs(data_dir)
    if not getattr(args, "json", False):
        blocked = jobs.engines_line(data_dir)
        hidden = 0
        if not _full(args):
            rows, hidden = _pick(rows, OUT_LINES - (1 if blocked else 0))
        lines = []
        for job in rows:
            task = " [" + job["task"] + "]" if job.get("task") else ""
            note = "  -- " + job["note"] if job.get("note") else ""
            lines.append("%-6s %-8s %-7s%s %s%s" % (job.get("id", "?"), job.get("status", "?"), job.get("model", "?"),
                                                    task, job.get("title", ""), note))
        if hidden:
            lines.append("+%d more (--full)" % hidden)
        for line in lines or ["no jobs"]:
            print(line)
        if blocked:
            print(blocked)
        return None
    return {"jobs": rows}


def _prune(args):
    removed, kept = jobs.prune_jobs(_data_dir(args))
    if not getattr(args, "json", False):
        print("pruned %d finished job(s); %d kept" % (removed, kept))
        return None
    return {"removed": removed, "kept": kept}
