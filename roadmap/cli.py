"""Command line entry point: the argparse tree, the --json envelope and the exit codes.

Each command group lives in roadmap/commands/<group>.py and is listed in COMMAND_MODULES. A new
command is a new module there; this file does not change.
"""

import argparse
import importlib
import json
import sys

from roadmap.errors import EXIT_ERROR, EXIT_OK, EXIT_USAGE, RoadmapError

COMMAND_MODULES = (
    "serve",
    "tick",
    "service",
    "project",
    "job",
    "task",
    "backlog",
    "plan",
    "issue",
    "subtask",
    "ask",
    "comment",
    "feature",
    "inbox",
    "budget",
    "undo",
    "research",
    "agent_guide",
    "status",
    "head",
    "work",
    "ref",
    "hook",
    "hooks",
    "control",
    "limits",
    "rules",
    "usage",
    "doctor",
    "phone",
    "backup",
    "skills",
    "watch",
    "version",
    "logs",
    "git",
)


class _Parser(argparse.ArgumentParser):
    """ArgumentParser that raises RoadmapError instead of exiting, so usage errors get the envelope."""

    def error(self, message):
        raise RoadmapError("usage", message, EXIT_USAGE)


def build_parser():
    """Return the root parser with every command module registered."""
    common = _Parser(add_help=False)
    common.add_argument(
        "--json",
        action="store_true",
        default=argparse.SUPPRESS,
        help="print the {ok, data | error} JSON envelope on stdout",
    )
    root = _Parser(
        prog="roadmap",
        description="roadmap-board: a live roadmap dashboard and job tracker for Claude Code projects.",
        parents=[common],
    )
    sub = root.add_subparsers(dest="command", metavar="COMMAND", required=True)
    for name in COMMAND_MODULES:
        module = importlib.import_module("roadmap.commands." + name)
        module.register(sub, common)
    return root


def _emit(obj):
    print(json.dumps(obj))


def _fail(exc, want_json):
    if want_json:
        error = {"code": exc.code, "message": exc.message}
        if exc.next:
            error["next"] = exc.next
        _emit({"ok": False, "error": error})
    else:
        lines = exc.message.split("\n")
        if exc.next and len(lines) == 1 and exc.code != "invalid_plan":
            text = "roadmap: " + lines[0] + ". next: " + exc.next
        else:
            text = "\n".join(["roadmap: " + lines[0]] + lines[1:] + (["next: " + exc.next] if exc.next else []))
        print(text, file=sys.stderr)
    return exc.exit


def main(argv=None):
    """Run the CLI and return the process exit code."""
    argv = sys.argv[1:] if argv is None else list(argv)
    want_json = "--json" in argv
    try:
        args = build_parser().parse_args(argv)
        data = args.handler(args)
    except RoadmapError as exc:
        return _fail(exc, want_json)
    except Exception as exc:  # keep the envelope contract even for bugs
        return _fail(RoadmapError("internal", "unexpected error (" + type(exc).__name__ + ")", EXIT_ERROR),
                     want_json)
    if getattr(args, "json", False):
        _emit({"ok": True, "data": data if data is not None else {}})
    return EXIT_OK
