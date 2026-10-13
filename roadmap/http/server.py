"""The dashboard server: ThreadingHTTPServer bound to 127.0.0.1 only, with the request handler, the access log and
the App that routes each request (Host check, API routes, then static pages).

make_server(0) binds a free port (tests use it). The access log records method, path without the query string,
status and milliseconds. The query string is dropped as soon as the request line is read, so it can never reach
routing or the log.
"""

import os
import socketserver
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from roadmap.errors import EXIT_USAGE, RoadmapError
from roadmap.http import routes, security
from roadmap.http.static import StaticFiles, etag_of
from roadmap.log import get_logger
from roadmap.services import usage

BIND_HOST = "127.0.0.1"
WEB_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "web")
access_log = get_logger("http.access")
error_log = get_logger("http")


def _default_sync():
    usage.sync_once()


class Request:
    """One request: method (HEAD is served as GET), path without query, headers and the body stream."""

    def __init__(self, method, target, headers, rfile, head=False):
        self.method = method
        self.path = target.split("?", 1)[0]
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

    def __init__(self, port, token, sync=None, static_files=None):
        self.port = port
        self.token = token
        self._sync = sync or _default_sync
        self.static = static_files

    def sync(self):
        """Run the usage sync hook (the real one in production, a fake in tests)."""
        return self._sync()

    def handle(self, req):
        """The Reply for a request: Host check first, then API routes, then static pages."""
        if not security.host_allowed(req.headers.get("Host"), self.port):
            return routes.error_reply(421, "misdirected_request", "this server answers only on 127.0.0.1 or localhost")
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
        body = self.static.render(entry, self.token)
        etag = etag_of(body)
        csp = security.CSP_LEGACY if entry.legacy else security.CSP
        if routes.etag_matches(req.headers.get("If-None-Match"), etag):
            return routes.Reply(304, headers=[("ETag", etag)], csp=csp)
        return routes.Reply(200, body, ctype=entry.ctype, headers=[("ETag", etag)], csp=csp)


class _Handler(BaseHTTPRequestHandler):
    server_version = "roadmap-board"
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
            reply = routes.error_reply(500, "internal", "unexpected error (" + type(exc).__name__ + ")")
        self._send(reply, head)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        access_log.info("%s %s %d %dms", method, path, reply.status, elapsed_ms)

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

    def __init__(self, port, token, sync, static_files):
        super().__init__((BIND_HOST, int(port)), _Handler)
        self.app = App(self.server_address[1], token, sync, static_files)

    def server_bind(self):
        # skip HTTPServer.server_bind: it resolves the host name, which may touch the network
        socketserver.TCPServer.server_bind(self)
        self.server_name = BIND_HOST
        self.server_port = self.server_address[1]


def make_server(port=0, sync=None, token=None, web_root=None):
    """A bound, not yet running server. Call serve_forever() (or start it in a thread) and shutdown() to stop.

    sync replaces the usage sync (tests pass a fake). token defaults to a fresh random CSRF token.
    web_root defaults to the repository's web/ folder. Raises OSError (EADDRINUSE) when the port is busy.
    """
    return RoadmapServer(port, token or security.new_token(), sync, StaticFiles(web_root or WEB_ROOT))
