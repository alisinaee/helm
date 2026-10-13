"""Phone listener (127.0.0.1:<phonePort>, read-only): Host and tunnel host (421), GET only (405), token file (503),
wrong token (401), the ?k= redirect with its cookie, the HMAC cookie, the failure limit (429), constant-time comparison
and the headers. A real server on port 0 in a thread; the token and the tunnel host are fakes."""

import hmac
import os
import stat
import threading
import unittest
from unittest import mock

from roadmap.http import security
from roadmap.http import server as http_server
from roadmap.store import paths
from tests.api.support import ServerCase

PHONE_TOKEN = "FAKE-PHONE-TOKEN-0123456789abcdefghijklmnopqrstuvwxyz"
SECURITY_HEADERS = {
    "x-frame-options": "DENY",
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
    "cross-origin-resource-policy": "same-origin",
}


class PhoneCase(ServerCase):
    def setUp(self):
        super().setUp()
        self.phone_token = PHONE_TOKEN
        self.tunnel_host = None
        self.clock = [1000.0]
        self.limiter = security.FailureLimiter(clock=lambda: self.clock[0])
        self.phone = self.start_phone()
        self.phone_port = self.phone.server_address[1]

    def start_phone(self, token_source=None, limiter=None):
        httpd = http_server.make_phone_server(
            0,
            token_source=token_source or (lambda: self.phone_token),
            tunnel_host=lambda: self.tunnel_host,
            web_root=self.web,
            limiter=limiter or self.limiter,
        )
        thread = threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        thread.start()

        def stop():
            httpd.shutdown()
            httpd.server_close()
            thread.join(5)

        self.addCleanup(stop)
        return httpd

    def phone_get(self, path, cookie=None, host=None, headers=None):
        sent = dict(headers or {})
        if cookie is not None:
            sent["Cookie"] = "%s=%s" % (security.PHONE_COOKIE, cookie)
        return self.request("GET", path, headers=sent, host=host, port=self.phone_port)

    def good_cookie(self):
        return security.cookie_value(self.phone_token)


class HostRules(PhoneCase):
    def test_foreign_host_is_421_even_with_the_token(self):
        res = self.request("GET", "/?k=" + PHONE_TOKEN, host="evil.example:%d" % self.phone_port,
                           port=self.phone_port)
        self.assertEqual(res.status, 421)
        self.assertEqual(res.json()["error"]["code"], "misdirected_request")

    def test_loopback_names_on_the_phone_port_are_allowed(self):
        self.assertEqual(self.phone_get("/?k=" + PHONE_TOKEN).status, 302)
        res = self.request("GET", "/?k=" + PHONE_TOKEN, host="localhost:%d" % self.phone_port, port=self.phone_port)
        self.assertEqual(res.status, 302)

    def test_tunnel_host_is_accepted_only_when_configured(self):
        self.assertEqual(self.phone_get("/?k=" + PHONE_TOKEN, host="abc123.lhr.life").status, 421)
        self.tunnel_host = "abc123.lhr.life"
        self.assertEqual(self.phone_get("/?k=" + PHONE_TOKEN, host="abc123.lhr.life").status, 302)
        self.assertEqual(self.phone_get("/?k=" + PHONE_TOKEN, host="abc123.lhr.life:443").status, 302)
        self.assertEqual(self.phone_get("/?k=" + PHONE_TOKEN, host="other.lhr.life").status, 421)
        self.assertEqual(self.phone_get("/?k=" + PHONE_TOKEN, host="x.abc123.lhr.life").status, 421)

    def test_an_invalid_configured_tunnel_host_allows_nothing(self):
        self.tunnel_host = "https://abc123.lhr.life/path"
        self.assertEqual(self.phone_get("/?k=" + PHONE_TOKEN, host="https://abc123.lhr.life/path").status, 421)


class ReadOnly(PhoneCase):
    def test_post_is_405_even_with_the_cookie_and_the_write_headers(self):
        headers = self.write_headers(Cookie="%s=%s" % (security.PHONE_COOKIE, self.good_cookie()))
        res = self.request("POST", "/api/v1/usage/sync", headers=headers, body=b"{}", port=self.phone_port)
        self.assertEqual(res.status, 405)
        self.assertEqual(res.header("allow"), "GET, HEAD")
        self.assertEqual(self.sync.calls, 0)

    def test_post_without_any_token_is_still_405_not_401(self):
        res = self.request("POST", "/api/v1/usage/sync", headers=self.write_headers(), body=b"{}",
                           port=self.phone_port)
        self.assertEqual(res.status, 405)

    def test_get_routes_work_with_the_cookie(self):
        self.assertEqual(self.phone_get("/api/v1/health", cookie=self.good_cookie()).status, 200)
        self.assertEqual(self.phone_get("/api/v1/projects", cookie=self.good_cookie()).status, 200)
        self.assertEqual(self.phone_get("/css/app.css", cookie=self.good_cookie()).status, 200)

    def test_the_phone_page_carries_no_csrf_token_of_the_main_listener(self):
        res = self.phone_get("/", cookie=self.good_cookie())
        self.assertEqual(res.status, 200)
        self.assertNotIn(self.token.encode(), res.body)
        self.assertIn(b'<meta name="csrf" content="">', res.body)


class TokenFile(PhoneCase):
    def test_no_token_is_503_for_every_request(self):
        self.phone_token = None
        self.assertEqual(self.phone_get("/?k=" + PHONE_TOKEN).status, 503)
        self.assertEqual(self.phone_get("/api/v1/health").status, 503)
        self.assertEqual(self.phone_get("/api/v1/health").json()["error"]["code"], "phone_off")

    def test_default_token_source_reads_phone_token_and_503_when_missing(self):
        httpd = self.start_phone(token_source=http_server.read_phone_token)
        port = httpd.server_address[1]
        self.assertEqual(self.request("GET", "/?k=x", port=port).status, 503)
        path = paths.phone_token_file()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(PHONE_TOKEN + "\n")
        os.chmod(path, 0o600)
        self.assertEqual(self.request("GET", "/?k=" + PHONE_TOKEN, port=port).status, 302)

    def test_a_token_file_readable_by_others_is_not_used(self):
        path = paths.phone_token_file()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(PHONE_TOKEN)
        os.chmod(path, 0o644)
        self.assertIsNone(http_server.read_phone_token())
        os.chmod(path, 0o600)
        self.assertEqual(http_server.read_phone_token(), PHONE_TOKEN)
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)


class Auth(PhoneCase):
    def test_wrong_token_and_no_token_are_401(self):
        for path in ("/?k=WRONG", "/api/v1/health?k=", "/api/v1/health"):
            with self.subTest(path=path):
                res = self.phone_get(path)
                self.assertEqual(res.status, 401)
                self.assertEqual(res.json()["error"]["code"], "unauthorized")

    def test_a_repeated_k_is_refused(self):
        self.assertEqual(self.phone_get("/?k=%s&k=%s" % (PHONE_TOKEN, PHONE_TOKEN)).status, 401)

    def test_token_redirect_strips_k_keeps_other_params_and_sets_the_cookie(self):
        res = self.phone_get("/css/app.css?x=1&k=" + PHONE_TOKEN)
        self.assertEqual(res.status, 302)
        self.assertEqual(res.header("location"), "/css/app.css?x=1")
        cookie = res.header("set-cookie")
        for flag in ("HttpOnly", "Secure", "SameSite=Strict", "Path=/", "Max-Age=604800"):
            self.assertIn(flag, cookie)
        self.assertIn("rb_phone=" + self.good_cookie() + ";", cookie)

    def test_redirect_to_root_when_only_k_was_given(self):
        self.assertEqual(self.phone_get("/?k=" + PHONE_TOKEN).header("location"), "/")

    def test_the_raw_token_never_appears_in_the_cookie_or_the_location(self):
        res = self.phone_get("/?k=" + PHONE_TOKEN)
        self.assertNotIn(PHONE_TOKEN, res.header("set-cookie"))
        self.assertNotIn(PHONE_TOKEN, res.header("location"))
        self.assertNotEqual(security.cookie_value(PHONE_TOKEN), PHONE_TOKEN)

    def test_cookie_value_is_hmac_of_cookie_keyed_with_the_token(self):
        expected = hmac.new(PHONE_TOKEN.encode(), b"cookie", "sha256").hexdigest()
        self.assertEqual(security.cookie_value(PHONE_TOKEN), expected)
        self.assertEqual(len(expected), 64)

    def test_the_hmac_cookie_grants_access_and_the_raw_token_as_cookie_does_not(self):
        self.assertEqual(self.phone_get("/api/v1/health", cookie=self.good_cookie()).status, 200)
        self.assertEqual(self.phone_get("/api/v1/health", cookie=PHONE_TOKEN).status, 401)

    def test_a_rotated_token_invalidates_old_cookies(self):
        old = self.good_cookie()
        self.phone_token = "ROTATED-" + PHONE_TOKEN
        self.assertEqual(self.phone_get("/api/v1/health", cookie=old).status, 401)

    def test_cookie_header_is_read_among_other_cookies(self):
        res = self.phone_get("/api/v1/health", headers={"Cookie": "a=1; rb_phone=%s; b=2" % self.good_cookie()})
        self.assertEqual(res.status, 200)

    def test_redirect_path_never_becomes_a_foreign_host(self):
        res = self.phone_get("//evil.example/?k=" + PHONE_TOKEN)
        self.assertEqual(res.status, 302)
        self.assertEqual(res.header("location"), "/")


class RateLimit(PhoneCase):
    def test_ten_failures_in_a_minute_then_429_even_for_the_right_token(self):
        for _ in range(10):
            self.assertEqual(self.phone_get("/?k=WRONG").status, 401)
        res = self.phone_get("/?k=" + PHONE_TOKEN)
        self.assertEqual(res.status, 429)
        self.assertEqual(res.json()["error"]["code"], "rate_limited")
        self.assertGreaterEqual(int(res.header("retry-after")), 1)

    def test_the_window_slides_and_access_comes_back_after_a_minute(self):
        for _ in range(10):
            self.phone_get("/?k=WRONG")
        self.clock[0] += 61
        self.assertEqual(self.phone_get("/?k=" + PHONE_TOKEN).status, 302)

    def test_nine_failures_do_not_block(self):
        for _ in range(9):
            self.assertEqual(self.phone_get("/?k=WRONG").status, 401)
        self.assertEqual(self.phone_get("/?k=" + PHONE_TOKEN).status, 302)

    def test_the_limiter_counts_per_instance_and_only_failures(self):
        limiter = security.FailureLimiter(limit=2, window_s=60, clock=lambda: self.clock[0])
        self.assertFalse(limiter.blocked())
        limiter.record_failure()
        limiter.record_failure()
        self.assertTrue(limiter.blocked())
        self.assertEqual(limiter.retry_after_s(), 61)
        self.clock[0] += 60
        self.assertFalse(limiter.blocked())


class ConstantTime(PhoneCase):
    def test_hmac_compare_digest_is_used_for_the_token_and_the_cookie(self):
        real = hmac.compare_digest
        with mock.patch("hmac.compare_digest", wraps=real) as spy:
            self.phone_get("/?k=WRONG")
            self.assertGreaterEqual(spy.call_count, 1)
            spy.reset_mock()
            self.phone_get("/api/v1/health", cookie=self.good_cookie())
            self.assertGreaterEqual(spy.call_count, 1)

    def test_safe_equal_never_matches_an_empty_expected_value(self):
        self.assertFalse(security.safe_equal("", ""))
        self.assertFalse(security.safe_equal(None, "abc"))
        self.assertTrue(security.safe_equal("abc", "abc"))


class Headers(PhoneCase):
    def test_every_phone_reply_carries_the_csp_and_security_headers(self):
        cases = [
            ("GET", "/?k=" + PHONE_TOKEN, None, None),
            ("GET", "/api/v1/health", None, None),
            ("GET", "/api/v1/health", None, "evil.example"),
            ("POST", "/api/v1/usage/sync", None, None),
            ("GET", "/no/such", None, None),
            ("GET", "/api/v1/health?k=WRONG", None, None),
        ]
        for method, path, cookie, host in cases:
            with self.subTest(method=method, path=path, host=host):
                res = self.request(method, path, host=host and host + ":%d" % self.phone_port,
                                   headers={"Cookie": "rb_phone=" + self.good_cookie()} if cookie else None,
                                   port=self.phone_port)
                self.assertIn("default-src 'self'", res.header("Content-Security-Policy"))
                self.assertIn("frame-ancestors 'none'", res.header("Content-Security-Policy"))
                self.assertNotIn("unsafe-inline", res.header("Content-Security-Policy"))
                for name, value in SECURITY_HEADERS.items():
                    self.assertEqual(res.header(name), value)

    def test_429_and_503_also_carry_the_headers(self):
        self.phone_token = None
        res = self.phone_get("/")
        self.assertEqual(res.status, 503)
        self.assertEqual(res.header("x-frame-options"), "DENY")
        self.assertEqual(res.header("referrer-policy"), "no-referrer")
        self.phone_token = PHONE_TOKEN
        for _ in range(10):
            self.phone_get("/?k=WRONG")
        res = self.phone_get("/")
        self.assertEqual(res.status, 429)
        self.assertEqual(res.header("x-content-type-options"), "nosniff")
        self.assertEqual(res.header("cross-origin-resource-policy"), "same-origin")
