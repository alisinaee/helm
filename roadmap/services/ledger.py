"""Usage ledger (WP27): the global ledger.json of measured account points and of each project's tracked tokens.

Two kinds of entry feed it. A usage reading (services/usage.py) adds the points used since the previous reading of the
weekly window. A finished job (services/budget.py) adds its thousands of tokens to its project for the day it ends.

    days[YYYY-MM-DD] = {pts, lastW, firstAt, lastAt, tok: {project: K}}
    recent           = [[epoch seconds, weekly percent, that day's points], ...]  (the last two hours)

The file keeps 14 local days and the newest readings, and stays at 4 KB or less. A corrupt file is moved aside to
ledger.json.corrupt and started again: the ledger is derived data. Python 3 standard library only.

Derivation of the points: a reading w adds w - lastW when w >= lastW. A drop of WEEKLY_RESET_DROP points or more is the
weekly window reset and adds w. A smaller drop is a jittery reading (two writers, rounding): it adds nothing and keeps
lastW. lastW is the last reading before the local midnight, so the first reading of a day is compared with yesterday's.
The first reading ever adds nothing, because nothing is known before it. A weekly percent below 0 or above
WEEKLY_MAX_PCT is refused; above 100 is a real over-allowance reading and is kept.
"""

import datetime
import json
import math
import os

from roadmap.errors import RoadmapError
from roadmap.log import get_logger
from roadmap.store import atomic, config as config_store, lock, paths

FILE = "ledger.json"
VERSION = 1
DAYS_KEEP = 14
CALIBRATION_DAYS = 7
MIN_TRACKED_K = 200.0          # no project estimate until this many thousand tokens are tracked
MAX_BYTES = 4096
PACE_WINDOW_S = 7200           # the pace projection looks at the last two hours
PACE_MIN_SPAN_S = 600          # and needs at least ten minutes of readings
RECENT_MAX = 36
OTHER = "_other"               # tokens of projects folded together to keep the file small (see _fit)
WEEKLY_MAX_PCT = 1000.0         # a sane bound: above 100 is possible (over the allowance), a value this big is not
WEEKLY_RESET_DROP = 10.0       # a fall of at least this many points is a weekly reset; less is a jitter

log = get_logger("services.ledger")


def path():
    return os.path.join(paths.state_dir(), FILE)


def _local(moment):
    """An aware local datetime; now() when moment is None."""
    if moment is None:
        return datetime.datetime.now().astimezone()
    return moment if moment.tzinfo is not None else moment.astimezone()


def _empty():
    return {"schemaVersion": VERSION, "days": {}, "recent": []}


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _valid(doc):
    """True when a parsed ledger has the shape this build writes."""
    if not isinstance(doc, dict) or doc.get("schemaVersion") != VERSION:
        return False
    days = doc.get("days")
    recent = doc.get("recent")
    if not isinstance(days, dict) or not isinstance(recent, list):
        return False
    for key, row in days.items():
        if not isinstance(key, str) or not isinstance(row, dict):
            return False
        last_w = row.get("lastW")
        toks = row.get("tok")
        if not _number(row.get("pts")) or not (last_w is None or _number(last_w)) or not isinstance(toks, dict):
            return False
        if not all(_number(v) for v in toks.values()):
            return False
    for entry in recent:
        if not isinstance(entry, list) or len(entry) != 3 or not all(_number(v) for v in entry):
            return False
    return True


def read(file_path=None):
    """(doc, status). status is ok, missing or corrupt. A corrupt or unreadable file is never raised."""
    where = file_path or path()
    if not os.path.exists(where):
        return _empty(), "missing"
    try:
        raw = atomic.read_json(where)
    except (RoadmapError, OSError):
        return _empty(), "corrupt"
    if not _valid(raw):
        return _empty(), "corrupt"
    return raw, "ok"


def _load_for_write(where):
    doc, status = read(where)
    if status == "corrupt":
        os.replace(where, where + ".corrupt")
        log.warning("usage ledger was corrupt; moved aside to %s and started again", where + ".corrupt")
        return _empty()
    return doc


def _new_day(moment):
    stamp = moment.isoformat(timespec="seconds")
    return {"pts": 0.0, "lastW": None, "firstAt": stamp, "lastAt": stamp, "tok": {}}


def _day_key(day):
    return day.isoformat()


def _keys(moment, window):
    """The local day keys a window covers: today for day, the last seven days for week."""
    today = _local(moment).date()
    count = 1 if window == "day" else CALIBRATION_DAYS
    return [_day_key(today - datetime.timedelta(days=i)) for i in range(count)]


def _baseline(days, today):
    """The weekly percent the first reading of today is compared with: today's last reading, else the newest earlier
    day's last reading (the carry across midnight). None when nothing is known yet."""
    row = days.get(today)
    if row is not None and row.get("lastW") is not None:
        return float(row["lastW"])
    for key in sorted(days, reverse=True):
        if key < today and days[key].get("lastW") is not None:
            return float(days[key]["lastW"])
    return None


def _prune(doc, moment):
    today = _local(moment).date()
    oldest = today - datetime.timedelta(days=DAYS_KEEP - 1)
    keep = {}
    for key, row in doc["days"].items():
        try:
            day = datetime.date.fromisoformat(key)
        except ValueError:
            continue
        if day >= oldest:
            keep[key] = row
    doc["days"] = keep
    cutoff = _local(moment).timestamp() - PACE_WINDOW_S
    doc["recent"] = [e for e in doc["recent"] if e[0] >= cutoff][-RECENT_MAX:]


def _size(doc):
    return len(json.dumps(doc, separators=(",", ":"), sort_keys=True).encode("utf-8")) + 1


def _fit(doc, moment):
    """Trim the readings, then the oldest days outside the current week, until the file is within MAX_BYTES. The days
    of the week stay whole, so the week's tracked tokens and points are never lost. If the week still does not fit,
    the tokens of its oldest day are folded into one "_other" entry (the total stays right, the per-project split
    does not)."""
    keep = set(_keys(moment, "week"))
    while _size(doc) > MAX_BYTES:
        if len(doc["recent"]) > 4:
            doc["recent"] = doc["recent"][len(doc["recent"]) // 2:]
            continue
        outside = [key for key in doc["days"] if key not in keep]
        if outside:
            del doc["days"][min(outside)]
            continue
        if not _fold_oldest_tokens(doc):
            break
    return doc


def _fold_oldest_tokens(doc):
    """Merge the per-project tokens of the oldest week day that still has named projects into its "_other" entry.
    Returns False when there is nothing left to merge."""
    for key in sorted(doc["days"]):
        toks = doc["days"][key]["tok"]
        named = [name for name in toks if name != OTHER]
        if named:
            toks[OTHER] = round(sum(toks[name] for name in named) + float(toks.get(OTHER, 0.0)), 1)
            for name in named:
                del toks[name]
            return True
    return False


def _save(where, doc, moment):
    atomic.write_text(where, json.dumps(_fit(doc, moment), separators=(",", ":"), sort_keys=True) + "\n")


def record_reading(weeklyPct, fiveHourPct=None, now=None, file_path=None):
    """Add one usage reading. Returns the points of today after the reading, or None when there is no weekly percent.

    fiveHourPct is accepted for the reading's full shape and is not used yet (the 5-hour window is LATER).
    """
    if not _number(weeklyPct) or not 0 <= float(weeklyPct) <= WEEKLY_MAX_PCT:
        return None
    moment = _local(now)
    today = _day_key(moment.date())
    where = file_path or path()
    stamp = moment.isoformat(timespec="seconds")
    w = float(weeklyPct)
    with lock.locked(paths.ensure_dir(paths.state_dir())):
        doc = _load_for_write(where)
        days = doc["days"]
        base = _baseline(days, today)
        if base is None:
            added = 0.0
        elif w >= base:
            added = w - base
        elif base - w >= WEEKLY_RESET_DROP:
            added = w  # the weekly window reset
        else:
            added, w = 0.0, base  # a jittery reading: nothing added, lastW stays where it was
        row = days.get(today) or _new_day(moment)
        row["pts"] = round(float(row["pts"]) + added, 2)
        row["lastW"] = w
        row["lastAt"] = stamp
        days[today] = row
        doc["recent"] = doc["recent"] + [[int(moment.timestamp()), w, row["pts"]]]
        _prune(doc, moment)
        _save(where, doc, moment)
    return row["pts"]


def record_spend(project, K, now=None, file_path=None):
    """Add a finished job's thousands of tokens to its project for the day it ends. Returns the project's K today."""
    amount = float(K)
    if not project or amount <= 0:
        return None
    moment = _local(now)
    today = _day_key(moment.date())
    where = file_path or path()
    with lock.locked(paths.ensure_dir(paths.state_dir())):
        doc = _load_for_write(where)
        row = doc["days"].get(today) or _new_day(moment)
        row["tok"][project] = round(float(row["tok"].get(project, 0.0)) + amount, 1)
        doc["days"][today] = row
        _prune(doc, moment)
        _save(where, doc, moment)
    return row["tok"][project]


def project_id_for_dir(data_dir):
    """The registered project whose data folder is data_dir, or None."""
    want = os.path.abspath(data_dir)
    for entry in config_store.list_projects():
        folder = os.path.join(os.path.abspath(entry.get("path", "")), entry.get("dataDir") or config_store.DEFAULT_DATA_DIR)
        if folder == want:
            return entry["id"]
    return None


def daily_points(doc, now=None):
    """The measured account points of today (global, all Claude use on the account)."""
    row = doc["days"].get(_day_key(_local(now).date()))
    return float(row["pts"]) if row else 0.0


def tokens_k(doc, project_id, window, now=None):
    """Thousands of tokens tracked for a project (None for every project) in a day or week window."""
    total = 0.0
    for key in _keys(now, window):
        row = doc["days"].get(key)
        if not row:
            continue
        toks = row["tok"]
        total += sum(toks.values()) if project_id is None else float(toks.get(project_id, 0.0))
    return round(total, 1)


def rate(doc, now=None):
    """Points per thousand tokens over the last seven days, or None while fewer than MIN_TRACKED_K are tracked."""
    pts = 0.0
    tracked = 0.0
    for key in _keys(now, "week"):
        row = doc["days"].get(key)
        if not row:
            continue
        pts += float(row["pts"])
        tracked += sum(row["tok"].values())
    if tracked < MIN_TRACKED_K:
        return None
    return pts / tracked


def project_estimate(doc, project_id, window, now=None):
    """The points a project used in a window, estimated as its tracked tokens times the calibration rate. None when
    there is no rate yet."""
    per_k = rate(doc, now)
    if per_k is None:
        return None
    return round(tokens_k(doc, project_id, window, now) * per_k, 2)


def last_reading(doc):
    """The local time of the newest reading in the two-hour window, or None. The pace is projected from it, so a
    snapshot does not change between readings (its ETag stays the same)."""
    if not doc["recent"]:
        return None
    return datetime.datetime.fromtimestamp(doc["recent"][-1][0]).astimezone()


def pace_per_hour(doc, now, field):
    """The slope of recent readings per hour: field "w" is the weekly percent (after the last weekly reset), field
    "pts" is the day's points (today's readings only). None when the readings do not show a trend."""
    moment = _local(now)
    epoch = moment.timestamp()
    entries = [e for e in doc["recent"] if epoch - PACE_WINDOW_S <= e[0] <= epoch]
    if field == "pts":
        today = moment.date()
        entries = [e for e in entries
                   if datetime.datetime.fromtimestamp(e[0]).astimezone().date() == today]
    else:
        start = 0
        for index in range(1, len(entries)):
            if entries[index][1] < entries[index - 1][1]:
                start = index
        entries = entries[start:]
    if len(entries) < 2 or entries[-1][0] - entries[0][0] < PACE_MIN_SPAN_S:
        return None
    index_of = 2 if field == "pts" else 1
    xs = [float(e[0]) for e in entries]
    ys = [float(e[index_of]) for e in entries]
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    denom = sum((x - mean_x) ** 2 for x in xs)
    if denom == 0:
        return None
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denom
    return slope * 3600.0
