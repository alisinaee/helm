"""Ordered migration steps per data kind. Reads upgrade in memory only; writers save the newest version."""

from roadmap.errors import EXIT_INVALID_DATA, RoadmapError


def _autonomy_v1_to_v2(data):
    """Version 2 keeps only the limit. The usage block moves to the global usage.json (see split_usage)."""
    out = {"schemaVersion": 2}
    if "limit" in data:
        out["limit"] = data["limit"]
    return out


# MIGRATIONS[kind] is an ordered list of (from_version, to_version, fn). fn takes a dict and returns a new dict.
MIGRATIONS = {
    "autonomy": [(1, 2, _autonomy_v1_to_v2)],
}


def upgrade(kind, data, found, target):
    """Return a copy of data upgraded from found to target. Raises invalid_data if a step is missing."""
    steps = MIGRATIONS.get(kind, [])
    out = dict(data)
    version = found
    while version < target:
        step = next((s for s in steps if s[0] == version), None)
        if step is None:
            raise RoadmapError("invalid_data", "no migration for " + kind + " from schema " + str(version)
                               + " to " + str(target), EXIT_INVALID_DATA)
        out = step[2](out)
        version = step[1]
    out["schemaVersion"] = target
    return out


def split_usage(data):
    """Return (upgraded_autonomy_v2, usage_block_or_None). The caller moves the usage block to usage.json."""
    usage = data.get("usage")
    upgraded = _autonomy_v1_to_v2(data) if data.get("schemaVersion", 1) < 2 else dict(data)
    upgraded.pop("usage", None)
    return upgraded, usage
