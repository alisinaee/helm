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
import stat
from datetime import datetime
from urllib.parse import parse_qsl

from roadmap import __version__
from roadmap.core import head as head_rules
from roadmap.core.snapshot import SNAPSHOT_SCHEMA_VERSION, head_link_state, head_row
from roadmap.errors import (EXIT_CONFLICT, EXIT_ERROR, EXIT_EXTERNAL, EXIT_INVALID_DATA, EXIT_NOT_FOUND,
                            EXIT_USAGE, RoadmapError)
from roadmap import log as rlog
from roadmap.http import security
from roadmap.services import agentguard, commands, control, loader, usage
from roadmap.services import head as head_service
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


def _snapshot_reply(req, snap, headers=(), app=None):
    if app is not None and app.cmd_source == "phone":
        snap = _phone_public(snap)
    etag = snapshot_etag(snap)
    extra = [("ETag", etag)] + list(headers)
    if etag_matches(req.headers.get("If-None-Match"), etag):
        return Reply(304, headers=extra)
    body = json.dumps(snap, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return Reply(200, body, headers=extra)


def _now_iso():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _guard_refused(reason, path):
    """Record one guard refusal (core.guard): the reason code and the path only. Never a header value or a body."""
    rlog.debug_event("core", "WARN", "core.guard", msg=reason, route=path, data={"reason": reason})


def _write_guard(app, req):
    """CSRF, Sec-Fetch-Site or Origin, then Content-Type, then body size. Raises before anything is done."""
    reason = security.write_refusal(req.headers, app.csrf_token(), app.port)
    if reason is not None:
        _guard_refused(reason, req.path)
        raise RoadmapError("forbidden", "this write needs the page's own CSRF token from the same origin",
                           EXIT_ERROR)
    ctype = (req.headers.get("Content-Type") or "").split(";")[0].strip().lower()
    if ctype != JSON_MEDIA:
        _guard_refused("ctype", req.path)
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
    return _snapshot_reply(req, loader.load_snapshot(match.group("pid")), app=app)


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
    return json_reply(200, usage.show())


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
            reply = commands.run(op, args, source, data_dir)
    except RoadmapError as exc:
        if exc.code == "usage":
            return _invalid(exc.message)
        raise
    control.after_write(project)
    return json_reply(200, reply)


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
            _guard_refused("body_cap", req.path)
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
        _guard_refused("rate", req.path)
        return error_reply(429, "rate_limited", "the debug log takes at most %d events a minute"
                           % security.LOG_EVENTS_PER_MIN, headers=[("Retry-After", "60")])
    for event in events:
        _log_ui_event(event, sid)
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
    return _snapshot_reply(req, loader.load_snapshot(first), headers, app=app)


# ---------------------------------------------------------------- research notes (read only)

NOTES_DIR = "research"            # the folder under the project's data folder that `roadmap research` writes
NOTE_NAME = re.compile(r"^[0-9]{2}-[a-z0-9-]+\.md$")
NOTE_MAX_BYTES = 64 * 1024
NOTE_TITLE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)


def _read_note(folder, name):
    """The bytes of one note, read without following a symlink. Raises not_found for a missing or non-file entry and
    too_large above NOTE_MAX_BYTES. The name is validated by the caller."""
    path = os.path.join(folder, name)
    try:
        before = os.lstat(path)
    except OSError:
        raise RoadmapError("not_found", "no research note named " + name, EXIT_NOT_FOUND)
    if not stat.S_ISREG(before.st_mode):
        raise RoadmapError("not_found", "no research note named " + name, EXIT_NOT_FOUND)
    if before.st_size > NOTE_MAX_BYTES:
        raise RoadmapError("too_large", name + " is larger than 64 KB", EXIT_USAGE)
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError:
        raise RoadmapError("not_found", "no research note named " + name, EXIT_NOT_FOUND)
    with os.fdopen(fd, "rb") as fh:
        opened = os.fstat(fh.fileno())
        if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise RoadmapError("not_found", "no research note named " + name, EXIT_NOT_FOUND)
        body = fh.read(NOTE_MAX_BYTES + 1)
    if len(body) > NOTE_MAX_BYTES:
        raise RoadmapError("too_large", name + " is larger than 64 KB", EXIT_USAGE)
    return body


def _notes_folder(data_dir):
    """The research folder, or None when it is missing or is a symlink (then the project has no readable notes)."""
    folder = os.path.join(data_dir, NOTES_DIR)
    try:
        info = os.lstat(folder)
    except OSError:
        return None
    return folder if stat.S_ISDIR(info.st_mode) else None


def _note_row(folder, name):
    """{name, title, size, lines} for one note file; title and lines are None when the note is over the size cap."""
    body = _read_note(folder, name)
    size = len(body)
    text = body.decode("utf-8", "replace")
    found = NOTE_TITLE.search(text)
    return {"name": name, "title": found.group(1) if found else None, "size": size,
            "lines": text.count("\n") + (0 if text.endswith("\n") or not text else 1)}


def notes(app, req, match):
    """GET /api/v1/projects/{pid}/notes: the note list. GET .../notes/{name}: one note as plain text (UTF-8).
    Names must match NN-slug.md, so no path can leave the research folder; symlinks are never followed."""
    project = _cmd_project(match.group("pid"))
    _, data_dir = task_service.resolve(project)
    name = match.group("name")
    folder = _notes_folder(data_dir)
    if name is None:
        rows = []
        if folder is not None:
            for entry in sorted(os.listdir(folder)):
                if not NOTE_NAME.match(entry):
                    continue
                try:
                    rows.append(_note_row(folder, entry))
                except RoadmapError as exc:
                    if exc.code != "too_large":
                        continue
                    rows.append({"name": entry, "title": None, "size": os.lstat(os.path.join(folder, entry)).st_size,
                                 "lines": None})
        return json_reply(200, {"notes": rows})
    if not NOTE_NAME.match(name):
        raise RoadmapError("invalid_input", "a note name looks like 01-landscape.md", EXIT_USAGE)
    if folder is None:
        raise RoadmapError("not_found", "no research note named " + name, EXIT_NOT_FOUND)
    return Reply(200, _read_note(folder, name), ctype="text/plain; charset=utf-8")


# ---------------------------------------------------------------- head (HEAD-SPEC section 5, read only)

HEAD_F = ("open", "all")
HEAD_N_DEFAULT, HEAD_N_MAX = 100, 200
HEAD_QUERY_KEYS = ("f", "n", "full")
HEAD_HISTORY_MAX = 20


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
    snap = loader.load_snapshot(project)
    moment = datetime.now().astimezone()
    entries = head_service.rows(data_dir, link_state=head_link_state(snap["tasks"], snap["jobs"]), now=moment)
    shown = [e for e in entries if f == "all" or e["status"] not in head_rules.CLOSED_STATUSES]
    body = {"f": f, "n": n, "total": len(shown), "rows": [head_row(e, moment) for e in shown[-n:]]}
    if full is not None:
        if not any(e["id"] == full for e in entries):
            raise RoadmapError("not_found", "no head entry " + full, EXIT_NOT_FOUND)
        body["full"] = {"id": full}
        if app.cmd_source != "phone":
            if not security.browser_proof(req.headers, app.port):
                raise RoadmapError("forbidden", "the full text is for this server's own page only", EXIT_ERROR)
            body["full"]["text"] = head_service.text_of(data_dir, full)
            body["full"]["history"] = _head_history(head_service._records(data_dir), full)
    if app.cmd_source == "phone":
        body = _phone_public(body)
    return json_reply(200, body)


# ---------------------------------------------------------------- table

_PID = r"[a-z0-9][a-z0-9-]{0,39}"
ROUTES = (
    (re.compile(r"/api/v1/health"), ("GET",), health),
    (re.compile(r"/api/v1/meta"), ("GET",), meta),
    (re.compile(r"/api/v1/projects"), ("GET",), projects),
    (re.compile(r"/api/v1/projects/(?P<pid>" + _PID + r")/snapshot"), ("GET",), project_snapshot),
    (re.compile(r"/api/v1/projects/(?P<pid>" + _PID + r")/notes(?:/(?P<name>[^/]*))?"), ("GET",), notes),
    (re.compile(r"/api/v1/projects/(?P<pid>" + _PID + r")/head"), ("GET",), project_head),
    (re.compile(r"/api/v1/usage"), ("GET",), usage_get),
    (re.compile(r"/api/v1/usage/sync"), ("POST",), usage_sync),
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
