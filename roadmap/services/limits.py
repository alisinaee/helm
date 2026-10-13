"""Limit rows (WP27): the rules that stop agents when a window of usage is used up. Specified in docs/UI-SPEC.md 2b.

A row is {id, scope: global|project, window: day|week|total, kind: pct|tok|acct, value, action: block|warn}.
    pct  percentage points of the account's weekly allowance used by the scope in a day or week (measured for
         global rows, estimated from tracked tokens for project rows; services/ledger.py)
    tok  thousands of tokens, exact from `job done --tokens` (day or week; a project total is window total)
    acct the stop on the whole-account weekly meter (autonomy.json limit.stopAtPercent)

Where rows live: global rows in the global config under "limits"; project rows in budget.json under "limitRows".
Two rows are read through from their own stores and are not copied: AUTO (autonomy.json stopAtPercent) and BUD (the
project budget in budget.json). evaluate() gives each row a state: ok, warn (80% or more), block (100% or more, only
for action block) or unknown. Unknown never blocks. A failure of the whole evaluation is ok and is logged once a minute.
"""

import datetime
import os
import re
import time

from roadmap.errors import EXIT_INVALID_DATA, EXIT_NOT_FOUND, EXIT_USAGE, RoadmapError
from roadmap.log import get_logger
from roadmap.services import budget, jobs, ledger, records
from roadmap.store import atomic, config as config_store, lock, paths, schema

SCOPES = ("global", "project")
WINDOWS = ("day", "week", "total")
KINDS = ("pct", "tok", "acct")
ACTIONS = ("block", "warn")
WARN_PCT = 80.0
BLOCK_PCT = 100.0
USAGE_STALE_S = 1800
LOG_EVERY_S = 60
AUTO_ID = "AUTO"
BUDGET_ID = "BUD"
STORED_ID = re.compile(r"^L[0-9]+$")
ANY_ID = re.compile(r"^(L[0-9]+|AUTO|BUD)$")
RANK = {"block": 3, "warn": 2, "ok": 1, "unknown": 0}
WORDS = {"block": "BLOCK", "warn": "WARN", "ok": "ok", "unknown": "unknown"}

log = get_logger("services.limits")
_logged = [0.0]


def _usage(message, next_cmd="roadmap limit show"):
    return RoadmapError("usage", message, EXIT_USAGE, next=next_cmd)


def _num(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value == value


def _now(now):
    if now is None:
        return datetime.datetime.now().astimezone()
    return now if now.tzinfo is not None else now.astimezone()


def _log_once(text):
    """Log a fail-open event at most once a minute."""
    moment = time.monotonic()
    if moment - _logged[0] >= LOG_EVERY_S:
        _logged[0] = moment
        log.warning("%s", text)


def _fmt(value):
    if value is None:
        return "?"
    if isinstance(value, float) and not float(value).is_integer():
        return ("%.1f" % value).rstrip("0").rstrip(".")
    return str(int(value))


def _unit(row):
    return "k" if row["kind"] == "tok" else "%"


# ------------------------------------------------------------------ the row fields

def check_spec(scope, window, kind, value, action="block"):
    """The checked fields of a row, or a usage error. Allowed: global pct and tok on day or week; project pct on day
    or week, tok on day, week or total, and acct on week (the weekly stop)."""
    if scope not in SCOPES:
        raise _usage("scope must be global or project")
    if window not in WINDOWS:
        raise _usage("window must be day, week or total")
    if kind not in KINDS:
        raise _usage("kind must be pct, tok or acct")
    if action not in ACTIONS:
        raise _usage("action must be block or warn")
    if not _num(value):
        raise _usage("value must be a number")
    number = float(value)
    if kind == "acct":
        if scope != "project" or window != "week":
            raise _usage("the weekly stop is a project row: --scope project --window week")
        if not 1 <= number <= 100:
            raise _usage("the weekly stop takes a percent from 1 to 100")
        number = int(number) if number.is_integer() else round(number, 1)
    elif kind == "pct":
        if window not in ("day", "week"):
            raise _usage("a pct row uses window day or week")
        if not 0 < number <= 100:
            raise _usage("a pct row takes a percent above 0 up to 100")
        number = round(number, 1)
    else:
        if scope == "global" and window == "total":
            raise _usage("a global tok row uses window day or week")
        if number <= 0:
            raise _usage("a tok row takes thousands of tokens above 0")
        number = round(number, 1)
    return {"scope": scope, "window": window, "kind": kind, "value": number, "action": action}


def _clean_row(item, scope, src):
    """A stored row as a dict, or None when it is not a valid row."""
    if not isinstance(item, dict) or not isinstance(item.get("id"), str):
        return None
    if not STORED_ID.match(item["id"]) or item.get("window") not in WINDOWS or item.get("kind") not in KINDS:
        return None
    if item.get("action") not in ACTIONS or not _num(item.get("value")):
        return None
    row = {"id": item["id"], "scope": scope, "window": item["window"], "kind": item["kind"],
           "value": item["value"], "action": item["action"], "src": src}
    for key in ("setBy", "setOn"):
        if isinstance(item.get(key), str):
            row[key] = item[key]
    return row


def _bud_row(value, action):
    return {"id": BUDGET_ID, "scope": "project", "window": "total", "kind": "tok", "value": value,
            "action": action, "src": "budget"}


def _auto_row(limit):
    """The autonomy stop as a row, from the limit block of autonomy.json, or None when it is not set."""
    if not isinstance(limit, dict) or not _num(limit.get("stopAtPercent")):
        return None
    action = "warn" if limit.get("action") == "warn" else "block"
    return {"id": AUTO_ID, "scope": "project", "window": "week", "kind": "acct", "value": limit["stopAtPercent"],
            "action": action, "src": "autonomy"}


def label(row):
    """A short name of a row for the activity line, e.g. L3 global day pct 2% block."""
    return "%s %s %s %s %s%s %s" % (row["id"], row["scope"], row["window"], row["kind"], _fmt(row["value"]),
                                    _unit(row), row["action"])


# ------------------------------------------------------------------ reading the stores

def global_rows():
    """The global rows from the global config, valid ones only."""
    raw = config_store.load().get("limits")
    if not isinstance(raw, list):
        return []
    return [row for row in (_clean_row(item, "global", "config") for item in raw) if row is not None]


def _project_state(data_dir):
    """(budget document, stored project rows, BUD row or None, AUTO row or None). Nothing when the folder is missing."""
    if not os.path.isdir(data_dir):
        return None, [], None, None
    doc = budget.get(data_dir)
    stored = [row for row in (_clean_row(item, "project", "limits") for item in doc["limitRows"]) if row is not None]
    bud = None
    if doc["limits"].get("project") is not None:
        bud = _bud_row(doc["limits"]["project"], "warn" if doc.get("limitAction") == "warn" else "block")
    return doc, stored, bud, _autonomy_row(data_dir)


def _autonomy_row(data_dir):
    path = os.path.join(data_dir, "autonomy.json")
    data, error = schema.read_data("autonomy", path)
    if error is not None:
        raise RoadmapError("newer_schema", error["message"], EXIT_INVALID_DATA)
    return _auto_row((data or {}).get("limit"))


def _usage_state(moment):
    """(weekly percent or None, fresh). Fresh means the stored reading is at most USAGE_STALE_S old."""
    try:
        data = atomic.read_json(paths.usage_file(), default=None)
    except RoadmapError:
        return None, False
    if not isinstance(data, dict):
        return None, False
    weekly = data.get("weeklyPercent")
    if not _num(weekly):
        return None, False
    age = _age(data.get("updated"), moment)
    return float(weekly), age is not None and age <= USAGE_STALE_S


def _age(text, moment):
    if not isinstance(text, str):
        return None
    try:
        stamp = datetime.datetime.fromisoformat(text)
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.astimezone()
    return (moment - stamp).total_seconds()


# ------------------------------------------------------------------ evaluation

class _Context(object):
    """What one evaluation reads once: the usage reading, the ledger and the project budget."""

    def __init__(self, project_id, bud, moment):
        self.pid = project_id
        self.now = moment
        self.weekly, fresh = _usage_state(moment)
        self.doc, self.ledger_status = ledger.read()
        self.pct_ok = fresh and self.ledger_status == "ok"
        self.spent_total = None
        if bud is not None:
            self.spent_total = round(sum(sum(models.values()) for models in bud["spent"].values()), 1)


def _measure(row, ctx):
    """(used, estimated) for a row. used is None when the row cannot be measured now."""
    kind, window, scope = row["kind"], row["window"], row["scope"]
    if kind == "tok":
        if row["src"] == "budget":
            return ctx.spent_total, False
        if ctx.ledger_status == "corrupt":
            return None, False
        return ledger.tokens_k(ctx.doc, ctx.pid if scope == "project" else None, window, ctx.now), False
    if not ctx.pct_ok:
        return None, False
    if kind == "acct":
        return ctx.weekly, False
    if scope == "global":
        if window == "day":
            return ledger.daily_points(ctx.doc, ctx.now), False
        return ctx.weekly, False
    estimate = ledger.project_estimate(ctx.doc, ctx.pid, window, ctx.now)
    return estimate, estimate is not None


def _ratio(used, limit):
    if limit <= 0:
        return 100.0 if used > 0 else 0.0
    return used / float(limit) * 100.0


def _state(used, ratio, action):
    if used is None:
        return "unknown"
    if ratio >= BLOCK_PCT:
        return "block" if action == "block" else "warn"
    if ratio >= WARN_PCT:
        return "warn"
    return "ok"


def _pace_at(row, used, ctx):
    """The local time the measured usage reaches the limit at the pace of the last two hours, or None. It is counted
    from the newest reading, not from now, so the value does not move between readings."""
    if used is None or row["kind"] == "tok" or ctx.ledger_status != "ok":
        return None
    if row["kind"] == "pct" and row["scope"] == "project":
        return None  # an estimate has no pace of its own
    field = "pts" if row["kind"] == "pct" and row["window"] == "day" and row["scope"] == "global" else "w"
    slope = ledger.pace_per_hour(ctx.doc, ctx.now, field)
    anchor = ledger.last_reading(ctx.doc)
    remaining = float(row["value"]) - used
    if slope is None or slope <= 0 or remaining <= 0 or anchor is None:
        return None
    return (anchor + datetime.timedelta(hours=remaining / slope)).isoformat(timespec="seconds")


def _judge(row, used, est, ctx):
    ratio = None if used is None else _ratio(used, float(row["value"]))
    out = dict(row)
    out.update({"used": None if used is None else round(used, 1), "limit": row["value"],
                "pct": None if ratio is None else round(ratio, 1), "state": _state(used, ratio or 0.0,
                                                                                     row["action"]),
                "est": bool(est), "paceAt": _pace_at(row, used, ctx)})
    return out


def _evaluate_rows(project, moment):
    data_dir = jobs.data_dir_of(project)
    doc, stored, bud, auto = _project_state(data_dir)
    rows = global_rows() + stored + [row for row in (bud, auto) if row is not None]
    ctx = _Context(project["id"], doc, moment)
    out = []
    for row in rows:
        used, est = _measure(row, ctx)
        out.append(_judge(row, used, est, ctx))
    return out


def evaluate_rows(project, now=None, strict=False):
    """Every row that applies to a project (global, its own and the read-through rows), each with its state.

    Never raises unless strict: a failure gives an empty list, which means ok (fail open), and is logged once a minute.
    """
    moment = _now(now)
    try:
        return _evaluate_rows(project, moment)
    except Exception as exc:
        if strict:
            raise
        _log_once("limits: could not evaluate the limit rows of %s (%s); allowing"
                  % (project.get("id"), type(exc).__name__))
        return []


def evaluate(project, now=None):
    """The worst row of a project: {state ok|warn|block|unknown, row, used, limit}. No rows is ok."""
    rows = evaluate_rows(project, now)
    if not rows:
        return {"state": "ok", "row": None, "used": None, "limit": None}
    worst = max(rows, key=lambda row: RANK[row["state"]])
    return {"state": worst["state"], "row": worst, "used": worst["used"], "limit": worst["limit"]}


def describe(row):
    """The reason line of a row that warns or blocks (the words the hooks and the status show)."""
    if row["id"] == AUTO_ID:
        if row["state"] == "block":
            return "weekly usage %d%% reached stopAtPercent %d%%" % (int(row["used"]), int(row["limit"]))
        return "weekly usage at %d%%" % int(row["used"])
    if row["id"] == BUDGET_ID:
        pct = int(row["pct"])
        return ("project budget %d%% used" % pct) if row["state"] == "block" else ("project budget at %d%%" % pct)
    where = "%s %s" % (row["scope"], row["window"])
    if row["kind"] == "tok":
        text = "%s token limit %s: %sk of %sk" % (where, row["id"], _fmt(row["used"]), _fmt(row["limit"]))
    else:
        verb = "reached at" if row["state"] == "block" else "at"
        text = "%s limit %s %s %d%%" % (where, row["id"], verb, int(row["pct"]))
    return text


def meters(project, now=None):
    """The snapshot's meters: limits (the rows, compact), today and week (the day's points and tracked tokens)."""
    moment = _now(now)
    rows = evaluate_rows(project, moment)
    doc, status = ledger.read()
    weekly, _ = _usage_state(moment)
    pid = project["id"]
    readable = status != "corrupt"
    return {
        "limits": [{"id": r["id"], "scope": r["scope"], "window": r["window"], "kind": r["kind"], "used": r["used"],
                    "limit": r["limit"], "state": r["state"], "est": r["est"], "paceAt": r["paceAt"],
                    "src": r["src"]} for r in rows],
        "today": {"pts": round(ledger.daily_points(doc, moment), 1) if readable else None,
                  "tokK": ledger.tokens_k(doc, pid, "day", moment) if readable else None,
                  "estPts": ledger.project_estimate(doc, pid, "day", moment) if readable else None},
        "week": {"pct": weekly,
                 "tokK": ledger.tokens_k(doc, pid, "week", moment) if readable else None,
                 "estPts": ledger.project_estimate(doc, pid, "week", moment) if readable else None},
    }


def list_rows(project):
    """The rows that apply to a project, without evaluation: global, its own, and the read-through AUTO and BUD."""
    data_dir = jobs.data_dir_of(project)
    _, stored, bud, auto = _project_state(data_dir)
    return global_rows() + stored + [row for row in (bud, auto) if row is not None]


def add(project, scope, window, kind, value, action="block", now=None):
    """Add or replace a row (the same scope, window and kind). Returns (prior, saved). Same as write_row."""
    spec = check_spec(scope, window, kind, value, action)
    return write_row(project, jobs.data_dir_of(project), spec, now=now)


def rm(project, row_id, now=None):
    """Remove a row by id. Returns the removed row."""
    return remove_row(project, jobs.data_dir_of(project), row_id, now=now)


def _amount_text(row):
    """used/limit with its unit, e.g. 62/60% or 4.1/10%; an estimate has a leading mark."""
    mark = "≈" if row["est"] else ""
    return "%s%s/%s%s" % (mark, _fmt(row["used"]), _fmt(row["limit"]), _unit(row))


def status_line(rows):
    """The one-line `limits:` entry of status: the three worst rows, e.g. limits: day 4/10% ok; week 62/60% BLOCK."""
    if not rows:
        return "limits: none set"
    ordered = sorted(rows, key=lambda r: -RANK[r["state"]])
    parts = ["%s %s %s" % (r["window"], _amount_text(r), WORDS[r["state"]]) for r in ordered[:3]]
    more = len(rows) - 3
    return "limits: " + "; ".join(parts) + (" (+%d more)" % more if more > 0 else "")


def _show_line(row):
    text = "%s %s %s %s %s" % (row["id"], row["scope"], row["window"], _amount_text(row), WORDS[row["state"]])
    if row["src"] in ("autonomy", "budget"):
        text += " (%s)" % row["src"]
    if row["paceAt"]:
        text += " pace hits limit %s" % row["paceAt"][11:16]
    return text


def show_lines(rows, limit=8):
    """The text of limit show: one line per row, at most eight lines."""
    if not rows:
        return ["no limits set (for example: roadmap limit set --scope global --window day --pct 10)"]
    lines = [_show_line(row) for row in rows]
    if len(lines) > limit:
        lines = lines[:limit - 1] + ["(+%d more rows)" % (len(lines) - limit + 1)]
    return lines


# ------------------------------------------------------------------ writing the rows

def _taken_ids(data_dir):
    """Every row id already in use (global config and this project), so a new row gets a free one."""
    taken = {str(item.get("id")) for item in (config_store.load().get("limits") or []) if isinstance(item, dict)}
    if os.path.isdir(data_dir):
        taken |= {str(item.get("id")) for item in budget.get(data_dir)["limitRows"] if isinstance(item, dict)}
    return taken


def _next_id(taken):
    best = 0
    for item in taken:
        if STORED_ID.match(item):
            best = max(best, int(item[1:]))
    return "L%d" % (best + 1)


def _same_key(item, spec):
    return isinstance(item, dict) and item.get("window") == spec["window"] and item.get("kind") == spec["kind"]


def _stored(spec, rid, moment):
    return {"id": rid, "scope": spec["scope"], "window": spec["window"], "kind": spec["kind"],
            "value": spec["value"], "action": spec["action"], "setBy": "roadmap", "setOn": moment.date().isoformat()}


def write_row(project, data_dir, spec, row_id=None, now=None):
    """Store a checked row. Returns (prior row or None, the saved row). The same scope, window and kind replace the
    row that is there, so one row per key. row_id is kept when given and free (undo of a removal)."""
    moment = _now(now)
    if spec["kind"] == "acct":
        return _write_autonomy(data_dir, spec, moment)
    if spec["kind"] == "tok" and spec["scope"] == "project" and spec["window"] == "total":
        return _write_budget(data_dir, spec)
    records.require_dir(data_dir)
    taken = _taken_ids(data_dir)
    if spec["scope"] == "global":
        def mutate_global(items):
            index = next((i for i, item in enumerate(items) if _same_key(item, spec)), None)
            return _put(items, index, spec, row_id, taken | _raw_ids(items), moment)

        return config_store.update_limits(mutate_global)

    def mutate_project(doc):
        items = doc["limitRows"]
        index = next((i for i, item in enumerate(items) if _same_key(item, spec)), None)
        return _put(items, index, spec, row_id, taken | _raw_ids(items), moment)

    return budget.update(data_dir, mutate_project)


def _raw_ids(items):
    return {str(item.get("id")) for item in items if isinstance(item, dict)}


def _put(items, index, spec, row_id, taken, moment):
    """Replace items[index] or append a new row. Returns (prior, saved)."""
    if index is not None:
        prior = _clean_row(items[index], spec["scope"], "config" if spec["scope"] == "global" else "limits")
        rid = items[index]["id"]
    else:
        prior = None
        rid = row_id if (row_id and STORED_ID.match(row_id) and row_id not in taken) else _next_id(taken)
    saved = _stored(spec, rid, moment)
    if index is not None:
        items[index] = saved
    else:
        items.append(saved)
    return prior, _clean_row(saved, spec["scope"], "config" if spec["scope"] == "global" else "limits")


def _autonomy_path(data_dir):
    return os.path.join(data_dir, "autonomy.json")


def _write_autonomy(data_dir, spec, moment):
    """The weekly stop: autonomy.json limit.stopAtPercent (as `limit set <pct>` always wrote it). A warn action adds
    limit.action; a block leaves the file exactly as before."""
    records.require_dir(data_dir)
    path = _autonomy_path(data_dir)
    with lock.locked(data_dir):
        data, error = schema.read_data("autonomy", path)
        if error is not None:
            raise RoadmapError("newer_schema", error["message"], EXIT_INVALID_DATA)
        doc = dict(data or {})
        limit = dict(doc.get("limit") or {})
        prior = _auto_row(limit)
        limit.update({"stopAtPercent": spec["value"], "setBy": "roadmap", "setOn": moment.date().isoformat()})
        if spec["action"] == "warn":
            limit["action"] = "warn"
        else:
            limit.pop("action", None)
        doc["limit"] = limit
        schema.write_data("autonomy", path, doc)
    return prior, _auto_row(limit)


def _write_budget(data_dir, spec):
    prior_value, prior_action = budget.set_project_limit(data_dir, spec["value"], spec["action"])
    prior = None if prior_value is None else _bud_row(prior_value, "warn" if prior_action == "warn" else "block")
    return prior, _bud_row(spec["value"], spec["action"])


def remove_row(project, data_dir, row_id, now=None):
    """Remove a row by id (L3, AUTO or BUD) and return it. AUTO removes the weekly stop from autonomy.json; BUD clears
    the project budget. Raises not_found when there is no such row."""
    if not ANY_ID.match(str(row_id or "")):
        raise _usage("row id '%s' looks like L3, AUTO or BUD" % row_id)
    records.require_dir(data_dir)
    if row_id == AUTO_ID:
        return _remove_autonomy(data_dir, row_id)
    if row_id == BUDGET_ID:
        bud = budget.get(data_dir)["limits"].get("project")
        if bud is None:
            raise RoadmapError("not_found", "no project budget to remove", EXIT_NOT_FOUND, next="roadmap limit show")
        prior = _bud_row(bud, "block")
        budget.set_project_limit(data_dir, None)
        return prior

    def mutate_project(doc):
        items = doc["limitRows"]
        index = next((i for i, item in enumerate(items) if isinstance(item, dict) and item.get("id") == row_id), None)
        if index is None:
            return None
        return _clean_row(items.pop(index), "project", "limits")

    removed = budget.update(data_dir, mutate_project)
    if removed is not None:
        return removed

    def mutate_global(items):
        index = next((i for i, item in enumerate(items) if isinstance(item, dict) and item.get("id") == row_id), None)
        if index is None:
            return None
        return _clean_row(items.pop(index), "global", "config")

    removed = config_store.update_limits(mutate_global)
    if removed is None:
        raise RoadmapError("not_found", "no limit row " + row_id, EXIT_NOT_FOUND, next="roadmap limit show")
    return removed


def _remove_autonomy(data_dir, row_id):
    path = _autonomy_path(data_dir)
    with lock.locked(data_dir):
        data, error = schema.read_data("autonomy", path)
        if error is not None:
            raise RoadmapError("newer_schema", error["message"], EXIT_INVALID_DATA)
        doc = dict(data or {})
        limit = dict(doc.get("limit") or {})
        prior = _auto_row(limit)
        if prior is None:
            raise RoadmapError("not_found", "no weekly stop to remove " + row_id, EXIT_NOT_FOUND,
                               next="roadmap limit show")
        limit.pop("stopAtPercent", None)
        limit.pop("action", None)
        doc["limit"] = limit
        schema.write_data("autonomy", path, doc)
    return prior
