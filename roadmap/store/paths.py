"""Locations of the config, state and log directories. Setting ROADMAP_HOME redirects every path under one root."""

import os
import sys
import re

from roadmap.errors import EXIT_USAGE, RoadmapError

ENV_HOME = "ROADMAP_HOME"
DIR_MODE = 0o700
FILE_MODE = 0o600
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")


def valid_id(value):
    """Return True for a safe project id: 1 to 40 lowercase letters, digits or dashes."""
    return isinstance(value, str) and _ID_RE.match(value) is not None


def _require_id(value):
    if not valid_id(value):
        raise RoadmapError("invalid_input", "not a valid project id: " + repr(value), EXIT_USAGE)


def _root():
    """Return the absolute ROADMAP_HOME override, or None when it is unset or blank."""
    value = os.environ.get(ENV_HOME, "").strip()
    return os.path.abspath(os.path.expanduser(value)) if value else None


def _home():
    return os.path.expanduser("~")


def _xdg_state():
    """$XDG_STATE_HOME, else ~/.local/state (Linux and other non-macOS systems)."""
    value = os.environ.get("XDG_STATE_HOME", "").strip()
    return value if value and os.path.isabs(value) else os.path.join(_home(), ".local", "state")


def config_dir():
    """Config directory (config.json, phone.token)."""
    root = _root()
    if root is not None:
        return os.path.join(root, "config")
    return os.path.join(_home(), ".config", "roadmap-board")


def state_dir():
    """State directory (usage.json, hooks-<project>.json, backups/, tunnel.pid)."""
    root = _root()
    if root is not None:
        return os.path.join(root, "state")
    if sys.platform == "darwin":
        return os.path.join(_home(), "Library", "Application Support", "roadmap-board")
    return os.path.join(_xdg_state(), "roadmap-board")


def logs_dir():
    """Log directory."""
    root = _root()
    if root is not None:
        return os.path.join(root, "logs")
    if sys.platform == "darwin":
        return os.path.join(_home(), "Library", "Logs", "roadmap-board")
    return os.path.join(_xdg_state(), "roadmap-board", "logs")


def config_file():
    return os.path.join(config_dir(), "config.json")


def phone_token_file():
    return os.path.join(config_dir(), "phone.token")


def usage_file():
    return os.path.join(state_dir(), "usage.json")


def hooks_file(project_id):
    _require_id(project_id)
    return os.path.join(state_dir(), "hooks-" + project_id + ".json")


def tunnel_pid_file():
    return os.path.join(state_dir(), "tunnel.pid")


def backups_dir(project_id=None):
    """Backup root, or the per-project backup folder when a project id is given."""
    root = os.path.join(state_dir(), "backups")
    if project_id is None:
        return root
    _require_id(project_id)
    return os.path.join(root, project_id)


def ensure_dir(path):
    """Create path and any missing parents, each new directory with mode 0700. Existing directories are not changed."""
    path = os.path.abspath(path)
    missing = []
    current = path
    while not os.path.isdir(current):
        missing.append(current)
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    for directory in reversed(missing):
        try:
            os.mkdir(directory, DIR_MODE)
        except FileExistsError:
            continue
        os.chmod(directory, DIR_MODE)
    return path
