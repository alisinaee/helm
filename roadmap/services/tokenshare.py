"""Share of the weekly limit per job (R10.35): an estimate, not a measurement.

Every real usage reading adds a sample (epoch, weekly %, 5-hour %) to state/usage-samples.jsonl (newest SAMPLES_KEEP
lines). Between two consecutive samples the weekly points that rose are split over the jobs that ran in that window,
in proportion to their weighted units (core/parsers.py weighted_units) times the part of the job inside the window.
A fall (weekly reset) adds nothing. Points of a window with no measured job stay unassigned (the head session has no
tokens here, so it gets no row). Fail-open: estimate() and record() never raise.
"""

import json
import os
import time

from roadmap.core.parsers import parse_ts
from roadmap.store import jsonl, lock, paths

FILE = "usage-samples.jsonl"
SAMPLES_KEEP = 2000
MIN_GAP_S = 3600  # an unchanged reading is stored again only after this long


def path():
    return os.path.join(paths.state_dir(), FILE)


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def read_samples(file_path=None):
    rows = []
    for row in jsonl.read_objects(file_path or path())[0]:
        if _num(row.get("t")) and _num(row.get("wk")):
            rows.append(row)
    rows.sort(key=lambda r: r["t"])
    return rows


def record(weekly, five_hour=None, now=None, file_path=None):
    """Append one sample. Returns True when stored. Never raises."""
    try:
        if not _num(weekly):
            return False
        where = file_path or path()
        stamp = int(now if now is not None else time.time())
        with lock.locked(paths.ensure_dir(os.path.dirname(where))):
            rows = read_samples(where)
            if rows and rows[-1].get("wk") == weekly and rows[-1].get("h5") == five_hour \
                    and stamp - rows[-1]["t"] < MIN_GAP_S:
                return False
            jsonl.append_line(where, {"t": stamp, "wk": weekly, "h5": five_hour})
            jsonl.keep_newest(where, SAMPLES_KEEP)
        return True
    except Exception:
        return False


def _span(job, now):
    start = parse_ts(job.get("started"))
    if start is None:
        return None
    end = parse_ts(job.get("ended")) if job.get("status") != "running" else None
    a = start.timestamp()
    b = end.timestamp() if end is not None else now
    return a, max(b, a)


def estimate(jobs, samples, now=None):
    """{job id: weekly points} for the jobs with units, from the samples. Empty when there is nothing to split."""
    try:
        now = now if now is not None else time.time()
        spans = {}
        for job in jobs:
            units = job.get("units")
            span = _span(job, now) if _num(units) and units > 0 and job.get("id") else None
            if span:
                spans[job["id"]] = (span, float(units))
        out = {}
        for prev, cur in zip(samples, samples[1:]):
            rise = cur["wk"] - prev["wk"]
            if rise <= 0:
                continue
            t0, t1 = prev["t"], cur["t"]
            shares = {}
            for jid, ((a, b), units) in spans.items():
                if b < t0 or a > t1:
                    continue
                inside = min(b, t1) - max(a, t0)
                whole = b - a
                frac = 1.0 if whole <= 0 else max(inside, 0.0) / whole
                if frac > 0:
                    shares[jid] = units * frac
            total = sum(shares.values())
            if total <= 0:
                continue
            for jid, share in shares.items():
                out[jid] = out.get(jid, 0.0) + rise * share / total
        return {jid: round(v, 3) for jid, v in out.items()}
    except Exception:
        return {}


def annotate(jobs, now=None, file_path=None):
    """Set estPct (weekly points, approximate) on each job dict that got a share. Returns the jobs."""
    try:
        for job in jobs:
            job.pop("estPct", None)
        if not any(isinstance(j.get("units"), (int, float)) for j in jobs):
            return jobs
        shares = estimate(jobs, read_samples(file_path), now)
        for job in jobs:
            if job.get("id") in shares:
                job["estPct"] = shares[job["id"]]
    except Exception:
        pass
    return jobs
