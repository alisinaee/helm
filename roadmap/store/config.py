"""Global config.json: schema v1 with ports, usage settings and the project list. Add, list, get and remove."""

import datetime
import os
import re

from roadmap.errors import EXIT_CONFLICT, EXIT_INVALID_DATA, EXIT_NOT_FOUND, EXIT_USAGE, RoadmapError
from roadmap.store import lock, paths, schema

DEFAULT_DATA_DIR = "docs"
MAX_NAME_LEN = 80
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


def default_config():
    """The config a fresh install starts from. Nothing is written until the first change."""
    return {
        "schemaVersion": 1,
        "port": 8765,
        "phonePort": 8766,
        "usage": {"intervalS": 120, "mirrorToProjects": True},
        "projects": [],
    }


def load():
    """Return the config dict. A missing file gives the defaults. A newer file raises newer_schema (exit 5)."""
    data, error = schema.read_data("config", paths.config_file())
    if error is not None:
        raise RoadmapError(error["code"], error["message"], EXIT_INVALID_DATA)
    if data is None:
        return default_config()
    if not isinstance(data.get("projects"), list):
        raise RoadmapError("invalid_data", "config.json has no projects list", EXIT_INVALID_DATA)
    return data


def list_projects():
    """Return copies of every project entry, in the order they were added."""
    return [dict(p) for p in load()["projects"]]


def get_project(project_id):
    """Return a copy of one project entry, or not_found (exit 3)."""
    for project in load()["projects"]:
        if project["id"] == project_id:
            return dict(project)
    raise _not_found(project_id)


def add_project(name, path, project_id=None, data_dir=DEFAULT_DATA_DIR):
    """Register a project folder. The id defaults to a slug of the name. Ids and names must be unique
    (names ignore case). The folder must exist. Returns the new entry."""
    clean_name = _clean_name(name)
    abs_path = os.path.abspath(os.path.expanduser(str(path)))
    if not os.path.isdir(abs_path):
        raise RoadmapError("not_found", "project folder does not exist: " + abs_path, EXIT_NOT_FOUND)
    clean_dir = _clean_data_dir(data_dir)
    pid = project_id if project_id is not None else _slug(clean_name)
    if not paths.valid_id(pid):
        raise RoadmapError("invalid_input", "project id must be 1-40 lowercase letters, digits or dashes: "
                           + repr(pid), EXIT_USAGE)

    def mutate(cfg):
        projects = cfg["projects"]
        if any(p["id"] == pid for p in projects):
            raise RoadmapError("conflict", "a project with id '" + pid + "' already exists", EXIT_CONFLICT)
        if any(p["name"].casefold() == clean_name.casefold() for p in projects):
            raise RoadmapError("conflict", "a project named '" + clean_name + "' already exists", EXIT_CONFLICT)
        project = {"id": pid, "name": clean_name, "path": abs_path, "dataDir": clean_dir, "addedAt": _now()}
        projects.append(project)
        return dict(project)

    return _update(mutate)


def remove_project(project_id):
    """Remove a project from the config. Its files are not touched. Returns the removed entry, or not_found."""

    def mutate(cfg):
        for index, project in enumerate(cfg["projects"]):
            if project["id"] == project_id:
                del cfg["projects"][index]
                return dict(project)
        raise _not_found(project_id)

    return _update(mutate)


def update_limits(mutate):
    """Run mutate(rows) on the global limit rows (config key "limits", a list) under the config lock, then save.
    mutate changes the list in place and returns its result (WP27, services/limits.py)."""

    def inner(cfg):
        rows = cfg.get("limits")
        if not isinstance(rows, list):
            rows = []
            cfg["limits"] = rows
        return mutate(rows)

    return _update(inner)


def _update(mutate):
    """Read-modify-write under the config directory lock. The config is re-read inside the lock."""
    paths.ensure_dir(paths.config_dir())
    with lock.locked(paths.config_dir()):
        cfg = load()
        result = mutate(cfg)
        schema.write_data("config", paths.config_file(), cfg)
    return result


def _not_found(project_id):
    return RoadmapError("not_found", "no project with id '" + str(project_id) + "'", EXIT_NOT_FOUND)


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _clean_name(name):
    text = "" if name is None else str(name).strip()
    if not text or len(text) > MAX_NAME_LEN or _CONTROL_RE.search(text):
        raise RoadmapError("invalid_input", "project name must be 1-80 printable characters", EXIT_USAGE)
    return text


def _slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40].rstrip("-")


def _clean_data_dir(value):
    text = str(value).strip().replace("\\", "/")
    parts = [p for p in text.split("/") if p not in ("", ".")]
    if not parts or text.startswith("/") or ".." in parts:
        raise RoadmapError("invalid_input", "dataDir must be a relative folder inside the project: " + repr(value),
                           EXIT_USAGE)
    return "/".join(parts)
