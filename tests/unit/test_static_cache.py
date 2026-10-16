"""Static files revalidate: every static reply says no-cache, carries a strong content ETag, and a 304 comes only when
If-None-Match names the current ETag. After a file edit the browser gets the new bytes, never a stale 304 or a
cached copy (R10.17: a service restart must show the new web code)."""

import os
import re

from tests.api.support import ServerCase

STRONG_ETAG = re.compile(r'^"[0-9a-f]{32}"$')


class StaticRevalidation(ServerCase):
    def _js(self, text):
        """Writes web/app.js and restarts the test server, since the allowlist is built when a server starts."""
        path = os.path.join(self.web, "app.js")
        self._write(path, text)
        self.httpd = self.start(self.web, self.sync)
        self.port = self.httpd.server_address[1]
        self.token = self.httpd.app.token
        return path

    def test_static_files_are_no_cache_with_a_strong_etag(self):
        self._js("export const v = 1;\n")
        for path in ("/app.js", "/css/app.css", "/index.html"):
            with self.subTest(path=path):
                res = self.request("GET", path)
                self.assertEqual(res.status, 200)
                self.assertEqual(res.header("cache-control"), "no-cache")
                self.assertRegex(res.header("etag"), STRONG_ETAG)

    def test_edited_js_gets_a_new_etag_and_the_new_bytes(self):
        path = self._js("export const v = 1;\n")
        old = self.request("GET", "/app.js").header("etag")
        self._write(path, "export const v = 2;\n")
        res = self.request("GET", "/app.js", headers={"If-None-Match": old})
        self.assertEqual(res.status, 200)
        self.assertNotEqual(res.header("etag"), old)
        self.assertIn(b"v = 2", res.body)

    def test_304_only_when_the_etag_matches(self):
        self._js("export const v = 1;\n")
        current = self.request("GET", "/app.js").header("etag")
        same = self.request("GET", "/app.js", headers={"If-None-Match": current})
        self.assertEqual(same.status, 304)
        self.assertEqual(same.body, b"")
        weak = self.request("GET", "/app.js", headers={"If-None-Match": "W/" + current})
        self.assertEqual(weak.status, 304)
        other = self.request("GET", "/app.js", headers={"If-None-Match": '"%s"' % ("0" * 32)})
        self.assertEqual(other.status, 200)
        self.assertIn(b"v = 1", other.body)

    def test_stale_etag_on_an_edited_css_gets_200_with_the_new_css(self):
        old = self.request("GET", "/css/app.css").header("etag")
        self._write(os.path.join(self.web, "css", "app.css"), "body{margin:4px}\n")
        res = self.request("GET", "/css/app.css", headers={"If-None-Match": old})
        self.assertEqual(res.status, 200)
        self.assertIn(b"margin:4px", res.body)
        self.assertEqual(res.header("cache-control"), "no-cache")

    def test_index_etag_follows_its_content(self):
        old = self.request("GET", "/").header("etag")
        self._write(os.path.join(self.web, "index.html"),
                    "<!doctype html><html><head><title>t2</title></head><body>new</body></html>\n")
        res = self.request("GET", "/", headers={"If-None-Match": old})
        self.assertEqual(res.status, 200)
        self.assertIn(b"new", res.body)
        self.assertNotEqual(res.header("etag"), old)
