"""API v1 routes: the path table, the reply helpers and one function per route.

A handler takes (app, request, match) and returns a Reply, or raises RoadmapError (mapped to a status by
status_for). Reads never write. POST /api/v1/usage/sync is the only write route. Every write checks CSRF, the
Content-Type and the body size before it does anything.
"""

import hashlib
import json
import os
import platform
import re
from datetime import datetime
from urllib.parse import parse_qsl

from roadmap import __version__
from roadmap.core import head as head_rules
from roadmap.core.snapshot import (ACTIVE, HEAD_JOB_STATES, SNAPSHOT_SCHEMA_VERSION, _progress, _resolve_links,
                                   head_link_state, head_row)
from roadmap.errors import (EXIT_CONFLICT, EXIT_ERROR, EXIT_EXTERNAL, EXIT_INVALID_DATA, EXIT_NOT_FOUND,
                            EXIT_USAGE, RoadmapError)
from roadmap import log as rlog
from roadmap.http import security
from roadmap.services import agentguard, commands, control, loader, usage, usage_accounts
from roadmap.services import git as git_service
from roadmap.services import head as head_service
from roadmap.services import history as history_service
from roadmap.services import headpanel, presence
from roadmap.services import jobs as job_service
from roadmap.services import system as system_service
from roadmap.services import system_arch, system_v2
from roadmap.services import work as work_service
from roadmap.services import systemheat
from roadmap.services import tokenhist
from roadmap.services import tasks as task_service
from roadmap.core.parsers import parse_jobs
from roadmap.store import config as config_store
from roadmap.store import schema

API_VERSION = "v1"
JSON_TYPE = "application/json; charset=utf-8"
JSON_MEDIA = "application/json"
STATUS_BY_CODE = {
    "misdirected_request": 421,
    "forbidden": 403,
    "too_large": 413,
    "unsupported_media_type": 415,
    "method_not_allowed": 405,
    "not_found": 404,
    "conflict": 409,
    "usage_unavailable": 502,
    "invalid_input": 400,
    "invalid_args": 422,
    "unknown_op": 404,
    "rate_limited": 429,
}
STATUS_BY_EXIT = {EXIT_USAGE: 400, EXIT_NOT_FOUND: 404, EXIT_CONFLICT: 409, EXIT_INVALID_DATA: 500, EXIT_EXTERNAL: 502}


class Reply:
    """One response: status, body bytes, content type, extra headers and the CSP to send with it."""

    __slots__ = ("status", "body", "ctype", "headers", "csp")

    def __init__(self, status, body=b"", ctype=JSON_TYPE, headers=(), csp=None):
        self.status = status
        self.body = body
        self.ctype = ctype
        self.headers = [("Cache-Control", "no-cache")] + list(headers)
        self.csp = csp


def json_reply(status, obj, headers=()):
    """A JSON reply. Keys keep their order; the body is UTF-8."""
    return Reply(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"), headers=headers)


def error_reply(status, code, message, headers=()):
    """The error envelope: {"error": {"code", "message"}}."""
    return json_reply(status, {"error": {"code": code, "message": message}}, headers)


def status_for(exc):
    """The HTTP status for a RoadmapError: by its code first, then by its CLI exit code, else 500."""
    if exc.code in STATUS_BY_CODE:
        return STATUS_BY_CODE[exc.code]
    return STATUS_BY_EXIT.get(exc.exit, 500)


def etag_matches(header, etag):
    """True when an If-None-Match header names the ETag (weak and strong forms compare equal here)."""
    if not header:
        return False
    if header.strip() == "*":
        return True
    for part in header.split(","):
        candidate = part.strip()
        if candidate.startswith("W/"):
            candidate = candidate[2:]
        if candidate == etag:
            return True
    return False


VOLATILE_KEYS = frozenset({"server_time", "elapsed_s", "age", "age_min"})


def _without_volatile(value):
    """The value with every clock-driven key (VOLATILE_KEYS) removed at any depth. Those keys stay in the response."""
    if isinstance(value, dict):
        return {key: _without_volatile(item) for key, item in value.items() if key not in VOLATILE_KEYS}
    if isinstance(value, list):
        return [_without_volatile(item) for item in value]
    return value


def content_etag(obj):
    """A strong ETag over a JSON body, with the clock-driven keys left out, so a poll with no real change gives a 304
    even while a running job's elapsed_s or a head row's age moves on."""
    raw = json.dumps(_without_volatile(obj), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return '"%s"' % hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


_ABS_PATH = re.compile(r"(?<![\w.~:/])/[^\s\"'`<>()\[\]{}]+")  # URLs (after ':' or '/') are left alone


def _phone_public(snap):
    """The snapshot as the phone listener may show it: project.path dropped; in every string value the home folder
    becomes ~ and any other absolute path becomes ...last-two-segments. Keys and numbers are not changed."""
    home = os.path.expanduser("~").rstrip("/")
    home_re = re.compile(re.escape(home) + r"(?!\w)") if home else None

    def shorten(match):
        segs = [s for s in match.group(0).split("/") if s]
        return "…/" + "/".join(segs[-2:]) if segs else "…"

    def scrub_text(text):
        if home_re is not None:
            text = home_re.sub("~", text)
        return _ABS_PATH.sub(shorten, text)

    def scrub(value):
        if isinstance(value, dict):
            return {k: scrub(v) for k, v in value.items()}
        if isinstance(value, list):
            return [scrub(v) for v in value]
        if isinstance(value, str):
            return scrub_text(value)
        return value

    out = scrub(snap)
    if isinstance(out.get("project"), dict):
        out["project"].pop("path", None)
    return out


def _rev_etag(rev):
    """The ETag of a snapshot: its revision (loader.revision), quoted."""
    return '"%s"' % rev


def _since_rev(query):
    """The revision named by ?since= in a query string, quotes stripped, or None when the query has no since."""
    for key, value in parse_qsl(query or "", keep_blank_values=True):
        if key == "since":
            return value.strip().strip('"')
    return None


def _snapshot_reply(req, pid, headers=(), app=None):
    """The snapshot of project pid. The revision is checked first: a matching If-None-Match, or ?since=<rev> equal to
    the current revision, gives 304 (unchanged) without any build. Otherwise the cached build for that revision is
    served, and its snap["rev"] is the ETag."""
    current = loader.project_revision(pid)
    pre = _rev_etag(current)
    if etag_matches(req.headers.get("If-None-Match"), pre) or _since_rev(req.query) == current:
        return Reply(304, headers=[("ETag", pre)] + list(headers))
    snap = loader.load_snapshot(pid)
    etag = _rev_etag(snap["rev"])
    if app is not None and app.cmd_source == "phone":
        snap = _phone_public(snap)
    body = json.dumps(snap, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return Reply(200, body, headers=[("ETag", etag)] + list(headers))


def _now_iso():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _guard_refused(app, reason, path):
    """Record one guard refusal (core.guard): the reason code and the path only. Never a header value or a body.
    The lines share a per-minute budget, so a flood of refused requests cannot push the real WARN and ERROR lines out."""
    if not app.guard_lines.take(1):
        return
    rlog.debug_event("core", "WARN", "core.guard", msg=reason, route=path, data={"reason": reason})


def _write_guard(app, req):
    """CSRF, Sec-Fetch-Site or Origin, then Content-Type, then body size. Raises before anything is done."""
    reason = security.write_refusal(req.headers, app.csrf_token(), app.port)
    if reason is not None:
        _guard_refused(app, reason, req.path)
        raise RoadmapError("forbidden", "this write needs the page's own CSRF token from the same origin",
                           EXIT_ERROR)
    ctype = (req.headers.get("Content-Type") or "").split(";")[0].strip().lower()
    if ctype != JSON_MEDIA:
        _guard_refused(app, "ctype", req.path)
        raise RoadmapError("unsupported_media_type", "write requests must send Content-Type: application/json",
                           EXIT_USAGE)


# ---------------------------------------------------------------- handlers

def health(app, req, match):
    return json_reply(200, {"ok": True, "version": __version__, "server_time": _now_iso()})


def meta(app, req, match):
    cfg = config_store.load()
    usage_cfg = cfg.get("usage") if isinstance(cfg.get("usage"), dict) else {}
    extra = {"csrf": app.csrf_token()} if app.cmd_source == "phone" else {}  # the phone's own value, never the main one
    body = {
        "version": __version__,
        "api_version": API_VERSION,
        "snapshot_schema_version": SNAPSHOT_SCHEMA_VERSION,
        "schema_versions": dict(schema.CURRENT),
        "poll_intervals_s": {"snapshot": 2, "usage": 30, "hidden_tab": 30},
        "usage_interval_s": usage_cfg.get("intervalS", usage.DEFAULT_INTERVAL_S),
    }
    body.update(extra)
    return json_reply(200, body)


def _summary(entry, snap):
    return {
        "id": entry["id"],
        "name": entry["name"],
        "progress": snap["overall"]["project"]["progress"],
        "tasks_left": snap["summary"]["tasks_left"],
        "running": snap["summary"]["running_count"],
        "need_user": snap["summary"]["need_user"],
        "errors_count": len(snap["errors"]),
        "stale": any(e.get("file") == "tasks.json" for e in snap["errors"]),
    }


def projects(app, req, match):
    """The project list. Each row is built from the same cached snapshot the project's own route serves, so the list
    and an open section cannot disagree. The ETag is the joined project revisions; a match gives 304 with no build."""
    entries = config_store.list_projects()
    pre = "|".join(loader.project_revision(entry["id"]) for entry in entries)
    if etag_matches(req.headers.get("If-None-Match"), '"%s"' % pre):
        return Reply(304, headers=[("ETag", '"%s"' % pre)])
    snaps = [loader.load_snapshot(entry["id"]) for entry in entries]
    etag = '"%s"' % "|".join(snap["rev"] for snap in snaps)
    body = {"projects": [_summary(entry, snap) for entry, snap in zip(entries, snaps)]}
    return json_reply(200, body, headers=[("ETag", etag)])


def project_snapshot(app, req, match):
    return _snapshot_reply(req, match.group("pid"), app=app)


def usage_get(app, req, match):
    return json_reply(200, usage.show())


def usage_sync(app, req, match):
    _write_guard(app, req)
    body = req.read_body()
    if body.strip():
        try:
            parsed = security.strict_json_loads(body.decode("utf-8"))
        except ValueError:
            raise RoadmapError("invalid_input", "the body must be JSON or empty", EXIT_USAGE)
        if not isinstance(parsed, dict):
            raise RoadmapError("invalid_input", "the body must be a JSON object", EXIT_USAGE)
    try:
        app.sync()
    except usage.UsageError as exc:
        raise RoadmapError("usage_unavailable", str(exc), EXIT_EXTERNAL)
    src = _cmd_source(app, req)[0]
    panel_dir = _panel_dir() if src in headpanel.PERSON_SOURCES else None
    if panel_dir:
        headpanel.record(panel_dir, "usage.sync", "usage Update pressed: a fresh usage reading was asked for",
                         src=src)
    return json_reply(200, usage.show())


ACCOUNT_ACTIONS = ("connect", "disconnect", "switch", "check", "login")


def usage_accounts_get(app, req, match):
    """GET /api/v1/usage/accounts: the Tokens page Account tab's rows, emails masked. Read only."""
    return json_reply(200, usage_accounts.list_status(full_email=False))


def usage_accounts_action(app, req, match):
    """POST /api/v1/usage/accounts/{id}/{action}: connect, disconnect, switch, check or login one account.
    The write guard runs first. An unknown action or account id gives a 404 error envelope."""
    _write_guard(app, req)
    account_id, action = match.group("id"), match.group("action")
    if action not in ACCOUNT_ACTIONS:
        raise RoadmapError("not_found", "no account action '%s'" % action[:40], EXIT_NOT_FOUND)
    if action == "check":
        result = usage_accounts.check(account_id)
    elif action == "login":
        result = usage_accounts.open_login(account_id, src="ui")
    elif action == "connect":
        result = usage_accounts.connect(account_id, src="ui")
    elif action == "disconnect":
        result = usage_accounts.disconnect(account_id, src="ui")
    else:
        result = usage_accounts.switch(account_id, src="ui")
    return json_reply(200, result)


def cmd(app, req, match):
    """POST /api/v1/cmd {op, args, project?}: one registry op. Order: CSRF and origin, JSON type, body size (413),
    JSON object (422), known op (404 unknown_op), the phone allowlist (403), the rate limit (429), the op's own
    checks (422 with the problem), then the write, the activity line and the control recompute."""
    _write_guard(app, req)
    body = req.read_body()
    try:
        parsed = security.strict_json_loads(body.decode("utf-8"))
    except ValueError:
        return _invalid("the body must be a JSON object with op and args")
    if not isinstance(parsed, dict):
        return _invalid("the body must be a JSON object with op and args")
    op = parsed.get("op")
    args = parsed.get("args") if parsed.get("args") is not None else {}
    if not isinstance(args, dict):
        return _invalid("args must be an object")
    request_key = req.headers.get("Idempotency-Key")
    if request_key is not None and not _IDEM_KEY_RE.fullmatch(request_key):
        return _invalid("Idempotency-Key must be 1 to 128 visible ASCII characters")
    if not isinstance(op, str) or op not in commands.public_ops():
        return error_reply(404, "unknown_op", "no op named '%s' (see docs/API.md)" % str(op)[:60])
    if not app.op_allowed(op):
        raise RoadmapError("forbidden", "op " + op + " is not allowed on this listener", EXIT_ERROR)
    if not app.cmd_limiter.allow():
        return error_reply(429, "rate_limited", "at most %d ops per second; wait a moment" % security.CMD_OPS_PER_S,
                           headers=[("Retry-After", "1")])
    project = _cmd_project(parsed.get("project"))
    _, data_dir = task_service.resolve(project)
    source, proven = _cmd_source(app, req)
    try:
        with agentguard.browser_proven(proven), commands.context(source, project):
            reply = commands.run(op, args, source, data_dir, request_key=request_key)
    except RoadmapError as exc:
        if exc.code == "usage":
            return _invalid(exc.message)
        raise
    control.after_write(project)
    _to_head(data_dir, reply, headpanel.record_op(data_dir, op, args, reply, source))
    return json_reply(200, reply)


def _to_head(data_dir, reply, line):
    """R11.2: the person's write is on its way to the head. The reply names the panel line and whether a head session
    is listening (watching, open or none), so the board can say sent / seen / acted. Never fails the write."""
    if isinstance(reply, dict) and line:
        reply["panel"] = {"id": line["id"], "head": presence.state(data_dir)}


def _panel_dir(project=None):
    try:
        return task_service.resolve(_cmd_project(project))[1]
    except Exception:
        return None


def project_panel(app, req, match):
    """GET /api/v1/projects/{pid}/panel (R11.2): the person's newest board actions with their head state (sent, seen,
    acted) and whether a head session is listening."""
    project = _cmd_project(match.group("pid"))
    _, data_dir = task_service.resolve(project)
    body = headpanel.state(data_dir)
    body["head"] = presence.state(data_dir)
    return json_reply(200, body)


_IDEM_KEY_RE = re.compile(r"[\x21-\x7e]{1,128}")


LOG_UI_LEVELS = ("DEBUG", "INFO", "WARN", "ERROR")
_SID_RE = re.compile(r"[0-9a-f]{8}")


def log_post(app, req, match):
    """POST /api/v1/log {sid, events: [...]} (R7.16): a batch of browser debug events, at most 50. Order: the write
    guard (403/415), the request rate (429), the body cap (413, 16 KB), the JSON shape (400), the event rate (429).
    Each event is checked by log.debug_event: only ui.* names from the closed list are written, the source is always
    'ui', and every value is capped and redacted. Answers 204 with no body; never returns what was logged."""
    _write_guard(app, req)
    if not app.log_requests.allow():
        return error_reply(429, "rate_limited", "the debug log takes at most %d requests a second"
                           % security.LOG_REQ_PER_S, headers=[("Retry-After", "1")])
    try:
        body = req.read_body(security.LOG_BODY_BYTES)
    except RoadmapError as exc:
        if exc.code == "too_large":
            _guard_refused(app, "body_cap", req.path)
        raise
    try:
        parsed = security.strict_json_loads(body.decode("utf-8"))
    except ValueError:
        raise RoadmapError("invalid_input", "the body must be a JSON object with sid and events", EXIT_USAGE)
    events = parsed.get("events") if isinstance(parsed, dict) else None
    sid = parsed.get("sid") if isinstance(parsed, dict) else None
    if not isinstance(events, list) or not isinstance(sid, str) or not _SID_RE.fullmatch(sid):
        raise RoadmapError("invalid_input", "the body must be a JSON object with sid (8 hex) and events",
                           EXIT_USAGE)
    if len(events) > security.LOG_BATCH_MAX:
        raise RoadmapError("invalid_input", "at most %d events per batch" % security.LOG_BATCH_MAX, EXIT_USAGE)
    if not app.log_events.take(len(events)):
        _guard_refused(app, "rate", req.path)
        return error_reply(429, "rate_limited", "the debug log takes at most %d events a minute"
                           % security.LOG_EVENTS_PER_MIN, headers=[("Retry-After", "60")])
    src = _cmd_source(app, req)[0]
    for event in events:
        _log_ui_event(event, sid)
        if isinstance(event, dict) and event.get("ev") == "ui.mark" and src in headpanel.PERSON_SOURCES:
            ref = event.get("ref") if isinstance(event.get("ref"), str) else ""
            route = event.get("route") if isinstance(event.get("route"), str) else ""
            scoped = re.match(r"#/p/([^/?#]+)", route)
            # R11.2: a Mark is the person flagging a bug: the head of the marked project hears of it
            panel_dir = _panel_dir(scoped.group(1) if scoped else None) or _panel_dir()
            if panel_dir:
                headpanel.record(panel_dir, "mark", "Mark: I am seeing a bug here" + (" at " + route if route else "")
                                 + (" on " + ref if ref else ""), src=src, ref=ref)
    return Reply(204)


def _log_ui_event(event, sid):
    """Hand one browser event to the debug log. Unknown names, non-ui names and bad shapes are dropped silently."""
    if not isinstance(event, dict):
        return
    name = event.get("ev")
    if not isinstance(name, str) or not name.startswith("ui.") or name not in rlog.EVENTS:
        return

    def text(key):
        value = event.get(key)
        return value if isinstance(value, str) else None

    level = event.get("lvl") if event.get("lvl") in LOG_UI_LEVELS else "INFO"
    data = event.get("data") if isinstance(event.get("data"), dict) else None
    rlog.debug_event("ui", level, name, msg=text("msg"), route=text("route"), ref=text("ref"), sid=sid, data=data)


def log_status(app, req, match):
    """GET /api/v1/log/status: whether the debug log is on, its size in bytes and its file count. No contents, no
    names. The phone listener refuses this route (see PhoneApp.handle)."""
    status = rlog.log_status()
    if status.get("error"):
        return json_reply(200, {"enabled": False, "bytes": 0, "files": 0})
    return json_reply(200, {"enabled": status["enabled"], "bytes": status["total_bytes"],
                            "files": len(status["files"])})


REPORT_DEFAULT_N, REPORT_MAX_N, REPORT_BYTES = 30, 100, 6 * 1024


def _report_n(query):
    """The n of GET /api/v1/log/report: absent gives 30, a number is capped to 1..100, and any other query is a 400."""
    if not query:
        return REPORT_DEFAULT_N
    pairs = parse_qsl(query, keep_blank_values=True)
    if len(pairs) != 1 or pairs[0][0] != "n" or not re.fullmatch(r"\d{1,6}", pairs[0][1]):
        raise RoadmapError("invalid_input", "the only query value is n, a whole number (default 30, capped 1..100)",
                           EXIT_USAGE)
    return min(max(int(pairs[0][1]), 1), REPORT_MAX_N)


def _report_project():
    try:
        return str(task_service.resolve(None)[0]["id"])
    except Exception:  # no project registered yet: the report still answers
        return "-"


def _report_body(lines):
    """The report text: a header, the event lines, and the hint. The oldest event lines are cut until it fits 6 KB."""
    head = ["roadmap " + __version__, "project " + _report_project(), "time " + _now_iso(),
            "python " + platform.python_version(), "os " + platform.system()]
    tail = ["next: roadmap logs --session last"]
    kept, dropped = list(lines), 0
    while True:
        note = ["(%d older lines cut)" % dropped] if dropped else []
        body = "\n".join(head + (note + kept if kept else ["no events: no WARN or ERROR events yet"]) + tail) + "\n"
        if len(body.encode("utf-8")) <= REPORT_BYTES or not kept:
            return body
        kept.pop(0)
        dropped += 1


def log_report(app, req, match):
    """GET /api/v1/log/report?n=30: the plain-text debug report for the GUI's Copy button (R7.16 step 2b). The newest
    n WARN and ERROR events and the last 5 ui.mark events, one line each, after a header with the versions. No paths,
    no user name; every value is already redacted. The phone listener refuses this route (see PhoneApp.handle)."""
    n = _report_n(req.query)
    reply = Reply(200, _report_body(rlog.report_lines(n)).encode("utf-8"), ctype="text/plain; charset=utf-8")
    reply.headers = [("Cache-Control", "no-store")]
    return reply


def _cmd_source(app, req):
    """(source, proven) of a cmd call on the main listener. A write is 'gui' only when the browser proof is on the
    request (Origin of this server and Sec-Fetch-Site same-origin). Any other write is labelled 'agent', so the guard
    refuses its loosening ops: only a proven browser or a real CLI process may loosen. The phone listener keeps its
    own source."""
    if app.cmd_source != "gui":
        return app.cmd_source, False
    if security.browser_proof(req.headers, app.port):
        return "gui", True
    return "agent", False


def _cmd_project(value):
    """The project a cmd call acts on: the body's project, else the first registered one."""
    entries = config_store.list_projects()
    if value is None:
        if not entries:
            raise RoadmapError("not_found", "no project is registered yet", EXIT_NOT_FOUND, next="roadmap project add")
        return entries[0]["id"]
    if not isinstance(value, str) or not any(e["id"] == value for e in entries):
        raise RoadmapError("not_found", "no registered project '%s'" % str(value)[:40], EXIT_NOT_FOUND,
                           next="roadmap project list")
    return value


def _invalid(message):
    """422 invalid_args with the problems list (one problem per op check, so at most this one)."""
    return json_reply(422, {"error": {"code": "invalid_args", "message": message, "problems": [message]}})


def legacy_data_json(app, req, match):
    """Deprecated alias: the first registered project's snapshot. Removed in 2.0."""
    entries = config_store.list_projects()
    if not entries:
        return error_reply(404, "not_found", "no project is registered yet")
    first = entries[0]["id"]
    headers = [("Deprecation", "true"),
               ("Link", '</api/v1/projects/%s/snapshot>; rel="successor-version"' % first)]
    return _snapshot_reply(req, first, headers, app=app)


# ---------------------------------------------------------------- head (HEAD-SPEC section 5, read only)

HEAD_F = ("open", "all")
HEAD_N_DEFAULT, HEAD_N_MAX = 100, 200
HEAD_QUERY_KEYS = ("f", "n", "full", "offset", "limit")
HEAD_HISTORY_MAX = 20
HEAD_LIMIT_DEFAULT, HEAD_LIMIT_MAX, HEAD_OFFSET_MAX = 50, 200, 1000000


def _head_query(query):
    """(f, n, full) of GET .../head?f=open|all&n=100&full=H12. An unknown or repeated key, or a bad value, gives 400."""
    pairs = parse_qsl(query or "", keep_blank_values=True)
    keys = [key for key, _ in pairs]
    if len(keys) != len(set(keys)) or any(key not in HEAD_QUERY_KEYS for key in keys):
        raise RoadmapError("invalid_input", "the query takes f (open|all), n (1..200) and full (an H id), once each",
                           EXIT_USAGE)
    opts = dict(pairs)
    f = opts.get("f", "open")
    if f not in HEAD_F:
        raise RoadmapError("invalid_input", "f must be open or all", EXIT_USAGE)
    n_text = opts.get("n", str(HEAD_N_DEFAULT))
    if not re.fullmatch(r"\d{1,4}", n_text) or not 1 <= int(n_text) <= HEAD_N_MAX:
        raise RoadmapError("invalid_input", "n must be a whole number from 1 to 200", EXIT_USAGE)
    full = opts.get("full")
    if full is not None and not re.fullmatch(r"H\d{1,4}", full):
        raise RoadmapError("invalid_input", "full must be a head id such as H12", EXIT_USAGE)
    return f, int(n_text), full


def _head_is_paged(query):
    """True when the query asks for a page (offset or limit given): the paged read of the full ledger."""
    keys = [key for key, _ in parse_qsl(query or "", keep_blank_values=True)]
    return "offset" in keys or "limit" in keys


def _head_page_query(query):
    """(offset, limit) of a paged read: offset 0..1000000 (default 0), limit 1..200 (default 50). Else 400."""
    opts = dict(parse_qsl(query or "", keep_blank_values=True))
    offset_text = opts.get("offset", "0")
    limit_text = opts.get("limit", str(HEAD_LIMIT_DEFAULT))
    if not re.fullmatch(r"\d{1,7}", offset_text) or int(offset_text) > HEAD_OFFSET_MAX:
        raise RoadmapError("invalid_input", "offset must be a whole number from 0 to 1000000", EXIT_USAGE)
    if not re.fullmatch(r"\d{1,4}", limit_text) or not 1 <= int(limit_text) <= HEAD_LIMIT_MAX:
        raise RoadmapError("invalid_input", "limit must be a whole number from 1 to 200", EXIT_USAGE)
    return int(offset_text), int(limit_text)


def _head_page_row(entry, moment, accepted, open_tasks, index, live_jobs):
    """One row of a paged read, in the snapshot row shape: suggest, linked and prog as the snapshot head key gives
    them (issue links are not indexed here, so an issue ref shows no title)."""
    suggest = None
    if entry["status"] not in head_rules.CLOSED_STATUSES and not entry["links"]:
        suggest = head_rules.suggest_binds(entry["sum"], open_tasks, ()) or None
    return head_row(entry, moment, entry["id"] in accepted, suggest,
                    linked=_resolve_links(entry, index, live_jobs) or None, prog=_progress(entry, index))


def _same_page_read(headers, port):
    """A same-origin page read: Sec-Fetch-Site same-origin, and an Origin only when one is sent (a browser sends no
    Origin on a same-origin GET, so browser_proof would refuse the page's own text fetch)."""
    site = headers.get("Sec-Fetch-Site")
    origin = headers.get("Origin")
    if site is None or site.strip().lower() != "same-origin":
        return False
    return origin is None or origin.strip().lower() in security.origins(port)


def _head_history(records, eid):
    """The last lines of one entry's history: when it was logged, and each update (set, link, note). Text is not here."""
    out = []
    for rec in records:
        if rec.get("id") != eid:
            continue
        if rec.get("t") == "e":
            out.append({"ts": rec.get("ts"), "by": rec.get("src")})
        elif rec.get("t") == "u":
            line = {"ts": rec.get("ts"), "by": rec.get("by")}
            line.update({key: rec[key] for key in ("set", "link", "note") if rec.get(key)})
            out.append(line)
    return out[-HEAD_HISTORY_MAX:]


def project_head(app, req, match):
    """GET /api/v1/projects/{pid}/head: the rows (f=open drops done and declined; the newest n) with their counts.
    full=H12 adds the verbatim text and the history, on the same-origin page only (403 otherwise). The phone listener
    never gets text or history: its body is the rows, with full reduced to the id."""
    project = _cmd_project(match.group("pid"))
    f, n, full = _head_query(req.query)
    _, data_dir = task_service.resolve(project)
    snap = loader.load_snapshot(project)  # the cached build of the current revision, not a new one
    moment = datetime.now().astimezone()
    link_state = head_link_state(snap["tasks"], snap["jobs"])
    if _head_is_paged(req.query):
        offset, limit = _head_page_query(req.query)
        page = head_service.page(data_dir, f=f, offset=offset, limit=limit, link_state=link_state, now=moment)
        entries = page["entries"]
        index = {}
        for t in snap["tasks"]:
            if t.get("id"):
                index["task:" + t["id"]] = {"title": str(t.get("title") or ""), "status": t.get("state")}
        for j in snap["jobs"]:
            if j.get("id"):
                index["job:" + j["id"]] = {"title": str(j.get("title") or ""), "status": j.get("status")}
        open_tasks = [t for t in snap["tasks"] if t.get("state") in ACTIVE]
        live_jobs = [j for j in snap["jobs"] if j.get("status") in HEAD_JOB_STATES]
        rows = [_head_page_row(e, moment, page["accepted"], open_tasks, index, live_jobs) for e in page["rows"]]
        if app.cmd_source != "phone" and _same_page_read(req.headers, app.port):
            # The same-origin page only: a short preview of each row's text and reply (R10.2), in one file read.
            previews = head_service.previews_of(data_dir, [row["id"] for row in rows])
            for row in rows:
                row["preview"] = previews[row["id"]]["text"]
                row["replyPreview"] = previews[row["id"]]["reply"]
        body = {"f": f, "offset": offset, "limit": limit, "total": page["total"], "counts": page["counts"],
                "rows": rows}
    else:
        entries = head_service.rows(data_dir, link_state=link_state, now=moment)
        shown = [e for e in entries if f == "all" or e["status"] not in head_rules.CLOSED_STATUSES]
        body = {"f": f, "n": n, "total": len(shown), "rows": [head_row(e, moment) for e in shown[-n:]]}
    if full is not None:
        if not any(e["id"] == full for e in entries):
            raise RoadmapError("not_found", "no head entry " + full, EXIT_NOT_FOUND)
        body["full"] = {"id": full}
        if app.cmd_source != "phone":
            if not _same_page_read(req.headers, app.port):
                raise RoadmapError("forbidden", "the full text is for this server's own page only", EXIT_ERROR)
            details = head_service.details_of(data_dir, full)
            body["full"]["text"] = details["text"]
            body["full"]["reply"] = details["reply"]
            body["full"]["assets"] = details["assets"]
            body["full"]["history"] = _head_history(head_service._records(data_dir), full)
    if app.cmd_source == "phone":
        body = _phone_public(body)
    return json_reply(200, body)


JOBS_PAGE_DEFAULT, JOBS_PAGE_MAX, JOBS_OFFSET_MAX = 10, 200, 1000000


def _jobs_page_query(query):
    """(offset, limit) of GET .../jobs?offset=0&limit=10: offset 0..1000000, limit 1..200. An unknown key gives 400."""
    pairs = parse_qsl(query or "", keep_blank_values=True)
    keys = [key for key, _ in pairs]
    if len(keys) != len(set(keys)) or any(key not in ("offset", "limit") for key in keys):
        raise RoadmapError("invalid_input", "the query takes offset and limit, once each", EXIT_USAGE)
    opts = dict(pairs)
    offset_text = opts.get("offset", "0")
    limit_text = opts.get("limit", str(JOBS_PAGE_DEFAULT))
    if not re.fullmatch(r"\d{1,7}", offset_text) or int(offset_text) > JOBS_OFFSET_MAX:
        raise RoadmapError("invalid_input", "offset must be a whole number from 0 to 1000000", EXIT_USAGE)
    if not re.fullmatch(r"\d{1,4}", limit_text) or not 1 <= int(limit_text) <= JOBS_PAGE_MAX:
        raise RoadmapError("invalid_input", "limit must be a whole number from 1 to 200", EXIT_USAGE)
    return int(offset_text), int(limit_text)


def project_jobs(app, req, match):
    """GET /api/v1/projects/{pid}/jobs?offset=0&limit=10: one page of the finished jobs, newest first, in the snapshot's
    job shape. Read only: nothing is pruned or removed here."""
    project = _cmd_project(match.group("pid"))
    offset, limit = _jobs_page_query(req.query)
    _, data_dir = task_service.resolve(project)
    rows, total = job_service.finished_page(data_dir, offset, limit)
    shaped, _ = parse_jobs(json.dumps({"jobs": rows}), datetime.now().astimezone())
    return json_reply(200, {"offset": offset, "limit": limit, "total": total, "rows": shaped})


def tokens_history(app, req, match):
    """GET /api/v1/tokens/history[?project=pid]: daily token sums by model, totals, per-task sums, the remaining
    estimate per phase and the weekly usage samples (services/tokenhist.py). Read only."""
    opts = _git_query(req.query, ("project",))
    pid = _cmd_project(opts["project"]) if opts.get("project") else None
    entries = []
    for entry in config_store.list_projects():
        if pid and entry["id"] != pid:
            continue
        try:
            entries.append({"id": entry["id"], "name": entry.get("name"),
                            "data_dir": task_service.resolve(entry["id"])[1]})
        except RoadmapError:
            continue
    return json_reply(200, tokenhist.collect(entries, pid))


# ---------------------------------------------------------------- history (R11.4, docs/ACTIVITY-V2.md)

def _history_reply(app, req, page_of):
    """One history page as JSON with a content ETag (304 on a match). Head item text and replies are only in the reply
    for this server's own page; the phone listener gets the paths scrubbed."""
    full = app.cmd_source != "phone" and _same_page_read(req.headers, app.port)
    body = page_of(parse_qsl(req.query or "", keep_blank_values=True), full)
    obj = _phone_public(body) if app.cmd_source == "phone" else body
    etag = content_etag(obj)
    if etag_matches(req.headers.get("If-None-Match"), etag):
        return Reply(304, headers=[("ETag", etag)])
    return json_reply(200, obj, headers=[("ETag", etag)])


def project_history(app, req, match):
    """GET /api/v1/projects/{pid}/history?kind=&actor=&from=&to=&q=&before=&limit=: the project's history, newest
    first, one page; next is the cursor for older events."""
    project = config_store.get_project(_cmd_project(match.group("pid")))
    return _history_reply(app, req, lambda pairs, full: history_service.project_page(project, pairs, full))


def all_history(app, req, match):
    """GET /api/v1/history?...&project=: every project's history merged, each event with project and pname."""
    entries = config_store.list_projects()
    return _history_reply(app, req, lambda pairs, full: history_service.all_page(entries, pairs, full))


# ---------------------------------------------------------------- git (GIT-SPEC step 2, read only)

GIT_LOG_DEFAULT, GIT_LOG_MAX = 10, 100


def _git_query(query, keys):
    """The query of a git read: each of keys at most once and nothing else. Returns the pairs as a dict; else 400."""
    pairs = parse_qsl(query or "", keep_blank_values=True)
    names = [key for key, _ in pairs]
    if len(names) != len(set(names)) or any(key not in keys for key in names):
        raise RoadmapError("invalid_input", "the query takes " + (", ".join(keys) or "no values"), EXIT_USAGE)
    return dict(pairs)


def _git_project(match):
    """(project id, project path) for a git route. The path is the registered folder; git runs only there."""
    pid = _cmd_project(match.group("pid"))
    return pid, config_store.get_project(pid)["path"]


def _git_reply(app, obj):
    """A git read as JSON. The phone listener gets the paths scrubbed, as for the snapshot."""
    return json_reply(200, _phone_public(obj) if app.cmd_source == "phone" else obj)


def _git_same_origin(app, req):
    """Commit detail and diffs: never on the phone listener, and on the main listener only from this server's page."""
    if app.cmd_source == "phone":
        raise RoadmapError("forbidden", "git commit detail and diffs are not on the phone listener", EXIT_ERROR)
    if not _same_page_read(req.headers, app.port):
        raise RoadmapError("forbidden", "git commit detail and diffs are for this server's own page only", EXIT_ERROR)


def git_status(app, req, match):
    """GET .../git/status: branch, upstream, ahead/behind, detached, in-progress, and the changed files."""
    _git_query(req.query, ())
    _, path = _git_project(match)
    return _git_reply(app, git_service.read_status(path))


def git_log(app, req, match):
    """GET .../git/log?n=10: the newest commits (n from 1 to 100) with their task and job links."""
    opts = _git_query(req.query, ("n",))
    text = opts.get("n", str(GIT_LOG_DEFAULT))
    if not re.fullmatch(r"\d{1,3}", text) or not 1 <= int(text) <= GIT_LOG_MAX:
        raise RoadmapError("invalid_input", "n must be a whole number from 1 to 100", EXIT_USAGE)
    _, path = _git_project(match)
    return _git_reply(app, {"n": int(text), "rows": git_service.read_log(path, limit=int(text))})


def git_branches(app, req, match):
    """GET .../git/branches: the local branches, the current one flagged, with ahead/behind and last commit time."""
    _git_query(req.query, ())
    _, path = _git_project(match)
    return _git_reply(app, {"branches": git_service.read_branches(path)})


def git_show(app, req, match):
    """GET .../git/show/{sha}: one commit (its links) and its files with +/- counts. Same-origin page only."""
    _git_query(req.query, ())
    _git_same_origin(app, req)
    _, path = _git_project(match)
    sha = git_service.valid_sha(match.group("sha"))
    root = git_service.repo_root(path)
    try:
        text = git_service.run(root, ["show", "-s", "--format=" + git_service.LOG_FORMAT, sha, "--"])
        numstat = git_service.run(root, ["show", "--numstat", "--no-renames", "--format=", sha, "--"])
    except RoadmapError as exc:
        if exc.code == "git_failed":
            raise RoadmapError("not_found", "no commit " + sha, EXIT_NOT_FOUND)
        raise
    commits = git_service.parse_log(text)
    if not commits:
        raise RoadmapError("not_found", "no commit " + sha, EXIT_NOT_FOUND)
    files = []
    for line in numstat.splitlines():
        parts = line.split("\t", 2)
        if len(parts) == 3:
            files.append({"path": parts[2], "added": None if parts[0] == "-" else parts[0],
                          "deleted": None if parts[1] == "-" else parts[1]})
    return _git_reply(app, {"commit": commits[0], "files": files})


def git_diff(app, req, match):
    """GET .../git/diff/{sha}?path=: one file's patch for that commit. Secret names are hidden; binary or over 1 MB
    files are skipped with their size; the text is capped per file. Same-origin page only."""
    opts = _git_query(req.query, ("path",))
    if "path" not in opts:
        raise RoadmapError("invalid_input", "the query needs path=<file>", EXIT_USAGE)
    _git_same_origin(app, req)
    _, project_path = _git_project(match)
    sha = git_service.valid_sha(match.group("sha"))
    rel = git_service.valid_rel_path(project_path, opts["path"])
    if git_service.is_secret_path(rel):
        return _git_reply(app, {"path": rel, "skipped": git_service.diff_skip_reason(rel, 0), "diff": None})
    root = git_service.repo_root(project_path)
    # --literal-pathspecs: the path is one file name, never a glob or magic pathspec (git's own argv guard)
    numstat = git_service.run(root, ["--literal-pathspecs", "show", "--numstat", "--no-renames", "--format=", sha,
                                     "--", rel])
    binary = any(line.startswith("-\t-\t") for line in numstat.splitlines())
    raw = git_service.run(root, ["--literal-pathspecs", "show", "--no-color", "--no-ext-diff", "--no-renames",
                                 "--format=", sha, "--", rel])
    data = raw.encode("utf-8")
    # numstat reports a binary file with '-'; the NUL stands in for it so the size rule words it the same way
    reason = git_service.diff_skip_reason(rel, len(data), b"\0" if binary else data)
    if reason is not None:
        return _git_reply(app, {"path": rel, "skipped": reason, "diff": None})
    text, truncated = git_service.cap_text(raw)
    return _git_reply(app, {"path": rel, "skipped": None, "diff": text, "truncated": truncated})


def git_worktree_diff(app, req, match):
    """GET .../git/diff?path=: one changed file's diff in the worktree (an untracked file as all added), capped.
    The path must be in the current status. Same-origin page only."""
    opts = _git_query(req.query, ("path",))
    if "path" not in opts:
        raise RoadmapError("invalid_input", "the query needs path=<file>", EXIT_USAGE)
    _git_same_origin(app, req)
    _, project_path = _git_project(match)
    return _git_reply(app, git_service.read_worktree_diff(project_path, opts["path"]))


def _system_etag(path, data_dir, sha):
    """The ETag of the system map: the HEAD sha plus the mtimes of docs/system.json, jobs.json, tasks.json and the
    Work store (heat and the bound tasks move with them). A missing file counts as 0. Quoted, as the other ETags
    here are."""
    stamps = []
    for name in (os.path.join(path, "docs", system_service.SYSTEM_FILE), os.path.join(data_dir, job_service.JOBS_FILE),
                 task_service.tasks_path(data_dir), os.path.join(data_dir, work_service.FILE)):
        try:
            stamps.append(os.stat(name).st_mtime_ns)
        except OSError:
            stamps.append(0)
    return '"%s-%s"' % (sha or "nosha", "-".join(str(n) for n in stamps))


def project_system(app, req, match):
    """GET /api/v1/projects/{pid}/system: the System map of one registered project. Components (with fileCount and
    heat), edges, layers, the heat by component id, warnings and the HEAD sha. Read only; the paths come from the
    registered folder and docs/system.json is confined to it. ETag = sha + system.json and jobs.json mtimes: a
    matching If-None-Match gives 304 before any heat is read. Same-origin page only (403 otherwise)."""
    _git_query(req.query, ())
    _git_same_origin(app, req)
    pid, path = _git_project(match)
    _, data_dir = task_service.resolve(pid)
    mapped = system_service.load(path)
    sha = mapped["sha"]
    etag = _system_etag(path, data_dir, sha)
    if etag_matches(req.headers.get("If-None-Match"), etag):
        return Reply(304, headers=[("ETag", etag)])
    running, open_work, open_issues = systemheat.collect(data_dir)
    heat = systemheat.build(path, mapped["components"], sha=sha, jobs=running, work=open_work, issues=open_issues)
    components = [dict(comp, heat=heat["heat"].get(comp["id"])) for comp in mapped["components"]]
    body = {"source": mapped["source"], "warnings": mapped["warnings"] + heat["warnings"],
            "layers": mapped["layers"], "components": components, "edges": mapped["edges"],
            "heat": heat["heat"], "summary": heat["summary"], "fileCount": mapped["fileCount"],
            "truncated": mapped["truncated"], "sha": sha}
    try:
        jobs = job_service.list_jobs(data_dir)
    except RoadmapError:
        jobs = []
    commits = []
    try:
        commits = systemheat.history(path, sha)["commits"]
        body["arch"] = system_arch.analyze(path, mapped, commits, jobs)
    except (RoadmapError, OSError, ValueError) as err:
        body["arch"] = None
        body["warnings"].append("system views unavailable: " + str(err)[:120])
    try:
        if body["arch"] is not None:
            system_v2.extend(path, mapped, body["arch"], data_dir, commits)
    except Exception as err:   # one failure only adds a warning; the arch from analyze is kept
        body["warnings"].append("system v2 unavailable: " + str(err)[:120])
    return json_reply(200, body, headers=[("ETag", etag)])


# ---------------------------------------------------------------- table

_PID = r"[a-z0-9][a-z0-9-]{0,39}"
ROUTES = (
    (re.compile(r"/api/v1/health"), ("GET",), health),
    (re.compile(r"/api/v1/meta"), ("GET",), meta),
    (re.compile(r"/api/v1/projects"), ("GET",), projects),
    (re.compile(r"/api/v1/projects/(?P<pid>" + _PID + r")/snapshot"), ("GET",), project_snapshot),
    (re.compile(r"/api/v1/projects/(?P<pid>" + _PID + r")/head"), ("GET",), project_head),
    (re.compile(r"/api/v1/projects/(?P<pid>" + _PID + r")/panel"), ("GET",), project_panel),
    (re.compile(r"/api/v1/projects/(?P<pid>" + _PID + r")/jobs"), ("GET",), project_jobs),
    (re.compile(r"/api/v1/projects/(?P<pid>" + _PID + r")/history"), ("GET",), project_history),
    (re.compile(r"/api/v1/history"), ("GET",), all_history),
    (re.compile(r"/api/v1/projects/(?P<pid>" + _PID + r")/git/status"), ("GET",), git_status),
    (re.compile(r"/api/v1/projects/(?P<pid>" + _PID + r")/git/log"), ("GET",), git_log),
    (re.compile(r"/api/v1/projects/(?P<pid>" + _PID + r")/git/branches"), ("GET",), git_branches),
    (re.compile(r"/api/v1/projects/(?P<pid>" + _PID + r")/git/show/(?P<sha>[^/]*)"), ("GET",), git_show),
    (re.compile(r"/api/v1/projects/(?P<pid>" + _PID + r")/git/diff/(?P<sha>[^/]*)"), ("GET",), git_diff),
    (re.compile(r"/api/v1/projects/(?P<pid>" + _PID + r")/git/diff"), ("GET",), git_worktree_diff),
    (re.compile(r"/api/v1/projects/(?P<pid>" + _PID + r")/system"), ("GET",), project_system),
    (re.compile(r"/api/v1/tokens/history"), ("GET",), tokens_history),
    (re.compile(r"/api/v1/usage"), ("GET",), usage_get),
    (re.compile(r"/api/v1/usage/sync"), ("POST",), usage_sync),
    (re.compile(r"/api/v1/usage/accounts"), ("GET",), usage_accounts_get),
    (re.compile(r"/api/v1/usage/accounts/(?P<id>[^/]+)/(?P<action>[a-z]+)"), ("POST",), usage_accounts_action),
    (re.compile(r"/api/v1/cmd"), ("POST",), cmd),
    (re.compile(r"/api/v1/log"), ("POST",), log_post),
    (re.compile(r"/api/v1/log/status"), ("GET",), log_status),
    (re.compile(r"/api/v1/log/report"), ("GET",), log_report),
    (re.compile(r"/data\.json"), ("GET",), legacy_data_json),
)


_NAMED_GROUP = re.compile(r"\(\?P<(\w+)>[^)]*\)")


def route_template(path):
    """The route template of a path (named parts as {name}, for example /api/v1/projects/{pid}/snapshot), or
    'unmatched' when no route has that path. The debug log records this, never the concrete path."""
    for pattern, _, _ in ROUTES:
        if pattern.fullmatch(path):
            text = _NAMED_GROUP.sub(lambda m: "{" + m.group(1) + "}", pattern.pattern)
            return text.replace("(?:", "").replace(")?", "").replace("\\", "")
    return "unmatched"


def match(app, req):
    """The Reply for a route path, or None when no route has that path (the caller then tries static files)."""
    for pattern, methods, handler in ROUTES:
        found = pattern.fullmatch(req.path)
        if found is None:
            continue
        if req.method not in methods:
            return error_reply(405, "method_not_allowed", "this route takes " + ", ".join(methods) + " only",
                               headers=[("Allow", ", ".join(methods))])
        return handler(app, req, found)
    return None
