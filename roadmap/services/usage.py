"""Account usage for the dashboard: the Anthropic usage reading, the global usage.json store, the mirror into each
project's autonomy.json, the background loop with backoff, manual push and show.

The service fetches usage by itself (R10.29, docs/USAGE-SOURCES.md), in this order: the OAuth usage endpoint with the
Claude Code login (refreshed only when usageTokenRefresh is true, else an expired login is reported), Claude Code's own rate_limits (status line / hooks / sidecar), and
last an estimate from the local transcripts, labelled as one. Sources live in services/usage_sources.py.

Python 3 standard library only. The OAuth token is read from the macOS keychain (through `security`, no shell),
kept in memory and sent to Anthropic HTTPS hosts only. It is never printed, logged, written to a file or put in an
exception: every failure raises UsageError with a short plain reason.
"""

import functools
import json
import os
import socket
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

from roadmap.errors import EXIT_INVALID_DATA, EXIT_USAGE, RoadmapError
from roadmap.log import get_logger
from roadmap.services import ledger
from roadmap.services import tokenshare
from roadmap.services import usage_accounts
from roadmap.services import usage_sources
from roadmap.store import config as config_store
from roadmap.store import atomic, lock, paths, schema

KEYCHAIN_SERVICE = "Claude Code-credentials"
KEYCHAIN_TIMEOUT_S = 10
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
USAGE_HOST = "api.anthropic.com"
TIMEOUT_S = 10
MAX_BYTES = 1_000_000
KEYCHAIN_ITEM_NOT_FOUND = 44  # `security` exit status for errSecItemNotFound

SOURCE_ENDPOINT = "Anthropic usage endpoint"
SOURCE_PUSH = "manual push"
SOURCE_MANUAL = "manual entry"
SOURCE_ESTIMATE = "estimate from local transcripts"
ESTIMATE_AFTER_S = 10 * 60        # estimate only when the last real reading is older than this
ESTIMATE_GAP_S = 60               # and recompute it at most this often
DEFAULT_INTERVAL_S = 120
MIN_INTERVAL_S = 30
BACKOFF_S = 600
BACKOFF_AFTER_FAILS = 3
MAX_USAGE_AGE_MIN = 90            # one freshness rule everywhere: a reading older than this is stale
MAX_USAGE_AGE_KEY = "maxUsageAgeMin"  # docs/autonomy.json key that overrides it (minutes)
KEYCHAIN_BACKOFF_S = 6 * 3600     # after a keychain failure the background loop skips the keychain this long
MANUAL_KEYCHAIN_GAP_S = 60        # a manual sync may retry a failed keychain read at most this often
TOKEN_REFRESH_KEY = "usageTokenRefresh"  # usage config key (opt-in, default false): may the service refresh the login
MIRROR_FIELDS = ("weeklyPercent", "fiveHourPercent", "weeklyResetsAt", "fiveHourResetsAt", "updated", "source")
VIEW_FIELDS = MIRROR_FIELDS + ("lastError", "syncError", "estimate")
REAL_FIELDS = ("weeklyPercent", "fiveHourPercent", "weeklyResetsAt", "fiveHourResetsAt", "updated", "source")
# Stable reason codes for syncError. The keychain ones back off; the others retry on the normal schedule.
CODE_NO_TOKEN = "no_token"
CODE_NO_ITEM = "no_item"
CODE_DENIED = "denied"
CODE_EXPIRED = "expired"          # the refresh token was refused: the Claude Code login must be renewed once
CODE_NET = "net"
CODE_OTHER = "other"
CODE_DISCONNECTED = "disconnected"  # R11.8: the person disconnected Helm from the active account; nothing is read
KEYCHAIN_CODES = (CODE_NO_TOKEN, CODE_NO_ITEM, CODE_DENIED, CODE_EXPIRED)
# No usable Claude Code login (desktop app sign-in only, or an expired one): not an error. The other sources run.
UNAVAILABLE_CODES = (CODE_NO_TOKEN, CODE_NO_ITEM, CODE_EXPIRED)
STATUS_UNAVAILABLE = "unavailable"
STATUS_ERROR = "error"
STATUS_DISCONNECTED = "disconnected"
DISCONNECTED_REASON = ("Helm's usage sync is disconnected from this Claude account: Tokens > Account > Connect "
                       "(or `helm usage account connect`)")
UNAVAILABLE_REASON = "no Claude Code login on this Mac: run `claude auth login` once (docs/USAGE-SOURCES.md)"
REQUEST_FILE = "usage-request.json"   # legacy head request flag (no longer written: Sync now fetches); still cleared
REQUEST_MAX_AGE_S = 30 * 60
RESTORE_FIELDS = ("weeklyPercent", "weeklyResetsAt", "fiveHourPercent", "fiveHourResetsAt", "updated", "source",
                  "lastError", "syncError")

log = get_logger("services.usage")


class UsageError(Exception):
    """A usage read failed. str() is a short plain reason; it never contains the token. code is the stable reason
    code (CODE_* above) that the store keeps as syncError."""

    def __init__(self, message, code=CODE_OTHER, status=None):
        super().__init__(message)
        self.code = code
        self.status = status


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse redirects: the token must not follow the request to another host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise UsageError("usage endpoint redirected, refusing to follow")


def token_refresh_allowed(cfg):
    """True only when the usage config says usageTokenRefresh: true. Refresh rotates the login's token pair, so it is
    opt-in: with it off the service never refreshes and never writes the Claude Code login."""
    return _usage_setting(cfg, TOKEN_REFRESH_KEY, False) is True


def read_keychain_token(allow_refresh=False, location=None):
    """The Claude Code OAuth access token (keychain, else ~/.claude/.credentials.json; location picks another usage
    account's login, R11.8). With allow_refresh it is refreshed first when it expires within 5 minutes; without it an
    expired token is code expired. Runs `security`; no shell."""
    try:
        if location is None:
            return usage_sources.access_token(allow_refresh=allow_refresh)
        return usage_sources.access_token(allow_refresh=allow_refresh, location=location)
    except usage_sources.SourceError as exc:
        raise UsageError(str(exc), exc.code)


def _force_refresh(location=None):
    """A new access token after the endpoint refused the current one (HTTP 401). Only with usageTokenRefresh on."""
    try:
        if location is None:
            return usage_sources.access_token(force=True, allow_refresh=True)
        return usage_sources.access_token(force=True, allow_refresh=True, location=location)
    except usage_sources.SourceError as exc:
        raise UsageError(str(exc), exc.code)


def _no_refresh():
    """The 401 retry when usageTokenRefresh is off: no refresh, the login is reported expired."""
    raise UsageError(usage_sources.EXPIRED_REASON, CODE_EXPIRED)


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
        raise UsageError("usage endpoint answered HTTP %d" % e.code, status=e.code)
    except (socket.timeout, TimeoutError):
        raise UsageError("usage endpoint timed out", CODE_NET)
    except urllib.error.URLError as e:
        if isinstance(e.reason, (socket.timeout, TimeoutError)):
            raise UsageError("usage endpoint timed out", CODE_NET)
        raise UsageError("usage endpoint not reachable", CODE_NET)
    except OSError:
        raise UsageError("usage endpoint not reachable", CODE_NET)
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


def collect(get_token=read_keychain_token, fetch=http_fetch, refresh=None):
    """One usage reading. Any failure raises UsageError; the token is never part of the message. When refresh is
    given, an HTTP 401 gets one retry with the token it returns."""
    try:
        token = get_token()
        try:
            payload = fetch(token)
        except UsageError as exc:
            if refresh is None or exc.status != 401:
                raise
            payload = fetch(refresh())
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


def max_age_s(cfg):
    """The freshness limit of a usage reading, in seconds. The first registered project whose docs/autonomy.json sets
    maxUsageAgeMin (a positive number of minutes) wins; otherwise MAX_USAGE_AGE_MIN (90 minutes)."""
    for project in (cfg.get("projects") or []) if isinstance(cfg, dict) else []:
        path = os.path.join(project.get("path", ""), project.get("dataDir", config_store.DEFAULT_DATA_DIR),
                            "autonomy.json")
        try:
            data = atomic.read_json(path, default=None) if os.path.isfile(path) else None
        except Exception:  # an unreadable project file never changes the limit; the next project or the default wins
            continue
        value = data.get(MAX_USAGE_AGE_KEY) if isinstance(data, dict) else None
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
            return int(value * 60)
    return MAX_USAGE_AGE_MIN * 60


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


def request_path():
    return os.path.join(paths.state_dir(), REQUEST_FILE)


def refresh_requested(now=None):
    """True while a manual sync's request flag asks the head for a fresh reading (at most REQUEST_MAX_AGE_S old)."""
    moment = now or datetime.now(timezone.utc)
    try:
        data = atomic.read_json(request_path(), default={})
    except (OSError, RoadmapError, ValueError):
        return False
    age = _age_s(data.get("at") if isinstance(data, dict) else None, moment)
    return age is not None and 0 <= age < REQUEST_MAX_AGE_S


def _clear_request():
    try:
        os.remove(request_path())
    except OSError:
        pass


def _record_error(reason, code=CODE_OTHER, retry_after=None):
    """Keep the last good values and only note why the newest read failed: the text, the reason code and, for a
    keychain failure, the time before which the background loop does not read the keychain again."""
    changes = {"lastError": reason, "syncError": code}
    if retry_after is not None:
        changes["keychainRetryAfter"] = retry_after
    _update_store(changes)


def _moment(text):
    """An ISO string as an aware datetime, or None when it is not one."""
    if not isinstance(text, str):
        return None
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.astimezone()
    return moment


def _age_s(updated, now):
    moment = _moment(updated)
    return None if moment is None else (now - moment).total_seconds()


REASON_RESET_PASSED = "reset passed"


def _passed(text, now):
    """True when a resets-at time is at or before now: the window it names has already reset."""
    moment = _moment(text)
    return moment is not None and moment <= now


def view(record, max_age=MAX_USAGE_AGE_MIN * 60, now=None):
    """The public usage view. stale is true when the last good reading is older than max_age seconds
    (or there has never been one). A window whose resets-at time has passed has no current percent: it reads
    null with the reason "reset passed" (the stored number is old). now is an aware datetime and defaults to now."""
    now = now or datetime.now(timezone.utc)
    out = {key: record.get(key) for key in VIEW_FIELDS}
    age = _age_s(record.get("updated"), now)
    out["ageS"] = None if age is None else int(age)
    out["stale"] = age is None or age > max_age
    out["maxAgeS"] = max_age
    for prefix, reset_key in (("fiveHour", "fiveHourResetsAt"), ("weekly", "weeklyResetsAt")):
        passed = _passed(record.get(reset_key), now)
        out[prefix + "Reason"] = REASON_RESET_PASSED if passed else None
        if passed:
            out[prefix + "Percent"] = None
    out["status"], out["reason"] = _status(record)
    return out


def _status(record):
    """(status, reason) of the last sync: unavailable (no claude.ai login here), error (a real failure), or None."""
    code = record.get("syncError")
    if code == CODE_DISCONNECTED:
        return STATUS_DISCONNECTED, DISCONNECTED_REASON
    if code in UNAVAILABLE_CODES:
        return STATUS_UNAVAILABLE, (record.get("lastError") if code == CODE_EXPIRED and record.get("lastError")
                                    else UNAVAILABLE_REASON)
    return (STATUS_ERROR, record.get("lastError")) if code else (None, None)


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
    """Store a reading. A real one (not an estimate) also becomes lastReal, the base the estimate scales from."""
    estimated = changes.get("estimate") is True
    if not estimated:
        changes["estimate"] = False
    stored = _update_store(changes)
    if not estimated:
        stored = _update_store({"lastReal": {key: stored.get(key) for key in REAL_FIELDS}})
        _clear_request()  # a new reading answers any refresh the head was asked for
        _record_ledger(changes, stored)
    mirrors = mirror_to_projects(cfg, stored) if _mirror_enabled(cfg) else []
    return stored, mirrors


def _record_ledger(changes, stored):
    """Add a weekly reading to the usage ledger (WP27, services/ledger.py). Best effort: the usage is saved already."""
    if "weeklyPercent" not in changes:
        return
    try:
        ledger.record_reading(stored.get("weeklyPercent"), stored.get("fiveHourPercent"), datetime.now().astimezone())
        tokenshare.record(stored.get("weeklyPercent"), stored.get("fiveHourPercent"))
    except Exception as exc:  # the ledger is derived data; a failure must not fail the sync
        log.warning("usage ledger not updated: %s", type(exc).__name__)


def _result(stored, cfg, mirrors):
    return {"usage": view(stored, max_age_s(cfg)), "mirrors": mirrors}


def _in_future(text, now):
    moment = _moment(text)
    return moment is not None and moment > now


def sync_once(config=None, get_token=None, fetch=None, background=False, now=None):
    """Read usage once through the source chain and store it (mirrored when enabled):

    1. the OAuth usage endpoint with the Claude Code login (refreshed before it expires and retried once after a 401
       only when usageTokenRefresh is true; otherwise an expired login is code expired and the sources below run);
    2. a fresh Claude Code rate_limits reading (status line sidecar), when the endpoint gave nothing;
    (R10.40: no transcript estimate; without a real reading the view is unknown.)

    On an endpoint failure the stored values stay and lastError/syncError are set. A real failure (network, HTTP)
    raises UsageError after the fallbacks had their turn, unless one of them stored a reading. No usable login is not
    an error: the result has status "unavailable" when no fallback stored anything either.

    Keychain backoff: after a keychain failure (no token, no item, denied, expired) the background loop
    (background=True) skips the keychain until KEYCHAIN_BACKOFF_S has passed and returns None when no fallback stored
    anything. A manual sync (the default) may retry, but no more than once per MANUAL_KEYCHAIN_GAP_S while the last
    failure was a keychain one.
    """
    cfg = _config(config)
    moment = now or datetime.now(timezone.utc)
    store = _load_store()
    account = usage_accounts.active_for_sync(cfg)
    disconnected = not account["connected"]
    if disconnected and store.get("syncError") != CODE_DISCONNECTED:
        _update_store({"syncError": CODE_DISCONNECTED, "lastError": None})
    skip = disconnected or (background and _in_future(store.get("keychainRetryAfter"), moment))
    oauth_error = None
    if not background and not disconnected:
        if store.get("syncError") in KEYCHAIN_CODES:
            age = _age_s(store.get("manualAttemptAt"), moment)
            if age is not None and age < MANUAL_KEYCHAIN_GAP_S:
                skip = True
                if store.get("syncError") not in UNAVAILABLE_CODES:
                    oauth_error = UsageError("the keychain was checked a moment ago, try again in a minute",
                                             store.get("syncError"))
        if not skip:
            _update_store({"manualAttemptAt": moment.isoformat(timespec="seconds")})
    if not skip:
        allow = token_refresh_allowed(cfg)
        own_login = get_token is None
        where = account["location"]
        try:
            if where is None:
                keychain_token = read_keychain_token if not allow else functools.partial(read_keychain_token,
                                                                                        allow_refresh=True)
                force = _force_refresh
            else:
                keychain_token = functools.partial(read_keychain_token, allow_refresh=allow, location=where)
                force = functools.partial(_force_refresh, location=where)
            reading = collect(get_token=get_token or keychain_token,
                              fetch=fetch or http_fetch,
                              refresh=((force if allow else _no_refresh) if own_login else None))
        except UsageError as exc:
            usage_accounts.note_failure(account["id"], exc.code, str(exc))
            retry = None
            if exc.code in KEYCHAIN_CODES:
                retry = (moment + timedelta(seconds=KEYCHAIN_BACKOFF_S)).isoformat(timespec="seconds")
            if exc.code in UNAVAILABLE_CODES:
                reason = str(exc) if exc.code == CODE_EXPIRED else None
                _update_store({"syncError": exc.code, "lastError": reason, "keychainRetryAfter": retry})
            else:
                _record_error(str(exc), exc.code, retry)
                oauth_error = exc
        else:
            changes = dict(usage_record(reading, SOURCE_ENDPOINT), lastError=None, syncError=None,
                           keychainRetryAfter=None)
            stored, mirrors = _commit(changes, cfg)
            usage_accounts.note_reading(account["id"], stored)
            result = _result(stored, cfg, mirrors)
            _control_after_write()
            return result
    fallback = _fallbacks(cfg, moment)
    if fallback is not None:
        return fallback
    if oauth_error is not None:
        raise oauth_error
    if skip and background:
        return None
    if disconnected:
        return {"ok": True, "status": STATUS_DISCONNECTED, "reason": DISCONNECTED_REASON,
                "usage": view(_load_store(), max_age_s(cfg)), "mirrors": []}
    return _unavailable(cfg)


def _fallbacks(cfg, moment):
    """The sources after the endpoint: a fresh status line sidecar reading, then the transcript estimate. Returns
    the sync result when one stored a reading, else None. Never raises."""
    try:
        source = auto_update(None, moment.astimezone().replace(microsecond=0), cfg)
        if source:
            return dict(_result(_load_store(), cfg, []), status=None, reason=None)
    except Exception as exc:  # a fallback must never break the sync
        log.warning("usage sidecar skipped: %s", type(exc).__name__)
    # R10.40: estimates removed, site shows real readings only (estimate_once is kept but never called here)
    return None


def estimate_once(cfg, moment, roots=None):
    """Store an estimate from the local transcripts when the last real reading is old. Returns the sync result, or
    None when there is no base reading, it is still fresh, or the transcripts give nothing."""
    store = _load_store()
    last = store.get("lastReal")
    if not isinstance(last, dict):
        return None
    age = _age_s(last.get("updated"), moment)
    if age is None or age < ESTIMATE_AFTER_S:
        return None
    if store.get("estimate") is True:
        since = _age_s(store.get("updated"), moment)
        if since is not None and 0 <= since < ESTIMATE_GAP_S:
            return dict(_result(store, cfg, []), status="estimate", reason=None)
    cal = store.get("estimateCal") if isinstance(store.get("estimateCal"), dict) else {}
    if store.get("estimateCalFor") != last.get("updated"):
        at = _moment(last.get("updated"))
        events = usage_sources.usage_events(at - usage_sources.ONE_WEEK - usage_sources.FIVE_HOURS, roots)
        fresh = usage_sources.calibration(last, events)
        cal = dict(cal, **fresh)
        _update_store({"estimateCal": cal, "estimateCalFor": last.get("updated")})
    changes = usage_sources.estimate(last, cal, moment, roots)
    if not changes:
        return None
    changes.update({"updated": moment.astimezone().isoformat(timespec="seconds"), "source": SOURCE_ESTIMATE,
                    "estimate": True})
    stored, mirrors = _commit(changes, cfg)
    _control_after_write()
    return dict(_result(stored, cfg, mirrors), status="estimate", reason=None)


def _unavailable(cfg):
    """No usable Claude Code login and no fallback reading: not an error, so lastError is not set. Returns the sync
    result with status "unavailable" and the one-time setup step as the reason."""
    stored = _load_store()
    return {"ok": True, "status": STATUS_UNAVAILABLE, "reason": UNAVAILABLE_REASON,
            "usage": view(stored, max_age_s(cfg)), "mirrors": []}


def account_login_reset(disconnected=False):
    """R11.8: the active account was connected or disconnected. Clear the keychain backoff so the next sync tries at
    once (connect), or mark the store disconnected (disconnect). The stored reading stays."""
    _update_store({"keychainRetryAfter": None, "manualAttemptAt": None, "lastError": None,
                   "syncError": CODE_DISCONNECTED if disconnected else None})


def account_switched(reading, config=None):
    """R11.8: another account became active. Its last kept reading (or nothing) replaces the shown one, so the board
    never shows one account's numbers under another; the estimate base is reset; no ledger point is added."""
    cfg = _config(config)
    fields = {key: (reading or {}).get(key) for key in REAL_FIELDS}
    real = fields if fields.get("updated") else None
    connected = usage_accounts.active_for_sync(cfg)["connected"]
    stored = _update_store(dict(fields, lastReal=real, estimate=False, estimateCal=None, estimateCalFor=None,
                                keychainRetryAfter=None, manualAttemptAt=None, lastError=None,
                                syncError=None if connected else CODE_DISCONNECTED))
    mirrors = mirror_to_projects(cfg, stored) if _mirror_enabled(cfg) else []
    _control_after_write()
    return _result(stored, cfg, mirrors)


def show(config=None, now=None):
    """The stored usage with stale and ageS computed now."""
    cfg = _config(config)
    return view(_load_store(), max_age_s(cfg), now)


def stored_record():
    """The stored usage fields as they are now (undo keeps them before a write). Empty when nothing is stored."""
    return _load_store()


def _store_manual(changes, cfg, source, moment):
    """The one path for usage given by hand (push and the usage.set op): stamp it, store it, mirror it, recompute
    the control state. A manual value clears the last error."""
    changes.update({"updated": moment.isoformat(timespec="seconds"), "source": source,
                    "lastError": None, "syncError": None})
    stored, mirrors = _commit(changes, cfg)
    result = _result(stored, cfg, mirrors)
    _control_after_write()
    return result


def set_manual(weekly, five_hour=None, weekly_resets=None, five_resets=None, config=None, now=None):
    """Store usage typed in by the person or the head (the usage.set op). Percents are already checked by the op.
    The weekly window is always replaced; the 5-hour window only when five_hour is given."""
    cfg = _config(config)
    moment = now or datetime.now().astimezone()
    changes = {"weeklyPercent": _round_pct(weekly), "weeklyResetsAt": weekly_resets}
    if five_hour is not None:
        changes["fiveHourPercent"] = _round_pct(five_hour)
        changes["fiveHourResetsAt"] = five_resets
    return _store_manual(changes, cfg, SOURCE_MANUAL, moment)


def restore(fields, config=None):
    """Put back the stored usage fields that an undo of usage.set names. No ledger point is added."""
    cfg = _config(config)
    stored = _update_store({key: fields[key] for key in RESTORE_FIELDS if key in fields})
    mirrors = mirror_to_projects(cfg, stored) if _mirror_enabled(cfg) else []
    _control_after_write()
    return _result(stored, cfg, mirrors)


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
    return _store_manual(parse_push(text), cfg, SOURCE_PUSH, datetime.now().astimezone())


# ---------------------------------------------------------------- automatic readings (R7.77)
# Claude Code hands account rate limits to the status line command as
# {"rate_limits": {"five_hour": {"used_percentage", "resets_at"}, "seven_day": {...}}}; a hook payload may carry the
# same block. A status line script may also leave the last block in a sidecar file (token-optimizer writes
# ~/.claude/token-optimizer/rate-limits.json). Neither holds a secret. The hooks feed whatever they find here, at most
# once per AUTO_GAP_S, and only a reading newer than the stored one replaces it.

SOURCE_HOOK = "Claude Code hook"
SOURCE_STATUSLINE = "Claude Code status line"
AUTO_GAP_S = 60
SIDECAR_MAX_AGE_S = 15 * 60
WINDOWS = (("seven_day", "weekly"), ("five_hour", "fiveHour"))


def sidecar_path():
    return os.path.join(os.path.expanduser("~"), ".claude", "token-optimizer", "rate-limits.json")


def parse_rate_limits(block):
    """The usage changes in a Claude Code rate_limits block, or {} when it has no usable window."""
    changes = {}
    if not isinstance(block, dict):
        return changes
    for kind, prefix in WINDOWS:
        window = block.get(kind)
        value = _percent(window.get("used_percentage")) if isinstance(window, dict) else None
        if value is None or not (0 <= value <= 100):
            continue
        changes[prefix + "Percent"] = _round_pct(value)
        changes[prefix + "ResetsAt"] = _iso(window.get("resets_at"))
    return changes


def read_sidecar(path=None, now=None):
    """(changes, moment) from a fresh status line sidecar file, or ({}, None)."""
    path = path or sidecar_path()
    now = now or datetime.now().astimezone()
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.loads(handle.read(65536))
    except (OSError, ValueError):
        return {}, None
    stamp = data.get("timestamp") if isinstance(data, dict) else None
    if isinstance(stamp, bool) or not isinstance(stamp, (int, float)):
        return {}, None
    moment = datetime.fromtimestamp(int(stamp / 1000 if stamp > 1e11 else stamp)).astimezone()
    if (now - moment).total_seconds() > SIDECAR_MAX_AGE_S:
        return {}, None
    return parse_rate_limits(data), moment


def auto_update(payload=None, now=None, config=None, sidecar=None, source=SOURCE_HOOK):
    """Store usage from a hook payload's rate_limits block, else from the status line sidecar. At most once per
    AUTO_GAP_S (counted from the stored reading); a reading not newer than the stored one is skipped. Returns the source stored, or None. Never raises
    for a missing or bad reading."""
    now = (now or datetime.now().astimezone()).replace(microsecond=0)
    block = payload.get("rate_limits") if isinstance(payload, dict) else None
    changes, moment = parse_rate_limits(block), now
    if not changes:
        changes, moment = read_sidecar(sidecar, now)
        source = SOURCE_STATUSLINE
    if not changes:
        return None  # nothing to store: no lock is taken, so a hook with no reading costs one small file read
    store = _load_store()
    base = store.get("updated")
    if store.get("estimate") is True:  # a real reading always replaces an estimate
        base = (store.get("lastReal") or {}).get("updated") if isinstance(store.get("lastReal"), dict) else None
    stored = _moment(base)
    if stored is not None and (moment <= stored or (now - stored).total_seconds() < AUTO_GAP_S):
        return None
    _store_manual(changes, _config(config), source, moment)
    return source


def _control_after_write():
    """After a usage write, recompute the control state of every project: the limit rows read usage and the ledger.
    Best effort: control.recompute_all never raises."""
    from roadmap.services import control
    control.recompute_all()


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
    # With no injected config, read it fresh each round: the active account can change while the service runs.
    run_sync = sync if sync is not None else (lambda: sync_once(config if config is not None else None,
                                                                background=True))
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
