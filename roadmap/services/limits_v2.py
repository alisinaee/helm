"""Limits v2 (R11.126, docs/LIMITS-V2-SPEC.md): one stop per usage window (five_hour, week), each a budget or a cap.

Stored in the global config under "limitsV2": {window: {on, mode budget|cap, value 1..100, base, once, baseReset}}.
  cap     stop at value %.
  budget  use at most value % more from now: stop = min(100, base + value); base is the reading when it was set.
A repeating budget re-bases when its window resets (base = the reading in the new window, 0 when unknown); a "once"
budget switches itself off at the reset. effective_stop() gives one absolute percent per window; limits.py turns the
active ones into acct rows, so the lowest stop gates new jobs (the same place the weekly stop gates).
The old weekly stop (a global pct row on the week) is moved into week/cap by migrate().
"""

import datetime
import math

from roadmap.errors import EXIT_USAGE, RoadmapError
from roadmap.services import usage
from roadmap.store import config as config_store

KEY = "limitsV2"
WINDOWS = ("five_hour", "week")
MODES = ("budget", "cap")
FIELDS = {"five_hour": ("fiveHourPercent", "fiveHourResetsAt", "5h", "5 hours"),
          "week": ("weeklyPercent", "weeklyResetsAt", "W", "week")}
DEFAULT_VALUE = {"five_hour": 50, "week": 95}
RESET_JITTER_S = 600
IDS = {"five_hour": "S5H", "week": "SWK"}


def _usage_error(message):
    return RoadmapError("usage", message, EXIT_USAGE, next="roadmap usage stops")


def _num(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def default_window(window):
    return {"on": False, "mode": "cap", "value": DEFAULT_VALUE[window], "base": 0, "once": False, "baseReset": None}


def _clean(window, raw):
    out = default_window(window)
    if not isinstance(raw, dict):
        return out
    out["on"] = raw.get("on") is True
    out["mode"] = raw.get("mode") if raw.get("mode") in MODES else "cap"
    if _num(raw.get("value")) and 1 <= raw["value"] <= 100:
        out["value"] = raw["value"]
    if _num(raw.get("base")) and 0 <= raw["base"] <= 100:
        out["base"] = raw["base"]
    out["once"] = raw.get("once") is True
    out["baseReset"] = raw["baseReset"] if isinstance(raw.get("baseReset"), str) else None
    return out


def _legacy_week(cfg):
    """The old weekly stop: the global pct row on the week with action block, or None."""
    for item in cfg.get("limits") if isinstance(cfg.get("limits"), list) else []:
        if (isinstance(item, dict) and item.get("scope", "global") == "global" and item.get("kind") == "pct"
                and item.get("window") == "week" and item.get("action") == "block" and _num(item.get("value"))):
            return item
    return None


def _from_config(cfg):
    stored = cfg.get(KEY) if isinstance(cfg.get(KEY), dict) else None
    out = {w: _clean(w, (stored or {}).get(w)) for w in WINDOWS}
    old = _legacy_week(cfg)
    if stored is None and old is not None:
        out["week"].update({"on": True, "mode": "cap", "value": min(100, max(1, old["value"]))})
    return out


def load():
    """The two window records (migrated view; nothing is written)."""
    return _from_config(config_store.load())


def _reading(window, moment=None):
    """(percent or None, resetsAt or None, fresh) of one window from the usage view."""
    pct_key, reset_key = FIELDS[window][0], FIELDS[window][1]
    try:
        shown = usage.show(now=moment)
    except RoadmapError:
        return None, None, False
    pct = shown.get(pct_key)
    return (float(pct) if _num(pct) else None), shown.get(reset_key), not shown.get("stale")


def _parse(text):
    try:
        value = datetime.datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None
    return value if value.tzinfo else value.astimezone()


def _reset_changed(rec, reset):
    if not reset or rec["baseReset"] is None:
        return False
    a, b = _parse(rec["baseReset"]), _parse(reset)
    if a is None or b is None:
        return rec["baseReset"] != reset
    return abs((a - b).total_seconds()) > RESET_JITTER_S


def rebased(rec, pct, reset):
    """The record after the window reset rule (a copy). A budget re-bases to the new reading; a once budget
    turns off."""
    out = dict(rec)
    if rec["mode"] != "budget" or not rec["on"]:
        return out
    if rec["baseReset"] is None and reset:
        out["baseReset"] = reset
    elif _reset_changed(rec, reset):
        out["baseReset"] = reset
        if rec["once"]:
            out["on"] = False
        else:
            out["base"] = round(min(pct, 100.0), 1) if pct is not None else 0
    return out


def effective_stop(rec):
    """The absolute stop percent of one record, or None when it is off."""
    if not rec["on"]:
        return None
    if rec["mode"] == "cap":
        return float(rec["value"])
    return float(min(100, rec["base"] + rec["value"]))


def stops(moment=None, persist=True):
    """The state of both windows: {window: {rec fields, stop, percent, resetsAt, fresh}}. A reset re-bases (and is
    saved when persist is true; a failed save is ignored: the computed values still apply)."""
    recs = load()
    out, changed = {}, {}
    for window in WINDOWS:
        pct, reset, fresh = _reading(window, moment)
        rec = rebased(recs[window], pct, reset)
        if rec != recs[window]:
            changed[window] = rec
        out[window] = dict(rec, stop=effective_stop(rec), percent=pct, resetsAt=reset, fresh=fresh)
    if changed and persist:
        try:
            _save(changed)
        except Exception:
            pass
    return out


def _save(changed):
    def mutate(cfg):
        current = _from_config(cfg)
        current.update({w: _clean(w, r) for w, r in changed.items()})
        cfg[KEY] = current
        _drop_legacy(cfg)
        return current

    return config_store._update(mutate)


def _drop_legacy(cfg):
    rows = cfg.get("limits")
    if isinstance(rows, list):
        old = _legacy_week(cfg)
        if old is not None:
            rows.remove(old)


def check_patch(window, patch):
    """The checked fields of a PUT body for one window (only the given keys)."""
    if window not in WINDOWS:
        raise _usage_error("window must be five_hour or week")
    if not isinstance(patch, dict):
        raise _usage_error("the window must be an object")
    out = {}
    if "on" in patch:
        if not isinstance(patch["on"], bool):
            raise _usage_error("on must be true or false")
        out["on"] = patch["on"]
    if "mode" in patch:
        if patch["mode"] not in MODES:
            raise _usage_error("mode must be budget or cap")
        out["mode"] = patch["mode"]
    if "value" in patch:
        if not _num(patch["value"]) or not 1 <= patch["value"] <= 100:
            raise _usage_error("value must be a number from 1 to 100")
        out["value"] = int(patch["value"]) if float(patch["value"]).is_integer() else round(patch["value"], 1)
    if "once" in patch:
        if not isinstance(patch["once"], bool):
            raise _usage_error("once must be true or false")
        out["once"] = patch["once"]
    return out


def set_window(window, patch, moment=None):
    """Apply a checked patch to one window; returns (before, after) records. Turning a budget on, or switching to
    budget, takes the current reading as its base."""
    patch = check_patch(window, patch)
    pct, reset, _ = _reading(window, moment)
    box = {}

    def mutate(cfg):
        current = _from_config(cfg)
        before = current[window]
        rec = dict(before)
        rec.update(patch)
        if rec["mode"] == "budget" and (rec["mode"] != before["mode"] or (rec["on"] and not before["on"])):
            rec["base"] = round(pct, 1) if pct is not None else 0
            rec["baseReset"] = reset
        current[window] = _clean(window, rec)
        cfg[KEY] = current
        _drop_legacy(cfg)
        box["pair"] = (before, current[window])
        return None

    config_store._update(mutate)
    return box["pair"]


def summary(window, rec):
    """A short sentence of one window for the activity line and the head panel."""
    name = FIELDS[window][3]
    if not rec["on"]:
        return "%s stop off" % name
    if rec["mode"] == "cap":
        return "%s stop at %g%%" % (name, rec["value"])
    return "%s budget +%g%% from %g%% (stop at %g%%)" % (name, rec["value"], rec["base"], effective_stop(rec))


def gate_rows(moment=None):
    """The active windows as acct rows for services/limits.py (lowest stop wins by being the worst row)."""
    rows = []
    for window, info in stops(moment).items():
        if info["stop"] is None:
            continue
        rows.append({"id": IDS[window], "scope": "global", "window": window, "kind": "acct",
                     "value": info["stop"], "action": "block", "src": "limits2", "measure": window})
    return rows


def lowest(moment=None):
    """(window, stop) of the lowest active stop, or None."""
    active = [(w, i["stop"]) for w, i in stops(moment).items() if i["stop"] is not None]
    return min(active, key=lambda x: x[1]) if active else None


def brief_line(moment=None):
    """"5h 49% / stop 50% | W 20% / stop off" for the head brief; an unknown reading reads "?"."""
    parts = []
    for window, info in stops(moment, persist=False).items():
        pct = "?" if info["percent"] is None else "%g%%" % info["percent"]
        stop = "off" if info["stop"] is None else "%g%%" % info["stop"]
        parts.append("%s %s / stop %s" % (FIELDS[window][2], pct, stop))
    return " | ".join(parts)


def view(moment=None):
    """The GET body: both windows with stop, percent, resetsAt and fresh."""
    return {"windows": stops(moment)}
