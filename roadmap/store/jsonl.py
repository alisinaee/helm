"""JSON-lines files (activity.jsonl and the *-archive.jsonl files): append one line, read tolerantly, keep the newest N.

Writers hold the project's directory lock. Trimming rewrites the file atomically and works on raw lines, so a
damaged line is never silently lost by a trim that keeps it inside the window."""

import json
import os

from roadmap.errors import EXIT_INVALID_DATA, RoadmapError
from roadmap.store import atomic

FILE_MODE = 0o600


def append_line(path, obj):
    """Append one JSON object as a line and fsync. The file is created with mode 0600. Symlinks are refused."""
    if os.path.islink(path):
        raise RoadmapError("invalid_data", "refusing to append to a symlink, left unchanged: " + path,
                           EXIT_INVALID_DATA)
    line = json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n"
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    created = not os.path.exists(path)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line)
        fh.flush()
        os.fsync(fh.fileno())
    if created:
        os.chmod(path, FILE_MODE)


def raw_lines(path):
    """The lines of the file without line ends. A missing file gives []."""
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read().splitlines()
    except UnicodeDecodeError as exc:
        raise RoadmapError("invalid_data", "not UTF-8 text, left unchanged: " + path + " (" + str(exc) + ")",
                           EXIT_INVALID_DATA)


def read_objects(path):
    """(objects, bad_lines). Blank lines are skipped; a line that is not a JSON object counts as bad."""
    objects = []
    bad = 0
    for line in raw_lines(path):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except ValueError:
            bad += 1
            continue
        if isinstance(value, dict):
            objects.append(value)
        else:
            bad += 1
    return objects, bad


def keep_newest(path, keep):
    """Trim the file to its newest keep lines (rewritten atomically) when it is longer. Returns the number dropped."""
    lines = [line for line in raw_lines(path) if line.strip()]
    if len(lines) <= keep:
        return 0
    atomic.write_text(path, "\n".join(lines[-keep:]) + "\n")
    return len(lines) - keep
