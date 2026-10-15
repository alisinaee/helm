"""Security rules for the HTTP layer as pure functions: Host and Origin checks, the CSRF check, the phone cookie, the
failure limiter, headers and limits.

Nothing here touches sockets or the filesystem. The server calls these functions for every request.
"""

import collections
import hmac
import json
import re
import secrets
import threading
import time

from roadmap.services.tunnel import valid_tunnel_host

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


def write_refusal(headers, token, port):
    """None for a same-origin write (Sec-Fetch-Site same-origin or Origin on this server, and the CSRF header). Else
    the reason code: 'origin' (cross-site, foreign Origin, or neither header) or 'csrf'.

    headers is any mapping with get(). A request with neither Sec-Fetch-Site nor Origin is refused too.
    """
    sec_fetch_site = headers.get("Sec-Fetch-Site")
    origin = headers.get("Origin")
    if sec_fetch_site is None and origin is None:
        return "origin"
    if sec_fetch_site is not None and sec_fetch_site.strip().lower() != "same-origin":
        return "origin"
    if origin is not None and origin.strip().lower() not in origins(port):
        return "origin"
    if not safe_equal(headers.get(CSRF_HEADER), token):
        return "csrf"
    return None


def write_request_allowed(headers, token, port):
    """True for a same-origin write: see write_refusal."""
    return write_refusal(headers, token, port) is None


def browser_proof(headers, port):
    """True when the request carries what a browser sends for a same-origin page: an Origin of this server and
    Sec-Fetch-Site same-origin. Only then is a write taken as a person's click (the agent guard then lets it through).
    A local process can send these headers too; see docs/SECURITY.md, Known limits."""
    origin = headers.get("Origin")
    sec_fetch_site = headers.get("Sec-Fetch-Site")
    if origin is None or sec_fetch_site is None:
        return False
    return origin.strip().lower() in origins(port) and sec_fetch_site.strip().lower() == "same-origin"


def _no_constant(name):
    raise ValueError("JSON constant " + name + " is not allowed")


def strict_json_loads(text):
    """json.loads that refuses NaN, Infinity and -Infinity (Python accepts them; JSON does not)."""
    return json.loads(text, parse_constant=_no_constant)


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


CMD_PATH = "/api/v1/cmd"
CMD_OPS_PER_S = 10
CMD_WINDOW_S = 1.0
# Ops a phone call may run when phoneWrites is true. Stopping is safe; resuming or raising limits is never allowed.
PHONE_OPS = frozenset(["question.answer", "comment.add", "task.status", "control.stop", "undo"])


def phone_csrf(token):
    """The phone listener's CSRF value: HMAC-SHA256 keyed with the phone token over the word 'csrf'. The phone pages
    carry it in their csrf meta tag; the raw token never goes to the page."""
    return hmac.new(token.encode("utf-8"), b"csrf", "sha256").hexdigest()


class RateLimiter:
    """At most limit events per window_s seconds, counted per process. allow() records an event and returns False
    once the window is full."""

    def __init__(self, limit=CMD_OPS_PER_S, window_s=CMD_WINDOW_S, clock=time.monotonic):
        self.limit = limit
        self.window_s = window_s
        self._clock = clock
        self._times = collections.deque()
        self._lock = threading.Lock()

    def allow(self):
        with self._lock:
            now = self._clock()
            while self._times and now - self._times[0] >= self.window_s:
                self._times.popleft()
            if len(self._times) >= self.limit:
                return False
            self._times.append(now)
            return True


# POST /api/v1/log (R7.16 step 2). The browser sends small batches of debug events; the limits are per process, and
# the only client is the local page, so one counter serves it. Requests: 20 per second. Events: 200 per minute.
LOG_PATH = "/api/v1/log"
LOG_BODY_BYTES = 16 * 1024
LOG_BATCH_MAX = 50
LOG_REQ_PER_S = 20
LOG_REQ_WINDOW_S = 1.0
LOG_EVENTS_PER_MIN = 200
LOG_EVENTS_WINDOW_S = 60.0
LOG_GUARD_LINES_PER_MIN = 20  # core.guard lines for refused writes: a flood of refusals must not fill the log


class EventBudget:
    """At most limit events per window_s seconds (a sliding window, counted per event, not per request). take(n)
    admits n events when they all fit, records them and returns True; otherwise it records nothing and returns False."""

    def __init__(self, limit=LOG_EVENTS_PER_MIN, window_s=LOG_EVENTS_WINDOW_S, clock=time.monotonic):
        self.limit = limit
        self.window_s = window_s
        self._clock = clock
        self._batches = collections.deque()
        self._total = 0
        self._lock = threading.Lock()

    def take(self, n):
        with self._lock:
            now = self._clock()
            while self._batches and now - self._batches[0][0] >= self.window_s:
                self._total -= self._batches.popleft()[1]
            if self._total + n > self.limit:
                return False
            self._batches.append((now, n))
            self._total += n
            return True


def security_headers(csp=CSP):
    """The headers that go on every response, as (name, value) pairs."""
    return [
        ("Content-Security-Policy", csp),
        ("X-Frame-Options", "DENY"),
        ("X-Content-Type-Options", "nosniff"),
        ("Referrer-Policy", "no-referrer"),
        ("Cross-Origin-Resource-Policy", "same-origin"),
    ]
