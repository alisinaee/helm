"""Comments (comments.json): a flat thread per target (a task or an issue id). At most 20 per target; the older ones
move to comments-archive.jsonl. The file is capped at 150 KB: the oldest comments move to the archive until it fits."""

import json

from roadmap.core.parsers import COMMENT_MAX
from roadmap.errors import EXIT_USAGE, RoadmapError
from roadmap.services import records
from roadmap.store import jsonl, lock

FILE = "comments.json"
ARCHIVE = "comments-archive.jsonl"
PER_TARGET = 20
FILE_MAX_BYTES = 150 * 1024
BY_MAX = 40


def add(data_dir, on, by, text, now=None):
    """Add a comment on a target and return it. Older comments on the same target, or the oldest overall when the
    file is over its cap, are moved to the archive first."""
    records.require_dir(data_dir)
    target = str(on or "").strip()
    if not records.ID_OK.match(target):
        raise RoadmapError("usage", "comment target '" + target + "' is not an id such as P2.4 or I3", EXIT_USAGE)
    body = records.text_field(text, "comment text", COMMENT_MAX)
    author = records.text_field(by, "by", BY_MAX, required=False)
    with lock.locked(data_dir):
        doc = records.load("comments", data_dir, FILE, "comments")
        comment = {"on": target, "by": author, "at": records.now_iso(now), "t": body}
        moved = []
        same = [c for c in doc["comments"] if c.get("on") == target]
        while len(same) >= PER_TARGET:
            oldest = same.pop(0)
            moved.append(oldest)
        if moved:
            drop = {id(c) for c in moved}
            doc["comments"] = [c for c in doc["comments"] if id(c) not in drop]
        doc["comments"].append(comment)
        while doc["comments"][:-1] and _size(doc) > FILE_MAX_BYTES:
            moved.append(doc["comments"].pop(0))
        for old in moved:
            jsonl.append_line(records.file_of(data_dir, ARCHIVE), old)
        records.save("comments", data_dir, FILE, doc)
    return dict(comment)


def list_comments(data_dir, on=None, limit=None):
    """Comments in file order (oldest first), optionally for one target and at most limit of the newest."""
    records.require_dir(data_dir)
    rows = [dict(c) for c in records.load("comments", data_dir, FILE, "comments")["comments"]
            if on is None or c.get("on") == on]
    if limit is not None:
        rows = rows[-limit:]
    return rows


def _size(doc):
    return len(json.dumps(doc, indent=2, ensure_ascii=False).encode("utf-8"))
