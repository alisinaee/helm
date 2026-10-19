"""The dashboard server: ThreadingHTTPServer bound to 127.0.0.1 only, with the request handler, the access log and
the App that routes each request (Host check, API routes, then static pages).

make_server(0) binds a free port (tests use it). The access log records method, path without the query string,
status and milliseconds. The query string is dropped as soon as the request line is read, so it can never reach
routing or the log.
"""

import ipaddress
import os
import socketserver
import stat
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl, urlencode

from roadmap import log as rlog
from roadmap.errors import EXIT_USAGE, RoadmapError
from roadmap.http import routes, security
from roadmap.http.static import StaticFiles, etag_of
from roadmap.log import get_logger
from roadmap.services import jobs, supervisor, usage
from roadmap.store import config as config_store
from roadmap.store import paths

BIND_HOST = "127.0.0.1"
# ROADMAP_BIND_HOST moves the main listener off loopback (for a reverse proxy on another interface). Only an IPv4
# address is taken; the phone listener stays on 127.0.0.1.
BIND_HOST_ENV = "ROADMAP_BIND_HOST"


def main_bind_host():
    """The main listener's address: ROADMAP_BIND_HOST when it is a valid IPv4 address, else 127.0.0.1."""
    value = (os.environ.get(BIND_HOST_ENV) or "").strip()
    try:
        return str(ipaddress.IPv4Address(value)) if value else BIND_HOST
    except ValueError:
        return BIND_HOST
WEB_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "web")
DEFAULT_PHONE_PORT = 8766
SLOW_API_MS = 1000
SUPERVISOR_INTERVAL_S = 30.0
access_log = get_logger("http.access")
error_log = get_logger("http")
phone_log = get_logger("http.phone")
supervisor_log = get_logger("supervisor")


def _default_sync():
    usage.sync_all()


def supervisor_pass(now=None):
    """One supervisor tick for every registered project whose data folder exists. Returns the reports. The lock inside
    supervisor.tick keeps two passes (serve here, or roadmap tick) from working at once."""
    reports = []
    for project in config_store.list_projects():
        data_dir = jobs.data_dir_of(project)
        if os.path.isdir(data_dir):
            reports.append(supervisor.tick(data_dir, now=now))
    return reports


def supervisor_loop(stop):
    """Run supervisor_pass now and then every SUPERVISOR_INTERVAL_S until stop is set. A failed pass is logged and the
    loop goes on; the next pass retries whatever was left."""
    while True:
        try:
            supervisor_pass()
        except Exception:  # keep the thread alive; the failure is in the log
            supervisor_log.warning("supervisor pass failed", exc_info=True)
        if stop.wait(SUPERVISOR_INTERVAL_S):
            return


class Request:
    """One request: method (HEAD is served as GET), path without query, the raw query string, headers and the body
    stream. The query is kept only for the phone listener's ?k= check; it never reaches the access log."""

    def __init__(self, method, target, headers, rfile, head=False):
        self.method = method
        self.path = target.split("?", 1)[0]
        self.query = target.split("?", 1)[1] if "?" in target else ""
        self.headers = headers
        self.head = head
        self._rfile = rfile

    def read_body(self, limit=security.MAX_BODY_BYTES):
        """The body bytes. Raises too_large (413) above limit and invalid_input (400) for a bad length."""
        if self.headers.get("Transfer-Encoding"):
            raise RoadmapError("invalid_input", "chunked request bodies are not accepted", EXIT_USAGE)
        raw = self.headers.get("Content-Length") or "0"
        try:
            length = int(raw)
        except ValueError:
            raise RoadmapError("invalid_input", "Content-Length is not a number", EXIT_USAGE)
        if length < 0:
            raise RoadmapError("invalid_input", "Content-Length is negative", EXIT_USAGE)
        if length > limit:
            raise RoadmapError("too_large", "the request body is larger than %d bytes" % limit, EXIT_USAGE)
        return self._rfile.read(length) if length else b""


class App:
    """Routes one parsed request. Holds the port, the CSRF token, the usage sync hook and the static allowlist."""

    cmd_source = "gui"

    def __init__(self, port, token, sync=None, static_files=None):
        self.port = port
        self.token = token
        self._sync = sync or _default_sync
        self.static = static_files
        self.cmd_limiter = security.RateLimiter()
        self.log_requests = security.RateLimiter(security.LOG_REQ_PER_S, security.LOG_REQ_WINDOW_S)
        self.log_events = security.EventBudget()
        self.guard_lines = security.EventBudget(limit=security.LOG_GUARD_LINES_PER_MIN)

    def csrf_token(self):
        """The CSRF value the write guard compares against and the pages carry."""
        return self.token

    def page_token(self):
        """The csrf meta value that pages carry (the main listener's pages carry the main token)."""
        return self.csrf_token()

    def op_allowed(self, op):
        """Every registry op is allowed on the main listener; the phone listener narrows this."""
        return True

    def sync(self):
        """Run the usage sync hook (the real one in production, a fake in tests)."""
        return self._sync()

    def handle(self, req):
        """The Reply for a request: Host check first, then API routes, then static pages."""
        if not security.host_allowed(req.headers.get("Host"), self.port):
            return routes.error_reply(421, "misdirected_request", "this server answers only on 127.0.0.1, localhost or its public host")
        reply = routes.match(self, req)
        if reply is not None:
            return reply
        return self._static(req)

    def _static(self, req):
        if req.method != "GET":
            return routes.error_reply(405, "method_not_allowed", "pages take GET only",
                                      headers=[("Allow", "GET, HEAD")])
        entry = self.static.lookup(req.path)
        if entry is None:
            return routes.error_reply(404, "not_found", "no such page")
        body = self.static.render(entry, self.page_token())
        etag = etag_of(body)
        csp = security.CSP_LEGACY if entry.legacy else security.CSP
        if routes.etag_matches(req.headers.get("If-None-Match"), etag):
            return routes.Reply(304, headers=[("ETag", etag)], csp=csp)
        return routes.Reply(200, body, ctype=entry.ctype, headers=[("ETag", etag)], csp=csp)


def read_phone_token():
    """The phone token from phone.token, or None. A missing, empty, unreadable or group/other-readable file gives None,
    so the listener answers 503. The token is never logged; only the path is named when the mode is wrong."""
    path = paths.phone_token_file()
    try:
        mode = stat.S_IMODE(os.stat(path).st_mode)
    except OSError:
        return None
    if mode & 0o077:
        phone_log.warning("phone token file %s is readable by others (mode %o); it is not used", path, mode)
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            token = fh.read().strip()
    except (OSError, UnicodeDecodeError):
        return None
    return token or None


def configured_tunnel_host():
    """The tunnel host saved by `roadmap phone start` (config phoneHost), or None. Never taken from a request."""
    try:
        value = config_store.load().get("phoneHost")
    except RoadmapError:
        return None
    return value if security.valid_tunnel_host(value) else None


def configured_phone_port():
    """The phone listener port from config (phonePort), 8766 by default."""
    value = config_store.load().get("phonePort", DEFAULT_PHONE_PORT)
    return value if isinstance(value, int) and not isinstance(value, bool) else DEFAULT_PHONE_PORT


class PhoneApp(App):
    """The phone listener's request rules, in this order: Host (421), GET only (405), a token must exist (503), the
    failure limit (429), then the token: ?k= once (302 to the same path without it, with the cookie) or the cookie (401
    otherwise). Only GET routes and the static pages are reachable; there is no write route here."""

    cmd_source = "phone"

    def __init__(self, port, token_source=None, tunnel_host=None, static_files=None, limiter=None):
        super().__init__(port, "", None, static_files)
        self._token_source = token_source or read_phone_token
        self._tunnel_host = tunnel_host or configured_tunnel_host
        self.limiter = limiter or security.FailureLimiter()

    def csrf_token(self):
        token = self._token_source()
        return security.phone_csrf(token) if token else ""

    def page_token(self):
        """Phone pages carry no csrf value; the phone reads its own from the cookie-authenticated meta route."""
        return ""

    def op_allowed(self, op):
        """Phone writes are off unless phoneWrites is true, and then only the phone allowlist runs."""
        return phone_writes_enabled() and op in security.PHONE_OPS

    def handle(self, req):
        if not security.phone_host_allowed(req.headers.get("Host"), self.port, self._tunnel_host()):
            return routes.error_reply(421, "misdirected_request", "this address is not allowed on the phone listener")
        if req.path.startswith(security.LOG_PATH):
            # the debug log is for the local browser only: the phone listener never takes or serves it
            return routes.error_reply(403, "forbidden", "the debug log is not available on the phone listener")
        is_cmd = req.method == "POST" and req.path == security.CMD_PATH
        if is_cmd and not phone_writes_enabled():
            return routes.error_reply(403, "forbidden", "phone writes are off (set phoneWrites true to allow the "
                                                        "phone allowlist)")
        if req.method != "GET" and not is_cmd:
            return routes.error_reply(405, "method_not_allowed", "the phone listener is read-only: GET only",
                                      headers=[("Allow", "GET, HEAD")])
        token = self._token_source()
        if not token:
            return routes.error_reply(503, "phone_off", "phone access is off: run roadmap phone start first")
        if self.limiter.blocked():
            return routes.error_reply(429, "rate_limited", "too many failed attempts, wait a minute",
                                      headers=[("Retry-After", str(self.limiter.retry_after_s()))])
        if is_cmd:
            cookie = security.cookie_from(req.headers.get("Cookie"))
            if not security.safe_equal(cookie, security.cookie_value(token)):
                return self._refuse()
            return routes.match(self, req)
        pairs = parse_qsl(req.query, keep_blank_values=True)
        supplied = [value for name, value in pairs if name == security.PHONE_PARAM]
        if supplied:
            if len(supplied) == 1 and security.safe_equal(supplied[0], token):
                rest = [(name, value) for name, value in pairs if name != security.PHONE_PARAM]
                location = security.plain_redirect_path(req.path) + ("?" + urlencode(rest) if rest else "")
                return routes.Reply(302, b"", ctype="text/plain; charset=utf-8",
                                    headers=[("Location", location),
                                             ("Set-Cookie", security.phone_cookie_header(token))])
            return self._refuse()
        cookie = security.cookie_from(req.headers.get("Cookie"))
        if security.safe_equal(cookie, security.cookie_value(token)):
            reply = routes.match(self, req)
            return reply if reply is not None else self._static(req)
        return self._refuse()

    def _refuse(self):
        self.limiter.record_failure()
        return routes.error_reply(401, "unauthorized", "a valid phone link is needed (roadmap phone link)")


def phone_writes_enabled():
    """True when config phoneWrites is true. Read on every call, so a change applies without a restart."""
    try:
        return config_store.load().get("phoneWrites") is True
    except RoadmapError:
        return False


def _core_event(ev, lvl, route, data=None):
    """One core event in the debug log. Fail-open: the log never raises into a request."""
    try:
        rlog.debug_event("core", lvl, ev, route=route, data=data)
    except Exception:
        pass


def _api_event(method, path, status, elapsed_ms):
    """core.api: only failures (status 500 and up, ERROR) and slow calls (over 1 s, WARN), and only for API paths.
    The route template is recorded, never the query string or the concrete ids."""
    if not path.startswith("/api/"):
        return
    if status < 500 and elapsed_ms <= SLOW_API_MS:
        return
    lvl = "ERROR" if status >= 500 else "WARN"
    _core_event("core.api", lvl, routes.route_template(path),
                {"method": method, "status": status, "ms": elapsed_ms})


def _exc_event(exc, path):
    """core.exc: the exception type, its message (capped by the log) and the last 12 frames. No locals."""
    try:
        frames = traceback.extract_tb(exc.__traceback__)[-12:]
        stack = "\n".join("%s:%d %s" % (os.path.basename(f.filename), f.lineno, f.name) for f in frames)
        rlog.debug_event("core", "ERROR", "core.exc", msg=type(exc).__name__, route=path,
                         data={"type": type(exc).__name__, "message": str(exc)[:200], "stack": stack})
    except Exception:
        pass


class _Handler(BaseHTTPRequestHandler):
    server_version = "Helm"
    protocol_version = "HTTP/1.1"
    timeout = 10

    def do_GET(self):
        self._serve("GET")

    def do_HEAD(self):
        self._serve("HEAD")

    def do_POST(self):
        self._serve("POST")

    def do_PUT(self):
        self._serve("PUT")

    def do_PATCH(self):
        self._serve("PATCH")

    def do_DELETE(self):
        self._serve("DELETE")

    def do_OPTIONS(self):
        self._serve("OPTIONS")

    def _serve(self, method):
        started = time.monotonic()
        head = method == "HEAD"
        target = self._raw_target()
        path = target.split("?", 1)[0]
        req = Request("GET" if head else method, target, self.headers, self.rfile, head)
        try:
            reply = self.server.app.handle(req)
        except RoadmapError as exc:
            reply = routes.error_reply(routes.status_for(exc), exc.code, exc.message)
        except Exception as exc:  # no traceback or secret goes to the client; the type name is enough
            error_log.error("unexpected error handling %s %s: %s", method, path, type(exc).__name__)
            _exc_event(exc, path)
            reply = routes.error_reply(500, "internal", "unexpected error (" + type(exc).__name__ + ")")
        self._send(reply, head)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        access_log.info("%s %s %d %dms", method, path, reply.status, elapsed_ms)
        _api_event(method, path, reply.status, elapsed_ms)

    def _raw_target(self):
        """The request target exactly as sent. BaseHTTPRequestHandler rewrites a leading '//' in self.path, so the
        routing decision is taken from the raw request line: '//index.html' must not reach the static allowlist."""
        parts = (getattr(self, "raw_requestline", b"") or b"").decode("latin-1", "replace").split()
        return parts[1] if len(parts) >= 2 else self.path

    def _send(self, reply, head):
        self.send_response(reply.status)
        for name, value in security.security_headers(reply.csp or security.CSP):
            self.send_header(name, value)
        for name, value in reply.headers:
            self.send_header(name, value)
        has_body = reply.status not in (204, 304)
        if has_body:
            self.send_header("Content-Type", reply.ctype)
            self.send_header("Content-Length", str(len(reply.body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        if has_body and not head and reply.body:
            self.wfile.write(reply.body)

    def send_error(self, code, message=None, explain=None):
        """Parser-level failures (bad request line and the like) get the same JSON envelope and headers."""
        phrase = message or "bad request"
        self._send(routes.error_reply(int(code), "http_error", phrase), False)

    def log_request(self, code="-", size="-"):
        """Replaced by the access log in _serve, which never records the query string."""

    def log_message(self, fmt, *args):
        """Silenced: the default writes the raw request line, query string included."""

    def log_error(self, fmt, *args):
        error_log.warning("http: %s", (fmt % args)[:200] if args else fmt[:200])

    def version_string(self):
        return self.server_version


class RoadmapServer(ThreadingHTTPServer):
    """The server. Binds 127.0.0.1 only; the port argument 0 asks the system for a free one."""

    daemon_threads = True

    def __init__(self, port, token, sync, static_files, supervise=False):
        super().__init__((main_bind_host(), int(port)), _Handler)
        self.app = App(self.server_address[1], token, sync, static_files)
        self._supervise = supervise
        self._supervisor_stop = threading.Event()

    def serve_forever(self, poll_interval=0.5):
        """Serve; when supervise is set, also run the supervisor loop in a daemon thread until shutdown()."""
        if self._supervise:
            threading.Thread(target=supervisor_loop, args=(self._supervisor_stop,), name="supervisor",
                             daemon=True).start()
        super().serve_forever(poll_interval)

    def shutdown(self):
        self._supervisor_stop.set()
        super().shutdown()

    def server_bind(self):
        # skip HTTPServer.server_bind: it resolves the host name, which may touch the network
        socketserver.TCPServer.server_bind(self)
        self.server_name = self.server_address[0]
        self.server_port = self.server_address[1]

    def server_close(self):
        _core_event("core.stop", "INFO", "/", {"port": self.server_address[1]})
        super().server_close()


def make_server(port=0, sync=None, token=None, web_root=None, supervise=True):
    """A bound, not yet running server. Call serve_forever() (or start it in a thread) and shutdown() to stop.

    sync replaces the usage sync (tests pass a fake). token defaults to a fresh random CSRF token.
    web_root defaults to the repository's web/ folder. supervise (default on) runs the supervisor loop while serving.
    Raises OSError (EADDRINUSE) when the port is busy.
    The debug log is pointed at the state directory here, so it never drifts from the service's own.
    """
    rlog.set_state_dir(paths.state_dir())
    httpd = RoadmapServer(port, token or security.new_token(), sync, StaticFiles(web_root or WEB_ROOT),
                          supervise=supervise)
    _core_event("core.start", "INFO", "/", {"port": httpd.server_address[1]})
    return httpd


class PhoneServer(RoadmapServer):
    """The read-only phone listener on 127.0.0.1 (default 8766). It shares the handler and the access log with the main
    listener, and differs only in its app: PhoneApp."""

    def __init__(self, port, token_source=None, tunnel_host=None, static_files=None, limiter=None):
        ThreadingHTTPServer.__init__(self, (BIND_HOST, int(port)), _Handler)
        self._supervise = False  # the phone listener never runs the supervisor (the main listener does)
        self._supervisor_stop = threading.Event()
        self.app = PhoneApp(self.server_address[1], token_source, tunnel_host, static_files, limiter)


def make_phone_server(port=None, token_source=None, tunnel_host=None, web_root=None, limiter=None):
    """A bound, not yet running phone listener. port None reads phonePort from config. token_source and tunnel_host
    replace the phone.token file and the saved tunnel host (tests pass fakes). Raises OSError when the port is busy."""
    use_port = configured_phone_port() if port is None else port
    rlog.set_state_dir(paths.state_dir())
    return PhoneServer(use_port, token_source, tunnel_host, StaticFiles(web_root or WEB_ROOT), limiter)
