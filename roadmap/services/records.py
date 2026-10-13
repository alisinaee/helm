"""Shared file work for the WP20 services: load a keyed JSON document at the current schema, save it atomically,
validate the input text. Writers hold the project's directory lock; these helpers never take it themselves."""

import datetime
import os
import re

from roadmap.errors import EXIT_CONFLICT, EXIT_INVALID_DATA, EXIT_NOT_FOUND, EXIT_USAGE, RoadmapError
from roadmap.store import schema

ID_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9./-]{0,39}$")


def require_dir(data_dir):
    if not os.path.isdir(data_dir):
        raise RoadmapError("not_found", "data folder does not exist: " + str(data_dir), EXIT_NOT_FOUND)


def file_of(data_dir, name):
    return os.path.join(data_dir, name)


def load(kind, data_dir, name, key=None):
    """The document in data_dir/name at the current schema. A missing file is empty (lazy creation).
    key names the list inside it; a missing key counts as an empty list. A newer or corrupt file raises."""
    path = file_of(data_dir, name)
    data, error = schema.read_data(kind, path)
    if error is not None:
        raise RoadmapError("newer_schema", error["message"], EXIT_INVALID_DATA)
    doc = dict(data) if data is not None else {}
    if key is not None:
        items = doc.get(key, [])
        if not isinstance(items, list):
            raise RoadmapError("invalid_data", name + " has no '" + key + "' list; fix it, then retry: " + path,
                               EXIT_INVALID_DATA)
        doc[key] = list(items)
    return doc


def save(kind, data_dir, name, doc):
    schema.write_data(kind, file_of(data_dir, name), doc)


def now_iso(now=None):
    moment = now if now is not None else datetime.datetime.now().astimezone()
    return moment.isoformat(timespec="seconds")


def text_field(value, what, limit, required=True):
    """A one-line text: whitespace collapsed, required and at most limit characters. Longer input is refused."""
    text = " ".join(str("" if value is None else value).split())
    if required and not text:
        raise RoadmapError("usage", what + " must not be empty", EXIT_USAGE)
    if len(text) > limit:
        raise RoadmapError("usage", what + " is " + str(len(text)) + " characters; the limit is " + str(limit),
                           EXIT_USAGE)
    return text


def conflict(text, next_cmd=None):
    return RoadmapError("conflict", text, EXIT_CONFLICT, next=next_cmd)


def next_number(prefix, *groups):
    """The next id such as I7 or Q3: one more than the highest number in any group (file and archive)."""
    best = 0
    for group in groups:
        for item in group:
            value = str(item.get("id", ""))
            if value.startswith(prefix) and value[len(prefix):].isdigit():
                best = max(best, int(value[len(prefix):]))
    return prefix + str(best + 1)
