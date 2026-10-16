"""Command group head (HEAD-SPEC section 4): the ledger of the person's asks. log, t (triage in one call), list, show,
set, bind, unbind, split, merge, convert, claim, brief, triage, review, accept and forget.

Writes go through commands.write, so each logs one activity line and can be undone. review, accept and forget are the
person's only: the op refuses an agent, the phone and a bare non-TTY shell. Output: one "ok ..." line with its
"next: ..." after it; reads print lines and end with "next: ..." too. --json keeps the envelope.
"""

import argparse
import os
from datetime import datetime, timezone

from roadmap.core import head as core
from roadmap.core.snapshot import head_link_state
from roadmap.services import agentguard, commands, control, headimport, hooks, jobs, loader, tasks
from roadmap.services import head as store
from roadmap.services import queue as queue_service
from roadmap.store import paths, schema

NEXT = "roadmap head list"
BRIEF = "roadmap head brief"
GATE_LINES = 5                # the gate's continue lines (head_svc.GATE_LIMIT)
DONE_CHECKLIST = (            # HEAD-SPEC section 11 item 3: the worker-completion checklist
    "done checklist (HEAD-SPEC 11.3):",
    "1. verify the diff: git diff --stat, then the tests",
    "2. close the job with tokens: roadmap job done <id> \"note\" --tokens K",
    "3. commit your own files by path, then push",
    "4. launch the next wave on disjoint files",
    "5. run the cursor or agy audit on this change",
    "6. tick the asks it answers: roadmap head set H<n> status=done note=\"<commit sha | job id | answer: ...>\"",
    "next: roadmap head brief --gate",
)
OUT_LINES = 15                # most lines a human output prints without --full (a next: line counts)
SHOW_MAX = 14                 # the show output in lines, header and text included (next: is the 15th)
TEXT_SHOW_MAX = 200           # verbatim characters on the show line
LIST_DEFAULT = 13             # rows head list prints without --full
JSON_LIST_DEFAULT = 20        # rows head list --json returns when --n is not given (unchanged)
SET_FIELDS = ("status", "kind", "sum", "note", "prio")
UNHANDLED = ("new", "understood")
LIST_FILTERS = ("open", "unhandled", "doing", "needs", "done", "all")


def _project_option():
    """Parent parser that adds --project to an action."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--project", metavar="ID", default=None,
                        help="project id (default: $ROADMAP_PROJECT, then the registered project of this folder)")
    return parser


def register(sub, common):
    """Add the head group and its actions."""
    project = _project_option()
    group = sub.add_parser("head", parents=[common],
                           help="the ask ledger: log, t, list, show, set, bind, unbind, split, merge, convert, claim, "
                                "brief, triage, review, accept, forget, import")
    actions = group.add_subparsers(dest="action", metavar="ACTION", required=True)

    def add(name, help_text, **kwargs):
        return actions.add_parser(name, parents=[common, project], help=help_text, **kwargs)

    log = add("log", "log one message verbatim (redacted), with its kind and summary")
    log.add_argument("text", help="the message")
    log.add_argument("--kind", default=None, metavar="K", help="ask, decision, rule, bug, preference, question, review, info")
    log.add_argument("--sum", default=None, metavar="S", help="the one-line summary (the heuristic when left out)")
    log.add_argument("--bind", nargs="+", default=None, metavar="REF", help="links such as task:R7.31")
    log.set_defaults(handler=_log)

    triage = add("t", "triage one entry in one call: head t H15 <kind> \"<sum>\" [REF..] [--status S]")
    triage.add_argument("id", metavar="H15")
    triage.add_argument("kind", metavar="K")
    triage.add_argument("sum", metavar="SUM")
    triage.add_argument("refs", nargs="*", metavar="REF")
    triage.add_argument("--status", default=None, metavar="S", help="merged, declined, needs-you, done or open")
    triage.set_defaults(handler=_triage_one)

    listing = add("list", "one line per entry: id, kind, status, age, links, summary")
    which = listing.add_mutually_exclusive_group()
    for flag in LIST_FILTERS:
        which.add_argument("--" + flag, dest="which", action="store_const", const=flag,
                           help="show the " + flag + " entries")
    listing.set_defaults(which="open")
    listing.add_argument("--kind", default=None, metavar="K", help="only this kind")
    listing.add_argument("--n", type=int, default=None, metavar="N",
                         help="the newest N rows (default 13; --full prints all, or N past 13)")
    listing.add_argument("--q", default=None, metavar="TEXT", help="only summaries containing this text")
    listing.add_argument("--full", action="store_true", help="print past the 15-line cap")
    listing.set_defaults(handler=_list)

    show = add("show", "one entry: summary, verbatim, links with their states, history (at most 14 lines)")
    show.add_argument("id", metavar="H15")
    show.add_argument("--full", action="store_true", help="print the whole history past the 15-line cap")
    show.set_defaults(handler=_show)

    setter = add("set", "change fields: head set H15 status=declined note=\"..\" (a done close needs a commit sha, "
                        "job id or answer: note)")
    setter.add_argument("id", metavar="H15")
    setter.add_argument("words", nargs="+", metavar="KEY=VALUE", help="status, kind, sum, note or prio (P0-P3)")
    setter.set_defaults(handler=_set)

    bind = add("bind", "add links to an entry")
    bind.add_argument("id", metavar="H15")
    bind.add_argument("refs", nargs="+", metavar="REF")
    bind.set_defaults(handler=_bind)

    unbind = add("unbind", "remove links from an entry")
    unbind.add_argument("id", metavar="H15")
    unbind.add_argument("refs", nargs="+", metavar="REF")
    unbind.set_defaults(handler=_unbind)

    split = add("split", "split one entry into two: head split H15 \"<sum a>\" \"<sum b>\"")
    split.add_argument("id", metavar="H15")
    split.add_argument("sums", nargs=2, metavar="SUM")
    split.set_defaults(handler=_split)

    merge = add("merge", "merge a duplicate into another entry: head merge H16 --into H9")
    merge.add_argument("id", metavar="H16")
    merge.add_argument("--into", required=True, metavar="H9")
    merge.set_defaults(handler=_merge)

    convert = add("convert", "create a task, issue or backlog item from an entry and bind it")
    convert.add_argument("id", metavar="H15")
    convert.add_argument("target", choices=("task", "issue", "backlog", "rule"))
    convert.add_argument("--phase", default=None, metavar="R8", help="the phase for a task (default: Backlog)")
    convert.add_argument("--kind", default=None, metavar="K", help="the issue kind (default: bug)")
    convert.set_defaults(handler=_convert)

    claim = add("claim", "start a head session: writes a claim record and prints the carried-over open asks")
    claim.add_argument("--model", required=True, metavar="M", help="the model, for example \"Opus 5.5\"")
    claim.add_argument("--acct", default=None, metavar="B", help="the account letter")
    claim.add_argument("--full", action="store_true", help="print past the 15-line cap")
    claim.set_defaults(handler=_claim)

    digest = add("brief", "the resume digest, at most 15 lines")
    digest.add_argument("--md", action="store_true", help="markdown bullets")
    digest.add_argument("--gate", action="store_true", help="the autopilot continue lines, or ok nothing pending")
    digest.add_argument("--done", action="store_true", help="the worker-completion checklist")
    digest.add_argument("--full", action="store_true", help="print past the 15-line cap")
    digest.set_defaults(handler=_brief)

    add("pause", "pause the autopilot gate (writes the head-pause file)").set_defaults(handler=_pause)
    add("resume", "resume the autopilot gate (removes the head-pause file)").set_defaults(handler=_resume)

    untriaged = add("triage", "untriaged entries with suggestions")
    untriaged.add_argument("--full", action="store_true", help="print past the 15-line cap")
    untriaged.set_defaults(handler=_triage_list)

    add("next", "the head ops that can run now, one runnable command per line").set_defaults(handler=_runnable)

    review = add("review", "the person's review: no id lists the done entries, H15 confirm or H15 reopen decides")
    review.add_argument("id", nargs="?", default=None, metavar="H15")
    review.add_argument("decision", nargs="?", default=None, metavar="confirm|reopen", choices=("confirm", "reopen"))
    review.add_argument("--full", action="store_true", help="print past the 15-line cap")
    review.set_defaults(handler=_review)

    accept = add("accept", "mark an entry accepted (the person only)")
    accept.add_argument("id", metavar="H15")
    accept.set_defaults(handler=_accept)

    forget = add("forget", "blank the verbatim text of an entry, keep the summary (the person only)")
    forget.add_argument("id", metavar="H15")
    forget.set_defaults(handler=_forget)

    imp = add("import", "seed the ledger from a markdown doc: head import --doc FILE [--section 2,2b]")
    imp.add_argument("--doc", required=True, metavar="FILE", help="a markdown file inside the project folder")
    imp.add_argument("--section", default=None, metavar="N,N", help="only these `## <n>` sections (default: all)")
    imp.set_defaults(handler=_import)


# ---------------------------------------------------------------- shared helpers

def _now():
    return datetime.now().astimezone()


def _json(args):
    return getattr(args, "json", False)


def _full(args):
    return getattr(args, "full", False)


def _fit(lines, full, reserve=0):
    """The lines that fit under OUT_LINES less reserve (room for a next: line); past that, one '+N more' line."""
    room = OUT_LINES - reserve
    if full or len(lines) <= room:
        return lines
    return lines[:room - 1] + ["+%d more (--full)" % (len(lines) - room + 1)]


def _state(project, data_dir, now=None):
    """The folded rows, the link states they read and the clock. The link states come from the snapshot's tasks and
    jobs, as the API and the status board read them."""
    now = now or _now()
    snap = loader.load_snapshot(project["id"])
    link_state = head_link_state(snap["tasks"], snap["jobs"])
    return store.rows(data_dir, link_state=link_state, now=now), link_state, now


def _kind(row):
    return str(row.get("kind") or "").rstrip("?")


def _age(row, now):
    ts = core.parse_ts(row.get("ts"))
    if ts is None:
        return "-"
    minutes = max(0, int((now - ts).total_seconds() // 60))
    if minutes < 60:
        return "%dm" % minutes
    if minutes < 1440:
        return "%dh" % (minutes // 60)
    return "%dd" % (minutes // 1440)


def _short_ref(ref):
    return str(ref).split(":", 1)[-1]


def _links(row):
    """The first link's id, then ',+N' for the others: R7.31,+1."""
    links = row.get("links") or []
    if not links:
        return ""
    first = _short_ref(links[0])
    return first if len(links) == 1 else "%s,+%d" % (first, len(links) - 1)


def _flat(text, limit):
    return " ".join(str(text or "").split())[:limit]


def _list_line(row, now):
    return "%-5s %-9s %-9s %4s %-10s %s" % (row["id"], _kind(row), row["status"], _age(row, now), _links(row),
                                             _flat(row["sum"], 60))


def _find(rows, eid):
    for row in rows:
        if row["id"] == eid:
            return row
    raise commands._usage("no head entry " + eid, NEXT)


def _ok(text, nxt):
    print("ok %s. next: %s" % (text, nxt))


def _next(text):
    print("next: " + text)


def _emit_write(args, reply, text, nxt):
    if _json(args):
        return commands.json_data(reply)
    _ok(text, nxt)
    return None


def _write(args, op, payload):
    return commands.write(args.project, op, payload, NEXT)


def _awaiting(data_dir, rows):
    """Done entries the person has not confirmed: the head or the links marked them done. A confirmation is a done
    update by the person; a reopen is not done at all."""
    last = {}
    for rec in store._records(data_dir):
        sets = rec.get("set") if isinstance(rec.get("set"), dict) else {}
        if rec.get("t") == "u" and "status" in sets:
            last[rec.get("id")] = (sets["status"], rec.get("by"))
    return [row for row in rows if row["status"] == "done" and last.get(row["id"]) != ("done", "person")]


def _select(rows, which, kind, text):
    out = rows
    if which == "open":
        out = [r for r in out if r["status"] not in core.CLOSED_STATUSES]
    elif which == "unhandled":
        out = [r for r in out if r["status"] in UNHANDLED]
    elif which == "doing":
        out = [r for r in out if r["status"] == "doing"]
    elif which == "needs":
        out = [r for r in out if r["status"] == "needs-you"]
    elif which == "done":
        out = [r for r in out if r["status"] == "done"]
    if kind:
        out = [r for r in out if _kind(r) == kind]
    if text:
        out = [r for r in out if text.lower() in str(r["sum"]).lower()]
    return out


def status_line(project, data_dir):
    """The head line of the status board: 'head: 3 open, 2 unhandled (oldest 2h), 5 doing, 1 needs-you'. None until
    the head holds an entry, so a project without asks gets no extra line."""
    if not os.path.exists(os.path.join(data_dir, store.FILE)):
        return None
    rows, link_state, now = _state(project, data_dir)
    if not rows:
        return None
    return store.brief(data_dir, link_state=link_state, now=now)[0]


# ---------------------------------------------------------------- writes

def _log(args):
    reply = _write(args, "head.log", {"text": args.text, "kind": args.kind, "sum": args.sum,
                                      "refs": args.bind or []})
    data = reply["data"]
    if data.get("id") is None:
        return _emit_write(args, reply, "logged, numbered after the next head write (spooled)", NEXT)
    status = "bound" if data.get("bound") else "new"
    text = "%s %s %s" % (data["id"], data["kind"], status)
    nxt = NEXT if status == "bound" else "roadmap head t %s .." % data["id"]
    return _emit_write(args, reply, text, nxt)


def _guard_head_write(args, eid, status=None, note=None, adds=(), removes=(), now=None):
    """The head's own writes (not the person's) are checked before they are written: a close needs a real ref and at
    most 3 a minute, and a bind may not leave an entry on umbrella tasks alone (services/head check_close and
    check_umbrella_binds)."""
    if agentguard.person_context(commands.current_source()):
        return
    _, data_dir = tasks.resolve(args.project)
    store.check_umbrella_binds(data_dir, eid, adds=adds, removes=removes, now=now)
    if status == "done":
        store.check_close(data_dir, eid, note or "", now=now)


def _triage_one(args):
    _guard_head_write(args, args.id, status=args.status, adds=args.refs or [])
    reply = _write(args, "head.triage", {"id": args.id, "kind": args.kind, "sum": args.sum, "refs": args.refs,
                                         "status": args.status})
    project, data_dir = tasks.resolve(args.project)
    rows, _, _ = _state(project, data_dir)
    row = _find(rows, args.id)
    text = "%s %s %s" % (args.id, _kind(row), row["status"])
    if row["links"]:
        text += " " + " ".join(row["links"][:3])
    return _emit_write(args, reply, text, NEXT)


def _set(args):
    payload = {"id": args.id, "status": None, "kind": None, "sum": None, "note": None, "prio": None}
    for word in args.words:
        key, sep, value = word.partition("=")
        if not sep or key not in SET_FIELDS:
            raise commands._usage("set takes key=value pairs (allowed: " + ", ".join(SET_FIELDS) + ")", NEXT)
        payload[key] = value
    _guard_head_write(args, payload["id"], status=payload["status"], note=payload["note"])
    reply = _write(args, "head.set", payload)
    return _emit_write(args, reply, "%s set %s" % (args.id, ", ".join(reply["data"]["changed"])), NEXT)


def _bind(args):
    _guard_head_write(args, args.id, adds=args.refs or [])
    reply = _write(args, "head.bind", {"id": args.id, "refs": args.refs})
    bound = ", ".join(reply["data"]["bound"]) or "nothing new"
    return _emit_write(args, reply, "%s bound %s" % (args.id, bound), NEXT)


def _unbind(args):
    reply = _write(args, "head.unbind", {"id": args.id, "refs": args.refs})
    removed = ", ".join(reply["data"]["unbound"]) or "nothing"
    return _emit_write(args, reply, "%s unbound %s" % (args.id, removed), NEXT)


def _split(args):
    reply = _write(args, "head.split", {"id": args.id, "sums": args.sums})
    into = ", ".join(reply["data"]["into"]) or "spooled entries"
    return _emit_write(args, reply, "%s split into %s" % (args.id, into), NEXT)


def _merge(args):
    reply = _write(args, "head.merge", {"id": args.id, "into": args.into})
    return _emit_write(args, reply, "%s merged into %s" % (args.id, args.into), NEXT)


def _convert(args):
    reply = _write(args, "head.convert", {"id": args.id, "target": args.target, "phase": args.phase,
                                          "kind": args.kind})
    data = reply["data"]
    text = "%s -> %s" % (args.id, data["ref"]) if data.get("ref") else "%s %s: add to rules.txt?" % (
        args.id, data.get("status"))
    return _emit_write(args, reply, text, NEXT)


def _review(args):
    if args.id is None:
        return _review_list(args)
    if args.decision is None:
        raise commands._usage("review " + args.id + " needs confirm or reopen", "roadmap head review " + args.id
                              + " confirm")
    reply = _write(args, "head.review", {"id": args.id, "action": args.decision})
    text = "%s confirmed done" % args.id if args.decision == "confirm" else "%s reopened" % args.id
    return _emit_write(args, reply, text, NEXT)


def _accept(args):
    reply = _write(args, "head.accept", {"id": args.id})
    return _emit_write(args, reply, "%s accepted" % args.id, NEXT)


def _forget(args):
    reply = _write(args, "head.forget", {"id": args.id})
    return _emit_write(args, reply, "%s verbatim forgotten" % args.id, NEXT)


def _inside_project(path, project):
    """The real path of a doc that lies inside the project folder; anything else is refused."""
    root = os.path.realpath(project["path"])
    doc = os.path.realpath(os.path.abspath(os.path.expanduser(path)))
    if doc != root and not doc.startswith(root.rstrip(os.sep) + os.sep):
        raise commands._usage("head import reads only files inside the project folder (" + root + ")", NEXT)
    return doc


def _import(args):
    project, data_dir = tasks.resolve(args.project)
    doc = _inside_project(args.doc, project)
    with commands.next_on_error(NEXT):
        results = headimport.import_doc(doc, args.section, data_dir)
    logged = [r["id"] for r in results if r["status"] == "logged"]
    skipped = len(results) - len(logged)
    if _json(args):
        return {"logged": logged, "skipped": skipped, "items": results}
    _ok("import %d logged, %d skipped" % (len(logged), skipped), NEXT)
    return None


def _claim(args):
    project, data_dir = tasks.resolve(args.project)
    model = commands._text(args.model)
    if not model:
        raise commands._usage("claim needs a model, for example --model \"Opus 5.5\"", BRIEF)
    acct = commands._text(args.acct) or None
    with commands.next_on_error(BRIEF):
        store.session(data_dir, "claim", acct=acct, model=model)
        rows, _, _ = _state(project, data_dir)
    carried = [r for r in rows if r["carried"] and r["status"] not in core.CLOSED_STATUSES]
    data = {"model": model, "acct": acct, "carried": [r["id"] for r in carried]}
    if _json(args):
        return data
    carried_lines = ["  %s %s %s %s" % (row["id"], _kind(row), row["status"], _flat(row["sum"], 60))
                     for row in carried]
    for line in _fit(carried_lines, _full(args), reserve=1):
        print(line)
    print("ok claim %s, %d carried. next: %s" % (model, len(carried), BRIEF))
    return None


# ---------------------------------------------------------------- reads

def _list(args):
    project, data_dir = tasks.resolve(args.project)
    if args.n is not None and args.n < 1:
        raise commands._usage("--n must be at least 1", NEXT)
    rows, _, now = _state(project, data_dir)
    matched = _select(rows, args.which, args.kind, args.q)
    if _json(args):
        return {"entries": [dict(r, age=_age(r, now)) for r in matched[-(args.n or JSON_LIST_DEFAULT):]]}
    if args.n is not None:
        cap = args.n if _full(args) else min(args.n, LIST_DEFAULT)
    else:
        cap = len(matched) if _full(args) else LIST_DEFAULT
    shown = matched[-cap:]
    for row in shown:
        print(_list_line(row, now))
    if not shown:
        print("no entries match (" + args.which + ")")
    if len(matched) > len(shown):
        print("+%d older (--full, or --n)" % (len(matched) - len(shown)))
    pending = [r for r in shown if r["status"] in UNHANDLED]
    _next('roadmap head t %s <kind> "<sum>"' % pending[0]["id"] if pending else BRIEF)
    return None


def _history(data_dir, eid):
    out = []
    for rec in store._records(data_dir):
        if rec.get("t") != "u" or rec.get("id") != eid:
            continue
        sets = rec.get("set") if isinstance(rec.get("set"), dict) else {}
        parts = ["%s=%s" % (key, sets[key]) for key in sorted(sets)] + list(rec.get("link") or [])
        if rec.get("note"):
            parts.append('note "%s"' % rec["note"])
        out.append("  %s %s %s" % (str(rec.get("ts") or "")[:16].replace("T", " "), rec.get("by") or "",
                                   ", ".join(parts)))
    return out


def _show(args):
    project, data_dir = tasks.resolve(args.project)
    rows, link_state, now = _state(project, data_dir)
    row = _find(rows, args.id)
    text = store.text_of(data_dir, args.id)
    history = _history(data_dir, args.id)
    if _json(args):
        return {"entry": dict(row, age=_age(row, now), text=text), "history": history}
    lines = [_list_line(row, now)]
    lines.append("text: " + (_flat(text, TEXT_SHOW_MAX) if text else "(none)"))
    if row["links"]:
        states = ["%s %s" % (ref, link_state.get(ref, "open")) for ref in row["links"]]
        lines.append("links: " + ", ".join(states))
    limit = 10 ** 6 if _full(args) else SHOW_MAX
    room = limit - len(lines) - 1
    if history:
        lines.append("history:")
        lines += history[-room:] if room > 0 else []
    lines = lines[:limit]
    print("\n".join(lines))
    _next('roadmap head t %s <kind> "<sum>"' % args.id if row["status"] in UNHANDLED else NEXT)
    return None


def _gate_items(project, data_dir, now):
    """The autopilot continue items, read the way the Stop hook reads them (hooks._stop_gate): the head config switch,
    the pause file or a stop in the control state, the queue, running jobs, git counts and the usage file. The
    hook's one-block-per-window stamp is not applied here: this is a read."""
    cfg = hooks._head_config(data_dir).get("head")
    if isinstance(cfg, dict) and cfg.get("gate") is False:
        return []
    state = control.read_state(project["id"]) or {}
    paused = os.path.exists(os.path.join(data_dir, store.GATE_PAUSE_FILE)) or state.get("stop") is True
    rows = store.rows(data_dir, now=now)
    queue = [e.get("task") for e in queue_service.list_queue(data_dir)]
    running = [j for j in jobs.list_jobs(data_dir) if j.get("status") == "running"]
    dirty, unpushed = hooks._git_counts(project["path"])
    data, error = schema.read_data("usage", paths.usage_file())
    usage = data if error is None and isinstance(data, dict) else None
    return store.gate(rows, queue=queue, running=running, dirty=dirty, unpushed=unpushed, usage=usage,
                      paused=paused, now=now)


def _gate(project, data_dir):
    with commands.next_on_error(BRIEF):
        items = _gate_items(project, data_dir, _now())
    if not items:
        print("ok nothing pending")
        return None
    for item in items[:GATE_LINES]:
        print("continue: " + item)
    return None


def _pause(args):
    project, data_dir = tasks.resolve(args.project)
    os.makedirs(data_dir, exist_ok=True)
    with open(os.path.join(data_dir, store.GATE_PAUSE_FILE), "w", encoding="utf-8") as fh:
        fh.write(_now().isoformat(timespec="seconds") + "\n")
    _ok("head paused: the gate stays silent", "roadmap head resume")
    return None


def _resume(args):
    project, data_dir = tasks.resolve(args.project)
    path = os.path.join(data_dir, store.GATE_PAUSE_FILE)
    was = os.path.exists(path)
    if was:
        os.remove(path)
    _ok("head resumed" if was else "head was not paused", BRIEF + " --gate")
    return None


def _brief(args):
    project, data_dir = tasks.resolve(args.project)
    if args.gate:
        return _gate(project, data_dir)
    if args.done:
        print("\n".join(DONE_CHECKLIST))
        return None
    with commands.next_on_error(NEXT):
        rows, link_state, now = _state(project, data_dir)
        lines = store.brief(data_dir, link_state=link_state, now=now)
    if args.md:
        lines = ["**" + lines[0] + "**"] + ["- " + line.strip() for line in lines[1:]]
    if _json(args):
        return {"lines": lines}
    print("\n".join(_fit(lines, _full(args))))
    return None


def _triage_list(args):
    project, data_dir = tasks.resolve(args.project)
    rows, _, _ = _state(project, data_dir)
    todo = [r for r in rows if r["status"] in UNHANDLED and not r["triaged"]]
    if _json(args):
        return {"entries": [{"id": r["id"], "kind": _kind(r), "sum": r["sum"], "dup": r["dup"]} for r in todo]}
    lines = []
    for row in todo:
        dup = " dup %s %.2f" % (row["dup"]["id"], row["dup"]["score"]) if row["dup"] else ""
        lines.append('%s %s%s | "%s"' % (row["id"], _kind(row), dup, _flat(row["sum"], 60)))
    if not todo:
        lines.append("no untriaged entries")
    for line in _fit(lines, _full(args), reserve=1):
        print(line)
    _next('roadmap head t %s <kind> "<sum>"' % todo[0]["id"] if todo else NEXT)
    return None


def _review_list(args):
    project, data_dir = tasks.resolve(args.project)
    rows, _, now = _state(project, data_dir)
    waiting = _awaiting(data_dir, rows)
    if _json(args):
        return {"entries": [dict(r, age=_age(r, now)) for r in waiting]}
    lines = [_list_line(row, now) for row in waiting] or ["nothing to review"]
    for line in _fit(lines, _full(args), reserve=1):
        print(line)
    _next("roadmap head review %s confirm|reopen" % waiting[0]["id"] if waiting else NEXT)
    return None


def _runnable(args):
    """head next: the ok line, then one runnable command per line: confirm each done entry the person has not
    confirmed, show each untriaged entry, and always the brief. Placeholders (<kind>) never appear here."""
    project, data_dir = tasks.resolve(args.project)
    rows, _, _ = _state(project, data_dir)
    waiting = _awaiting(data_dir, rows)
    untriaged = [r for r in rows if r["status"] in UNHANDLED and not r["triaged"]]
    ops = ["roadmap head review %s confirm" % r["id"] for r in waiting]
    ops += ["roadmap head show %s" % r["id"] for r in untriaged]
    ops.append(BRIEF)
    if _json(args):
        return {"ops": ops}
    print("ok %d runnable. next: %s" % (len(ops), ops[0]))
    for line in _fit(ops, _full(args), reserve=1):
        print(line)
    return None
