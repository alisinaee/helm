"""Static pages from web/: an allowlist built once at startup. URL paths are only looked up in that map, so they
never reach the filesystem. HTML pages get the per-process CSRF token in a <meta name="csrf"> tag."""

import hashlib
import html
import os
import re
from collections import namedtuple

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
}
LEGACY_FILE = "legacy.html"
INDEX_FILE = "index.html"
_HEAD_RE = re.compile(r"<head[^>]*>", re.IGNORECASE)
Entry = namedtuple("Entry", "path ctype legacy")


class StaticFiles:
    """The allowlist of served files, keyed by URL path. "/" is index.html, or legacy.html while that is missing."""

    def __init__(self, root):
        self.root = os.path.abspath(root)
        self._map = {}
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d != "__pycache__")
            for name in sorted(filenames):
                ext = os.path.splitext(name)[1].lower()
                if name.startswith(".") or ext not in CONTENT_TYPES:
                    continue
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, self.root).replace(os.sep, "/")
                self._map["/" + rel] = Entry(full, CONTENT_TYPES[ext], rel == LEGACY_FILE)
        home = "/" + INDEX_FILE if "/" + INDEX_FILE in self._map else "/" + LEGACY_FILE
        if home in self._map:
            self._map["/"] = self._map[home]

    def paths(self):
        """The allowlisted URL paths, sorted."""
        return sorted(self._map)

    def lookup(self, url_path):
        """The Entry for an exact URL path, or None. No decoding, no normalising: anything not listed is absent."""
        return self._map.get(url_path)

    def render(self, entry, token):
        """The bytes to send for an entry. HTML gets the CSRF meta tag inside <head>."""
        with open(entry.path, "rb") as fh:
            body = fh.read()
        if not entry.ctype.startswith("text/html"):
            return body
        text = body.decode("utf-8")
        tag = '<meta name="csrf" content="%s">' % html.escape(token, quote=True)
        match = _HEAD_RE.search(text)
        if match is None:
            return (tag + text).encode("utf-8")
        return (text[:match.end()] + tag + text[match.end():]).encode("utf-8")


def etag_of(body):
    """A strong ETag for served bytes."""
    return '"%s"' % hashlib.sha256(body).hexdigest()[:32]
