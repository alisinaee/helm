"""Security rules for the HTTP layer as pure functions: Host and Origin checks, the CSRF check, the phone cookie, the
failure limiter, headers and limits.

Nothing here touches sockets or the filesystem. The server calls these functions for every request.
"""

import collections
import hmac
import re
import secrets
import threading
import time

MAX_BODY_BYTES = 4096
CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; "
       "frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
# TODO(WP8): temporary exception for web/legacy.html only, which has inline <style> and <script> and style=
# attributes. Remove it together with the file. index.html (WP7) must work under CSP, so no page but legacy gets it.
CSP_LEGACY = ("default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
              "connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; "
              "form-action 'none'")
CSRF_HEADER = "X-Roadmap-CSRF"
PHONE_PARAM = "k"
PHONE_COOKIE = "rb_phone"
PHONE_COOKIE_MAX_AGE_S = 7 * 24 * 3600
PHONE_FAIL_LIMIT = 10
PHONE_FAIL_WINDOW_S = 60
_TUNNEL_HOST_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*$")
_PLAIN_PATH_RE = re.compile(r"/(?!/)[A-Za-z0-9._~/-]*")


def new_token():
    """A per-process CSRF token: 32 random bytes, URL-safe."""
    return secrets.token_urlsafe(32)


def safe_equal(given, expected):
    """Constant-time comparison (hmac.compare_digest). A missing value is compared as empty and never matches."""
    given = given or ""
    expected = expected or ""
    if not expected:
        return False
    return hmac.compare_digest(given.encode("utf-8"), expected.encode("utf-8"))


def host_allowed(host, port):
    """True when the Host header names this server on 127.0.0.1 or localhost (DNS rebinding guard)."""
    if not isinstance(host, str):
        return False
    return host.strip().lower() in ("127.0.0.1:%d" % port, "localhost:%d" % port)


def valid_tunnel_host(value):
    """True for a bare host name such as abc123.lhr.life: no scheme, no port, no path."""
    return isinstance(value, str) and len(value) <= 253 and _TUNNEL_HOST_RE.match(value) is not None


def phone_host_allowed(host, port, tunnel_host):
    """The phone listener's Host check: the loopback names, or the saved tunnel host (with or without :443)."""
    if host_allowed(host, port):
        return True
    if not valid_tunnel_host(tunnel_host) or not isinstance(host, str):
        return False
    value = host.strip().lower()
    return value in (tunnel_host, tunnel_host + ":443")


def origins(port):
    """The two origins this server answers to."""
    return ("http://127.0.0.1:%d" % port, "http://localhost:%d" % port)


def write_request_allowed(headers, token, port):
    """True for a same-origin write: Sec-Fetch-Site same-origin (or Origin on this server) and the CSRF header.

    headers is any mapping with get(). A cross-site Sec-Fetch-Site or a foreign Origin always fails.
    A request with neither Sec-Fetch-Site nor Origin fails too.
    """
    sec_fetch_site = headers.get("Sec-Fetch-Site")
    origin = headers.get("Origin")
    if sec_fetch_site is None and origin is None:
        return False
    if sec_fetch_site is not None and sec_fetch_site.strip().lower() != "same-origin":
        return False
    if origin is not None and origin.strip().lower() not in origins(port):
        return False
    return safe_equal(headers.get(CSRF_HEADER), token)


def cookie_value(token):
    """The phone cookie value: HMAC-SHA256 keyed with the phone token over the word 'cookie'. The raw token never
    goes into the cookie."""
    return hmac.new(token.encode("utf-8"), b"cookie", "sha256").hexdigest()


def phone_cookie_header(token):
    """The Set-Cookie value that sets the phone cookie for seven days."""
    return ("%s=%s; Max-Age=%d; Path=/; HttpOnly; Secure; SameSite=Strict"
            % (PHONE_COOKIE, cookie_value(token), PHONE_COOKIE_MAX_AGE_S))


def cookie_from(header):
    """The phone cookie's value from a Cookie header, or '' when it is not there."""
    for part in (header or "").split(";"):
        name, _, value = part.strip().partition("=")
        if name == PHONE_COOKIE:
            return value
    return ""


def plain_redirect_path(path):
    """The path to redirect to: the request path when it is a plain absolute path, else '/'. Never a //host form."""
    return path if _PLAIN_PATH_RE.fullmatch(path or "") else "/"


class FailureLimiter:
    """At most PHONE_FAIL_LIMIT failed phone attempts per PHONE_FAIL_WINDOW_S seconds, counted per process."""

    def __init__(self, limit=PHONE_FAIL_LIMIT, window_s=PHONE_FAIL_WINDOW_S, clock=time.monotonic):
        self.limit = limit
        self.window_s = window_s
        self._clock = clock
        self._times = collections.deque()
        self._lock = threading.Lock()

    def _trim(self, now):
        while self._times and now - self._times[0] >= self.window_s:
            self._times.popleft()

    def blocked(self):
        """True while the failure count in the window has reached the limit."""
        with self._lock:
            now = self._clock()
            self._trim(now)
            return len(self._times) >= self.limit

    def record_failure(self):
        """Count one failed attempt."""
        with self._lock:
            now = self._clock()
            self._trim(now)
            self._times.append(now)

    def retry_after_s(self):
        """Whole seconds until the oldest counted failure leaves the window (at least 1)."""
        with self._lock:
            now = self._clock()
            self._trim(now)
            if not self._times:
                return 1
            return max(1, int(self.window_s - (now - self._times[0])) + 1)


def security_headers(csp=CSP):
    """The headers that go on every response, as (name, value) pairs."""
    return [
        ("Content-Security-Policy", csp),
        ("X-Frame-Options", "DENY"),
        ("X-Content-Type-Options", "nosniff"),
        ("Referrer-Policy", "no-referrer"),
        ("Cross-Origin-Resource-Policy", "same-origin"),
    ]
