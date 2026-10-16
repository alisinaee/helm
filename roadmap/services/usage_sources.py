"""Where account usage comes from when nobody pastes it (R10.29). services/usage.py runs the chain; this module holds
the sources and has no store of its own.

1. Claude Code OAuth login: the "Claude Code-credentials" keychain item (macOS) or ~/.claude/.credentials.json
   (Linux, or $CLAUDE_CONFIG_DIR). The access token is refreshed with its refresh token shortly before it expires
   (or after a 401) and the new pair is written back to the same place, the way Claude Code does it, so the login
   Claude Code keeps never goes stale and never gets out of step with ours.
2. Claude Code's own rate_limits block (status line command `roadmap usage statusline`, hook payloads, the
   token-optimizer sidecar): handled by usage.auto_update.
3. Estimate from the local Claude Code transcripts (~/.claude/projects/**/*.jsonl, read only): the tokens in each
   window, scaled by the tokens-per-percent of the last real reading. Always labelled an estimate.

Secrets: tokens stay in memory, go only to Anthropic hosts over HTTPS, and never appear in a log line, an exception
text or argv (the keychain write goes through `security -i` on stdin, hex encoded). A credentials file is rewritten
atomically with mode 0600.
"""

import json
import os
import re
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

KEYCHAIN_SERVICE = "Claude Code-credentials"
KEYCHAIN_TIMEOUT_S = 10
KEYCHAIN_ITEM_NOT_FOUND = 44
OAUTH_KEY = "claudeAiOauth"
# Claude Code's public OAuth client (PKCE, no secret) and its token hosts, newest first.
CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
TOKEN_URLS = ("https://platform.claude.com/v1/oauth/token", "https://console.anthropic.com/v1/oauth/token")
TOKEN_HOSTS = ("platform.claude.com", "console.anthropic.com")
REFRESH_MARGIN_S = 5 * 60
TIMEOUT_S = 10
MAX_BYTES = 1_000_000

CODE_NO_TOKEN = "no_token"
CODE_NO_ITEM = "no_item"
CODE_DENIED = "denied"
CODE_EXPIRED = "expired"
CODE_NET = "net"
CODE_OTHER = "other"


class SourceError(Exception):
    """A source failed. str() is a short plain reason without any secret; code is a usage CODE_* value."""

    def __init__(self, message, code=CODE_OTHER):
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------- 1. OAuth credentials and refresh

def credentials_file():
    base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    return os.path.join(base.split(",")[0].strip(), ".credentials.json")


def _keychain_read():
    """The raw keychain JSON text. Raises SourceError with a keychain code."""
    try:
        proc = subprocess.run(["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
                              capture_output=True, text=True, timeout=KEYCHAIN_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        raise SourceError("keychain did not answer in time")
    except OSError:
        raise SourceError("keychain tool is not available", CODE_NO_ITEM)
    if proc.returncode == KEYCHAIN_ITEM_NOT_FOUND:
        raise SourceError("keychain item not found, sign in to Claude Code first", CODE_NO_ITEM)
    if proc.returncode != 0:
        raise SourceError("keychain access denied or failed (exit %d)" % proc.returncode, CODE_DENIED)
    return proc.stdout


def _keychain_account():
    """The keychain item's account name (metadata only, no -w)."""
    proc = subprocess.run(["security", "find-generic-password", "-s", KEYCHAIN_SERVICE],
                          capture_output=True, text=True, timeout=KEYCHAIN_TIMEOUT_S)
    found = re.search(r'"acct"<blob>="([^"\n]*)"', proc.stdout or "")
    return found.group(1) if found else (os.environ.get("USER") or "")


def _keychain_write(text):
    """Replace the keychain item's data, keeping its account. The secret goes hex encoded through stdin."""
    account = _keychain_account()
    if not account or re.search(r'["\\\n]', account):
        raise SourceError("keychain account name is not usable")
    line = 'add-generic-password -U -a "%s" -s "%s" -X %s\n' % (account, KEYCHAIN_SERVICE,
                                                                text.encode("utf-8").hex())
    try:
        proc = subprocess.run(["security", "-i"], input=line, capture_output=True, text=True,
                              timeout=KEYCHAIN_TIMEOUT_S)
    except (subprocess.TimeoutExpired, OSError):
        raise SourceError("keychain write did not finish")
    if proc.returncode != 0 or (proc.stderr or "").strip():
        raise SourceError("keychain write failed (exit %d)" % proc.returncode)


def _file_write(path, text):
    folder = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".credentials.", suffix=".tmp")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise SourceError("credentials file write failed")


def load_credentials():
    """(oauth dict, raw dict, place) from the keychain, else the credentials file. place is ("keychain", None) or
    ("file", path). Raises SourceError (no_item, no_token, denied)."""
    keychain_error = None
    try:
        text, place = _keychain_read(), ("keychain", None)
    except SourceError as exc:
        keychain_error, text, place = exc, None, None
    if text is None or OAUTH_KEY not in text:
        path = credentials_file()
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    text, place = handle.read(MAX_BYTES), ("file", path)
            except OSError:
                pass
    if text is None:
        raise keychain_error or SourceError("no Claude Code login found", CODE_NO_ITEM)
    try:
        raw = json.loads(text)
    except ValueError:
        raise SourceError("keychain entry has no usable token", CODE_NO_TOKEN)
    oauth = raw.get(OAUTH_KEY) if isinstance(raw, dict) else None
    token = oauth.get("accessToken") if isinstance(oauth, dict) else None
    if not isinstance(token, str) or not token.strip():
        raise SourceError("keychain entry has no usable token", CODE_NO_TOKEN)
    return oauth, raw, place


def _expires_soon(oauth, now_s):
    value = oauth.get("expiresAt")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    seconds = value / 1000 if value > 1e11 else value
    return seconds - now_s < REFRESH_MARGIN_S


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise SourceError("token endpoint redirected, refusing to follow")


def _post_json(url, body):
    """POST JSON to an Anthropic token host and return the parsed reply. Kept apart so tests replace the network."""
    if not any(url.startswith("https://" + host + "/") for host in TOKEN_HOSTS):
        raise SourceError("token address is not an Anthropic host")
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST", headers={
        "Content-Type": "application/json", "Accept": "application/json", "User-Agent": "roadmap-dashboard"})
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(req, timeout=TIMEOUT_S) as resp:
            raw = resp.read(MAX_BYTES)
    except urllib.error.HTTPError as e:
        code = CODE_EXPIRED if e.code in (400, 401, 403) else CODE_OTHER
        raise SourceError("token refresh answered HTTP %d" % e.code, code)
    except (socket.timeout, TimeoutError, urllib.error.URLError, OSError):
        raise SourceError("token endpoint not reachable", CODE_NET)
    try:
        return json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise SourceError("token reply is not valid JSON")


def refresh(oauth, raw, place, post=None, write=None, now_s=None):
    """Trade the refresh token for a new pair, write it back where it came from, and return the new access token.
    A refused refresh (HTTP 400/401/403) raises code expired: the login must be renewed once by hand."""
    post = post or _post_json
    now_s = time.time() if now_s is None else now_s
    token = oauth.get("refreshToken")
    if not isinstance(token, str) or not token:
        raise SourceError("the Claude Code login has no refresh token", CODE_EXPIRED)
    body = {"grant_type": "refresh_token", "refresh_token": token, "client_id": CLIENT_ID}
    reply, last = None, None
    for url in TOKEN_URLS:
        try:
            reply = post(url, body)
            break
        except SourceError as exc:
            last = exc
            if exc.code == CODE_EXPIRED:
                raise
    if reply is None:
        raise last or SourceError("token refresh failed", CODE_NET)
    access = reply.get("access_token") if isinstance(reply, dict) else None
    if not isinstance(access, str) or not access:
        raise SourceError("token reply has no access token")
    new = dict(oauth, accessToken=access)
    if isinstance(reply.get("refresh_token"), str) and reply["refresh_token"]:
        new["refreshToken"] = reply["refresh_token"]
    expires_in = reply.get("expires_in")
    if isinstance(expires_in, (int, float)) and not isinstance(expires_in, bool):
        new["expiresAt"] = int((now_s + expires_in) * 1000)
    out = dict(raw)
    out[OAUTH_KEY] = new
    text = json.dumps(out)
    (write or _write_back)(place, text)
    return access


def _write_back(place, text):
    kind, path = place
    if kind == "file":
        _file_write(path, text)
    else:
        _keychain_write(text)


def access_token(force=False, now_s=None, post=None, write=None):
    """A usable Claude Code access token, refreshed first when it expires within 5 minutes (or force is set)."""
    now_s = time.time() if now_s is None else now_s
    oauth, raw, place = load_credentials()
    if force or _expires_soon(oauth, now_s):
        # Read again right before the refresh: Claude Code may have refreshed it a moment ago.
        oauth, raw, place = load_credentials()
        if force or _expires_soon(oauth, now_s):
            return refresh(oauth, raw, place, post=post, write=write, now_s=now_s)
    return oauth["accessToken"].strip()


# ---------------------------------------------------------------- 3. transcript estimate

FIVE_HOURS = timedelta(hours=5)
ONE_WEEK = timedelta(days=7)
MIN_CAL_PERCENT = 2           # a reading below this gives no usable tokens-per-percent
CACHE_READ_WEIGHT = 0.1
_cache = {}                   # path -> {"offset", "events": [(epoch_s, weight, key)]} (in-memory, per process)


def transcript_roots():
    roots = []
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    if env:
        roots += [os.path.join(p.strip(), "projects") for p in env.split(",") if p.strip()]
    home = os.path.expanduser("~")
    roots += [os.path.join(home, ".claude", "projects"), os.path.join(home, ".config", "claude", "projects")]
    return [r for i, r in enumerate(roots) if r not in roots[:i] and os.path.isdir(r)]


def _weight(usage):
    def n(key):
        v = usage.get(key)
        return v if isinstance(v, (int, float)) and not isinstance(v, bool) else 0
    return (n("input_tokens") + n("output_tokens") + n("cache_creation_input_tokens")
            + CACHE_READ_WEIGHT * n("cache_read_input_tokens"))


def _event(line):
    try:
        row = json.loads(line)
    except ValueError:
        return None
    if not isinstance(row, dict) or row.get("type") != "assistant":
        return None
    msg = row.get("message")
    usage = msg.get("usage") if isinstance(msg, dict) else None
    stamp = row.get("timestamp")
    if not isinstance(usage, dict) or not isinstance(stamp, str):
        return None
    try:
        moment = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    key = (msg.get("id"), row.get("requestId"))
    return moment.timestamp(), _weight(usage), key


def _scan_file(path, since_s):
    entry = _cache.get(path)
    try:
        size = os.path.getsize(path)
    except OSError:
        return []
    if entry is None or size < entry["offset"]:
        entry = {"offset": 0, "events": []}
    if size > entry["offset"]:
        try:
            with open(path, "rb") as handle:
                handle.seek(entry["offset"])
                chunk = handle.read()
        except OSError:
            return entry["events"]
        end = chunk.rfind(b"\n") + 1  # a half-written last line is read next time
        for line in chunk[:end].splitlines():
            if b'"usage"' not in line:
                continue
            ev = _event(line.decode("utf-8", "replace"))
            if ev is not None:
                entry["events"].append(ev)
        entry["offset"] += end
    entry["events"] = [e for e in entry["events"] if e[0] >= since_s]
    _cache[path] = entry
    return entry["events"]


def usage_events(since, roots=None):
    """[(epoch_s, weight)] of every assistant reply since `since` (aware datetime), one per message."""
    since_s = since.timestamp()
    seen, out = set(), []
    for root in roots if roots is not None else transcript_roots():
        for folder, _dirs, files in os.walk(root):
            for name in files:
                if not name.endswith(".jsonl"):
                    continue
                path = os.path.join(folder, name)
                try:
                    if os.path.getmtime(path) < since_s:
                        continue
                except OSError:
                    continue
                for stamp, weight, key in _scan_file(path, since_s):
                    if key != (None, None):
                        if key in seen:
                            continue
                        seen.add(key)
                    out.append((stamp, weight))
    return out


def _tokens(events, start, end):
    a, b = start.timestamp(), end.timestamp()
    return sum(w for s, w in events if a <= s <= b)


def _aware(text):
    if not isinstance(text, str):
        return None
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.astimezone()


def _window_now(events, last_reset, length, now, step):
    """(start, resets_at) of the window that holds now, from the last known reset time. A passed 5-hour reset
    starts a new window at the first reply after it (hour floor); a passed weekly reset moves on by whole weeks."""
    if last_reset is not None and last_reset > now:
        return last_reset - length, last_reset
    if last_reset is None:
        return now - length, None
    if step:
        reset = last_reset
        while reset <= now:
            reset += length
        return reset - length, reset
    after = sorted(s for s, _w in events if s > last_reset.timestamp())
    if not after:
        return now, None
    first = datetime.fromtimestamp(after[0], timezone.utc).replace(minute=0, second=0, microsecond=0)
    if first + length <= now:
        first = now - length
    return first, first + length


def calibration(last_real, events):
    """{"fiveHour": tokens per percent, "weekly": ...} from the last real reading and the transcripts up to it."""
    out = {}
    at = _aware(last_real.get("updated")) if isinstance(last_real, dict) else None
    if at is None:
        return out
    for prefix, length in (("fiveHour", FIVE_HOURS), ("weekly", ONE_WEEK)):
        pct = last_real.get(prefix + "Percent")
        reset = _aware(last_real.get(prefix + "ResetsAt"))
        if not isinstance(pct, (int, float)) or pct < MIN_CAL_PERCENT or reset is None:
            continue
        tokens = _tokens(events, reset - length, at)
        if tokens > 0:
            out[prefix] = tokens / float(pct)
    return out


def estimate(last_real, cal, now=None, roots=None):
    """The usage changes estimated from the transcripts, or {} when there is no calibration. Percents are capped
    at 100 and rounded to whole numbers; resets follow the last real reading."""
    now = now or datetime.now(timezone.utc)
    if not isinstance(last_real, dict) or not cal:
        return {}
    events = usage_events(now - ONE_WEEK - FIVE_HOURS, roots)
    changes = {}
    for prefix, length, step in (("fiveHour", FIVE_HOURS, False), ("weekly", ONE_WEEK, True)):
        ratio = cal.get(prefix)
        if not isinstance(ratio, (int, float)) or ratio <= 0:
            continue
        start, reset = _window_now(events, _aware(last_real.get(prefix + "ResetsAt")), length, now, step)
        pct = min(100, int(round(_tokens(events, start, now) / ratio)))
        changes[prefix + "Percent"] = pct
        changes[prefix + "ResetsAt"] = reset.astimezone().isoformat(timespec="seconds") if reset else None
    return changes
