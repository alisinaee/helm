"""Shared setup for the API tests: a temporary ROADMAP_HOME, the split-net fixture registered as a project, a real
server on 127.0.0.1 port 0 running in a thread, a raw HTTP client (so Host and headers can be set exactly), and a
stdlib validator for the JSON schemas in tests/api/schemas/. No test touches the network or the keychain: the usage
sync is always a FakeSync."""

import http.client
import json
import os
import shutil
import tempfile
import threading
import unittest

from roadmap.http import server as http_server
from roadmap.store import config as config_store

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
FIXTURE = os.path.join(TESTS, "fixtures", "splitnet")
SCHEMAS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schemas")
REPO_LEGACY = os.path.join(REPO, "web", "legacy.html")
PROJECT_ID = "splitnet"


class FakeSync:
    """Stands in for usage.sync_once. Counts calls; raises error when one is given."""

    def __init__(self, error=None):
        self.calls = 0
        self.error = error

    def __call__(self):
        self.calls += 1
        if self.error is not None:
            raise self.error


class Result:
    def __init__(self, status, headers, body):
        self.status = status
        self.headers = headers
        self.body = body

    def header(self, name):
        return self.headers.get(name.lower())

    def json(self):
        return json.loads(self.body.decode("utf-8"))


def load_schema(name):
    with open(os.path.join(SCHEMAS, name + ".json"), encoding="utf-8") as fh:
        return json.load(fh)


_TYPES = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}


def validate(value, schema, path="$"):
    """A list of problems (empty when valid). Supports type (a name or a list of names), required, properties,
    and items. That is all the schemas in tests/api/schemas use."""
    problems = []
    kinds = schema.get("type")
    if kinds is not None:
        names = kinds if isinstance(kinds, list) else [kinds]
        if not any(_TYPES[name](value) for name in names):
            return [path + ": expected " + "|".join(names) + ", got " + type(value).__name__]
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                problems.append(path + ": missing key '" + key + "'")
        for key, sub in schema.get("properties", {}).items():
            if key in value:
                problems.extend(validate(value[key], sub, path + "." + key))
    if isinstance(value, list) and "items" in schema:
        for index, item in enumerate(value):
            problems.extend(validate(item, schema["items"], "%s[%d]" % (path, index)))
    return problems


class ServerCase(unittest.TestCase):
    """Starts one server per test on port 0, with a temp home that has the fixture registered as project splitnet."""

    def setUp(self):
        self._saved_home = os.environ.get("ROADMAP_HOME")
        self.tmp = tempfile.mkdtemp(prefix="rb-api-")
        self.addCleanup(self._cleanup)
        os.environ["ROADMAP_HOME"] = os.path.join(self.tmp, "home")
        self.project_root = os.path.join(self.tmp, "split_net")
        shutil.copytree(FIXTURE, os.path.join(self.project_root, "docs"))
        config_store.add_project("split-net", self.project_root, project_id=PROJECT_ID)
        self.web = os.path.join(self.tmp, "web")
        os.makedirs(os.path.join(self.web, "css"))
        shutil.copy(REPO_LEGACY, os.path.join(self.web, "legacy.html"))
        self._write(os.path.join(self.web, "index.html"), "<!doctype html><html><head><title>t</title></head>"
                    "<body>index</body></html>\n")
        self._write(os.path.join(self.web, "css", "app.css"), "body{margin:0}\n")
        self._write(os.path.join(self.web, "notes.md"), "not served\n")
        self._write(os.path.join(self.tmp, "secret.txt"), "outside the web root\n")
        self.sync = FakeSync()
        self.httpd = self.start(self.web, self.sync)
        self.port = self.httpd.server_address[1]
        self.token = self.httpd.app.token

    def _cleanup(self):
        if self._saved_home is None:
            os.environ.pop("ROADMAP_HOME", None)
        else:
            os.environ["ROADMAP_HOME"] = self._saved_home
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, path, text):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)

    def start(self, web_root, sync):
        """Start a server on port 0 in a thread. It is shut down at cleanup."""
        httpd = http_server.make_server(0, sync=sync, web_root=web_root)
        thread = threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        thread.start()

        def stop():
            httpd.shutdown()
            httpd.server_close()
            thread.join(5)

        self.addCleanup(stop)
        return httpd

    def request(self, method, path, headers=None, body=None, host=None, port=None):
        """One request with exactly these headers. Host defaults to 127.0.0.1:<port>."""
        use_port = self.port if port is None else port
        sent = {"Host": host or "127.0.0.1:%d" % use_port}
        sent.update(headers or {})
        conn = http.client.HTTPConnection("127.0.0.1", use_port, timeout=10)
        try:
            conn.request(method, path, body=body, headers=sent)
            resp = conn.getresponse()
            data = resp.read()
            return Result(resp.status, {k.lower(): v for k, v in resp.getheaders()}, data)
        finally:
            conn.close()

    def write_headers(self, **extra):
        """The headers of a same-origin JSON write with the CSRF token."""
        base = {"X-Roadmap-CSRF": self.token, "Sec-Fetch-Site": "same-origin", "Content-Type": "application/json"}
        base.update(extra)
        return base

    def assert_schema(self, result, schema_name):
        self.assertEqual(result.status, 200, result.body[:300])
        problems = validate(result.json(), load_schema(schema_name))
        self.assertEqual(problems, [])
