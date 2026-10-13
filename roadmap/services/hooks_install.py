"""Install, remove and inspect the roadmap hook entries in a project's .claude/settings.local.json (WP10).

Entries run the absolute path of this repo's bin/roadmap with the "hook" command, because the desktop app gives hooks
a minimal PATH. An entry is ours when its command contains MARKER. Install merges: it replaces our entries and keeps
every other key and entry. It is idempotent, so running it twice writes the same bytes. Before any change the old file
is backed up. Legacy entries (commands containing LEGACY_MARKER, from the split-net jobs_auto.py) are removed only
when asked. Uninstall removes only our entries.
"""

import copy
import json
import os

from roadmap.errors import EXIT_CONFLICT, EXIT_INVALID_DATA, EXIT_USAGE, RoadmapError
from roadmap.store import atomic, backup, config, lock

MARKER = "roadmap hook"
LEGACY_MARKER = "jobs_auto.py"
SETTINGS_RELPATH = os.path.join(".claude", "settings.local.json")
HOOK_TIMEOUT_S = 10
MERGE_ATTEMPTS = 3  # re-merge when Claude Code changed the settings file between our read and our replace
# (event, matcher or None, suffix added to the hook command). The suffix "pre" makes the PreToolUse gate: the shim
# exits at once, without starting Python, while no project is stopped (see bin/roadmap).
PRE_MATCHER = "Edit|Write|MultiEdit|NotebookEdit|Bash|Agent|Task|WebFetch|WebSearch"
EVENTS = (
    ("PreToolUse", PRE_MATCHER, " pre"),
    ("SessionStart", None, ""),
    ("PostToolUse", "Agent|Task|Bash", ""),
    ("SubagentStop", None, ""),
    ("Stop", None, ""),
)
_UNSAFE_CHARS = set(" \t\"'$`\\;&|<>()*?[]{}!#~")


def shim_path():
    """Absolute path of bin/roadmap in the repo this package was loaded from."""
    here = os.path.realpath(os.path.abspath(__file__))
    repo = os.path.dirname(os.path.dirname(os.path.dirname(here)))
    return os.path.join(repo, "bin", "roadmap")


def hook_command():
    """The command every entry runs.

    A path with spaces or shell characters is refused, since the command is not quoted.
    """
    shim = shim_path()
    if not os.path.isfile(shim):
        raise RoadmapError("not_found", "the roadmap shim is missing: " + shim, EXIT_USAGE)
    if _UNSAFE_CHARS & set(shim):
        raise RoadmapError("invalid_input", "the roadmap folder path has spaces or shell characters; move the repo "
                           "to a plain path before installing hooks: " + shim, EXIT_USAGE)
    return shim + " hook"


def settings_file(project):
    """The settings path inside the project. A project that ships .claude or settings.local.json as a symlink is
    refused, and so is a settings file whose real path is outside the project's own .claude folder."""
    root = os.path.abspath(project["path"])
    path = os.path.join(root, SETTINGS_RELPATH)
    claude = os.path.join(root, ".claude")
    for candidate in (claude, path):
        if os.path.islink(candidate):
            raise RoadmapError("invalid_data", "refusing a symlink in the project settings path, left unchanged: "
                               + candidate, EXIT_INVALID_DATA)
    if os.path.lexists(path):
        base = os.path.join(os.path.realpath(root), ".claude") + os.sep
        if not os.path.realpath(path).startswith(base):
            raise RoadmapError("invalid_data", "the settings file resolves outside the project's .claude folder, "
                               "left unchanged: " + path, EXIT_INVALID_DATA)
    return path


def _is_ours(hook):
    command = hook.get("command") if isinstance(hook, dict) else None
    return isinstance(command, str) and MARKER in command


def _is_legacy(hook):
    command = hook.get("command") if isinstance(hook, dict) else None
    return isinstance(command, str) and LEGACY_MARKER in command


def _read_raw(path):
    """The exact bytes of the settings file, or None when it does not exist. O_NOFOLLOW: a symlink is refused."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise RoadmapError("invalid_data", "settings file cannot be read safely, left unchanged: " + path
                           + " (" + str(exc) + ")", EXIT_INVALID_DATA)
    with os.fdopen(fd, "rb") as fh:
        return fh.read()


def _parse(raw, path):
    """The settings object for the given bytes: {} for a missing file. A file that is not a JSON object is left
    alone."""
    if raw is None:
        return {}
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise RoadmapError("invalid_data", "not valid JSON, left unchanged: " + path + " (" + str(exc)[:80] + ")",
                           EXIT_INVALID_DATA)
    if not isinstance(data, dict):
        raise RoadmapError("invalid_data", "settings file is not a JSON object, left unchanged: " + path,
                           EXIT_INVALID_DATA)
    return data


def _hooks_of(settings, create):
    """The hooks object of the settings. With create=False a missing one gives an empty dict and nothing is added."""
    value = settings.get("hooks")
    if value is None:
        if not create:
            return {}
        value = settings["hooks"] = {}
    if not isinstance(value, dict):
        raise RoadmapError("invalid_data", "settings 'hooks' is not an object; fix it, then retry", EXIT_INVALID_DATA)
    return value


def _groups(hooks, event):
    value = hooks.get(event, [])
    if not isinstance(value, list):
        raise RoadmapError("invalid_data", "settings hooks." + event + " is not a list; fix it, then retry",
                           EXIT_INVALID_DATA)
    return value


def _strip(groups, predicate):
    """Return (groups without the hooks that match, number removed). A group left with no hooks is dropped."""
    kept = []
    removed = 0
    for group in groups:
        inner = group.get("hooks") if isinstance(group, dict) else None
        if not isinstance(inner, list) or not any(predicate(h) for h in inner):
            kept.append(group)
            continue
        rest = [h for h in inner if not predicate(h)]
        removed += len(inner) - len(rest)
        if rest:
            trimmed = dict(group)
            trimmed["hooks"] = rest
            kept.append(trimmed)
    return kept, removed


def _ours_in(groups):
    return [h["command"] for g in groups if isinstance(g, dict) and isinstance(g.get("hooks"), list)
            for h in g["hooks"] if _is_ours(h)]


def _edit(project, path, transform):
    """Apply transform(settings) to the settings file and write the result if it changed.

    Claude Code does not take our lock, so the file is re-read just before the replace. When its bytes changed since
    our read, the transform is applied again to the new content. Returns (changed, backup folder, transform result).
    """
    for _ in range(MERGE_ATTEMPTS):
        raw = _read_raw(path)
        before = _parse(raw, path)
        settings = copy.deepcopy(before)
        extra = transform(settings)
        if settings == before:
            return False, None, extra
        if _read_raw(path) != raw:
            continue
        folder = backup.backup_files(project["id"], [path]) if raw is not None else None
        atomic.write_json(path, settings)
        return True, folder, extra
    raise RoadmapError("locked", "the settings file kept changing while it was merged; try again", EXIT_CONFLICT)


def _apply_install(settings, command, replace_legacy):
    """Add our entries to settings in place. Returns the number of legacy entries removed."""
    hooks = _hooks_of(settings, create=True)
    legacy_removed = 0
    if replace_legacy:
        for event in list(hooks):
            if not isinstance(hooks[event], list):
                continue
            kept, count = _strip(hooks[event], _is_legacy)
            legacy_removed += count
            if count:
                hooks[event] = kept
                if not kept:
                    del hooks[event]
    for event, matcher, suffix in EVENTS:
        kept, _ = _strip(_groups(hooks, event), _is_ours)
        entry = {"type": "command", "command": command + suffix, "timeout": HOOK_TIMEOUT_S}
        group = {"hooks": [entry]}
        if matcher is not None:
            group = {"matcher": matcher, "hooks": [entry]}
        kept.append(group)
        hooks[event] = kept
    return legacy_removed


def _apply_uninstall(settings):
    """Remove only our entries from settings in place. Returns the number removed."""
    before_hooks = bool(settings.get("hooks"))
    hooks = _hooks_of(settings, create=False)
    removed = 0
    for event in list(hooks):
        if not isinstance(hooks[event], list):
            continue
        kept, count = _strip(hooks[event], _is_ours)
        removed += count
        if count:
            if kept:
                hooks[event] = kept
            else:
                del hooks[event]
    if "hooks" in settings and not hooks and before_hooks:
        del settings["hooks"]
    return removed


def install(project_id, replace_legacy=False):
    """Merge the roadmap hook entries into the project's settings. Returns a summary."""
    project = config.get_project(project_id)
    path = settings_file(project)
    command = hook_command()
    with lock.locked(os.path.dirname(path)):
        changed, folder, legacy_removed = _edit(
            project, path, lambda settings: _apply_install(settings, command, replace_legacy))
    return {"project": project_id, "settings": path, "command": command, "changed": changed,
            "backup": folder, "legacyRemoved": legacy_removed}


def uninstall(project_id):
    """Remove only the roadmap hook entries. Returns a summary."""
    project = config.get_project(project_id)
    path = settings_file(project)
    if not os.path.exists(path):
        return {"project": project_id, "settings": path, "removed": 0, "changed": False, "backup": None}
    with lock.locked(os.path.dirname(path)):
        changed, folder, removed = _edit(project, path, _apply_uninstall)
    return {"project": project_id, "settings": path, "removed": removed, "changed": changed, "backup": folder}


def status(project_id):
    """Per event: installed with the current command, stale (installed with another path) or missing."""
    project = config.get_project(project_id)
    path = settings_file(project)
    expected = hook_command()
    hooks = _hooks_of(_parse(_read_raw(path), path), create=False)
    events = {}
    for event, matcher, suffix in EVENTS:
        commands = _ours_in(_groups(hooks, event))
        if expected + suffix in commands:
            state = "installed"
        elif commands:
            state = "stale"
        else:
            state = "missing"
        events[event] = {"state": state, "matcher": matcher, "commands": commands}
    return {"project": project_id, "settings": path, "command": expected,
            "installed": all(row["state"] == "installed" for row in events.values()), "events": events}
