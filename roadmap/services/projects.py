"""Project maintenance (WP10): init templates, add, list, show, remove, check, migrate and backup.

The registry is the global config (store.config). The data files live in each project's data folder. Every write
takes the folder lock, saves atomically and backs up first when it changes a file. A file newer than this build
is refused and never written. Nothing here runs a subprocess or touches the network.
"""

import datetime
import json
import os

from roadmap.core import parsers
from roadmap.errors import EXIT_CONFLICT, EXIT_INVALID_DATA, EXIT_NOT_FOUND, RoadmapError
from roadmap.services import hooks, jobs, usage
from roadmap.store import atomic, backup, config, lock, paths, schema

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates")

# (file name, schema kind) for every data file a project may hold, in the order reports list them
DATA_FILES = (
    ("tasks.json", "tasks"),
    ("jobs.json", "jobs"),
    ("autonomy.json", "autonomy"),
    ("roadmap.config.json", "roadmap_config"),
)

# WP20 files. init never writes them (their services create them on the first write), but migrate and backup cover them.
LAZY_DATA_FILES = (
    ("issues.json", "issues"),
    ("questions.json", "questions"),
    ("comments.json", "comments"),
    ("budget.json", "budget"),
    ("queue.json", "queue"),
)
LOG_FILES = ("activity.jsonl", "issues-archive.jsonl", "questions-archive.jsonl", "comments-archive.jsonl")


def _existing_folder(path):
    folder = os.path.abspath(os.path.expanduser(str(path)))
    if not os.path.isdir(folder):
        raise RoadmapError("not_found", "folder does not exist: " + folder, EXIT_NOT_FOUND)
    return folder


def _template(filename):
    with open(os.path.join(TEMPLATE_DIR, filename), "r", encoding="utf-8") as fh:
        return json.load(fh)


def init_project(path):
    """Write the template data files into <path>/docs where they are missing. Existing files are never changed."""
    folder = _existing_folder(path)
    data_dir = os.path.join(folder, config.DEFAULT_DATA_DIR)
    created = []
    kept = []
    os.makedirs(data_dir, exist_ok=True)
    with lock.locked(data_dir):
        for filename, kind in DATA_FILES:
            target = os.path.join(data_dir, filename)
            if os.path.exists(target):
                kept.append(filename)
                continue
            body = _template(filename)
            if filename == "roadmap.config.json":
                body["title"] = os.path.basename(folder) or "Project"
            schema.write_data(kind, target, body)
            created.append(filename)
    return {"path": folder, "dataDir": data_dir, "created": created, "kept": kept}


def add_project(path, name=None, data_dir=config.DEFAULT_DATA_DIR):
    """Register a project folder. The folder must exist, its data folder must already exist (run project init),
    and neither the folder nor the name may be registered yet."""
    folder = _existing_folder(path)
    display = name if name is not None else os.path.basename(folder)
    for entry in config.list_projects():
        if os.path.abspath(entry["path"]) == folder:
            raise RoadmapError("conflict", "this folder is already registered as '" + entry["id"] + "'",
                               EXIT_CONFLICT)
    if not os.path.isdir(os.path.join(folder, data_dir)):
        raise RoadmapError("not_found", "data folder does not exist: " + os.path.join(folder, data_dir)
                           + "; run: roadmap project init " + str(path), EXIT_NOT_FOUND)
    return describe(config.add_project(display, folder, None, data_dir))


def describe(entry):
    """A registry entry plus where its data lives and whether its folder still exists."""
    out = dict(entry)
    out["dataPath"] = jobs.data_dir_of(entry)
    out["pathExists"] = os.path.isdir(entry["path"])
    return out


def list_projects():
    return [describe(p) for p in config.list_projects()]


def show_project(project_id):
    out = describe(config.get_project(project_id))
    out["files"] = {name: os.path.isfile(os.path.join(out["dataPath"], name)) for name, _ in DATA_FILES}
    return out


def remove_project(project_id):
    """Unregister a project. Its files are never touched."""
    return config.remove_project(project_id)


def _targets(project_id):
    if project_id is None:
        return config.list_projects()
    return [config.get_project(project_id)]


def check_projects(project_id=None):
    """Parse every data file of one project (or all). Returns a list of per-project reports with an ok flag."""
    reports = []
    for entry in _targets(project_id):
        data_dir = jobs.data_dir_of(entry)
        report = {"id": entry["id"], "name": entry["name"], "dataPath": data_dir, "files": []}
        if not os.path.isdir(data_dir):
            report["files"].append({"file": config.DEFAULT_DATA_DIR, "status": "error", "schemaVersion": None,
                                    "current": None, "error": "data folder does not exist"})
        else:
            for filename, kind in DATA_FILES:
                if kind == "roadmap_config":
                    report["files"].append(_check_settings(data_dir))
                else:
                    report["files"].append(_check_file(data_dir, filename, kind))
        report["ok"] = all(row["status"] != "error" for row in report["files"])
        reports.append(report)
    return reports


def _check_file(data_dir, filename, kind):
    path = os.path.join(data_dir, filename)
    row = {"file": filename, "status": "ok", "schemaVersion": None, "current": schema.current_version(kind),
           "error": None}
    if not os.path.exists(path):
        row["status"] = "missing"
        return row
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except (OSError, UnicodeDecodeError) as exc:
        return _failed(row, "cannot read the file (" + type(exc).__name__ + ")")
    try:
        raw = json.loads(text)
    except ValueError as exc:
        return _failed(row, "not valid JSON (" + str(exc) + ")")
    if not isinstance(raw, dict):
        return _failed(row, "expected a JSON object")
    try:
        found = schema.version_of(raw)
    except RoadmapError as exc:
        return _failed(row, exc.message)
    row["schemaVersion"] = found
    if found > row["current"]:
        return _failed(row, "written by a newer roadmap-board (schema " + str(found) + "); update roadmap-board")
    errors = _parser_errors(kind, text, filename)
    if errors:
        return _failed(row, errors[0]["error"])
    return row


def _parser_errors(kind, text, filename):
    if kind == "tasks":
        return parsers.parse_tasks(text, filename)[1]
    if kind == "jobs":
        return parsers.parse_jobs(text, datetime.datetime.now(datetime.timezone.utc), filename)[1]
    if kind == "autonomy":
        return parsers.parse_autonomy(text, filename)[1]
    return []


def _check_settings(data_dir):
    """roadmap.config.json has no core parser: its read rules and detector and pattern settings are checked here."""
    row = {"file": "roadmap.config.json", "status": "ok", "schemaVersion": None,
           "current": schema.current_version("roadmap_config"), "error": None}
    if not os.path.exists(os.path.join(data_dir, "roadmap.config.json")):
        row["status"] = "missing"
        return row
    try:
        pattern, _ = hooks.project_settings(data_dir)
        hooks.task_regex(pattern)
    except RoadmapError as exc:
        return _failed(row, exc.message)
    row["schemaVersion"] = schema.version_of(_read_raw(data_dir, "roadmap.config.json"))
    return row


def _read_raw(data_dir, filename):
    return atomic.read_json(os.path.join(data_dir, filename))


def _failed(row, message):
    row["status"] = "error"
    row["error"] = message
    return row


def migrate_project(project_id):
    """Upgrade a project's files to the current schema. A newer file stops the command before anything is written.
    Backs up every data file first, and only when at least one file changes."""
    entry = config.get_project(project_id)
    data_dir = jobs.data_dir_of(entry)
    if not os.path.isdir(data_dir):
        raise RoadmapError("not_found", "data folder does not exist: " + data_dir, EXIT_NOT_FOUND)
    migrated = []
    unchanged = []
    with lock.locked(data_dir):
        plan = []
        for filename, kind in DATA_FILES + LAZY_DATA_FILES:
            path = os.path.join(data_dir, filename)
            if not os.path.exists(path):
                continue
            raw = atomic.read_json(path)
            if not isinstance(raw, dict):
                raise RoadmapError("invalid_data", "expected a JSON object in " + path, EXIT_INVALID_DATA)
            found = schema.version_of(raw)
            target = schema.current_version(kind)
            if found > target:
                raise RoadmapError("newer_schema", filename + " was written by a newer roadmap-board (schema "
                                   + str(found) + "); migrate refuses it and nothing was changed. "
                                   "Update roadmap-board first.", EXIT_INVALID_DATA)
            if found < target or "schemaVersion" not in raw:
                plan.append((filename, kind, path, found, target))
            else:
                unchanged.append(filename)
        backup_folder = None
        if plan:
            names = [f for f, _ in DATA_FILES + LAZY_DATA_FILES] + list(LOG_FILES)
            existing = [os.path.join(data_dir, f) for f in names if os.path.exists(os.path.join(data_dir, f))]
            backup_folder = backup.backup_files(project_id, existing)
            for filename, kind, path, found, target in plan:
                data, _ = schema.read_data(kind, path)
                schema.write_data(kind, path, data)
                migrated.append({"file": filename, "from": found, "to": target})
    if any(row["file"] == "autonomy.json" for row in migrated):
        _remirror_usage(entry)
    return {"project": project_id, "backup": backup_folder, "migrated": migrated, "unchanged": unchanged}


def _remirror_usage(entry):
    """The v2 autonomy file has no usage block. Put back the stored usage when mirroring is on, as a sync would."""
    cfg = config.load()
    if cfg.get("usage", {}).get("mirrorToProjects") is not True:
        return
    stored, _ = schema.read_data("usage", paths.usage_file())
    if stored:
        usage.mirror_to_projects({"projects": [entry]}, stored)


def backup_projects(project_id=None):
    """Back up the data files of one project or of all of them. A project whose folder is missing is skipped."""
    rows = []
    for entry in _targets(project_id):
        data_dir = jobs.data_dir_of(entry)
        if not os.path.isdir(data_dir):
            rows.append({"project": entry["id"], "status": "skipped", "reason": "data folder does not exist"})
            continue
        names = [f for f, _ in DATA_FILES + LAZY_DATA_FILES] + list(LOG_FILES)
        files = [os.path.join(data_dir, f) for f in names]
        with lock.locked(data_dir):
            folder = backup.backup_files(entry["id"], files)
        rows.append({"project": entry["id"], "status": "ok", "folder": folder,
                     "files": [f for f in names if os.path.isfile(os.path.join(data_dir, f))]})
    return rows
