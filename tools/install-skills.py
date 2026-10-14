"""Install the roadmap skill drafts into a Claude Code skills folder.

The drafts are docs/skill-draft/SKILL.md (installed as roadmap-dashboard), docs/skill-draft/roadmap-update/SKILL.md
and docs/skill-draft/roadmap-plan-new/SKILL.md. Each one is checked before anything is written:
  - the file starts with a frontmatter block that has a non-empty name and description, and the name matches the
    skill folder it installs into;
  - every `roadmap ...` line in a fenced bash or sh block parses with roadmap.cli.build_parser() (nothing runs).
If any skill is invalid, nothing is installed and the exit code is 1.

An existing skill folder is never overwritten silently. Without --yes the run refuses (exit 2) and changes nothing.
With --yes the folder is first renamed to <name>.bak-<timestamp> next to it, then the new SKILL.md is copied in.

Usage:
  python3 tools/install-skills.py [--target DIR] [--dry-run] [--yes]

  --target DIR   the skills folder (default ~/.claude/skills)
  --dry-run      print what would happen, change nothing
  --yes          allow replacing existing skill folders (they are backed up first)

Exit codes: 0 done (or dry run ok), 1 invalid skill draft, 2 refused (existing folder without --yes), 3 I/O error.
"""

import contextlib
import datetime
import io
import os
import re
import shlex
import shutil
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from roadmap.errors import RoadmapError  # noqa: E402  (needs REPO on sys.path first)

DEFAULT_TARGET = os.path.join("~", ".claude", "skills")
# (installed skill name, draft path relative to the repo)
SKILLS = (
    ("roadmap-dashboard", "docs/skill-draft/SKILL.md"),
    ("roadmap-update", "docs/skill-draft/roadmap-update/SKILL.md"),
    ("roadmap-plan-new", "docs/skill-draft/roadmap-plan-new/SKILL.md"),
)
SHELL_LANGS = ("bash", "sh")
FENCE_RE = re.compile(r"^\s*```(\S*)\s*$")
FIELD_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):[ \t]*(.*)$")
EXIT_OK, EXIT_INVALID, EXIT_REFUSED, EXIT_IO = 0, 1, 2, 3


def frontmatter(text):
    """The frontmatter fields of a SKILL.md as a dict, or None when there is no closed frontmatter block."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    fields = {}
    for raw in lines[1:]:
        if raw.strip() == "---":
            return fields
        match = FIELD_RE.match(raw)
        if match:
            fields[match.group(1)] = match.group(2).strip()
    return None


def roadmap_lines(text):
    """(line number, text) for each line that starts with `roadmap ` inside a fenced bash or sh block."""
    found = []
    in_shell = False
    for number, raw in enumerate(text.splitlines(), start=1):
        fence = FENCE_RE.match(raw)
        if fence:
            in_shell = (not in_shell) and fence.group(1) in SHELL_LANGS
            continue
        if in_shell and raw.strip().startswith("roadmap "):
            found.append((number, raw.strip()))
    return found


def parse_problem(line):
    """None when the roadmap line parses with the real parser, else the reason it does not."""
    from roadmap.cli import build_parser

    try:
        argv = shlex.split(line, comments=True)[1:]
    except ValueError as exc:
        return "does not split: %s" % exc
    parser = build_parser()
    sink = io.StringIO()
    try:
        with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            parser.parse_args(argv)
    except SystemExit as exc:
        if exc.code in (0, None):
            return None
        return "does not parse"
    except RoadmapError as exc:
        return "does not parse: %s" % exc
    return None


def validate(name, path):
    """The list of problems with one draft. An empty list means it can be installed."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        return ["cannot read %s: %s" % (path, exc)]
    problems = []
    fields = frontmatter(text)
    if fields is None:
        problems.append("no frontmatter block (--- ... ---) at the top")
    else:
        for key in ("name", "description"):
            if not fields.get(key):
                problems.append("frontmatter has no '%s'" % key)
        if fields.get("name") and fields.get("name") != name:
            problems.append("frontmatter name '%s' is not '%s'" % (fields.get("name"), name))
    for number, line in roadmap_lines(text):
        reason = parse_problem(line)
        if reason:
            problems.append("line %d: %s: %s" % (number, line, reason))
    return problems


def plan(target, root, skills):
    """Validate every draft, then return a list of (name, source, destination folder) or raise ValueError."""
    problems = []
    rows = []
    for name, rel in skills:
        source = os.path.join(root, rel)
        for problem in validate(name, source):
            problems.append("%s (%s): %s" % (name, rel, problem))
        rows.append((name, source, os.path.join(target, name)))
    if problems:
        raise ValueError("\n".join(problems))
    return rows


def run(target, root=REPO, skills=SKILLS, dry_run=False, yes=False, now=None, out=print):
    """Install the drafts into target. Returns the exit code."""
    target = os.path.abspath(os.path.expanduser(target))
    stamp = (now or datetime.datetime.now()).strftime("%Y%m%d-%H%M%S")
    try:
        rows = plan(target, root, skills)
    except ValueError as exc:
        out("refused: invalid skill draft, nothing installed:")
        out(str(exc))
        return EXIT_INVALID

    existing = []
    for name, source, dest in rows:
        if os.path.lexists(dest):
            if not os.path.isdir(dest) or os.path.islink(dest):
                out("refused: %s exists and is not a plain folder; move it by hand" % dest)
                return EXIT_REFUSED
            existing.append((name, dest))
    if existing and not yes:
        for name, dest in existing:
            out("refused: %s already exists; rerun with --yes to back it up and replace it" % dest)
        return EXIT_REFUSED

    out(("dry run, target %s" if dry_run else "target %s") % target)
    for name, dest in existing:
        backup = "%s.bak-%s" % (dest, stamp)
        if dry_run:
            out("would back up %s -> %s" % (dest, backup))
        else:
            out("back up %s -> %s" % (dest, backup))
    for name, source, dest in rows:
        skill_file = os.path.join(dest, "SKILL.md")
        if dry_run:
            out("would install %s: %s -> %s" % (name, source, skill_file))
        else:
            out("install %s: %s -> %s" % (name, source, skill_file))
    if dry_run:
        out("dry run: nothing changed")
        return EXIT_OK

    try:
        os.makedirs(target, exist_ok=True)
        for name, dest in existing:
            os.rename(dest, "%s.bak-%s" % (dest, stamp))
        for name, source, dest in rows:
            os.makedirs(dest, exist_ok=True)
            shutil.copyfile(source, os.path.join(dest, "SKILL.md"))
    except OSError as exc:
        out("io error: %s" % exc)
        return EXIT_IO
    out("done: %d skill(s) installed" % len(rows))
    return EXIT_OK


def main(argv=None):
    """Parse the options and run the install. Returns the exit code."""
    import argparse

    parser = argparse.ArgumentParser(description="Install the roadmap skill drafts into a Claude Code skills folder.")
    parser.add_argument("--target", default=DEFAULT_TARGET, help="skills folder (default ~/.claude/skills)")
    parser.add_argument("--dry-run", action="store_true", help="print what would happen, change nothing")
    parser.add_argument("--yes", action="store_true", help="replace existing skill folders (backed up first)")
    args = parser.parse_args(argv)
    return run(args.target, dry_run=args.dry_run, yes=args.yes)


if __name__ == "__main__":
    sys.exit(main())
