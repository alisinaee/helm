"""Security: Host allowlist (421), CSRF and same-site checks (403), content type (415), body size (413), and the
headers on every response."""

import os

from tests.api.support import FakeSync, ServerCase

SECURITY_HEADERS = {
    "x-frame-options": "DENY",
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
    "cross-origin-resource-policy": "same-origin",
}


class HostAllowlist(ServerCase):
    def test_foreign_host_is_421_everywhere(self):
        for method, path in (("GET", "/api/v1/health"), ("GET", "/"), ("GET", "/data.json"),
                             ("POST", "/api/v1/usage/sync")):
            with self.subTest(method=method, path=path):
                res = self.request(method, path, host="evil.example:%d" % self.port,
                                   headers=self.write_headers(), body=b"{}")
                self.assertEqual(res.status, 421)
                self.assertEqual(res.json()["error"]["code"], "misdirected_request")
        self.assertEqual(self.sync.calls, 0)

    def test_rebinding_name_and_wrong_port_are_421(self):
        self.assertEqual(self.request("GET", "/api/v1/health", host="127.0.0.1").status, 421)
        self.assertEqual(self.request("GET", "/api/v1/health", host="127.0.0.1:1").status, 421)
        self.assertEqual(self.request("GET", "/api/v1/health", host="example.com:%d" % self.port).status, 421)

    def test_localhost_and_loopback_are_allowed(self):
        self.assertEqual(self.request("GET", "/api/v1/health", host="localhost:%d" % self.port).status, 200)
        self.assertEqual(self.request("GET", "/api/v1/health", host="127.0.0.1:%d" % self.port).status, 200)


class WriteChecks(ServerCase):
    def test_no_csrf_header_is_403(self):
        headers = self.write_headers()
        del headers["X-Roadmap-CSRF"]
        res = self.request("POST", "/api/v1/usage/sync", headers=headers, body=b"{}")
        self.assertEqual(res.status, 403)
        self.assertEqual(self.sync.calls, 0)

    def test_wrong_csrf_is_403(self):
        res = self.request("POST", "/api/v1/usage/sync", headers=self.write_headers(**{"X-Roadmap-CSRF": "nope"}),
                           body=b"{}")
        self.assertEqual(res.status, 403)
        self.assertEqual(self.sync.calls, 0)

    def test_cross_site_is_403_even_with_the_token(self):
        for value in ("cross-site", "same-site", "none"):
            with self.subTest(sec_fetch_site=value):
                res = self.request("POST", "/api/v1/usage/sync",
                                   headers=self.write_headers(**{"Sec-Fetch-Site": value}), body=b"{}")
                self.assertEqual(res.status, 403)
        self.assertEqual(self.sync.calls, 0)

    def test_foreign_origin_is_403(self):
        headers = self.write_headers(Origin="http://evil.example")
        self.assertEqual(self.request("POST", "/api/v1/usage/sync", headers=headers, body=b"{}").status, 403)
        self.assertEqual(self.sync.calls, 0)

    def test_origin_of_this_server_is_accepted_without_sec_fetch_site(self):
        headers = self.write_headers(Origin="http://127.0.0.1:%d" % self.port)
        del headers["Sec-Fetch-Site"]
        self.assertEqual(self.request("POST", "/api/v1/usage/sync", headers=headers, body=b"{}").status, 200)
        self.assertEqual(self.sync.calls, 1)

    def test_no_sec_fetch_site_and_no_origin_is_403(self):
        headers = self.write_headers()
        del headers["Sec-Fetch-Site"]
        self.assertEqual(self.request("POST", "/api/v1/usage/sync", headers=headers, body=b"{}").status, 403)

    def test_good_write_passes(self):
        res = self.request("POST", "/api/v1/usage/sync", headers=self.write_headers(), body=b"{}")
        self.assertEqual(res.status, 200)
        self.assertEqual(self.sync.calls, 1)

    def test_wrong_content_type_is_415(self):
        res = self.request("POST", "/api/v1/usage/sync",
                           headers=self.write_headers(**{"Content-Type": "text/plain"}), body=b"{}")
        self.assertEqual(res.status, 415)
        self.assertEqual(self.sync.calls, 0)

    def test_body_over_4_kb_is_413_before_anything_runs(self):
        body = b'{"pad":"' + b"x" * 5000 + b'"}'
        res = self.request("POST", "/api/v1/usage/sync", headers=self.write_headers(), body=body)
        self.assertEqual(res.status, 413)
        self.assertEqual(res.json()["error"]["code"], "too_large")
        self.assertEqual(self.sync.calls, 0)

    def test_body_that_is_not_json_is_400(self):
        res = self.request("POST", "/api/v1/usage/sync", headers=self.write_headers(), body=b"not json")
        self.assertEqual(res.status, 400)
        self.assertEqual(self.sync.calls, 0)

    def test_body_that_is_json_but_not_an_object_is_400(self):
        res = self.request("POST", "/api/v1/usage/sync", headers=self.write_headers(), body=b"[1,2]")
        self.assertEqual(res.status, 400)
        self.assertEqual(self.sync.calls, 0)


class Headers(ServerCase):
    def test_every_response_carries_the_security_headers(self):
        cases = [
            ("GET", "/api/v1/health", {}, None),
            ("GET", "/", {}, None),
            ("GET", "/css/app.css", {}, None),
            ("GET", "/no/such/page", {}, None),
            ("POST", "/api/v1/health", {}, None),
            ("GET", "/api/v1/health", {}, "evil.example"),
            ("POST", "/api/v1/usage/sync", {"X-Roadmap-CSRF": "bad"}, None),
        ]
        for method, path, headers, host in cases:
            with self.subTest(method=method, path=path, host=host):
                res = self.request(method, path, headers=headers, body=b"{}" if method == "POST" else None,
                                   host=host and host + ":%d" % self.port)
                self.assertIn("default-src 'self'", res.header("Content-Security-Policy"))
                for name, value in SECURITY_HEADERS.items():
                    self.assertEqual(res.header(name), value)

    def test_csp_has_the_required_directives(self):
        csp = self.request("GET", "/api/v1/health").header("Content-Security-Policy")
        for directive in ("script-src 'self'", "style-src 'self'", "connect-src 'self'", "img-src 'self' data:",
                          "frame-ancestors 'none'", "base-uri 'none'", "form-action 'none'"):
            self.assertIn(directive, csp)
        self.assertNotIn("unsafe-inline", csp)

    def test_error_responses_are_json_envelopes(self):
        res = self.request("GET", "/api/v1/nope")
        self.assertEqual(res.status, 404)
        self.assertEqual(res.header("content-type"), "application/json; charset=utf-8")
        self.assertEqual(sorted(res.json()), ["error"])
