"""Atomic JSON writes (temp file, fsync, replace, fsync the directory) and strict JSON reads."""

import json
import os
import stat
import tempfile

from roadmap.errors import EXIT_INVALID_DATA, EXIT_NOT_FOUND, RoadmapError

NEW_FILE_MODE = 0o600
_MISSING = object()


def read_json(path, default=_MISSING):
    """Read a JSON file. A missing file gives default when one is passed, otherwise not_found (exit 3).
    Bad JSON raises invalid_data (exit 5) and the file is left alone."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except FileNotFoundError:
        if default is _MISSING:
            raise RoadmapError("not_found", "file not found: " + path, EXIT_NOT_FOUND)
        return default
    except UnicodeDecodeError as exc:
        raise RoadmapError("invalid_data", "not UTF-8 text, left unchanged: " + path + " (" + str(exc) + ")",
                           EXIT_INVALID_DATA)
    try:
        return json.loads(text)
    except ValueError as exc:
        raise RoadmapError("invalid_data", "not valid JSON, left unchanged: " + path + " (" + str(exc) + ")",
                           EXIT_INVALID_DATA)


def write_json(path, obj):
    """Replace path with obj as JSON, atomically. New files get mode 0600; an existing file keeps its mode."""
    path = os.path.abspath(path)
    if os.path.islink(path):
        raise RoadmapError("invalid_data", "refusing to replace a symlink, left unchanged: " + path,
                           EXIT_INVALID_DATA)
    directory = os.path.dirname(path)
    payload = json.dumps(obj, indent=2, ensure_ascii=False) + "\n"
    os.makedirs(directory, exist_ok=True)
    mode = _mode_of(path)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix="." + os.path.basename(path) + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
            fh.flush()
            os.fchmod(fh.fileno(), mode)
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        _remove_quiet(tmp)
        raise
    _fsync_dir(directory)


def _mode_of(path):
    """The mode of an existing regular file, else 0600. lstat, so a symlink's target mode is never used."""
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return NEW_FILE_MODE
    return stat.S_IMODE(st.st_mode) if stat.S_ISREG(st.st_mode) else NEW_FILE_MODE


def _fsync_dir(directory):
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _remove_quiet(path):
    try:
        os.remove(path)
    except OSError:
        pass
