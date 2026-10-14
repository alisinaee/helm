"""Command ref: resolve a board ref (rb:<project>/<kind>/<id>, from the Copy button) to one short record. Read only.

Output: at most 10 lines of key: value, ending with next: the full command. --json prints the same as one object.
"""

import os
import re

from roadmap.core import refs
from roadmap.errors import EXIT_NOT_FOUND, EXIT_USAGE, RoadmapError
from roadmap.services import issues, loader, questions
from roadmap.store import config

RESEARCH_DIR = "research"
NOTE_RE = re.compile(r"^(\d{2})-([a-z0-9][a-z0-9-]*)\.md$")
PROJECTS_NEXT = "roadmap project list"


def register(sub, common):
    """Add the ref command."""
    parser = sub.add_parser("ref", parents=[common], help="resolve a board ref (rb:<project>/<kind>/<id>)")
    parser.add_argument("ref", help="the ref the Copy button gives, for example rb:roadmap-board/task/R3.2")
    parser.set_defaults(handler=_run)


def _project_entry(slug):
    for entry in config.list_projects():
        if entry["id"] == slug:
            return entry
    raise RoadmapError("not_found", "no registered project with id '" + slug + "'", EXIT_NOT_FOUND,
                       next=PROJECTS_NEXT)


def _lookup(kind, ident, folder):
    """The one record the snapshot does not hold in full, or None when there is no such item."""
    try:
        if kind == "issue":
            return issues.get(folder, ident)
        if kind == "question":
            return questions.get(folder, ident)
        if kind == "research":
            return _note(folder, ident)
    except RoadmapError as exc:
        if exc.exit == EXIT_NOT_FOUND:
            return None
        raise
    return None


def _note(folder, ident):
    """The research note numbered ident (its two-digit file prefix), or None."""
    research = os.path.join(folder, RESEARCH_DIR)
    if not os.path.isdir(research):
        return None
    for name in sorted(os.listdir(research)):
        match = NOTE_RE.match(name)
        if match and match.group(1) == ident:
            return {"id": ident, "title": match.group(2).replace("-", " "),
                    "file": RESEARCH_DIR + "/" + name}
    return None


def _run(args):
    try:
        project, kind, ident = refs.parse(args.ref)
    except ValueError as exc:
        raise RoadmapError("usage", "unknown ref: " + args.ref + " (" + str(exc) + ")", EXIT_USAGE,
                           next="roadmap status")
    entry = _project_entry(project)
    snap = loader.load_snapshot(project)
    folder = loader.project_folder(entry)
    found = refs.build(snap, project, kind, ident, _lookup(kind, ident, folder))
    if found is None:
        raise RoadmapError("usage", "unknown ref: " + refs.format_ref(project, kind, ident), EXIT_USAGE,
                           next="roadmap status")
    rows, next_cmd = found
    ref = refs.format_ref(project, kind, ident)
    if not getattr(args, "json", False):
        for line in refs.lines(ref, rows, next_cmd):
            print(line)
        return None
    return refs.data(ref, rows, next_cmd)
