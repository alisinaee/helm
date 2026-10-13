"""Account usage for the dashboard: the Anthropic usage reading, the global usage.json store, the mirror into each
project's autonomy.json, the background loop with backoff, manual push and show.

Python 3 standard library only. The OAuth token is read from the macOS keychain (through `security`, no shell),
kept in memory and sent to one HTTPS host only. It is never printed, logged, written to a file or put in an
exception: every failure raises UsageError with a short plain reason.
"""

import json
import os
import socket
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timezone

from roadmap.errors import EXIT_INVALID_DATA, EXIT_USAGE, RoadmapError
from roadmap.log import get_logger
from roadmap.store import config as config_store
from roadmap.store import lock, paths, schema

KEYCHAIN_SERVICE = "Claude Code-credentials"
KEYCHAIN_TIMEOUT_S = 10
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
USAGE_HOST = "api.anthropic.com"
TIMEOUT_S = 10
MAX_BYTES = 1_000_000
KEYCHAIN_ITEM_NOT_FOUND = 44  # `security` exit status for errSecItemNotFound

SOURCE_ENDPOINT = "Anthropic usage endpoint"
SOURCE_PUSH = "manual push"
DEFAULT_INTERVAL_S = 120
MIN_INTERVAL_S = 30
BACKOFF_S = 600
BACKOFF_AFTER_FAILS = 3
STALE_FACTOR = 2
MIRROR_FIELDS = ("weeklyPercent", "fiveHourPercent", "weeklyResetsAt", "fiveHourResetsAt", "updated", "source")
VIEW_FIELDS = MIRROR_FIELDS + ("lastError",)

log = get_logger("services.usage")


class UsageError(Exception):
    """A usage read failed. str() is a short plain reason; it never contains the token."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse redirects: the token must not follow the request to another host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise UsageError("usage endpoint redirected, refusing to follow")


def read_keychain_token():
    """The Claude Code OAuth access token from the keychain. Runs `security`; no shell."""
    try:
        proc = subprocess.run(
            ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
            capture_output=True, text=True, timeout=KEYCHAIN_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        raise UsageError("keychain did not answer in time")
    except OSError:
        raise UsageError("keychain tool is not available")
    if proc.returncode == KEYCHAIN_ITEM_NOT_FOUND:
        raise UsageError("keychain item not found, sign in to Claude Code first")
    if proc.returncode != 0:
        raise UsageError("keychain access denied or failed (exit %d)" % proc.returncode)
    try:
        token = json.loads(proc.stdout)["claudeAiOauth"]["accessToken"]
    except (ValueError, KeyError, TypeError):
        raise UsageError("keychain entry has no usable token")
    if not isinstance(token, str) or not token.strip():
        raise UsageError("keychain entry has no usable token")
    return token.strip()


def _open(req):
    """Send the request and return the raw body. Kept apart so tests can replace the network."""
    opener = urllib.request.build_opener(_NoRedirect)
    with opener.open(req, timeout=TIMEOUT_S) as resp:
        return resp.read(MAX_BYTES)


def http_fetch(token):
    """GET the usage endpoint with the bearer token; returns the parsed JSON reply."""
    if not USAGE_URL.startswith("https://" + USAGE_HOST + "/"):
        raise UsageError("usage address is not the Anthropic host")
    req = urllib.request.Request(USAGE_URL, method="GET", headers={
        "Authorization": "Bearer " + token,
        "anthropic-beta": "oauth-2025-04-20",
        "User-Agent": "roadmap-dashboard",
        "Accept": "application/json",
    })
    try:
        raw = _open(req)
    except urllib.error.HTTPError as e:
        raise UsageError("usage endpoint answered HTTP %d" % e.code)
    except (socket.timeout, TimeoutError):
        raise UsageError("usage endpoint timed out")
    except urllib.error.URLError as e:
        if isinstance(e.reason, (socket.timeout, TimeoutError)):
            raise UsageError("usage endpoint timed out")
        raise UsageError("usage endpoint not reachable")
    except OSError:
        raise UsageError("usage endpoint not reachable")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise UsageError("usage reply is not valid JSON")
    return payload


def _percent(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        try:
            value = float(value)
        except ValueError:
            return None
    if not isinstance(value, (int, float)):
        return None
    return value


def _round_pct(value):
    return int(value) if float(value).is_integer() else round(float(value), 1)


def _iso(value):
    """resets_at as an ISO string with offset; epoch seconds are converted; anything else is None."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value).astimezone().isoformat(timespec="seconds")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _window(payload, key, label):
    obj = payload.get(key)
    if not isinstance(obj, dict):
        raise UsageError("usage reply has no %s window" % label)
    value = None
    for name in ("utilization", "percent_used"):
        value = _percent(obj.get(name))
        if value is not None:
            break
    if value is None or not (0 <= value <= 100):
        raise UsageError("usage reply has no valid %s percent" % label)
    return _round_pct(value), _iso(obj.get("resets_at"))


def parse_usage(payload):
    """Turn the endpoint reply into the four usage fields. Raises UsageError when a window is missing."""
    if not isinstance(payload, dict):
        raise UsageError("usage reply has an unexpected shape")
    five_pct, five_reset = _window(payload, "five_hour", "5-hour")
    week_pct, week_reset = _window(payload, "seven_day", "weekly")
    return {
        "weeklyPercent": week_pct,
        "fiveHourPercent": five_pct,
        "weeklyResetsAt": week_reset,
        "fiveHourResetsAt": five_reset,
    }


def collect(get_token=read_keychain_token, fetch=http_fetch):
    """One usage reading. Any failure raises UsageError; the token is never part of the message."""
    try:
        token = get_token()
        payload = fetch(token)
    except UsageError:
        raise
    except Exception as e:  # report the type only: a fake or library error may carry the token
        raise UsageError("unexpected failure (%s)" % type(e).__name__)
    return parse_usage(payload)


def usage_record(reading, source, now=None):
    """The usage fields for one reading, stamped with the local time and offset."""
    now = now or datetime.now().astimezone()
    return dict(reading, updated=now.isoformat(timespec="seconds"), source=source)


# ---------------------------------------------------------------- global store, mirror, push and show

def _config(config):
    return config if config is not None else config_store.load()


def _usage_setting(cfg, key, default):
    block = cfg.get("usage") if isinstance(cfg, dict) else None
    if not isinstance(block, dict) or key not in block:
        return default
    return block[key]


def _interval(cfg):
    value = _usage_setting(cfg, "intervalS", DEFAULT_INTERVAL_S)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return DEFAULT_INTERVAL_S
    return max(MIN_INTERVAL_S, int(value))


def _mirror_enabled(cfg):
    return _usage_setting(cfg, "mirrorToProjects", True) is True


def _load_store():
    data, error = schema.read_data("usage", paths.usage_file())
    if error is not None:
        raise RoadmapError(error["code"], error["message"], EXIT_INVALID_DATA)
    return dict(data) if data else {}


def _update_store(changes):
    """Merge changes into usage.json under the state-directory lock. Returns the stored record."""
    state = paths.ensure_dir(paths.state_dir())
    with lock.locked(state):
        current = _load_store()
        current.update(changes)
        schema.write_data("usage", paths.usage_file(), current)
    return current


def _record_error(reason):
    """Keep the last good values and only note why the newest read failed."""
    _update_store({"lastError": reason})


def _age_s(updated, now):
    if not isinstance(updated, str):
        return None
    try:
        moment = datetime.fromisoformat(updated)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.astimezone()
    return (now - moment).total_seconds()


def view(record, interval_s=DEFAULT_INTERVAL_S, now=None):
    """The public usage view. stale is true when the last good reading is older than 2x the interval
    (or there has never been one). now is an aware datetime and defaults to the current time."""
    now = now or datetime.now(timezone.utc)
    out = {key: record.get(key) for key in VIEW_FIELDS}
    age = _age_s(record.get("updated"), now)
    out["ageS"] = None if age is None else int(age)
    out["stale"] = age is None or age > STALE_FACTOR * interval_s
    return out


def _mirror_one(project, block):
    pid = project.get("id")
    folder = os.path.join(project.get("path", ""), project.get("dataDir", config_store.DEFAULT_DATA_DIR))
    target = os.path.join(folder, "autonomy.json")
    if not os.path.isfile(target):
        return {"project": pid, "status": "skipped", "reason": "no autonomy.json"}
    try:
        with lock.locked(folder):
            data, error = schema.read_data("autonomy", target)
            if error is not None:
                return {"project": pid, "status": "failed", "reason": error["message"]}
            out = dict(data or {})  # keeps the limit part; a v1 file has its usage moved out by the migration
            out["usage"] = dict(block)
            schema.write_data("autonomy", target, out)
    except RoadmapError as exc:
        return {"project": pid, "status": "failed", "reason": exc.message}
    except OSError as exc:
        return {"project": pid, "status": "failed", "reason": type(exc).__name__}
    return {"project": pid, "status": "ok"}


def mirror_to_projects(cfg, record):
    """Write the usage block into every registered project's autonomy.json.

    One project failing does not stop the rest.
    """
    block = {key: record.get(key) for key in MIRROR_FIELDS}
    return [_mirror_one(project, block) for project in cfg.get("projects", [])]


def _commit(changes, cfg):
    stored = _update_store(changes)
    mirrors = mirror_to_projects(cfg, stored) if _mirror_enabled(cfg) else []
    return stored, mirrors


def _result(stored, cfg, mirrors):
    return {"usage": view(stored, _interval(cfg)), "mirrors": mirrors}


def sync_once(config=None, get_token=None, fetch=None):
    """Read usage once, store it and mirror it when enabled. On failure the stored values stay and lastError is set;
    UsageError is raised with the plain reason. get_token and fetch default to the keychain and the endpoint."""
    cfg = _config(config)
    try:
        reading = collect(get_token=get_token or read_keychain_token, fetch=fetch or http_fetch)
    except UsageError as exc:
        _record_error(str(exc))
        raise
    stored, mirrors = _commit(dict(usage_record(reading, SOURCE_ENDPOINT), lastError=None), cfg)
    result = _result(stored, cfg, mirrors)
    _control_after_write()
    return result


def show(config=None, now=None):
    """The stored usage with stale and ageS computed now."""
    cfg = _config(config)
    return view(_load_store(), _interval(cfg), now)


def parse_push(text):
    """Turn the push input into changes.

    Input shape: {"rateLimits": [{"kind": "seven_day"|"five_hour", "percentUsed", "resetsAt"}]}.
    """
    try:
        payload = json.loads(text)
    except ValueError:
        raise RoadmapError("invalid_input", "push input is not valid JSON", EXIT_USAGE)
    limits = payload.get("rateLimits") if isinstance(payload, dict) else None
    if not isinstance(limits, list):
        raise RoadmapError("invalid_input", 'push input needs {"rateLimits": [...]}', EXIT_USAGE)
    changes = {}
    for entry in limits:
        if not isinstance(entry, dict):
            continue
        kind = entry.get("kind")
        if kind == "seven_day":
            prefix = "weekly"
        elif kind == "five_hour":
            prefix = "fiveHour"
        else:
            continue
        value = _percent(entry.get("percentUsed"))
        if value is None or not (0 <= value <= 100):
            raise RoadmapError("invalid_input", kind + " percentUsed must be a number from 0 to 100", EXIT_USAGE)
        changes[prefix + "Percent"] = _round_pct(value)
        changes[prefix + "ResetsAt"] = _iso(entry.get("resetsAt"))
    if not changes:
        raise RoadmapError("invalid_input", "rateLimits has no seven_day or five_hour entry", EXIT_USAGE)
    return changes


def push(text, config=None):
    """Store usage given by hand (JSON text) and mirror it like a sync. Windows not in the input keep their values."""
    cfg = _config(config)
    changes = parse_push(text)
    changes.update({"updated": datetime.now().astimezone().isoformat(timespec="seconds"),
                    "source": SOURCE_PUSH, "lastError": None})
    stored, mirrors = _commit(changes, cfg)
    result = _result(stored, cfg, mirrors)
    _control_after_write()
    return result


def _control_after_write():
    """After a usage write, recompute the control state of every project (weekly limits read usage.json). Best effort:
    control.after_write never raises."""
    from roadmap.services import control
    from roadmap.store import config as project_config
    for entry in project_config.list_projects():
        control.after_write(entry["id"])


# ---------------------------------------------------------------- background loop

def usage_wait_s(failures, interval_s=DEFAULT_INTERVAL_S):
    """Seconds to wait before the next read: the interval, or the 600 s backoff after 3 failures in a row."""
    if failures >= BACKOFF_AFTER_FAILS:
        return max(BACKOFF_S, interval_s)
    return interval_s


def run_loop(stop_event, config=None, sync=None, wait=None):
    """Refresh usage until stop_event is set. It waits before every attempt, so it never retries tightly.
    sync() and wait(seconds) are injectable for tests; wait returns True when the loop should stop.
    Failures are logged with the plain reason only."""
    cfg = _config(config)
    interval = _interval(cfg)
    run_sync = sync if sync is not None else (lambda: sync_once(cfg))
    pause = wait if wait is not None else stop_event.wait
    failures = 0
    while not pause(usage_wait_s(failures, interval)):
        try:
            run_sync()
            failures = 0
        except UsageError as exc:
            failures += 1
            log.warning("usage sync failed (%d in a row): %s", failures, exc)
        except RoadmapError as exc:
            failures += 1
            log.warning("usage sync failed (%d in a row): %s", failures, exc.message)
        except Exception as exc:
            failures += 1
            log.warning("usage sync failed (%d in a row): unexpected %s", failures, type(exc).__name__)
