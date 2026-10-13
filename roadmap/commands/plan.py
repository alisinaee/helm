"""Command group plan: import plan text into tasks.json, export it for a re-plan, or print the grammar (plan template).

Plan text is documented in docs/AGENT-INTERFACE.md section 2. Import takes plain plan text or a Markdown file whose
first fenced block is tagged roadmap-plan. Import validates everything first and writes nothing on error.
"""

import argparse
import sys

from roadmap.commands.task import apply_records, plan_failure, print_diff
from roadmap.core import planfmt
from roadmap.errors import EXIT_NOT_FOUND, RoadmapError
from roadmap.services import tasks

TEMPLATE = """Plan text: UTF-8, one record per line. Blank lines and lines starting with # are ignored.
P <id> <status> | <name>
T <id> <status> <tokensK> <model>/<thinking> [!] [c:<check>/<checkK>] | <title> [# <note>]
id: letters and digits; a task id is <phase>.<number>. status: todo|partial|done|hold|- (- keeps the value)
model: haiku|sonnet|opus|-. thinking: low|medium|high|-. tokensK: whole number or -.
!: needs you. check: none|sonnet|opus, checkK: whole number of K tokens.
Example (creates one phase and 5 tasks):
P M1 todo | Foundations
T M1.1 todo 20 haiku/low | Scaffold repo, CI and lint
T M1.2 todo 40 sonnet/medium c:sonnet/8 | Data model and storage layer
T M1.3 todo 5 haiku/low ! | Create hosting account and API key # needs your login
T M1.4 todo 80 opus/high c:opus/15 | Sync engine design and spike
T M1.5 todo 10 haiku/low | README quick start"""


def _project_option():
    """Parent parser that adds --project to an action."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--project", metavar="ID", default=None,
                        help="project id (default: $ROADMAP_PROJECT, then the registered project of this folder)")
    return parser


def _phase_of(task):
    phase = task.get("phase")
    if isinstance(phase, str) and phase:
        return phase
    return str(task.get("id", "")).split(".")[0]


def register(sub, common):
    """Add the plan group and its actions."""
    project = _project_option()
    group = sub.add_parser("plan", parents=[common], help="import, export or template plan text")
    actions = group.add_subparsers(dest="action", metavar="ACTION", required=True)

    importer = actions.add_parser("import", parents=[common, project],
                                  help="create or update phases and tasks from plan text")
    importer.add_argument("source", metavar="file", help="a plan file, a Markdown file, or - for stdin")
    importer.add_argument("--dry-run", action="store_true", help="show what would change, write nothing")
    importer.add_argument("--replace-phase", metavar="P", default=None,
                          help="also remove the tasks of phase P that are missing from the input (dry run lists them)")
    importer.set_defaults(handler=_import)

    exporter = actions.add_parser("export", parents=[common, project], help="print the plan text")
    exporter.add_argument("--phase", metavar="P", default=None, help="only this phase and its tasks")
    exporter.set_defaults(handler=_export)

    template = actions.add_parser("template", parents=[common], help="print the plan grammar and an example")
    template.set_defaults(handler=_template)


def _import(args):
    project, data_dir = tasks.resolve(args.project)
    text = _read(args.source)
    if "roadmap-plan" in text:
        block = planfmt.extract_block(text)
        if block is not None:
            text = block
    records, errors = planfmt.parse_plan(text)
    next_cmd = "roadmap plan import " + args.source + " --dry-run"
    if errors:
        raise plan_failure(errors, next_cmd)
    diff = apply_records(data_dir, project["id"], records, next_cmd, dry_run=args.dry_run,
                         replace_phase=args.replace_phase)
    return print_diff(diff, getattr(args, "json", False))


def _export(args):
    _, data_dir = tasks.resolve(args.project)
    doc = tasks.load(data_dir)
    lines = []
    phase_ids = []
    for phase in doc["phases"]:
        if not isinstance(phase, dict) or not isinstance(phase.get("id"), str):
            continue
        if args.phase is not None and phase["id"] != args.phase:
            continue
        phase_ids.append(phase["id"])
        lines.append(planfmt.format_phase(phase))
        lines.extend(planfmt.format_task(t) for t in doc["tasks"]
                     if isinstance(t, dict) and _phase_of(t) == phase["id"])
    if args.phase is not None and not phase_ids:
        raise RoadmapError("not_found", "no phase " + args.phase, EXIT_NOT_FOUND,
                           next="roadmap status")
    if args.phase is None:
        lines.extend(planfmt.format_task(t) for t in doc["tasks"]
                     if isinstance(t, dict) and _phase_of(t) not in phase_ids)
    if not getattr(args, "json", False):
        for line in lines:
            print(line)
        return None
    return {"lines": lines}


def _template(args):
    if not getattr(args, "json", False):
        print(TEMPLATE)
        return None
    return {"text": TEMPLATE}


def _read(source):
    if source == "-":
        return sys.stdin.read()
    try:
        with open(source, "r", encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        raise RoadmapError("not_found", "cannot read " + source, EXIT_NOT_FOUND)
