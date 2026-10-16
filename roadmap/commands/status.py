"""Top-level command status: the board summary of one project in at most 8 lines and 700 characters.

Lines keep this order, and when space runs out the lowest ones go first: header, left, phase, run, ask, queue,
issues, features, budget, you, next. The ask, queue, issues and budget lines come from the command layer
(docs/AGENT-INTERFACE.md section 2; docs/PRODUCT-SPEC.md section 4).
"""

import os
import re

from roadmap.commands import head as head_cmd, research
from roadmap.services import commands, features, jobs, limits, tasks

MAX_LINES = 8
MAX_CHARS = 700
HEAD = 3


def register(sub, common):
    """Add the status command to the root subparsers."""
    parser = sub.add_parser("status", parents=[common], help="brief board summary of a project")
    parser.add_argument("--project", metavar="ID", default=None,
                        help="project id (default: $ROADMAP_PROJECT, then the registered project of this folder)")
    parser.set_defaults(handler=_run)


def compose(base, extras):
    """Put the base summary lines and the four command-layer lines in priority order, then fit the budget."""
    head, rest = base[:HEAD], base[HEAD:]
    you = [line for line in rest if line.startswith("you:")]
    nxt = [line for line in rest if line.startswith("next:")]
    run = [line for line in rest if line.startswith("run:")]
    if extras.get("running"):
        run = [extras["running"]]
    gate = [line for line in (extras.get("gate"), extras.get("head")) if line]
    meters = [extras["limits"]] if extras.get("limits") else []
    plan = [extras["features"]] if extras.get("features") else []
    ordered = (head + run + gate + [extras["ask"], extras["queue"], extras["issues"]] + plan + [extras["budget"]]
               + meters + you + nxt)
    return _fit(ordered)


def fold_backlog(base, doc):
    """Backlog tasks (BACKLOG-SPEC 3) out of the base summary: the header's task total leaves them out and the header
    names them ('..., backlog 7'), and the phase line percent leaves them out too. base is returned as it is when the
    project has no backlog task."""
    all_tasks = [t for t in doc.get("tasks", []) if isinstance(t, dict)]
    backlog = [t for t in all_tasks if t.get("status") == "backlog"]
    if not backlog or not base:
        return base
    live = [t for t in all_tasks if t.get("status") != "backlog"]
    out = list(base)
    out[0] = re.sub(r"  \d+ tasks: ", "  %d tasks: " % len(live), out[0], count=1) + ", backlog %d" % len(backlog)
    if len(out) >= 3:
        out[2] = tasks._phase_line(dict(doc, tasks=live), live)
    return out


RUNNING_STATUSES = ("running", "claimed")


def running_line(jobs_list):
    """The running ids line: 'running 2: j1,j2' for every running or claimed job. The run: lines name only the first two
    running jobs (status 'running'), so a claimed job, or a third running job, gets this line. None when only one or two
    running jobs are in flight and none is claimed, since their own run lines already name them."""
    live = [job for job in jobs_list if isinstance(job, dict) and job.get("status") in RUNNING_STATUSES]
    if not live or (len(live) <= 2 and all(job.get("status") == "running" for job in live)):
        return None
    return "running %d: %s" % (len(live), ",".join(str(job.get("id")) for job in live))


def _fit(lines):
    """Keep lines in order while they fit: at most MAX_LINES lines and MAX_CHARS characters in all."""
    kept = []
    for line in lines:
        candidate = kept + [line]
        if len(candidate) > MAX_LINES or len("\n".join(candidate)) > MAX_CHARS:
            break
        kept.append(line)
    return kept


def gate_line(data_dir):
    """One line for research and approval (WP62b): 'research 1/1 open, phase P1 not approved'. The research part
    shows when the research folder exists (open notes out of all notes in INDEX.md); the phase part names the first
    phase whose approved flag is false. None when neither applies."""
    phases = tasks.unapproved_phases(data_dir)
    folder = os.path.join(data_dir, research.RESEARCH_DIR)
    parts = []
    if os.path.isdir(folder):
        entries = research._index_entries(folder)
        open_notes = sum(1 for line in entries if research.NO_FINDING in line)
        parts.append("research %d/%d open" % (open_notes, len(entries)))
    if phases:
        more = " (+%d)" % (len(phases) - 1) if len(phases) > 1 else ""
        parts.append("phase %s not approved%s" % (phases[0], more))
    return ", ".join(parts) or None


def _run(args):
    project, data_dir = tasks.resolve(args.project)
    base = tasks.summary(data_dir, jobs.list_jobs(data_dir), name=project["id"])
    base = fold_backlog(base, tasks.load(data_dir))
    extras = commands.status_extras(data_dir)
    extras["limits"] = limits.status_line(limits.evaluate_rows(project))
    extras["features"] = features.status_line(data_dir)
    extras["gate"] = gate_line(data_dir)
    extras["head"] = head_cmd.status_line(project, data_dir)
    extras["running"] = running_line(jobs.list_jobs(data_dir))
    lines = compose(base, extras)
    if not getattr(args, "json", False):
        for line in lines:
            print(line)
        return None
    return {"lines": lines}
