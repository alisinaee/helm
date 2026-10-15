"""Command group backlog: add an idea to the backlog (status backlog: known, not committed, not scheduled).

backlog add "<title>" [--phase P]   a new backlog task in phase P; without --phase it goes to the reserved phase BL
                                    (named Backlog, created on first use). Agents may add; promote is the person's
                                    (roadmap task promote, see commands/task.py).
The task id is the next number in the phase. Output: one line, then a next: line.
"""

import unicodedata

from roadmap.commands import task as task_cmd
from roadmap.core import parsers, planfmt
from roadmap.errors import EXIT_USAGE, RoadmapError
from roadmap.services import tasks

RESERVED_PHASE = "BL"
RESERVED_NAME = "Backlog"
DEFAULT_MODEL = "haiku"          # a backlog task has no work yet; the model and thinking are placeholders
DEFAULT_THINKING = "low"


def register(sub, common):
    """Add the backlog group and its add action."""
    group = sub.add_parser("backlog", parents=[common], help="add ideas to the backlog (not committed)")
    actions = group.add_subparsers(dest="action", metavar="ACTION", required=True)
    add = actions.add_parser("add", parents=[common], help="add a backlog task")
    add.add_argument("title", help="the idea, up to %d characters" % parsers.TITLE_MAX)
    add.add_argument("--phase", metavar="P", default=None,
                     help="phase to put it in (default: %s, the reserved Backlog phase)" % RESERVED_PHASE)
    add.add_argument("--project", metavar="ID", default=None,
                     help="project id (default: $ROADMAP_PROJECT, then the registered project of this folder)")
    add.set_defaults(handler=_add)


def _title(value):
    title = " ".join(str(value or "").split())
    if not title:
        raise RoadmapError("usage", "title is empty (allowed: text)", EXIT_USAGE, next='roadmap backlog add "<title>"')
    if len(title) > parsers.TITLE_MAX:
        raise RoadmapError("usage", "title is %d characters (allowed: up to %d)" % (len(title), parsers.TITLE_MAX),
                           EXIT_USAGE, next='roadmap backlog add "<title>"')
    if any(unicodedata.category(ch) == "Cc" for ch in title):
        raise RoadmapError("usage", "title has a control character (allowed: text)", EXIT_USAGE)
    return title


def _next_number(doc, phase):
    """One past the highest number used by a task id in this phase (P.<n>)."""
    numbers = [0]
    for task in doc["tasks"]:
        tid = task.get("id") if isinstance(task, dict) else None
        if isinstance(tid, str) and tid.startswith(phase + ".") and tid[len(phase) + 1:].isdigit():
            numbers.append(int(tid[len(phase) + 1:]))
    return max(numbers) + 1


def _add(args):
    project, data_dir = tasks.resolve(args.project)
    title = _title(args.title)
    phase = args.phase or RESERVED_PHASE
    if not planfmt.PHASE_ID_RE.match(phase):
        raise RoadmapError("usage", "phase id '" + phase + "' has a dot or a symbol (allowed: letters and digits)",
                           EXIT_USAGE, next="roadmap status")
    doc = tasks.load(data_dir)
    phase_ids = [p.get("id") for p in doc["phases"] if isinstance(p, dict)]
    records = []
    if phase == RESERVED_PHASE and phase not in phase_ids:
        records.append({"kind": "phase", "line": 1, "id": phase, "name": RESERVED_NAME, "status": None})
    tid = phase + "." + str(_next_number(doc, phase))
    records.append({"kind": "task", "line": 2, "id": tid, "phase": phase, "title": title, "status": "backlog",
                    "tokensK": 0, "thinking": DEFAULT_THINKING, "model": DEFAULT_MODEL, "needsUser": None,
                    "check": None, "checkK": None, "note": None, "after": None, "feats": None})
    task_cmd.apply_records(data_dir, project["id"], records, "roadmap status")
    if getattr(args, "json", False):
        return {"id": tid, "phase": phase, "status": "backlog", "title": title}
    print("ok %s backlog in %s. next: roadmap task promote %s" % (tid, phase, tid))
    return None
