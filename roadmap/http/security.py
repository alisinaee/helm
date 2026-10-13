"""Security rules for the HTTP layer as pure functions: Host and Origin checks, the CSRF check, headers and limits.

Nothing here touches sockets or the filesystem. The server calls these functions for every request.
"""

import hmac
import secrets

MAX_BODY_BYTES = 4096
CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; "
       "frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
# TODO(WP8): temporary exception for web/legacy.html only, which has inline <style> and <script> and style=
# attributes. Remove it together with the file. index.html (WP7) must work under CSP, so no page but legacy gets it.
CSP_LEGACY = ("default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
              "connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; "
              "form-action 'none'")
CSRF_HEADER = "X-Roadmap-CSRF"


def new_token():
    """A per-process CSRF token: 32 random bytes, URL-safe."""
    return secrets.token_urlsafe(32)


def host_allowed(host, port):
    """True when the Host header names this server on 127.0.0.1 or localhost (DNS rebinding guard)."""
    if not isinstance(host, str):
        return False
    return host.strip().lower() in ("127.0.0.1:%d" % port, "localhost:%d" % port)


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
    given = headers.get(CSRF_HEADER) or ""
    return bool(token) and hmac.compare_digest(given.encode("utf-8"), token.encode("utf-8"))


def security_headers(csp=CSP):
    """The headers that go on every response, as (name, value) pairs."""
    return [
        ("Content-Security-Policy", csp),
        ("X-Frame-Options", "DENY"),
        ("X-Content-Type-Options", "nosniff"),
        ("Referrer-Policy", "no-referrer"),
        ("Cross-Origin-Resource-Policy", "same-origin"),
    ]
