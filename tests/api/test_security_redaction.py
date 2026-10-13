"""Redaction audit (WP13 R1): no path that logs or prints a secret leaks one. The keychain token, the phone token, a
Bearer header and the ?k= value are fakes here. The checks capture stdout, stderr, every roadmap log record and the
real server.log file, and a static scan lists print and log calls whose arguments name a secret."""

import ast
import contextlib
import glob
import io
import logging
import os
import re
import threading
import unittest
from unittest import mock

from roadmap import cli, log
from roadmap.http import security
from roadmap.services import usage
from roadmap.store import paths
from tests.api.support import ServerCase
from tests.unit.test_tunnel_fakes import TunnelCase
from roadmap.services import tunnel

KEYCHAIN_SECRET = "sk-ant-oat01-FAKEKEYCHAINSECRET0123456789"
PHONE_SECRET = "FAKE-PHONE-SECRET-abcdefghijklmnopqrstuvwxyz0123"
REPO_PKG = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "roadmap")


class Capture(logging.Handler):
    """Keeps every record that the roadmap logger tree emits, already formatted."""

    def __init__(self):
        super().__init__(logging.DEBUG)
        self.lines = []

    def emit(self, record):
        self.lines.append(record.getMessage() + " " + " ".join(str(a) for a in (record.args or ())))


class RedactionCase(TunnelCase):
    def setUp(self):
        super().setUp()
        self.capture = Capture()
        root = logging.getLogger("roadmap")
        root.addHandler(self.capture)
        self.addCleanup(root.removeHandler, self.capture)
        self._saved_level = root.level
        root.setLevel(logging.DEBUG)
        self.addCleanup(root.setLevel, self._saved_level)

    def run_cli(self, argv):
        out = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(argv)
        return code, out.getvalue(), err.getvalue()

    def assert_no_secret(self, text, *secrets):
        for secret in secrets:
            self.assertNotIn(secret, text)


class UsageSyncRedaction(RedactionCase):
    def test_successful_sync_prints_and_logs_no_keychain_secret(self):
        payload = {"five_hour": {"utilization": 12, "resets_at": None},
                   "seven_day": {"utilization": 40, "resets_at": None}}
        with mock.patch.object(usage, "read_keychain_token", lambda: KEYCHAIN_SECRET), \
                mock.patch.object(usage, "http_fetch", lambda token: payload):
            code, out, err = self.run_cli(["usage", "sync"])
        self.assertEqual(code, 0)
        self.assert_no_secret(out + err + "\n".join(self.capture.lines), KEYCHAIN_SECRET, "Bearer ")

    def test_failed_endpoint_read_with_the_token_in_its_error_leaks_nothing(self):
        def leaky_fetch(token):
            raise RuntimeError("Authorization: Bearer " + token)

        with mock.patch.object(usage, "read_keychain_token", lambda: KEYCHAIN_SECRET), \
                mock.patch.object(usage, "http_fetch", leaky_fetch):
            code, out, err = self.run_cli(["usage", "sync", "--json"])
        self.assertEqual(code, 6)
        self.assert_no_secret(out + err + "\n".join(self.capture.lines), KEYCHAIN_SECRET, "Bearer")

    def test_keychain_failure_message_leaks_nothing(self):
        def leaky_keychain():
            raise RuntimeError("keychain said " + KEYCHAIN_SECRET)

        with mock.patch.object(usage, "read_keychain_token", leaky_keychain):
            code, out, err = self.run_cli(["usage", "sync"])
        self.assertEqual(code, 6)
        self.assert_no_secret(out + err + "\n".join(self.capture.lines), KEYCHAIN_SECRET)

    def test_background_loop_failure_log_names_the_type_only(self):
        stop = threading.Event()
        calls = []

        def failing():
            calls.append(1)
            if len(calls) > 1:
                stop.set()
            raise RuntimeError("Bearer " + KEYCHAIN_SECRET)

        usage.run_loop(stop, sync=failing, wait=lambda seconds: stop.is_set())
        self.assert_no_secret("\n".join(self.capture.lines), KEYCHAIN_SECRET)


class PhoneStartRedaction(RedactionCase):
    def test_phone_start_stop_link_status_print_no_token_except_the_link(self):
        code, out, err = self.run_cli(["phone", "start"])
        token = tunnel.read_token()
        self.assertEqual(code, 0)
        self.assert_no_secret(out + err + "\n".join(self.capture.lines), token)
        code, out, err = self.run_cli(["phone", "status", "--json"])
        self.assert_no_secret(out + err, token)
        code, out, err = self.run_cli(["phone", "stop", "--json"])
        self.assert_no_secret(out + err + "\n".join(self.capture.lines), token)

    def test_the_link_is_the_only_output_that_carries_the_token(self):
        self.run_cli(["phone", "start"])
        token = tunnel.read_token()
        code, out, err = self.run_cli(["phone", "link"])
        self.assertIn(token, out)
        self.assert_no_secret(err + "\n".join(self.capture.lines), token)

    def test_a_refused_stop_prints_no_token(self):
        self.run_cli(["phone", "start"])
        token = tunnel.read_token()
        self.ssh.table[self.ssh.pid] = "/bin/sleep 9"
        code, out, err = self.run_cli(["phone", "stop", "--json"])
        self.assertEqual(code, 4)
        self.assert_no_secret(out + err + "\n".join(self.capture.lines), token)


class ServerRedaction(ServerCase):
    def assert_no_secret(self, text, *secrets):
        for secret in secrets:
            self.assertNotIn(secret, text)

    def setUp(self):
        super().setUp()
        self.logs = os.path.join(self.tmp, "logs")
        self.server_log = log.setup_file_logging(self.logs)
        root = logging.getLogger("roadmap")
        self.addCleanup(self._drop_file_handlers, root)

    def _drop_file_handlers(self, root):
        for handler in list(root.handlers):
            if getattr(handler, log._FILE_TAG, None):
                root.removeHandler(handler)
                handler.close()

    def test_phone_request_with_k_never_reaches_any_log(self):
        phone = self._start_phone()
        port = phone.server_address[1]
        with self.assertLogs("roadmap", level="DEBUG") as logs:
            self.request("GET", "/api/v1/health?k=" + PHONE_SECRET, port=port)
            self.request("GET", "/?k=" + PHONE_SECRET, port=port)
            self.request("GET", "/nope?k=" + PHONE_SECRET + "&x=1", port=port)
            self.request("GET", "/?k=WRONG-" + PHONE_SECRET, port=port)
        text = "\n".join(record.getMessage() for record in logs.records)
        self.assertGreaterEqual(len(logs.records), 4)
        self.assert_no_secret(text, PHONE_SECRET, "k=", "?")
        with open(self.server_log, encoding="utf-8") as fh:
            self.assert_no_secret(fh.read(), PHONE_SECRET, "k=")

    def test_the_redirect_and_cookie_do_not_carry_the_phone_token(self):
        phone = self._start_phone()
        res = self.request("GET", "/?k=" + PHONE_SECRET, port=phone.server_address[1])
        self.assertEqual(res.status, 302)
        self.assert_no_secret(res.header("location") + res.header("set-cookie"), PHONE_SECRET)

    def test_main_listener_request_with_k_is_logged_without_the_query(self):
        with self.assertLogs("roadmap.http.access", level="INFO") as logs:
            self.request("GET", "/api/v1/health?k=" + PHONE_SECRET)
        self.assert_no_secret("\n".join(r.getMessage() for r in logs.records), PHONE_SECRET, "?k=")

    def test_server_log_file_is_owner_only_and_redacts_bearer_and_keys(self):
        with self.assertLogs("roadmap", level="INFO"):
            logging.getLogger("roadmap.services.usage").warning("Bearer %s and %s", KEYCHAIN_SECRET, KEYCHAIN_SECRET)
        with open(self.server_log, encoding="utf-8") as fh:
            text = fh.read()
        self.assert_no_secret(text, KEYCHAIN_SECRET)
        self.assertEqual(os.stat(self.server_log).st_mode & 0o077, 0)

    def _start_phone(self):
        httpd = self.start_phone_listener()
        return httpd

    def start_phone_listener(self):
        from roadmap.http import server as http_server
        httpd = http_server.make_phone_server(0, token_source=lambda: PHONE_SECRET, tunnel_host=lambda: None,
                                              web_root=self.web, limiter=security.FailureLimiter())
        thread = threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        thread.start()

        def stop():
            httpd.shutdown()
            httpd.server_close()
            thread.join(5)

        self.addCleanup(stop)
        return httpd


SECRET_WORDS = re.compile(r"token|secret|accessToken|keychain|Bearer|sk-ant|\?k=", re.IGNORECASE)
LOG_NAMES = {"debug", "info", "warning", "error", "exception", "critical", "log"}


class StaticAudit(unittest.TestCase):
    """Every print() and logging call in roadmap/ whose arguments name a secret. The list must stay empty, except for
    the help text and the one place that is meant to print the link (commands/phone.py: link)."""

    ALLOWED = {
        # the link command prints the private link on purpose; it names the token in its help text only
        ("roadmap/commands/phone.py", "print"),
    }

    def _sinks(self):
        for path in sorted(glob.glob(os.path.join(REPO_PKG, "**", "*.py"), recursive=True)):
            with open(path, encoding="utf-8") as fh:
                tree = ast.parse(fh.read(), filename=path)
            rel = os.path.relpath(path, os.path.dirname(REPO_PKG)).replace(os.sep, "/")
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if isinstance(func, ast.Name) and func.id == "print":
                    yield rel, "print", node
                elif isinstance(func, ast.Attribute) and func.attr in LOG_NAMES:
                    yield rel, "log", node

    def _names_secret(self, node):
        for sub in ast.walk(node):
            if isinstance(sub, ast.Name) and SECRET_WORDS.search(sub.id):
                return True
            if isinstance(sub, ast.Attribute) and SECRET_WORDS.search(sub.attr):
                return True
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str) and SECRET_WORDS.search(sub.value):
                if sub.value.lower().startswith("phone tunnel") or "token file" in sub.value:
                    continue
                return True
        return False

    def test_no_print_or_log_call_names_a_secret(self):
        found = []
        for rel, kind, node in self._sinks():
            if (rel, kind) in self.ALLOWED:
                continue
            args = list(node.args) + [kw.value for kw in node.keywords]
            if any(self._names_secret(arg) for arg in args):
                found.append("%s:%d (%s)" % (rel, node.lineno, kind))
        self.assertEqual(found, [], "print or log calls that name a secret")

    def test_the_audit_sees_the_sinks_it_is_meant_to_check(self):
        sinks = list(self._sinks())
        self.assertGreater(len([s for s in sinks if s[1] == "log"]), 5)
        self.assertGreater(len([s for s in sinks if s[1] == "print"]), 20)
