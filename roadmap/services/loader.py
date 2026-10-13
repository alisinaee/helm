"""Load a registered project's data files into a snapshot, and name the process that holds a TCP port.

The project's files are read from <path>/<dataDir> and parsed by roadmap.core.snapshot. A missing or unreadable
file never raises: it becomes an entry in the snapshot's errors[]. port_owner() lives here because subprocess
is allowed only in services/; it runs lsof, read-only.
"""

import json
import os
import subprocess
from datetime import datetime

from roadmap.core.extras import extra_file
from roadmap.core.parsers import error_entry
from roadmap.core.snapshot import build_snapshot
from roadmap.store import config as config_store

BASE_FILES = ("tasks.json", "jobs.json", "autonomy.json", "issues.json", "questions.json", "comments.json",
              "budget.json", "queue.json", "activity.jsonl")
CONFIG_FILE = "roadmap.config.json"
LSOF_TIMEOUT_S = 5


def project_folder(entry):
    """The data folder of a registered project entry: its path joined with dataDir."""
    return os.path.join(entry["path"], entry.get("dataDir") or config_store.DEFAULT_DATA_DIR)


def load_snapshot(project_id, now=None):
    """The snapshot of one registered project. Raises not_found (exit 3) only for an unknown id."""
    entry = config_store.get_project(project_id)
    folder = project_folder(entry)
    errors = []
    project_cfg = _read_project_config(folder, errors)
    project_cfg.setdefault("id", entry["id"])
    project_cfg.setdefault("title", entry["name"])
    names = list(BASE_FILES)
    for name in _extra_names(project_cfg, errors):
        if name not in names:
            names.append(name)
    files = {name: _read_text(folder, name, errors) for name in names}
    moment = now if now is not None else datetime.now().astimezone()
    snap = build_snapshot(files, project_cfg, moment)
    snap["errors"] = errors + snap["errors"]
    return snap


def _read_text(folder, name, errors):
    """The text of folder/name, or None when the file is missing. Other failures are noted in errors."""
    if not _plain_name(name):
        errors.append(error_entry(str(name), ValueError("a data file name must be a plain file name")))
        return None
    try:
        with open(os.path.join(folder, name), "r", encoding="utf-8") as fh:
            return fh.read()
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError) as exc:
        errors.append(error_entry(name, exc))
        return None


def _read_project_config(folder, errors):
    """The project's roadmap.config.json as a dict. Missing gives {}; a broken file adds an error and gives {}."""
    text = _read_text(folder, CONFIG_FILE, errors)
    if text is None:
        return {}
    try:
        data = json.loads(text)
    except ValueError as exc:
        errors.append(error_entry(CONFIG_FILE, exc))
        return {}
    if not isinstance(data, dict):
        errors.append(error_entry(CONFIG_FILE, ValueError("expected a JSON object")))
        return {}
    return data


def _extra_names(project_cfg, errors):
    """The file names the configured extras read, in config order."""
    extras = project_cfg.get("extras")
    if not isinstance(extras, dict):
        return []
    names = []
    for entry in extras.values():
        name = extra_file(entry)
        if name is not None and name not in names:
            names.append(name)
    return names


def _plain_name(name):
    return (isinstance(name, str) and name not in ("", ".", "..") and "/" not in name and "\\" not in name
            and "\x00" not in name)


def port_owner(port):
    """{"pid", "name"} of the process listening on TCP port, from lsof, or None when nobody is or lsof is missing."""
    try:
        proc = subprocess.run(["lsof", "-nP", "-iTCP:%d" % int(port), "-sTCP:LISTEN", "-Fpc"],
                              capture_output=True, text=True, timeout=LSOF_TIMEOUT_S, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    pid = name = None
    for line in proc.stdout.splitlines():
        if line.startswith("p") and pid is None:
            pid = line[1:]
        elif line.startswith("c") and name is None:
            name = line[1:]
    if pid is None:
        return None
    return {"pid": int(pid) if pid.isdigit() else None, "name": name or "unknown"}
