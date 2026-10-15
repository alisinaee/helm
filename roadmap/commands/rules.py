"""Command group rules: show, add, rm, sync and check the project rules (services/rules.py), and the proposals
that lead to them (propose, proposals, accept, reject).

show is for the lead and for workers (at most 12 lines). add, rm, sync, accept and reject are refused from an agent
shell. propose is open to agents.
"""

from roadmap.services import rules, tasks


def register(sub, common):
    """Add the rules group and its actions."""
    group = sub.add_parser("rules", parents=[common], help="show, add, remove, sync or check the project rules")
    actions = group.add_subparsers(dest="action", metavar="ACTION", required=True)

    show = actions.add_parser("show", parents=[common], help="the rules for a task, model and role (at most 12 lines)")
    show.add_argument("--for", dest="task", default=None, metavar="ID", help="the task the worker will do")
    show.add_argument("--model", default=None, metavar="M", help="haiku, sonnet or opus")
    show.add_argument("--role", default=None, choices=("lead", "worker"))
    show.add_argument("--project", default=None, metavar="ID")
    show.set_defaults(handler=_show)

    add = actions.add_parser("add", parents=[common], help="add a rule at the end of docs/rules.txt")
    add.add_argument("scope", help="all, lead, worker, haiku, sonnet, opus, phase:X, task:X or claude")
    add.add_argument("kind", help="do, dont, budget or done")
    add.add_argument("text", help="the rule, at most 160 characters")
    add.add_argument("--budget", type=int, default=None, metavar="N", help="thousands of tokens, for kind budget")
    add.add_argument("--project", default=None, metavar="ID")
    add.set_defaults(handler=_add)

    remove = actions.add_parser("rm", parents=[common], help="remove a rule by id, for example R3")
    remove.add_argument("rule_id", metavar="R3")
    remove.add_argument("--project", default=None, metavar="ID")
    remove.set_defaults(handler=_rm)

    sync = actions.add_parser("sync", parents=[common], help="write the all, lead and claude rules into CLAUDE.md")
    sync.add_argument("--dry-run", action="store_true", help="print the counts, change nothing")
    sync.add_argument("--project", default=None, metavar="ID")
    sync.set_defaults(handler=_sync)

    check = actions.add_parser("check", parents=[common], help="validate docs/rules.txt against the caps")
    check.add_argument("--project", default=None, metavar="ID")
    check.set_defaults(handler=_check)

    propose = actions.add_parser("propose", parents=[common], help="propose a rule (agents may); the person accepts")
    propose.add_argument("text", help="the proposed rule, at most 160 characters")
    propose.add_argument("--from", dest="sources", action="append", default=[], metavar="Hn",
                         help="a Head id the rule comes from (repeat for more)")
    propose.add_argument("--project", default=None, metavar="ID")
    propose.set_defaults(handler=_propose)

    listing = actions.add_parser("proposals", parents=[common], help="the open rule proposals (at most 15 lines)")
    listing.add_argument("--project", default=None, metavar="ID")
    listing.set_defaults(handler=_proposals)

    accept = actions.add_parser("accept", parents=[common], help="accept a proposal into docs/rules.txt (person only)")
    accept.add_argument("proposal_id", metavar="RP1")
    accept.add_argument("--text", default=None, help="the rule text to keep instead of the proposal's")
    accept.add_argument("--project", default=None, metavar="ID")
    accept.set_defaults(handler=_accept)

    reject = actions.add_parser("reject", parents=[common], help="reject a proposal (person only)")
    reject.add_argument("proposal_id", metavar="RP1")
    reject.add_argument("--project", default=None, metavar="ID")
    reject.set_defaults(handler=_reject)


def _json(args):
    return getattr(args, "json", False)


def _show(args):
    _, data_dir = tasks.resolve(args.project)
    lines = rules.show(data_dir, task_id=args.task, model=args.model, role=args.role)
    if _json(args):
        return {"lines": lines}
    for line in lines or ["no rules apply"]:
        print(line)
    return None


def _add(args):
    _, data_dir = tasks.resolve(args.project)
    rule = rules.add(data_dir, args.scope, args.kind, args.text, value=args.budget)
    if _json(args):
        return {"rule": rule}
    print(rules.format_rule(rule))
    return None


def _rm(args):
    _, data_dir = tasks.resolve(args.project)
    rule = rules.remove(data_dir, args.rule_id)
    if _json(args):
        return {"removed": rule["id"]}
    print("removed " + rule["id"])
    return None


def _sync(args):
    project, data_dir = tasks.resolve(args.project)
    result = rules.sync(project, data_dir, dry_run=args.dry_run)
    counts = "+%d ~%d -%d" % (result["added"], result["changed"], result["removed"])
    if _json(args):
        return dict(result, project=project["id"])
    print(counts + (" (dry run)" if args.dry_run else ""))
    return None


def _check(args):
    _, data_dir = tasks.resolve(args.project)
    count = rules.check(data_dir)
    if _json(args):
        return {"rules": count}
    print("ok: %d rules" % count)
    return None


def _propose(args):
    _, data_dir = tasks.resolve(args.project)
    row = rules.propose(data_dir, args.text, sources=args.sources)
    if _json(args):
        return dict(row)
    if row.get("duplicate"):
        print("duplicate of %s %s" % ("rule" if row["of"] == "rule" else "proposal", row["id"]))
    else:
        print("%s proposed" % row["id"])
    return None


PROPOSAL_LINES = 15


def _proposals(args):
    _, data_dir = tasks.resolve(args.project)
    items = rules.open_proposals(data_dir)
    lines = []
    for row in items:
        srcs = ", ".join(row.get("sources") or []) or "no source"
        lines.append("%s (from %s) %s" % (row["id"], srcs, row["text"]))
    if len(lines) > PROPOSAL_LINES:
        lines = lines[:PROPOSAL_LINES - 1] + ["+%d more" % (len(lines) - PROPOSAL_LINES + 1)]
    if _json(args):
        return {"proposals": items}
    for line in lines or ["no open proposals"]:
        print(line)
    return None


def _accept(args):
    _, data_dir = tasks.resolve(args.project)
    row = rules.accept(data_dir, args.proposal_id, edited_text=args.text)
    if _json(args):
        return dict(row)
    print("%s accepted as %s" % (row["id"], row["rule"]))
    return None


def _reject(args):
    _, data_dir = tasks.resolve(args.project)
    row = rules.reject(data_dir, args.proposal_id)
    if _json(args):
        return dict(row)
    print("%s rejected" % row["id"])
    return None
