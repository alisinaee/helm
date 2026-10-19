"""Several Claude logins on one Linux machine, switched without logging in again (docs/USAGE-ACCOUNTS.md, Linux).

Claude Code on Linux keeps its login in two files: the OAuth token pair in ~/.claude/.credentials.json (key
claudeAiOauth) and who it is in ~/.claude.json (key oauthAccount). A second login lives in its own config folder
(CLAUDE_CONFIG_DIR=~/.claude-<name>) with the same two files inside it.

"Use in Claude Code" (use_in_claude) makes one stored login the one plain `claude` uses:

1. The login now in ~/.claude is first saved back to its own ~/.claude-<name> folder (found by accountUuid), or to
   a new folder that is then added as a Helm account, so no login is ever lost. Its token pair there is replaced
   with the live one, which is the freshest (refresh tokens rotate).
2. The chosen login's claudeAiOauth goes into ~/.claude/.credentials.json (other keys there, such as mcpOAuth, stay)
   and its oauthAccount into ~/.claude.json. Both files are written atomically with their old mode.

New Claude Code sessions use the new login; a session already running keeps the one it started with.

Web login (login_start / login_code): runs `claude auth login` for a config folder in a pseudo terminal, hands the
sign-in URL to the page, and types the code the person pastes back. Nothing here reads a token value out to a caller,
a log line or an error text. macOS keeps the login in the keychain, so the switch is Linux only there.
"""

import json
import os
import pty
import re
import select
import signal
import stat
import sys
import tempfile
import threading
import time

from roadmap.errors import EXIT_CONFLICT, EXIT_ERROR, EXIT_NOT_FOUND, EXIT_USAGE, RoadmapError
from roadmap.log import get_logger
from roadmap.services import usage_accounts
from roadmap.store import config as config_store
from roadmap.store import paths

log = get_logger("claude_slots")

OAUTH_KEY = "claudeAiOauth"
ACCOUNT_KEY = "oauthAccount"
CREDENTIALS_NAME = ".credentials.json"
STATE_NAME = ".claude.json"
FOLDER_PREFIX = ".claude-"
MAX_BYTES = 4_000_000
LOGIN_TTL_S = 10 * 60
LOGIN_URL_WAIT_S = 20
LOGIN_CODE_WAIT_S = 45
_URL_RE = re.compile(r"https://(?:[a-z0-9-]+\.)*(?:claude\.com|claude\.ai|anthropic\.com)/[^\s\x1b\x07\"'<>]+")
_CODE_RE = re.compile(r"[A-Za-z0-9#_.~-]{8,512}")
_ANSI_RE = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b\[[0-9;?]*[A-Za-z]")
_SLUG_RE = re.compile(r"[^a-z0-9-]+")

_lock = threading.RLock()
_logins = {}   # key -> {"pid", "fd", "folder", "accountId", "label", "url", "started", "out"}


def supported():
    """True where Claude Code keeps its login in files (not macOS, which uses the keychain)."""
    return sys.platform != "darwin"


def _need_support():
    if not supported():
        raise RoadmapError("conflict", "switching the Claude Code login is Linux only (macOS keeps it in the keychain)",
                           EXIT_CONFLICT)


def home():
    return os.path.expanduser("~")


def credentials_path(folder=None):
    """The credentials file of a config folder; None is plain `claude` (~/.claude)."""
    return os.path.join(folder or os.path.join(home(), ".claude"), CREDENTIALS_NAME)


def state_path(folder=None):
    """The .claude.json of a config folder; None is plain `claude` (~/.claude.json)."""
    return os.path.join(folder, STATE_NAME) if folder else os.path.join(home(), STATE_NAME)


def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.loads(handle.read(MAX_BYTES))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _write_json(path, data, default_mode=0o600):
    """Atomic write that keeps the old file's mode (0600 for a new one)."""
    try:
        mode = stat.S_IMODE(os.stat(path).st_mode)
    except OSError:
        mode = default_mode
    folder = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".helm-", suffix=".tmp")
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
        os.replace(tmp, path)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise RoadmapError("io_error", "could not write " + usage_accounts._home_short(path), EXIT_ERROR)


def oauth_account(folder=None):
    """The oauthAccount block (who is logged in) of a config folder, or None."""
    data = _read_json(state_path(folder))
    block = data.get(ACCOUNT_KEY) if data else None
    return block if isinstance(block, dict) and block.get("accountUuid") else None


def account_uuid(folder=None):
    block = oauth_account(folder)
    return block.get("accountUuid") if block else None


def _oauth(folder=None):
    data = _read_json(credentials_path(folder))
    block = data.get(OAUTH_KEY) if data else None
    return block if isinstance(block, dict) and block.get("accessToken") else None


def identity(folder=None):
    """{"email", "emailMasked", "orgName", "plan"} from a folder's files, or None. Reads no token value."""
    block = oauth_account(folder)
    if not block:
        return None
    email = block.get("emailAddress") if isinstance(block.get("emailAddress"), str) else None
    oauth = _oauth(folder) or {}
    org = block.get("organizationName") if isinstance(block.get("organizationName"), str) else None
    return {"email": email, "emailMasked": usage_accounts.mask_email(email),
            "orgName": usage_accounts.mask_email(org[:80]) if org else None,
            "plan": oauth.get("subscriptionType") if isinstance(oauth.get("subscriptionType"), str) else None}


def live_uuid():
    """The accountUuid plain `claude` uses now (~/.claude.json), or None."""
    return account_uuid(None)


def _folders(cfg):
    """Every known config folder: the Helm accounts' folders plus logged-in ~/.claude-* folders."""
    out = []
    for account in usage_accounts.accounts(cfg):
        folder = usage_accounts.config_dir_of(account)
        if folder and folder not in out:
            out.append(folder)
    try:
        names = sorted(os.listdir(home()))
    except OSError:
        names = []
    for name in names:
        full = os.path.join(home(), name)
        if name.startswith(FOLDER_PREFIX) and os.path.isdir(full) and full not in out:
            out.append(full)
    return out


def folder_of_uuid(uuid, cfg=None):
    """The stored config folder that holds this login, or None."""
    if not uuid:
        return None
    cfg = cfg if cfg is not None else config_store.load()
    for folder in _folders(cfg):
        if account_uuid(folder) == uuid:
            return folder
    return None


def _slug(text, taken):
    base = _SLUG_RE.sub("-", (text or "").lower()).strip("-")[:30].strip("-") or "account"
    slug, n = base, 2
    while slug in taken or os.path.exists(os.path.join(home(), FOLDER_PREFIX + slug)) or not paths.valid_id(slug):
        slug = ("%s-%d" % (base, n))[:40]
        n += 1
        if n > 99:
            raise RoadmapError("conflict", "no free account name", EXIT_CONFLICT)
    return slug


def _new_folder(slug):
    folder = os.path.join(home(), FOLDER_PREFIX + slug)
    os.makedirs(folder, mode=0o700, exist_ok=True)
    return folder


def _store_into(folder, oauth, block):
    """Put a login's token pair and identity into a config folder, keeping the folder's other keys."""
    creds = _read_json(credentials_path(folder)) or {}
    creds[OAUTH_KEY] = oauth
    _write_json(credentials_path(folder), creds)
    state = _read_json(state_path(folder)) or {}
    state[ACCOUNT_KEY] = block
    _write_json(state_path(folder), state)


def _account_for_folder(cfg, folder):
    for account in usage_accounts.accounts(cfg):
        if usage_accounts.config_dir_of(account) == folder:
            return account
    return None


def save_live(cfg=None, src="cli", data_dir=None):
    """Save the login plain `claude` uses now into its own config folder (made and added as an account when it has
    none). Returns the folder, or None when nobody is logged in."""
    cfg = cfg if cfg is not None else config_store.load()
    block, oauth = oauth_account(None), _oauth(None)
    if not block or not oauth:
        return None
    folder = folder_of_uuid(block["accountUuid"], cfg)
    if folder is None:
        email = block.get("emailAddress") if isinstance(block.get("emailAddress"), str) else ""
        taken = {a["id"] for a in usage_accounts.accounts(cfg)}
        slug = _slug(email.split("@")[0], taken)
        folder = _new_folder(slug)
    _store_into(folder, oauth, block)
    if _account_for_folder(cfg, folder) is None:
        name = os.path.basename(folder)[len(FOLDER_PREFIX):]
        taken = {a["id"] for a in usage_accounts.accounts(cfg)}
        account_id = name if paths.valid_id(name) and name not in taken else _slug(name, taken)
        usage_accounts.add(account_id, label=account_id, source="config-dir", path=folder, src=src,
                           data_dir=data_dir)
    return folder


def use_in_claude(account_id, src="cli", data_dir=None):
    """Make a stored login the one plain `claude` uses, without a new login. Returns the account list."""
    _need_support()
    with _lock:
        cfg = config_store.load()
        account = usage_accounts._find(cfg, account_id)
        folder = usage_accounts.config_dir_of(account)
        if not folder:
            raise RoadmapError("conflict", "'%s' is the login Claude Code uses already" % account_id, EXIT_CONFLICT)
        block, oauth = oauth_account(folder), _oauth(folder)
        if not block or not oauth:
            raise RoadmapError("conflict", "'%s' is not logged in: log in first" % account_id, EXIT_CONFLICT)
        if block["accountUuid"] == live_uuid():
            return usage_accounts.list_status()
        save_live(cfg, src=src, data_dir=data_dir)
        os.makedirs(os.path.dirname(credentials_path(None)), mode=0o700, exist_ok=True)
        live = _read_json(credentials_path(None)) or {}
        live[OAUTH_KEY] = oauth
        _write_json(credentials_path(None), live)
        state = _read_json(state_path(None)) or {}
        state[ACCOUNT_KEY] = block
        _write_json(state_path(None), state)
    usage_accounts._event("use-in-claude", account_id, src, data_dir)
    _after_switch(account_id)
    return usage_accounts.list_status()


def _after_switch(account_id):
    """The board's default login just changed: show the new login's kept reading until the next sync."""
    try:
        cfg = config_store.load()
        if usage_accounts.config_dir_of(usage_accounts._find(cfg, usage_accounts.active_id(cfg))) is None:
            from roadmap.services import usage
            usage.account_switched(usage_accounts.last_reading(account_id), config=cfg)
    except Exception as exc:
        log.warning("usage store not updated after the login switch: %s", type(exc).__name__)


# ---------------------------------------------------------------- web login (pseudo terminal)

def _claude():
    binary = usage_accounts.claude_binary()
    if not binary:
        raise RoadmapError("not_found", "the claude command was not found on this machine", EXIT_NOT_FOUND)
    return binary


def _spawn(argv, env):
    """Start argv in a pseudo terminal. Returns (pid, fd). Kept apart so tests replace it."""
    pid, fd = pty.fork()
    if pid == 0:  # child
        try:
            os.execvpe(argv[0], argv, env)
        finally:
            os._exit(127)
    return pid, fd


def _read_some(fd, wait_s):
    ready, _w, _x = select.select([fd], [], [], wait_s)
    if not ready:
        return b""
    try:
        return os.read(fd, 65536)
    except OSError:
        return b""


def _exited(pid):
    """The exit code when the child has ended, else None."""
    try:
        done, status = os.waitpid(pid, os.WNOHANG)
    except ChildProcessError:
        return -1
    if done == 0:
        return None
    return os.waitstatus_to_exitcode(status)


def _stop(entry):
    try:
        os.kill(entry["pid"], signal.SIGTERM)
    except OSError:
        pass
    try:
        os.close(entry["fd"])
    except OSError:
        pass
    _exited(entry["pid"])


def _sweep(now):
    for key in [k for k, e in _logins.items() if now - e["started"] > LOGIN_TTL_S]:
        _stop(_logins.pop(key))


def _expire(key, pid):
    """Stop a login nobody finished within LOGIN_TTL_S."""
    with _lock:
        entry = _logins.get(key)
        if entry is not None and entry["pid"] == pid:
            _stop(_logins.pop(key))


def find_url(text):
    """The sign-in URL in `claude auth login` output (terminal codes removed), or None."""
    found = _URL_RE.search(_ANSI_RE.sub(" ", text or ""))
    return found.group(0) if found else None


def login_start(account_id=None, label=None, spawn=None, now_s=None):
    """Start `claude auth login` for an account's folder, or for a new folder named after label. Returns
    {"key", "url", "folder"}. The person opens the URL, signs in and pastes the code to login_code."""
    _need_support()
    spawn = spawn or _spawn
    now = time.time() if now_s is None else now_s
    cfg = config_store.load()
    with _lock:
        _sweep(now)
        if account_id:
            account = usage_accounts._find(cfg, account_id)
            folder, key, name = usage_accounts.config_dir_of(account), account["id"], account["label"]
        else:
            name = usage_accounts._clean_label(label, "")
            taken = {a["id"] for a in usage_accounts.accounts(cfg)} | set(_logins)
            key = _slug(name, taken)
            folder = os.path.join(home(), FOLDER_PREFIX + key)
        if key in _logins:
            _stop(_logins.pop(key))
        if folder:
            os.makedirs(folder, mode=0o700, exist_ok=True)
        env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE_CODE") and k != "CLAUDECODE"}
        env.pop("CLAUDE_CONFIG_DIR", None)
        if folder:
            env["CLAUDE_CONFIG_DIR"] = folder
        env.update({"BROWSER": "/bin/false", "TERM": "dumb", "NO_COLOR": "1"})
        env.pop("DISPLAY", None)
        pid, fd = spawn([_claude(), "auth", "login"], env)
        entry = {"pid": pid, "fd": fd, "folder": folder, "accountId": account_id, "label": name, "key": key,
                 "url": None, "started": now, "out": ""}
        _logins[key] = entry
        timer = threading.Timer(LOGIN_TTL_S, _expire, args=(key, pid))
        timer.daemon = True
        timer.start()
        deadline = time.time() + LOGIN_URL_WAIT_S
        while entry["url"] is None and time.time() < deadline:
            entry["out"] = (entry["out"] + _read_some(fd, 0.5).decode("utf-8", "replace"))[-20000:]
            entry["url"] = find_url(entry["out"])
            if entry["url"] is None and _exited(pid) is not None:
                break
        if entry["url"] is None:
            _stop(_logins.pop(key))
            raise RoadmapError("error", "claude auth login gave no sign-in link", EXIT_ERROR)
    usage_accounts._event("login-start", key, "ui", None)
    return {"key": key, "url": entry["url"], "folder": usage_accounts._home_short(folder) if folder else "~/.claude"}


def login_code(key, code, src="ui", data_dir=None):
    """Type the pasted code into the waiting login, wait for it to finish, add a new folder as an account and read
    who is logged in. Returns the account list plus {"loggedIn": key}."""
    _need_support()
    if not isinstance(code, str) or not _CODE_RE.fullmatch(code.strip()):
        raise RoadmapError("invalid_input", "the code does not look right: paste the whole code", EXIT_USAGE)
    with _lock:
        entry = _logins.get(key)
        if entry is None:
            raise RoadmapError("not_found", "no login is waiting for a code: start the login again", EXIT_NOT_FOUND)
        os.write(entry["fd"], code.strip().encode("ascii") + b"\r")
        deadline = time.time() + LOGIN_CODE_WAIT_S
        status = None
        while status is None and time.time() < deadline:
            entry["out"] = (entry["out"] + _read_some(entry["fd"], 0.5).decode("utf-8", "replace"))[-20000:]
            status = _exited(entry["pid"])
        _logins.pop(key, None)
        if status is None:
            _stop(entry)
            raise RoadmapError("error", "the login did not finish in time: start it again", EXIT_ERROR)
        try:
            os.close(entry["fd"])
        except OSError:
            pass
        folder = entry["folder"]
        if status != 0 or not oauth_account(folder) or not _oauth(folder):
            raise RoadmapError("error", "the login was not accepted (wrong or old code): start it again", EXIT_ERROR)
        cfg = config_store.load()
        account_id = entry["accountId"]
        if account_id is None:
            existing = _account_for_folder(cfg, folder)
            if existing is None:
                usage_accounts.add(key, label=entry["label"], source="config-dir", path=folder, src=src,
                                   data_dir=data_dir)
                account_id = key
            else:
                account_id = existing["id"]
    try:
        usage_accounts.check(account_id)
    except Exception as exc:
        log.warning("identity check after login failed: %s", type(exc).__name__)
    usage_accounts._event("login", account_id, src, data_dir)
    result = usage_accounts.list_status()
    result["loggedIn"] = account_id
    return result


def login_cancel(key):
    with _lock:
        entry = _logins.pop(key, None)
        if entry is not None:
            _stop(entry)
    return {"cancelled": entry is not None}

