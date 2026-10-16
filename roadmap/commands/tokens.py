"""Command group tokens: measured per-job tokens from Claude Code subagent transcripts (R10.32)."""

import argparse
import os

from roadmap.services import jobs, jobtokens

DEFAULT_ROOT = os.path.join("~", ".claude", "projects", "-Users-ali-Works-roadmap-board")


def register(sub, common):
    group = sub.add_parser("tokens", parents=[common], help="measured tokens per job")
    actions = group.add_subparsers(dest="action", metavar="ACTION", required=True)
    fill = actions.add_parser("backfill", parents=[common], help="fill tokens of past jobs from subagent transcripts")
    fill.add_argument("--project", metavar="ID", default=None)
    fill.add_argument("--root", metavar="DIR", default=DEFAULT_ROOT,
                      help="folder with <session>/subagents/agent-*.jsonl (default: this project's Claude folder)")
    fill.add_argument("--overwrite", action="store_true", help="replace tokens already stored")
    fill.add_argument("--dry-run", action="store_true", help="match only, store nothing")
    fill.set_defaults(handler=_backfill)


def _backfill(args):
    data_dir = jobs.data_dir_of(jobs.resolve_project(args.project))
    result = jobtokens.backfill(data_dir, os.path.expanduser(args.root), args.overwrite, args.dry_run)
    if not getattr(args, "json", False):
        print("matched %d job(s); %d without a transcript" % (result["matched"], result["skipped"]))
        return None
    return result
