"""Activity log (activity.jsonl): one line per write, {id, at, src, op, sum, undo}. Keeps the newest 500 lines."""

import json
import re

from roadmap.core.parsers import ACTIVITY_SUM_MAX
from roadmap.errors import EXIT_USAGE, RoadmapError
from roadmap.services import records
from roadmap.store import jsonl, lock

FILE = "activity.jsonl"
KEEP = 500
SOURCES = ("gui", "cli", "agent", "phone")
_ID_RE = re.compile(r"^A(\d+)$")


def append(data_dir, src, op, summary, undo=False, now=None):
    """Record one write and return the line. summary is cut to 60 characters. Trims the file to the newest 500 lines."""
    records.require_dir(data_dir)
    if src not in SOURCES:
        raise RoadmapError("usage", "activity source '" + str(src) + "' is not valid (allowed: "
                           + "|".join(SOURCES) + ")", EXIT_USAGE)
    op_name = records.text_field(op, "activity op", 40)
    text = " ".join(str(summary or "").split())[:ACTIVITY_SUM_MAX]
    path = records.file_of(data_dir, FILE)
    with lock.locked(data_dir):
        line = {"id": _next_id(path), "at": records.now_iso(now), "src": src, "op": op_name, "sum": text,
                "undo": undo is True}
        jsonl.append_line(path, line)
        jsonl.keep_newest(path, KEEP)
    return dict(line)


def recent(data_dir, count=15):
    """The newest count valid lines, oldest first. A missing file gives []."""
    records.require_dir(data_dir)
    objects, _ = jsonl.read_objects(records.file_of(data_dir, FILE))
    return objects[-count:] if count > 0 else []


def _next_id(path):
    for raw in reversed(jsonl.raw_lines(path)):
        if not raw.strip():
            continue
        try:
            value = json.loads(raw)
        except ValueError:
            continue
        match = _ID_RE.match(str(value.get("id", ""))) if isinstance(value, dict) else None
        if match:
            return "A" + str(int(match.group(1)) + 1)
    return "A1"

