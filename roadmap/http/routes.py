"""API v1 routes: the path table, the reply helpers and one function per route.

A handler takes (app, request, match) and returns a Reply, or raises RoadmapError (mapped to a status by
status_for). Reads never write. POST /api/v1/usage/sync is the only write route. Every write checks CSRF, the
Content-Type and the body size before it does anything.
"""

import hashlib
import json
import re
from datetime import datetime

from roadmap import __version__
from roadmap.core.snapshot import SNAPSHOT_SCHEMA_VERSION
from roadmap.errors import (EXIT_CONFLICT, EXIT_ERROR, EXIT_EXTERNAL, EXIT_INVALID_DATA, EXIT_NOT_FOUND,
                            EXIT_USAGE, RoadmapError)
from roadmap.http import security
from roadmap.services import commands, control, loader, usage
from roadmap.services import tasks as task_service
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


def snapshot_etag(snap):
    """A strong ETag over the snapshot content. server_time is left out, so an unchanged project gives a 304."""
    stable = {key: value for key, value in snap.items() if key != "server_time"}
    raw = json.dumps(stable, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return '"%s"' % hashlib.sha256(raw).hexdigest()[:32]


def _snapshot_reply(req, snap, headers=()):
    etag = snapshot_etag(snap)
    extra = [("ETag", etag)] + list(headers)
    if etag_matches(req.headers.get("If-None-Match"), etag):
        return Reply(304, headers=extra)
    body = json.dumps(snap, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return Reply(200, body, headers=extra)


def _now_iso():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _write_guard(app, req):
    """CSRF, Sec-Fetch-Site or Origin, then Content-Type, then body size. Raises before anything is done."""
    if not security.write_request_allowed(req.headers, app.csrf_token(), app.port):
        raise RoadmapError("forbidden", "this write needs the page's own CSRF token from the same origin",
                           EXIT_ERROR)
    ctype = (req.headers.get("Content-Type") or "").split(";")[0].strip().lower()
    if ctype != JSON_MEDIA:
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
    rows = [_summary(entry, loader.load_snapshot(entry["id"])) for entry in config_store.list_projects()]
    return json_reply(200, {"projects": rows})


def project_snapshot(app, req, match):
    return _snapshot_reply(req, loader.load_snapshot(match.group("pid")))


def usage_get(app, req, match):
    return json_reply(200, usage.show())


def usage_sync(app, req, match):
    _write_guard(app, req)
    body = req.read_body()
    if body.strip():
        try:
            parsed = json.loads(body.decode("utf-8"))
        except ValueError:
            raise RoadmapError("invalid_input", "the body must be JSON or empty", EXIT_USAGE)
        if not isinstance(parsed, dict):
            raise RoadmapError("invalid_input", "the body must be a JSON object", EXIT_USAGE)
    try:
        app.sync()
    except usage.UsageError as exc:
        raise RoadmapError("usage_unavailable", str(exc), EXIT_EXTERNAL)
    return json_reply(200, usage.show())


def cmd(app, req, match):
    """POST /api/v1/cmd {op, args, project?}: one registry op. Order: CSRF and origin, JSON type, body size (413),
    JSON object (422), known op (404 unknown_op), the phone allowlist (403), the rate limit (429), the op's own
    checks (422 with the problem), then the write, the activity line and the control recompute."""
    _write_guard(app, req)
    body = req.read_body()
    try:
        parsed = json.loads(body.decode("utf-8"))
    except ValueError:
        return _invalid("the body must be a JSON object with op and args")
    if not isinstance(parsed, dict):
        return _invalid("the body must be a JSON object with op and args")
    op = parsed.get("op")
    args = parsed.get("args") if parsed.get("args") is not None else {}
    if not isinstance(args, dict):
        return _invalid("args must be an object")
    if not isinstance(op, str) or op not in commands.public_ops():
        return error_reply(404, "unknown_op", "no op named '%s' (see docs/API.md)" % str(op)[:60])
    if not app.op_allowed(op):
        raise RoadmapError("forbidden", "op " + op + " is not allowed on this listener", EXIT_ERROR)
    if not app.cmd_limiter.allow():
        return error_reply(429, "rate_limited", "at most %d ops per second; wait a moment" % security.CMD_OPS_PER_S,
                           headers=[("Retry-After", "1")])
    project = _cmd_project(parsed.get("project"))
    _, data_dir = task_service.resolve(project)
    try:
        with commands.context(app.cmd_source, project):
            reply = commands.run(op, args, app.cmd_source, data_dir)
    except RoadmapError as exc:
        if exc.code == "usage":
            return _invalid(exc.message)
        raise
    control.after_write(project)
    return json_reply(200, reply)


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
    return _snapshot_reply(req, loader.load_snapshot(first), headers)


# ---------------------------------------------------------------- table

_PID = r"[a-z0-9][a-z0-9-]{0,39}"
ROUTES = (
    (re.compile(r"/api/v1/health"), ("GET",), health),
    (re.compile(r"/api/v1/meta"), ("GET",), meta),
    (re.compile(r"/api/v1/projects"), ("GET",), projects),
    (re.compile(r"/api/v1/projects/(?P<pid>" + _PID + r")/snapshot"), ("GET",), project_snapshot),
    (re.compile(r"/api/v1/usage"), ("GET",), usage_get),
    (re.compile(r"/api/v1/usage/sync"), ("POST",), usage_sync),
    (re.compile(r"/api/v1/cmd"), ("POST",), cmd),
    (re.compile(r"/data\.json"), ("GET",), legacy_data_json),
)


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
