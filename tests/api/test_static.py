"""Static pages: the allowlist, traversal refusals, MIME types, the CSRF meta tag, the index and legacy fallback,
and the CSP exception that only legacy.html gets."""

import os
import shutil
import tempfile
import unittest

from roadmap.http.static import StaticFiles
from tests.api.support import REPO_LEGACY, ServerCase


class Allowlist(ServerCase):
    def test_listed_files_are_served_with_their_mime_type(self):
        css = self.request("GET", "/css/app.css")
        self.assertEqual(css.status, 200)
        self.assertEqual(css.header("content-type"), "text/css; charset=utf-8")
        self.assertIn(b"margin", css.body)

    def test_unlisted_extension_is_404(self):
        self.assertEqual(self.request("GET", "/notes.md").status, 404)

    def test_traversal_and_odd_paths_are_404(self):
        for path in ("/../secret.txt", "/..%2fsecret.txt", "/%2e%2e/secret.txt", "/%2e%2e%2fsecret.txt",
                     "/css/%2e%2e/index.html", "/css/../index.html", "//index.html", "/css//app.css",
                     "/css/app.css/", "/secret.txt", "/./css/app.css", "/css%2fapp.css", "/%00"):
            with self.subTest(path=path):
                self.assertEqual(self.request("GET", path).status, 404)

    def test_static_pages_take_get_only(self):
        res = self.request("POST", "/css/app.css", headers=self.write_headers(), body=b"{}")
        self.assertEqual(res.status, 405)
        self.assertEqual(res.header("Allow"), "GET, HEAD")

    def test_head_has_headers_and_no_body(self):
        res = self.request("HEAD", "/css/app.css")
        self.assertEqual(res.status, 200)
        self.assertEqual(res.body, b"")
        self.assertIsNotNone(res.header("etag"))


class Index(ServerCase):
    def test_slash_is_index_html_with_the_csrf_meta_tag(self):
        res = self.request("GET", "/")
        self.assertEqual(res.status, 200)
        self.assertIn(b"<title>t</title>", res.body)
        meta = '<meta name="csrf" content="%s">' % self.token
        self.assertIn(meta.encode("utf-8"), res.body)
        self.assertEqual(res.header("content-type"), "text/html; charset=utf-8")

    def test_index_gets_the_strict_csp_without_unsafe_inline(self):
        csp = self.request("GET", "/").header("Content-Security-Policy")
        self.assertNotIn("unsafe-inline", csp)
        self.assertIn("script-src 'self';", csp)

    def test_legacy_page_gets_the_only_csp_exception(self):
        legacy = self.request("GET", "/legacy.html")
        self.assertEqual(legacy.status, 200)
        self.assertIn("'unsafe-inline'", legacy.header("Content-Security-Policy"))
        self.assertIn(b'<meta name="csrf" content="%s">' % self.token.encode("utf-8"), legacy.body)
        self.assertNotIn("unsafe-inline", self.request("GET", "/css/app.css").header("Content-Security-Policy"))

    def test_slash_falls_back_to_legacy_when_there_is_no_index(self):
        bare = os.path.join(self.tmp, "bare")
        os.makedirs(bare)
        shutil.copy(REPO_LEGACY, os.path.join(bare, "legacy.html"))
        httpd = self.start(bare, self.sync)
        res = self.request("GET", "/", port=httpd.server_address[1])
        self.assertEqual(res.status, 200)
        self.assertIn("'unsafe-inline'", res.header("Content-Security-Policy"))
        self.assertIn(b"Usage", res.body)

    def test_etag_304_for_static(self):
        first = self.request("GET", "/css/app.css").header("ETag")
        res = self.request("GET", "/css/app.css", headers={"If-None-Match": first})
        self.assertEqual(res.status, 304)
        self.assertEqual(res.body, b"")


class SymlinksInWebRoot(unittest.TestCase):
    def test_a_symlink_whose_real_file_is_outside_web_is_not_served(self):
        tmp = tempfile.mkdtemp(prefix="rb-static-")
        self.addCleanup(shutil.rmtree, tmp)
        web = os.path.join(tmp, "web")
        os.makedirs(web)
        secret = os.path.join(tmp, "token.txt")
        with open(secret, "w", encoding="utf-8") as fh:
            fh.write("k=secret\n")
        inside = os.path.join(web, "real.txt")
        with open(inside, "w", encoding="utf-8") as fh:
            fh.write("inside\n")
        os.symlink(secret, os.path.join(web, "note.txt"))
        os.symlink(inside, os.path.join(web, "alias.txt"))
        files = StaticFiles(web)
        self.assertIsNone(files.lookup("/note.txt"))
        self.assertEqual(files.lookup("/alias.txt").path, os.path.realpath(inside))
