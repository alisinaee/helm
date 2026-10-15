"""Schema versions per data file kind, with the read and write rules.

Reads never write. Writes stamp the current version."""

import os

from roadmap.errors import EXIT_ERROR, EXIT_INVALID_DATA, RoadmapError
from roadmap.store import atomic, migrations

CURRENT = {
    "config": 1,
    "autonomy": 2,
    "tasks": 1,
    "jobs": 1,
    "roadmap_config": 1,
    "usage": 1,
    "hooks": 1,
    "issues": 1,
    "questions": 1,
    "comments": 1,
    "budget": 1,
    "queue": 1,
    "features": 1,
    "head": 1,
    "git": 1,
}


def current_version(kind):
    """Return the schema version this build writes for a data kind."""
    if kind not in CURRENT:
        raise RoadmapError("unknown_kind", "unknown data kind: " + repr(kind), EXIT_ERROR)
    return CURRENT[kind]


def version_of(data):
    """Return the schemaVersion of a parsed file. A missing key counts as 1."""
    value = data.get("schemaVersion", 1)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise RoadmapError("invalid_data", "schemaVersion must be a whole number from 1", EXIT_INVALID_DATA)
    return value


def read_data(kind, path):
    """Return (data, error). data is upgraded in memory to the current version. A missing file gives (None, None).
    A file newer than this build gives (None, {code: newer_schema, path, message}) and is never touched."""
    target = current_version(kind)
    if not os.path.exists(path):
        return None, None
    raw = atomic.read_json(path)
    if not isinstance(raw, dict):
        raise RoadmapError("invalid_data", "expected a JSON object in " + path, EXIT_INVALID_DATA)
    found = version_of(raw)
    if found > target:
        return None, _newer_error(path, found, target)
    return migrations.upgrade(kind, raw, found, target), None


def write_data(kind, path, data):
    """Save data at the current version. The caller holds the directory lock. Refuses to overwrite a newer file
    (newer_schema, exit 5) and refuses a file that is not valid JSON, so a broken file is never silently replaced."""
    target = current_version(kind)
    if os.path.exists(path):
        on_disk = atomic.read_json(path)
        if isinstance(on_disk, dict) and version_of(on_disk) > target:
            raise RoadmapError("newer_schema", _newer_message(path, version_of(on_disk), target), EXIT_INVALID_DATA)
    out = dict(data)
    out["schemaVersion"] = target
    atomic.write_json(path, out)


def _newer_message(path, found, target):
    return (os.path.basename(path) + " was written by a newer roadmap-board (schema " + str(found)
            + "; this build reads up to " + str(target) + "). It was not changed. Update roadmap-board.")


def _newer_error(path, found, target):
    return {"code": "newer_schema", "path": path, "message": _newer_message(path, found, target)}
