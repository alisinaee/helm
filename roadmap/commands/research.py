"""Command group research (WP17): numbered research notes in <data dir>/research, one INDEX line per note, and checks.

Layout and caps: docs/AGENT-INTERFACE.md section 3. A note is NN-<slug>.md: at most 6 notes, each at most 120 lines and
6 KB, with the headings in REQUIRED_HEADINGS and an optional roadmap-plan block that must parse with planfmt.
"""

import argparse
import os
import re

from roadmap.core import planfmt
from roadmap.errors import EXIT_CONFLICT, EXIT_INVALID_DATA, EXIT_NOT_FOUND, EXIT_USAGE, RoadmapError
from roadmap.services import jobs
from roadmap.store import lock

MAX_NOTES = 6
MAX_LINES = 120
MAX_BYTES = 6 * 1024
REQUIRED_HEADINGS = ("## Question", "## Findings", "## Decisions", "## Sources")
RESEARCH_DIR = "research"
INDEX_FILE = "INDEX.md"
INDEX_HEADER = "# Research index\n\n"
NO_FINDING = "(no finding yet)"
TITLE_MAX = 80
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
NOTE_RE = re.compile(r"^(\d{2})-([a-z0-9][a-z0-9-]*)\.md$")
TEMPLATE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates",
                        "research_note.md")


def _project_option():
    """Parent parser that adds --project to an action."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--project", metavar="ID", default=None,
                        help="project id (default: $ROADMAP_PROJECT, then the registered project of this folder)")
    return parser


def register(sub, common):
    """Add the research group and its actions."""
    project = _project_option()
    group = sub.add_parser("research", parents=[common], help="numbered research notes (at most 6 per project)")
    actions = group.add_subparsers(dest="action", metavar="ACTION", required=True)

    new = actions.add_parser("new", parents=[common, project],
                             help="start a note: next number, template, and its INDEX line")
    new.add_argument("slug", help="lowercase letters, digits and dashes, for example landscape")
    new.add_argument("title", help="one line, shown in INDEX.md")
    new.set_defaults(handler=_new)

    listing = actions.add_parser("list", parents=[common, project], help="print the research index")
    listing.set_defaults(handler=_list)

    check = actions.add_parser("check", parents=[common, project],
                               help="check the caps, the headings and any roadmap-plan block")
    check.set_defaults(handler=_check)


def _folder(args):
    """The research folder of the project. The project's data folder must exist (project init)."""
    data_dir = jobs.data_dir_of(jobs.resolve_project(args.project))
    if not os.path.isdir(data_dir):
        raise RoadmapError("not_found", "data folder does not exist: " + data_dir, EXIT_NOT_FOUND,
                           next="roadmap project init <project-path>")
    return os.path.join(data_dir, RESEARCH_DIR)


def _notes(folder):
    """(number, slug, filename) of each note file in the folder, in number order."""
    if not os.path.isdir(folder):
        return []
    found = []
    for name in os.listdir(folder):
        match = NOTE_RE.match(name)
        if match and os.path.isfile(os.path.join(folder, name)):
            found.append((int(match.group(1)), match.group(2), name))
    return sorted(found)


def _index_entries(folder):
    """The INDEX.md lines that start with '- ' (one per note). A missing index gives an empty list."""
    path = os.path.join(folder, INDEX_FILE)
    if not os.path.isfile(path):
        return []
    with open(path, "r", encoding="utf-8") as fh:
        return [line.rstrip("\n") for line in fh if line.startswith("- ")]


def _clean_title(text):
    title = " ".join(str(text or "").split())
    if not title:
        raise RoadmapError("invalid_input", "the title is empty", EXIT_USAGE)
    if len(title) > TITLE_MAX:
        raise RoadmapError("invalid_input", "the title is longer than %d characters" % TITLE_MAX, EXIT_USAGE)
    return title


def _write_text(path, text):
    """Write a UTF-8 text file through a temporary file and an atomic rename."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def _new(args):
    slug = str(args.slug or "")
    if not SLUG_RE.match(slug):
        raise RoadmapError("invalid_input", "slug must be 1 to 40 lowercase letters, digits or dashes: "
                           + repr(slug), EXIT_USAGE)
    title = _clean_title(args.title)
    folder = _folder(args)
    with lock.locked(folder):
        os.makedirs(folder, exist_ok=True)
        notes = _notes(folder)
        if any(note_slug == slug for _, note_slug, _ in notes):
            raise RoadmapError("conflict", "a note with slug '" + slug + "' already exists", EXIT_CONFLICT,
                               next="roadmap research list")
        if len(notes) >= MAX_NOTES:
            raise RoadmapError("research_limit", "research is capped at %d notes; extend an existing note instead"
                               % MAX_NOTES, EXIT_CONFLICT, next="roadmap research list")
        number = max([n for n, _, _ in notes] or [0]) + 1
        if number > 99:
            raise RoadmapError("research_limit", "no free note number", EXIT_CONFLICT)
        name = "%02d-%s.md" % (number, slug)
        with open(TEMPLATE, "r", encoding="utf-8") as fh:
            body = fh.read().replace("{number}", "%02d" % number).replace("{title}", title)
        _write_text(os.path.join(folder, name), body)
        _add_index_line(folder, number, slug, title)
    data = {"file": os.path.join(folder, name), "number": number, "slug": slug}
    if not getattr(args, "json", False):
        print("created " + data["file"])
        return None
    return data


def _add_index_line(folder, number, slug, title):
    path = os.path.join(folder, INDEX_FILE)
    text = INDEX_HEADER
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    if text and not text.endswith("\n"):
        text += "\n"
    text += "- %02d %s — %s — %s\n" % (number, slug, title, NO_FINDING)
    _write_text(path, text)


def _list(args):
    entries = _index_entries(_folder(args))
    if not getattr(args, "json", False):
        if not entries:
            print("no research notes")
        for line in entries:
            print(line)
        return None
    return {"notes": entries}


def note_problems(name, raw):
    """Every problem of one note given its bytes: the caps, the required headings and the plan block."""
    problems = []
    text = raw.decode("utf-8", errors="replace")
    lines = text.splitlines()
    if len(lines) > MAX_LINES:
        problems.append("%s: %d lines; the cap is %d" % (name, len(lines), MAX_LINES))
    if len(raw) > MAX_BYTES:
        problems.append("%s: %d bytes; the cap is %d (6 KB)" % (name, len(raw), MAX_BYTES))
    stripped = set(line.strip() for line in lines)
    for heading in REQUIRED_HEADINGS:
        if heading not in stripped:
            problems.append("%s: missing heading '%s'" % (name, heading))
    block = planfmt.extract_block(text)
    if block is not None:
        _, errors = planfmt.parse_plan(block)
        problems.extend("%s: roadmap-plan %s" % (name, error) for error in errors)
    return problems


def _check(args):
    folder = _folder(args)
    notes = _notes(folder)
    problems = []
    if len(notes) > MAX_NOTES:
        problems.append("%d notes; the cap is %d" % (len(notes), MAX_NOTES))
    entries = _index_entries(folder)
    for number, slug, name in notes:
        with open(os.path.join(folder, name), "rb") as fh:
            problems.extend(note_problems(name, fh.read()))
        prefix = "- %02d %s " % (number, slug)
        if not any(line.startswith(prefix) for line in entries):
            problems.append("%s: no line in %s (run research new, or add the line by hand)" % (name, INDEX_FILE))
    if problems:
        raise RoadmapError("invalid_data", "\n".join(problems), EXIT_INVALID_DATA,
                           next="fix the lines above, then run: roadmap research check")
    data = {"notes": len(notes), "problems": []}
    if not getattr(args, "json", False):
        print("ok: %d notes" % len(notes))
        return None
    return data
