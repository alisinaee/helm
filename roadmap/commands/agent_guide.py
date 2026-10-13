"""Command agent-guide: print the short guide for AI agents (roadmap.core.guide, at most 40 lines)."""

from roadmap.core import guide


def register(sub, common):
    """Add the agent-guide command to the root subparsers."""
    parser = sub.add_parser("agent-guide", parents=[common], help="print the short guide for AI agents")
    parser.set_defaults(handler=_run)


def _run(args):
    lines = guide.lines()
    if not getattr(args, "json", False):
        for line in lines:
            print(line)
        return None
    return {"lines": lines}
