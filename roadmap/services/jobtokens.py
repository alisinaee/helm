"""Measured tokens per job (R10.32): read a Claude Code subagent transcript and store the sums on the job.

Transcripts: ~/.claude/projects/<slug>/<session>/subagents/agent-<id>.jsonl (+ agent-<id>.meta.json with the
description and model). Every assistant line carries message.usage; a message that streams in several lines repeats
its id, so the last line of each id counts. The file is streamed line by line and bounded (MAX_BYTES). Hook use
is fail-open: capture_for_agent never raises.
"""

import glob
import json
import os

from roadmap.core.parsers import weighted_units
from roadmap.services import jobs

MAX_BYTES = 200 * 1024 * 1024
MODEL_NAMES = ("haiku", "sonnet", "opus")


def _short_model(value):
    text = str(value or "").lower()
    return next((n for n in MODEL_NAMES if n in text), text[:40])


def read_usage(path):
    """{in, out, cacheRead, cacheWrite, model} summed over a transcript, or None when it has no usage."""
    last = {}
    model = ""
    read = 0
    try:
        with open(path, "rb") as fh:
            for raw in fh:
                read += len(raw)
                if read > MAX_BYTES:
                    break
                if b'"usage"' not in raw:
                    continue
                try:
                    row = json.loads(raw)
                except ValueError:
                    continue
                msg = row.get("message") if isinstance(row, dict) else None
                usage = msg.get("usage") if isinstance(msg, dict) else None
                if row.get("type") != "assistant" or not isinstance(usage, dict):
                    continue
                if msg.get("model") and msg.get("model") != "<synthetic>":
                    model = msg["model"]
                key = msg.get("id") or row.get("requestId") or row.get("uuid") or len(last)
                last[key] = usage
    except OSError:
        return None
    if not last:
        return None
    total = {"in": 0, "out": 0, "cacheRead": 0, "cacheWrite": 0}
    for usage in last.values():
        for key, field in (("in", "input_tokens"), ("out", "output_tokens"), ("cacheRead", "cache_read_input_tokens"),
                           ("cacheWrite", "cache_creation_input_tokens")):
            value = usage.get(field)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                total[key] += int(value)
    total["model"] = _short_model(model)
    return total


def units(tokens):
    return weighted_units(tokens)


def transcript_path(payload):
    """The subagent transcript of a SubagentStop payload, or None."""
    given = payload.get("agent_transcript_path")
    if isinstance(given, str) and given:
        return given
    agent_id = str(payload.get("agent_id") or "")
    session = payload.get("transcript_path")
    if agent_id and isinstance(session, str) and session.endswith(".jsonl"):
        return os.path.join(session[:-len(".jsonl")], "subagents", "agent-" + agent_id + ".jsonl")
    return None


def capture_for_agent(data_dir, job_id, payload):
    """Store the agent's measured tokens on its job. Fail-open: any problem returns False."""
    try:
        path = transcript_path(payload)
        if not path or not job_id:
            return False
        usage = read_usage(path)
        return bool(usage) and jobs.set_job_usage(data_dir, job_id, usage)
    except Exception:
        return False


def _read_meta(path):
    try:
        with open(path[:-len(".jsonl")] + ".meta.json", encoding="utf-8") as fh:
            meta = json.load(fh)
        return meta if isinstance(meta, dict) else {}
    except (OSError, ValueError):
        return {}


def _first_stamp(path):
    try:
        with open(path, "rb") as fh:
            for raw in fh:
                try:
                    stamp = json.loads(raw).get("timestamp")
                except (ValueError, AttributeError):
                    continue
                if stamp:
                    return str(stamp)
    except OSError:
        pass
    return ""


def backfill(data_dir, transcripts_root, overwrite=False, dry_run=False):
    """Fill tokens on jobs that lack them. A job matches a transcript whose meta description is in the job title
    (titles are '<model>: <description>', cut at 120) and whose model agrees; equal titles pair in start order.
    Returns {"matched", "skipped", "jobs": [ids]}."""
    files = sorted(glob.glob(os.path.join(transcripts_root, "*", "subagents", "agent-*.jsonl")))
    pool = []
    for path in files:
        desc = str(_read_meta(path).get("description") or "").strip()
        if desc:
            pool.append((_first_stamp(path), desc[:100], str(_read_meta(path).get("model") or ""), path))
    pool.sort()
    done = []
    skipped = 0
    for job in jobs.list_jobs(data_dir):
        if job.get("tokens") and not overwrite:
            continue
        title = str(job.get("title") or "")
        hit = next((p for p in pool if p[1] in title and (not p[2] or p[2] in str(job.get("model") or p[2]))), None)
        if hit is None:
            skipped += 1
            continue
        usage = read_usage(hit[3])
        if usage is None:
            skipped += 1
            continue
        pool.remove(hit)
        if not dry_run:
            jobs.set_job_usage(data_dir, job["id"], usage, overwrite=overwrite)
        done.append(job["id"])
    return {"matched": len(done), "skipped": skipped, "jobs": done}
