"""Build the roadmap snapshot: the dict the dashboard renders, from the texts of a project's data files.

build_snapshot(files, config, now) is pure. files maps a file name (tasks.json, jobs.json, autonomy.json
and the extras files) to its text, or to None when the file is missing. config is the parsed
roadmap.config.json. now is the moment to measure running jobs and the recent window from.
"""

import json
from datetime import timedelta

from roadmap.core import features as feature_rules
from roadmap.core import head as head_rules
from roadmap.core.extras import parse_extras
from roadmap.core import refs as ref_rules
from roadmap.core import workstatus
from roadmap.core.parsers import (ISSUE_OPEN, error_entry, parse_activity, parse_autonomy, parse_budget,
                                  parse_comments, parse_issues, parse_jobs, parse_questions, parse_queue, parse_tasks,
                                  parse_ts)

SNAPSHOT_SCHEMA_VERSION = 1
PHASE_WEIGHT = {"done": 1.0, "partial": 0.5}
ACTIVE = ("todo", "partial")                        # task states counted as "left"
EXCLUDED = ("deferred", "backlog")                 # states left out of totals, progress, tokens (BACKLOG-SPEC 2)
RECENT_WINDOW = timedelta(minutes=30)               # finished jobs shown under their task
RECENT_MAX = 2
ACTIVITY_SHOWN = 15                                 # log lines on the Overview
COMMENTS_SHOWN = 3                                  # newest comments per target
WORKFLOW_SPANS = 200                                # newest job spans in the workflow key
HEAD_JOB_LINK = ("running", "done", "failed")       # job states the head link keeps (failed reads as failed)
ISSUE_CLOSED = ("closed", "wontfix")                # issue states out of the open list (issues.py CLOSED)
ISSUES_CLOSED_MAX = 5                               # newest closed issues in the issuesClosed key (WORK-UNIFIED 1)
WORKFLOW_DAYS = timedelta(days=7)                   # jobs that ended (or started) longer ago are dropped
AFTER_MAX = 5                                       # most task ids in one after list
SESSION_STATES = ("watching", "open", "none")       # presence.state() values (R7.1 T1)
HEAD_OPEN_MAX = 40                                  # HEAD-SPEC section 5: open asks in the head key, newest first
HEAD_DONE_MAX = 5                                   # newest done asks in the head key
HEAD_SUM_MAX = 60                                   # summary characters per head row
HEAD_NOTE_MAX = 200                                  # latest note characters per head row (only when present)
HEAD_LINKS_MAX = 3                                  # link refs per head row (links); the rest is a count
HEAD_LINKED_MAX = 6                                 # resolved links per head row (linked), HEAD-SPEC section 12
HEAD_TITLE_MAX = 60                                 # title characters per resolved link
HEAD_JOB_STATES = ("running", "queued")             # the only jobs a resolved link lists
HEAD_PREV_MAX = 3                                   # earlier sessions in the head key
HEAD_BYTES_MAX = 8192                               # the head key as compact JSON; link titles are dropped once to fit


def _missing(name):
    return error_entry(name, FileNotFoundError("file not found"))


def _read_optional(files, name, parse, errors):
    """The parsed value of an optional WP20 file, or None when the file is missing (a missing file adds no error)."""
    text = files.get(name)
    if text is None:
        return None
    value, errs = parse(text, name)
    errors.extend(errs)
    return value


def _budget_view(doc, tasks, phases):
    """Limits, spend and percent of limit per total, phase, model and task. Spend is in thousands of tokens.
    Percent is None when there is no limit. Spend on '-' (no task) counts in the total and models only."""
    limits = doc["limits"]
    spent = doc["spent"]
    task_phase = {t["id"]: t["phase"] for t in tasks if t.get("id") and t.get("phase")}

    def row(amount, limit):
        pct = round(100.0 * amount / limit, 1) if limit else None
        return {"spent": round(amount, 1), "limit": limit, "pct": pct}

    task_spent = {tid: sum(models.values()) for tid, models in spent.items()}
    model_spent = {}
    phase_spent = {}
    for tid, models in spent.items():
        for model, amount in models.items():
            model_spent[model] = model_spent.get(model, 0.0) + amount
        if tid != "-":
            pid = task_phase.get(tid) or tid.split(".")[0]
            phase_spent[pid] = phase_spent.get(pid, 0.0) + task_spent[tid]
    phase_ids = [p["id"] for p in phases] + [k for k in list(limits["phases"]) + list(phase_spent)
                                              if k not in [p["id"] for p in phases]]
    model_ids = sorted(set(model_spent) | set(limits["models"]))
    task_ids = sorted(set(task_spent) | set(limits["tasks"]))
    return {
        "limits": limits,
        "total": row(sum(task_spent.values()), limits.get("project")),
        "phases": {pid: row(phase_spent.get(pid, 0.0), limits["phases"].get(pid)) for pid in phase_ids},
        "models": {m: row(model_spent.get(m, 0.0), limits["models"].get(m)) for m in model_ids},
        "tasks": {tid: row(task_spent.get(tid, 0.0), limits["tasks"].get(tid)) for tid in task_ids},
        "spent": spent,
    }


def _round_k(value):
    return round(float(value), 1) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _span(job):
    """One job as a compact list: [id, task, model, role, parent, startEpoch, endEpoch|null, status, tokensK]."""
    start = parse_ts(job.get("started"))
    end = None if job["status"] == "running" else parse_ts(job.get("ended"))
    return [job["id"], job.get("task"), job.get("model") or None, job.get("role"), job.get("parent"),
            int(start.timestamp()), int(end.timestamp()) if end else None, job["status"],
            _round_k(job.get("tokensK"))]


# R7.10: a feature row leaves out these keys when they are empty (null or false). The Planner reads a missing key as
# that empty value, so the GUI shows the same thing.
FEATURE_EMPTY_OMITTED = ("parent", "phase", "accepted")


def _drop_empty_feature_keys(row):
    return {key: value for key, value in row.items() if not (key in FEATURE_EMPTY_OMITTED and not value)}


def _features_view(text, tasks, jobs_list, issues_open, errors):
    """The features key (WP52): rows, uncovered, orphans and counts from docs/features.json text. Absent text is an
    empty derive. Bad JSON or a bad feature goes into errors; nothing raises."""
    raw = []
    if text is not None:
        try:
            doc = json.loads(text)
            raw = doc.get("features") if isinstance(doc, dict) else None
            if not isinstance(raw, list):
                raw = []
                errors.append(error_entry("features.json", ValueError("features.json has no features array")))
        except ValueError as exc:
            errors.append(error_entry("features.json", exc))
    view = feature_rules.derive(raw, tasks, jobs_list, issues_open)
    errors.extend({"file": "features.json", "error": message} for message in view["errors"])
    return {"rows": [_drop_empty_feature_keys(row) for row in feature_rules.snapshot_rows(view["rows"])],
            "uncovered": view["uncovered"],
            "orphans": view["orphans"], "counts": view["counts"]}


def _after_edges(tasks_text, known):
    """[from, to] pairs from each task's after list in the raw tasks.json text: from is the task waited for, to the
    waiting task. Only ids that are tasks in this file count; a bad file gives no edges."""
    try:
        raw = json.loads(tasks_text) if tasks_text else {}
    except ValueError:
        return []
    items = raw.get("tasks") if isinstance(raw, dict) else None
    edges = []
    for task in items if isinstance(items, list) else []:
        if not isinstance(task, dict) or task.get("id") not in known or not isinstance(task.get("after"), list):
            continue
        for dep in task["after"][:AFTER_MAX]:
            if isinstance(dep, str) and dep in known:
                edges.append([dep, task["id"]])
    return edges


def _workflow_view(jobs, issues_open, tasks_text, task_ids, moment):
    """The workflow key: the newest job spans (at most WORKFLOW_SPANS, in start order, jobs older than WORKFLOW_DAYS
    dropped) and the edges: after from tasks.json, and block from open blocker issues to their tasks."""
    cutoff = moment - WORKFLOW_DAYS
    spans = []
    for job in jobs:
        start = parse_ts(job.get("started"))
        if start is None:
            continue
        last = parse_ts(job.get("ended")) if job["status"] != "running" else None
        if (last or start) < cutoff:
            continue
        spans.append((start, _span(job)))
    spans.sort(key=lambda pair: pair[0])
    block = [[issue["id"], tid] for issue in issues_open if issue["kind"] == "blocker"
             for tid in issue["tasks"] if tid in task_ids]
    return {"spans": [row for _, row in spans[-WORKFLOW_SPANS:]],
            "edges": {"after": _after_edges(tasks_text, task_ids), "block": block}}


def _issues_closed(issues_all):
    """The newest ISSUES_CLOSED_MAX closed or wontfix issues as {id, title, kind, closed} (WORK-UNIFIED section 1).
    Newest first by closed stamp, then created. The key is left out when no issue is closed (additive key)."""
    closed = [i for i in issues_all if i.get("status") in ISSUE_CLOSED]
    closed.sort(key=lambda i: i.get("closed") or i.get("created") or "", reverse=True)
    return [{"id": i["id"], "title": i["title"], "kind": i["kind"], "closed": i.get("closed")}
            for i in closed[:ISSUES_CLOSED_MAX]]


def _work_view(work_text, tasks, errors):
    """The work key (WORK-MODEL section 2, M7): one row per Work item in work.json order, {id, title, kind, status,
    prio, badges, progress: {done, total}}. Status and progress roll up from the agent tasks linked to the item
    (work.json links: task id -> work id). A linked task missing from tasks.json counts as cancelled. None when
    work.json is missing; the key is left out then (additive)."""
    if work_text is None:
        return None
    try:
        doc = json.loads(work_text)
        items, links = doc["items"], doc.get("links") or {}
        if not isinstance(items, list) or not isinstance(links, dict):
            raise ValueError("work.json has no items list")
    except (ValueError, KeyError, TypeError) as exc:
        errors.append(error_entry("work.json", exc))
        return None
    state_of = {t["id"]: t["state"] for t in tasks}
    rows = []
    for item in items:
        linked = sorted(tid for tid, wid in links.items() if wid == item.get("id"))
        done_ids = [tid for tid in linked if state_of.get(tid) == "done"]
        pending = item.get("reopenDone") is not None and done_ids == sorted(item["reopenDone"])
        stored = {"Backlog": "backlog", "Won't do": "wontfix"}.get(item.get("status"), "")
        result = workstatus.rollup({"state": stored, "reopened": pending},
                                   [{"state": state_of.get(tid, "cancelled")} for tid in linked],
                                   person_accepted=item.get("accepted") is not None)
        rows.append({"id": item.get("id"), "title": item.get("title"), "kind": item.get("kind"),
                     "status": result["status"], "prio": "P%d" % int(item.get("prio", 2)),
                     "badges": result["badges"], "progress": result["progress"]})
    return rows


def head_link_state(tasks, jobs, issues=()):
    """The link states the head fold reads: task:<id> from the task state, job:<id> as running, done or open,
    issue:<id> as open or done. A task with a running job on it reads as running, so the ask it is bound to is doing
    (HEAD-SPEC section 2: a job runs on a linked task)."""
    state = {"task:" + t["id"]: t["state"] for t in tasks if t.get("id")}
    for job in jobs:
        if job.get("id"):
            state["job:" + job["id"]] = job["status"] if job.get("status") in HEAD_JOB_LINK else "open"
        if job.get("status") == "running" and job.get("task"):
            state["task:" + job["task"]] = "running"
    for issue in issues:
        if issue.get("id"):
            state["issue:" + issue["id"]] = "open" if issue.get("status") in ISSUE_OPEN else "done"
    return state


def _resolve_links(entry, index, live_jobs):
    """The resolved links of a head row: [{ref,title,status,jobs:[{id,model,state}]}] at most HEAD_LINKED_MAX. A ref the
    snapshot does not hold is left out. jobs lists the running or queued jobs on the link: the job itself for a job
    link, the jobs whose task is the link for a task link."""
    out = []
    for ref in (entry.get("links") or [])[:HEAD_LINKED_MAX]:
        info = index.get(ref)
        if info is None:
            continue
        kind, _, ident = ref.partition(":")
        if kind == "job":
            jobs = [j for j in live_jobs if j["id"] == ident]
        elif kind == "task":
            jobs = [j for j in live_jobs if j.get("task") == ident]
        else:
            jobs = []
        item = {"ref": ref, "status": info["status"],
                "jobs": [{"id": j["id"], "model": j["model"], "state": j["status"]} for j in jobs]}
        if not out:  # only the first link carries its title; the rest keep ref, status and jobs
            item["title"] = info["title"][:HEAD_TITLE_MAX]
        out.append(item)
    return out


def _progress(entry, index):
    """{done, total} over the task links of a head row that the snapshot holds, or None when it has none."""
    refs_t = [ref for ref in entry.get("links") or [] if ref.startswith("task:") and ref in index]
    if not refs_t:
        return None
    return {"done": sum(1 for ref in refs_t if index[ref]["status"] == "done"), "total": len(refs_t)}


def head_row(entry, moment, accepted=False, suggest=None, linked=None, prog=None):
    """One head row (HEAD-SPEC section 5), also used by the API: the summary cut, age in whole minutes, and the
    flags left out when empty (stale, carried, acc and auto only when true, links only when some, more, dup and
    suggest only when set). acc: the person's last status change was done (a confirmation or an accept), given by
    accepted. auto: the fold marked it done from its links, so it waits for the head or the person to confirm.
    suggest: up to two bind refs (task:R7.31) from head.suggest_binds, given only for open unbound rows.
    linked: the resolved links (_resolve_links) and prog: {done,total} over the task links (_progress), each given
    only when set."""
    ts = head_rules.parse_ts(entry.get("ts"))
    row = {"id": entry["id"], "kind": str(entry.get("kind") or "").rstrip("?"),
           "sum": (entry.get("sum") or "")[:HEAD_SUM_MAX], "status": entry["status"],
           "age": None if ts is None else max(0, int((moment - ts).total_seconds() // 60)),
           "ts": entry.get("ts")}
    if entry.get("stale"):
        row["stale"] = True
    if entry.get("carried"):
        row["carried"] = True
    if accepted and entry["status"] == "done":
        row["acc"] = True
    if entry.get("auto_done") and entry["status"] == "done":
        row["auto"] = True
    links = entry.get("links") or []
    if links:
        row["links"] = links[:HEAD_LINKS_MAX]
        if len(links) > HEAD_LINKS_MAX:
            row["more"] = len(links) - HEAD_LINKS_MAX
    if linked:
        row["linked"] = linked
    if prog:
        row["prog"] = prog
    if entry.get("dup"):
        row["dup"] = {"id": entry["dup"]["id"], "score": entry["dup"].get("score")}
    if suggest:
        row["suggest"] = list(suggest)
    if entry.get("note"):
        row["note"] = str(entry["note"])[:HEAD_NOTE_MAX]
    return row


def _head_sessions(records):
    """now (the latest claim or start: model, acct, since, sid, usage) and prev (up to HEAD_PREV_MAX earlier ones,
    newest first, each with until = the next start). Verbatim text never appears here."""
    starts = [r for r in records if r.get("t") == "s" and r.get("ev") in ("claim", "start")]
    usage = next((r["usage"] for r in reversed(records) if r.get("t") == "s" and isinstance(r.get("usage"), dict)),
                 None)
    usage = None if usage is None else {k: usage[k] for k in ("h5", "wk") if k in usage}
    last = starts[-1] if starts else {}
    current = {"model": last.get("model"), "acct": last.get("acct"), "since": last.get("ts"),
               "sid": last.get("sid"), "usage": usage}
    prev = []
    for i in range(len(starts) - 2, -1, -1):
        if len(prev) == HEAD_PREV_MAX:
            break
        prev.append({"model": starts[i].get("model"), "acct": starts[i].get("acct"), "since": starts[i].get("ts"),
                     "until": starts[i + 1].get("ts")})
    return current, prev


def _accepted_ids(records):
    """The ids whose last status change is the person's done (a confirmation from head review, or an accept). Any
    later change, such as a reopen, clears it. Same rule as the head CLI's awaiting list."""
    last = {}
    for rec in records:
        sets = rec.get("set") if isinstance(rec.get("set"), dict) else {}
        if rec.get("t") == "u" and "status" in sets:
            last[rec.get("id")] = (sets["status"], rec.get("by"))
    return {eid for eid, mark in last.items() if mark == ("done", "person")}


def _head_size(view):
    return len(json.dumps(view, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _newest_key(entry):
    """Sort key matching the head screen (head.js sortRows): the ts as time, then the numeric id part."""
    when = head_rules.parse_ts(entry.get("ts"))
    num = int("".join(ch for ch in str(entry.get("id") or "") if ch.isdigit()) or 0)
    return (when.timestamp() if when is not None else 0, num)


def _newest(entries):
    """Entries newest first (by ts, then numeric id), so a cut keeps the recent ones."""
    return sorted(entries, key=_newest_key, reverse=True)


RULE_STATE_RANK = {"in rules": 0, "proposed": 1, "kept as context": 2}
RULE_STATE_OF = {"accepted": "in rules", "proposed": "proposed", "rejected": "kept as context",
                 "merged": "kept as context"}


def rule_state_map(proposals):
    """{Hn: ruleState} from the rule proposals (every status). An accepted proposal sourced from Hn gives "in rules",
    an open one "proposed", a rejected or merged one "kept as context"; the strongest state wins. Hn with none is
    "to review" (given by the caller)."""
    out = {}
    for p in proposals or []:
        state = RULE_STATE_OF.get(p.get("status"))
        if state is None:
            continue
        for src in p.get("sources") or []:
            if src not in out or RULE_STATE_RANK[state] < RULE_STATE_RANK[out[src]]:
                out[src] = state
    return out


def _head_view(records, link_state, moment, tasks=(), issues=(), jobs=(), issues_all=None, rule_states=None):
    """The head key: now, prev, counts and rows (newest first, open and done together, as the head screen sorts them).
    Open unbound rows get suggest from the open tasks (state todo or partial) and the open issues. Each row carries
    linked (resolved links, from tasks, issues_all and jobs) and prog. Rows are the newest HEAD_OPEN_MAX open and
    HEAD_DONE_MAX done. To fit HEAD_BYTES_MAX the link titles are dropped first, then the oldest rows. Counts match the
    rows placed. The result also has askOf (task id -> ask ids, from refs.ask_backlinks); the caller takes it out of
    the head key."""
    entries = head_rules.fold(records, link_state=link_state, now=moment)
    accepted = _accepted_ids(records)
    open_rows = [e for e in entries if e["status"] not in head_rules.CLOSED_STATUSES]
    done_rows = [e for e in entries if e["status"] == "done"]
    open_tasks = [t for t in tasks if t.get("state") in ACTIVE]
    index = {}
    for t in tasks:
        if t.get("id"):
            index["task:" + t["id"]] = {"title": str(t.get("title") or ""), "status": t.get("state")}
    for i in (issues if issues_all is None else issues_all):
        if i.get("id"):
            index["issue:" + i["id"]] = {"title": str(i.get("title") or ""), "status": i.get("status")}
    for j in jobs:
        if j.get("id"):
            index["job:" + j["id"]] = {"title": str(j.get("title") or ""), "status": j.get("status")}
    live_jobs = [j for j in jobs if j.get("status") in HEAD_JOB_STATES]

    notes = {}
    for rec in records:
        if rec.get("t") == "u" and rec.get("note") and rec.get("id"):
            notes[rec["id"]] = rec["note"]

    def row(e):
        suggest = None
        if e["status"] not in head_rules.CLOSED_STATUSES and not e["links"]:
            suggest = head_rules.suggest_binds(e["sum"], open_tasks, issues) or None
        if e["id"] in notes:
            e = dict(e, note=notes[e["id"]])
        out = head_row(e, moment, e["id"] in accepted, suggest,
                       linked=_resolve_links(e, index, live_jobs) or None, prog=_progress(e, index))
        if out["kind"] == "rule":
            out["ruleState"] = (rule_states or {}).get(e["id"], "to review")
        return out

    current, prev = _head_sessions(records)
    # (is_open, entry, row) for the newest open and newest done rows, newest first across both (the screen order).
    items = [(True, e, row(e)) for e in _newest(open_rows)[:HEAD_OPEN_MAX]]
    items += [(False, e, row(e)) for e in _newest(done_rows)[:HEAD_DONE_MAX]]
    items.sort(key=lambda it: _newest_key(it[1]), reverse=True)

    def build(pairs):
        opened = [r for is_open, _, r in pairs if is_open]
        return {
            "now": current, "prev": prev,
            "counts": {"open": len(opened),
                       "unhandled": sum(1 for r in opened if r["status"] in ("new", "understood")),
                       "doing": sum(1 for r in opened if r["status"] == "doing"),
                       "needs": sum(1 for r in opened if r["status"] == "needs-you"),
                       "doneUnacc": sum(1 for is_open, _, r in pairs if not is_open and not r.get("acc"))},
            "rows": [r for _, _, r in pairs],
        }

    view = build(items)
    if view["rows"] and _head_size(view) > HEAD_BYTES_MAX:
        for _, _, r in items:
            for item in r.get("linked") or []:
                item.pop("title", None)
        view = build(items)
    # Still too big: drop the oldest row (the last one in newest-first order) until it fits. Counts follow the rows.
    while view["rows"] and _head_size(view) > HEAD_BYTES_MAX:
        items = items[:-1]
        view = build(items)
    view["askOf"] = ref_rules.ask_backlinks(entries)
    return view


def build_snapshot(files, config, now, control=None, meters=None, rules=None, session=None, folder=None,
                   head_records=None, rev=None, usage=None, rule_proposals=None):
    """The snapshot dict. Same shape as the old server's build(), plus "project" and "schemaVersion".
    meters (WP27: limits, today, week) is added only when given, so a snapshot built without it is unchanged.
    rules (WP33b: the parsed docs/rules.txt list) is added only when given, for the same reason.
    session (R7.1 T6: presence.state(), "watching"/"open"/"none") is added only when given; any other value reads as
    "none". folder (the project folder) is added as project.path only when given, for the Copy command.
    head_records (HEAD-SPEC section 5: the raw head.jsonl records) adds the head key only when given, and askOf (task
    id -> ask ids, HEAD-SPEC section 12) with it.
    rev (the revision string, loader.revision) and usage (the usage view) add those keys only when given, as meters
    does. The loader passes both, so every served snapshot has them.
    rule_proposals (R7.103: every rule proposal dict) adds rulesProposals (the open ones, id, text, sources) only when
    some are open, and gives each Head row of kind rule its ruleState (rule_state_map).

    server_time is now in ISO 8601 with whole seconds. Parse problems go into errors[]; nothing raises.
    """
    config = config if isinstance(config, dict) else {}
    files = files if isinstance(files, dict) else {}
    moment = now if now.tzinfo else now.astimezone()
    errors = []

    # a missing jobs.json is normal (no job has run yet), so it adds no error; a bad one does
    jobs_text = files.get("jobs.json")
    if jobs_text is None:
        jobs = []
    else:
        jobs, errs = parse_jobs(jobs_text, moment)
        errors.extend(errs)

    out = {
        "server_time": moment.isoformat(timespec="seconds"),
        "errors": errors,
        "jobs": jobs,
        "project": {"id": str(config.get("id") or ""), "title": str(config.get("title") or "")},
        "schemaVersion": SNAPSHOT_SCHEMA_VERSION,
    }

    tasks_text = files.get("tasks.json")
    if tasks_text is None:
        tasks_updated, phases, tasks = "", [], []
        errors.append(_missing("tasks.json"))
    else:
        parsed, errs = parse_tasks(tasks_text)
        errors.extend(errs)
        tasks_updated, phases, tasks = parsed["updated"], parsed["phases"], parsed["tasks"]

    def cost(ts):
        return round(sum(t["tokensK"] + t["checkK"] for t in ts), 1)

    task_phase = {t["id"]: t["phase"] for t in tasks if t.get("id") and t.get("phase")}

    def phase_of(j):
        # A job's task id is looked up in tasks.json first (L-, S- and P-tasks);
        # the old "P2.17" prefix rule is the fallback.
        tid = j.get("task")
        if not tid:
            return None
        return task_phase.get(tid) or tid.split(".")[0]

    def ended_recently(j):
        e = parse_ts(j.get("ended"))
        return j["status"] != "running" and e is not None and moment - e <= RECENT_WINDOW

    running_jobs = [j for j in jobs if j["status"] == "running"]
    recent_jobs = [j for j in jobs if ended_recently(j)]

    for p in phases:
        ts = [t for t in tasks if t["phase"] == p["id"]]
        live = [t for t in ts if t["state"] not in EXCLUDED]        # deferred and backlog never count
        deferred = [t for t in ts if t["state"] == "deferred"]
        backlog = [t for t in ts if t["state"] == "backlog"]
        active = [t for t in live if t["state"] in ACTIVE]
        p["total"] = len(live)
        p["done"] = sum(1 for t in live if t["state"] == "done")
        p["deferred"] = len(deferred)
        p["deferred_k"] = cost(deferred)
        p["only_deferred"] = not live and bool(deferred)
        if backlog:                                                 # additive: only in phases with backlog tasks
            p["backlog_count"] = len(backlog)
            p["backlog_tokens_k"] = cost(backlog)
            if not live:
                p["only_backlog"] = True
        if live:
            p["progress"] = sum(PHASE_WEIGHT.get(t["state"], 0.0) for t in live) / len(live)
        elif deferred or backlog:
            p["progress"] = None                                    # shown as "deferred" or "backlog", no percent
        else:
            p["progress"] = 1.0 if p["state"] == "done" else 0.0
        p["remaining_k"] = cost(active)
        p["running"] = [j["id"] for j in running_jobs if phase_of(j) == p["id"]]
        recent = sorted((j for j in recent_jobs if phase_of(j) == p["id"]),
                        key=lambda j: parse_ts(j["ended"]), reverse=True)
        p["recent"] = [j["id"] for j in recent[:RECENT_MAX]]

    autonomy_text = files.get("autonomy.json")
    autonomy = None
    if autonomy_text is not None:
        autonomy, errs = parse_autonomy(autonomy_text)
        errors.extend(errs)

    extras, errs = parse_extras(config.get("extras"), files)
    errors.extend(errs)
    spikes, rh, nxt, log = extras["spikes"], extras["rh"], extras["next"], extras["log"]

    # "left" = todo + partial only: deferred tasks and other holds are parked, not left to do
    open_t = [t for t in tasks if t["state"] in ACTIVE]
    deferred_t = [t for t in tasks if t["state"] == "deferred"]
    backlog_t = [t for t in tasks if t["state"] == "backlog"]
    summary = {
        "tasks_total": sum(1 for t in tasks if t["state"] not in EXCLUDED),
        "tasks_left": len(open_t),
        "tokens_left_k": cost(open_t),
        "work_haiku_k": round(sum(t["tokensK"] for t in open_t if t["model"] == "haiku"), 1),
        "work_other_k": round(sum(t["tokensK"] for t in open_t if t["model"] not in ("haiku", "cursor", "agy")), 1),
        "work_cursor_k": round(sum(t["tokensK"] for t in open_t if t["model"] == "cursor"), 1),
        "work_agy_k": round(sum(t["tokensK"] for t in open_t if t["model"] == "agy"), 1),
        "check_sonnet_k": round(sum(t["checkK"] for t in open_t if t["check"] == "sonnet"), 1),
        "check_opus_k": round(sum(t["checkK"] for t in open_t if t["check"] == "opus"), 1),
        "need_user": sum(1 for t in open_t if t["needsUser"]),
        "deferred_count": len(deferred_t),
        "deferred_tokens_k": cost(deferred_t),
        "running_count": len(running_jobs),
        "autonomy": autonomy,
        "tokens_done_k": cost([t for t in tasks if t["state"] == "done"]),
        "tokens_partial_k": cost([t for t in tasks if t["state"] == "partial"]),
        "tokens_roadmap_k": cost([t for t in tasks if t["state"] not in EXCLUDED]),
        "jobs_tokens_k": round(sum(j["tokensK"] or 0 for j in jobs), 1),
        "jobs_with_tokens": sum(1 for j in jobs if j["tokensK"]),
    }
    if backlog_t:                                                   # additive: absent when no backlog task exists
        summary["backlog_count"] = len(backlog_t)
        summary["backlog_tokens_k"] = cost(backlog_t)

    def project_progress(all_tasks):
        """Whole-project progress over every task that is not deferred or backlog: done, partial, todo, percent."""
        live_all = [t for t in all_tasks if t["state"] not in EXCLUDED]
        n = len(live_all)
        done = sum(1 for t in live_all if t["state"] == "done")
        part = sum(1 for t in live_all if t["state"] == "partial")
        prog = (sum(PHASE_WEIGHT.get(t["state"], 0.0) for t in live_all) / n) if n else 0.0
        return {"done": done, "partial": part, "todo": n - done - part, "total": n, "progress": round(prog, 4)}

    def ratio(done, total):
        return {"done": done, "total": total, "ratio": round(done / total, 4) if total else 0.0}

    out.update({
        "tasks_updated": tasks_updated,
        "summary": summary,
        "overall": {
            "project": project_progress(tasks),
            "phases": ratio(sum(1 for p in phases if p["state"] == "done"), len(phases)),
            "spikes": ratio(sum(1 for s in spikes if s["state"] == "done"), len(spikes)),
            "rh": ratio(sum(1 for r in rh if r["state"] == "done"), len(rh)),
        },
        "phases": phases,
        "tasks": tasks,
        "spikes": spikes,
        "rh": rh,
        "next": nxt,
        "log": log,
    })

    # WP20 keys. A project without the new files gets them empty (budget gets {} when budget.json is missing).
    issues_all = _read_optional(files, "issues.json", parse_issues, errors) or []
    questions_all = _read_optional(files, "questions.json", parse_questions, errors) or []
    comments_all = _read_optional(files, "comments.json", parse_comments, errors) or []
    queue_all = _read_optional(files, "queue.json", parse_queue, errors) or []
    activity_all = _read_optional(files, "activity.jsonl", parse_activity, errors) or []
    budget_doc = _read_optional(files, "budget.json", parse_budget, errors)

    issues_open = [i for i in issues_all if i["status"] in ISSUE_OPEN]
    questions_open = [q for q in questions_all if q["status"] == "open"]
    blocked = sorted({tid for i in issues_open if i["kind"] == "blocker" for tid in i["tasks"]})
    by_target = {}
    for comment in comments_all:
        by_target.setdefault(comment["on"], []).append(comment)
    needs_you = ([{"kind": "task", "id": t["id"], "title": t["title"]}
                  for t in tasks if t["needsUser"] and t["state"] in ACTIVE]
                 + [{"kind": "question", "id": q["id"], "text": q["text"]} for q in questions_open if q["block"]])
    running_ids = {j["id"] for j in running_jobs}
    running_rows = [{"id": j["id"], "title": j["title"], "model": j["model"], "task": j["task"],
                     "role": j.get("role"), "parent": j.get("parent"), "effort": j.get("effort"),
                     "engine_model": j.get("engine_model"), "elapsed_s": j["elapsed_s"],
                     "tokensK": j["tokensK"]} for j in running_jobs]
    groups = {}
    for j in running_jobs:
        if j.get("parent") in running_ids:
            groups.setdefault(j["parent"], []).append(j["id"])
    out.update({
        "workflow": _workflow_view(jobs, issues_open, tasks_text, {t["id"] for t in tasks}, moment),
        "issues": issues_open,
        "questions": questions_open,
        "comments": {target: rows[-COMMENTS_SHOWN:] for target, rows in by_target.items()},
        "budget": {} if budget_doc is None else _budget_view(budget_doc, tasks, phases),
        "features": _features_view(files.get("features.json"), tasks, jobs, issues_open, errors),
        "blocked": blocked,
        "needsYou": needs_you,
        "agents": {"running": running_rows, "groups": groups,
                   "roots": [j["id"] for j in running_jobs if j.get("parent") not in running_ids]},
        "control": {} if control is None else control,
        "queue": queue_all,
        "activity": activity_all[-ACTIVITY_SHOWN:],
    })
    closed = _issues_closed(issues_all)
    if closed:
        out["issuesClosed"] = closed
    work = _work_view(files.get("work.json"), tasks, errors)
    if work is not None:
        out["work"] = work
    if meters is not None:
        out["meters"] = meters
    if rules is not None:
        out["rules"] = rules
    if session is not None:
        out["session"] = session if session in SESSION_STATES else "none"
    if folder is not None:
        out["project"]["path"] = str(folder)
    if head_records is not None:
        head = _head_view(head_records, head_link_state(tasks, jobs, issues_all), moment, tasks=tasks,
                          issues=issues_open, jobs=jobs, issues_all=issues_all,
                          rule_states=rule_state_map(rule_proposals))
        out["askOf"] = head.pop("askOf")
        out["head"] = head
    opened = [p for p in rule_proposals or [] if p.get("status") == "proposed"]
    if opened:
        out["rulesProposals"] = [{"id": p.get("id"), "text": p.get("text"), "sources": list(p.get("sources") or [])}
                                 for p in opened]
    if rev is not None:
        out["rev"] = rev
    if usage is not None:
        out["usage"] = usage
    return out
